"""Authoritative Delivery state machine implementing protocol DEL-01 to DEL-12."""
from __future__ import annotations

from enum import Enum
import json
import sqlite3
import time
from typing import Any, Dict, List, Optional, Tuple

from src.conversation.contract import (
    ControlEvent,
    ControlEventKind,
    DeliveryEventType,
    DeliveryMode,
    DeliveryPayload,
)
from src.conversation.errors import ErrorCode, ConversationCoreException


class DeliveryAckStatus(str, Enum):
    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    IGNORED = "ignored"
    REJECTED = "rejected"


class DeliveryAck:
    def __init__(
        self,
        status: DeliveryAckStatus,
        reason: str,
        presentation_event_id: Optional[str] = None,
        eligible: bool = False,
    ):
        self.status = status
        self.reason = reason
        self.presentation_event_id = presentation_event_id
        self.eligible = eligible

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "reason": self.reason,
            "presentation_event_id": self.presentation_event_id,
            "eligible": self.eligible,
        }


class DeliveryTracker:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def process_delivery_event(self, event: ControlEvent) -> DeliveryAck:
        """Process delivery ControlEvent according to authoritative protocol DEL-01..12."""
        if event.kind != ControlEventKind.DELIVERY:
            return DeliveryAck(DeliveryAckStatus.REJECTED, "not_a_delivery_event")

        payload = DeliveryPayload.model_validate(event.payload)
        now = time.time()

        # 1. Look up response
        resp_row = self.conn.execute(
            "SELECT * FROM core_responses WHERE response_id = ? AND request_id = ?",
            (payload.response_id, event.request_id),
        ).fetchone()
        if resp_row is None:
            return DeliveryAck(DeliveryAckStatus.REJECTED, "unknown_response")

        # 2. Check session and owner generation
        req_row = self.conn.execute(
            "SELECT * FROM core_requests WHERE request_id = ?", (event.request_id,)
        ).fetchone()
        if req_row is None:
            return DeliveryAck(DeliveryAckStatus.REJECTED, "unknown_request")

        if event.trusted.owner_generation < req_row["owner_generation"]:
            return DeliveryAck(DeliveryAckStatus.IGNORED, "stale_generation")

        if req_row["owner_session_id"] != event.session_id:
            return DeliveryAck(DeliveryAckStatus.IGNORED, "wrong_session")

        # 3. Handle Voice vs Text Mode
        if payload.mode == DeliveryMode.VOICE:
            playback_id = payload.playback_id
            if not playback_id:
                return DeliveryAck(DeliveryAckStatus.REJECTED, "missing_playback_id")

            # Check or create presentation row
            row = self.conn.execute(
                "SELECT * FROM core_presentations WHERE playback_id = ?", (playback_id,)
            ).fetchone()

            if row is None:
                # Must be started or text
                self.conn.execute(
                    """INSERT INTO core_presentations (
                        playback_id, response_id, request_id, session_id,
                        owner_generation, transport, phase, required_segment_ids_json,
                        created_at_utc
                       ) VALUES (?, ?, ?, ?, ?, 'voice', 'prepared', ?, ?)""",
                    (
                        playback_id,
                        payload.response_id,
                        event.request_id,
                        event.session_id,
                        event.trusted.owner_generation,
                        json.dumps([payload.segment_id]),
                        now,
                    ),
                )
                row = self.conn.execute(
                    "SELECT * FROM core_presentations WHERE playback_id = ?", (playback_id,)
                ).fetchone()

            current_phase = row["phase"]
            if current_phase in ("interrupted", "failed"):
                # DEL-04: Late completion/ACK cannot revive interrupted attempt
                return DeliveryAck(
                    DeliveryAckStatus.IGNORED,
                    "attempt_terminal",
                    presentation_event_id=event.input_id,
                    eligible=False,
                )

            # Process voice event types
            if payload.event_type == DeliveryEventType.PLAYBACK_STARTED:
                self.conn.execute(
                    "UPDATE core_presentations SET phase = 'sent' WHERE playback_id = ?",
                    (playback_id,),
                )
                return DeliveryAck(
                    DeliveryAckStatus.ACCEPTED,
                    "recorded",
                    presentation_event_id=event.input_id,
                    eligible=False,
                )

            elif payload.event_type == DeliveryEventType.PLAYBACK_INTERRUPTED:
                self.conn.execute(
                    "UPDATE core_presentations SET phase = 'interrupted' WHERE playback_id = ?",
                    (playback_id,),
                )
                return DeliveryAck(
                    DeliveryAckStatus.ACCEPTED,
                    "interrupted",
                    presentation_event_id=event.input_id,
                    eligible=False,
                )

            elif payload.event_type in (DeliveryEventType.PLAYBACK_FAILED, DeliveryEventType.OUTPUT_UNAVAILABLE):
                self.conn.execute(
                    "UPDATE core_presentations SET phase = 'failed' WHERE playback_id = ?",
                    (playback_id,),
                )
                return DeliveryAck(
                    DeliveryAckStatus.ACCEPTED,
                    "failed",
                    presentation_event_id=event.input_id,
                    eligible=False,
                )

            elif payload.event_type == DeliveryEventType.PLAYBACK_COMPLETED:
                self.conn.execute(
                    "UPDATE core_presentations SET server_completed_at_utc = ? WHERE playback_id = ?",
                    (now, playback_id),
                )

            elif payload.event_type == DeliveryEventType.OUTPUT_AVAILABLE:
                self.conn.execute(
                    "UPDATE core_presentations SET client_output_available_ack_at_utc = ? WHERE playback_id = ?",
                    (now, playback_id),
                )

            # Refresh row to check eligibility (DEL-01, DEL-02: requires BOTH completed AND output_available ACK)
            updated = self.conn.execute(
                "SELECT * FROM core_presentations WHERE playback_id = ?", (playback_id,)
            ).fetchone()

            is_eligible = bool(
                updated["server_completed_at_utc"] is not None
                and updated["client_output_available_ack_at_utc"] is not None
                and updated["phase"] not in ("interrupted", "failed")
            )

            if is_eligible and updated["phase"] != "completed":
                self.conn.execute(
                    "UPDATE core_presentations SET phase = 'completed' WHERE playback_id = ?",
                    (playback_id,),
                )

            return DeliveryAck(
                DeliveryAckStatus.ACCEPTED,
                "recorded",
                presentation_event_id=event.input_id,
                eligible=is_eligible,
            )

        else:
            # Text Mode (WEB / CLI)
            playback_id = f"text-{event.input_id}"
            existing = self.conn.execute(
                "SELECT * FROM core_presentations WHERE playback_id = ?", (playback_id,)
            ).fetchone()
            if existing is not None:
                return DeliveryAck(
                    DeliveryAckStatus.DUPLICATE,
                    "duplicate",
                    presentation_event_id=event.input_id,
                    eligible=True,
                )

            self.conn.execute(
                """INSERT INTO core_presentations (
                    playback_id, response_id, request_id, session_id,
                    owner_generation, transport, phase, required_segment_ids_json,
                    text_presented_at_utc, created_at_utc
                   ) VALUES (?, ?, ?, ?, ?, 'text', 'completed', ?, ?, ?)""",
                (
                    playback_id,
                    payload.response_id,
                    event.request_id,
                    event.session_id,
                    event.trusted.owner_generation,
                    json.dumps([payload.segment_id]),
                    now,
                    now,
                ),
            )
            return DeliveryAck(
                DeliveryAckStatus.ACCEPTED,
                "recorded",
                presentation_event_id=event.input_id,
                eligible=True,
            )

    def is_question_eligible(self, request_id: str, question_id: str) -> bool:
        """Check if offered question segment has achieved authoritative delivery eligibility."""
        # Find offered response for this question
        offer_row = self.conn.execute(
            "SELECT * FROM core_question_offers WHERE question_id = ? AND request_id = ?",
            (question_id, request_id),
        ).fetchone()
        if offer_row is None:
            return False

        # Find presentations for this response
        pres_rows = self.conn.execute(
            "SELECT * FROM core_presentations WHERE response_id = ? AND request_id = ?",
            (offer_row["response_id"], request_id),
        ).fetchall()

        for pres in pres_rows:
            if pres["transport"] == "text" and pres["phase"] == "completed":
                return True
            if (
                pres["transport"] == "voice"
                and pres["phase"] == "completed"
                and pres["server_completed_at_utc"] is not None
                and pres["client_output_available_ack_at_utc"] is not None
            ):
                return True
        return False
