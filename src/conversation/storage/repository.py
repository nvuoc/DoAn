"""Authoritative SQLite repository for vanuoc conversation core."""
from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Dict, List, Optional, Tuple

from src.conversation.contract import (
    TurnInput,
    TurnResult,
    TurnStatus,
    BookingStatus,
    ControlEvent,
)
from src.conversation.domain.models import (
    BookingDraft,
    ConversationAggregate,
    ConversationState,
    LocationEvidence,
)
from src.conversation.errors import ErrorCode, ConversationCoreException


class StorageRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get_or_create_session(
        self, session_id: str, channel: str = "cli", auth_scope_ref: str = "default_auth"
    ) -> sqlite3.Row:
        row = self.conn.execute(
            "SELECT * FROM core_sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row is None:
            now = time.time()
            self.conn.execute(
                """INSERT INTO core_sessions (session_id, channel, auth_scope_ref, lifecycle, created_at_utc)
                   VALUES (?, ?, ?, 'active', ?)""",
                (session_id, channel, auth_scope_ref, now),
            )
            row = self.conn.execute(
                "SELECT * FROM core_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        return row

    def get_or_create_request(
        self,
        request_id: str,
        session_id: str,
        engine_id: str = "vanuoc_v3",
        engine_revision: str = "3.0.0",
        state_schema_version: int = 1,
        pinned_bundle: Optional[Dict[str, Any]] = None,
        initial_owner_generation: int = 1,
    ) -> sqlite3.Row:
        row = self.conn.execute(
            "SELECT * FROM core_requests WHERE request_id = ?", (request_id,)
        ).fetchone()
        if row is None:
            now = time.time()
            bundle_json = json.dumps(pinned_bundle or {"policy_version": "development_conservative_3_0"})
            conv_json = json.dumps({})
            self.conn.execute(
                """INSERT INTO core_requests (
                    request_id, engine_id, engine_revision, state_schema_version,
                    pinned_bundle_json, owner_kind, owner_session_id, owner_generation,
                    state_version, booking_status, conversation_json, created_at_utc, updated_at_utc
                   ) VALUES (?, ?, ?, ?, ?, 'ai', ?, ?, 0, 'collecting', ?, ?, ?)""",
                (
                    request_id,
                    engine_id,
                    engine_revision,
                    state_schema_version,
                    bundle_json,
                    session_id,
                    initial_owner_generation,
                    conv_json,
                    now,
                    now,
                ),
            )
            # Link request session
            self.conn.execute(
                """INSERT OR IGNORE INTO core_request_sessions (
                    request_id, session_id, owner_generation_at_link, authorized_scope_ref, linked_at_utc
                   ) VALUES (?, ?, ?, 'default_scope', ?)""",
                (request_id, session_id, initial_owner_generation, now),
            )
            row = self.conn.execute(
                "SELECT * FROM core_requests WHERE request_id = ?", (request_id,)
            ).fetchone()
        return row

    def get_or_create_draft(
        self, draft_id: str, request_id: str
    ) -> sqlite3.Row:
        row = self.conn.execute(
            "SELECT * FROM core_drafts WHERE draft_id = ? AND request_id = ?",
            (draft_id, request_id),
        ).fetchone()
        if row is None:
            now = time.time()
            self.conn.execute(
                """INSERT INTO core_drafts (
                    draft_id, request_id, booking_revision, is_active, slots_json,
                    location_evidence_json, updated_at_utc
                   ) VALUES (?, ?, 0, 1, '{}', '{}', ?)""",
                (draft_id, request_id, now),
            )
            row = self.conn.execute(
                "SELECT * FROM core_drafts WHERE draft_id = ? AND request_id = ?",
                (draft_id, request_id),
            ).fetchone()
        return row

    def find_input(self, request_id: str, input_id: str) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM core_inputs WHERE request_id = ? AND input_id = ?",
            (request_id, input_id),
        ).fetchone()

    def find_turn(self, turn_id: str) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM core_turns WHERE turn_id = ?", (turn_id,)
        ).fetchone()

    def find_turn_by_input(self, request_id: str, input_id: str) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM core_turns WHERE request_id = ? AND input_id = ?",
            (request_id, input_id),
        ).fetchone()

    def load_aggregate(self, request_id: str) -> Optional[ConversationAggregate]:
        req_row = self.conn.execute(
            "SELECT * FROM core_requests WHERE request_id = ?", (request_id,)
        ).fetchone()
        if req_row is None:
            return None

        draft_row = self.conn.execute(
            "SELECT * FROM core_drafts WHERE request_id = ? AND is_active = 1", (request_id,)
        ).fetchone()
        
        draft = BookingDraft(
            draft_id=draft_row["draft_id"] if draft_row else f"draft-{request_id}",
            booking_revision=draft_row["booking_revision"] if draft_row else 0,
            status=BookingStatus(req_row["booking_status"]),
        )
        if draft_row:
            slots = json.loads(draft_row["slots_json"])
            if "origin" in slots and slots["origin"]:
                draft.origin = LocationEvidence.model_validate(slots["origin"])
            if "destination" in slots and slots["destination"]:
                draft.destination = LocationEvidence.model_validate(slots["destination"])
            if "vehicle_type" in slots:
                draft.vehicle_type = slots["vehicle_type"]
            if "passengers" in slots:
                draft.passengers = slots["passengers"]
            if "driver_note" in slots:
                draft.driver_note = slots["driver_note"]

        conv_state = ConversationState()
        if req_row["conversation_json"]:
            conv_dict = json.loads(req_row["conversation_json"])
            if conv_dict:
                conv_state = ConversationState.model_validate(conv_dict)

        # Restore pending offered_question from authoritative core_questions if not in conv_state
        if conv_state.offered_question is None:
            q_row = self.conn.execute(
                """SELECT q.*, o.response_id
                   FROM core_questions q
                   LEFT JOIN core_question_offers o ON q.question_id = o.question_id AND q.request_id = o.request_id
                   WHERE q.request_id = ? AND q.status = 'pending'
                   ORDER BY q.created_at_utc DESC LIMIT 1""",
                (request_id,),
            ).fetchone()
            if q_row:
                target_data = q_row["target_ref"]
                try:
                    target_obj = json.loads(target_data) if target_data else "booking"
                except Exception:
                    target_obj = target_data or "booking"

                binding = {}
                if q_row["binding_json"]:
                    try:
                        binding = json.loads(q_row["binding_json"])
                    except Exception:
                        pass

                from src.conversation.domain.models import OfferedQuestion
                conv_state.offered_question = OfferedQuestion(
                    question_id=q_row["question_id"],
                    kind=q_row["decision_kind"],
                    target=target_obj,
                    response_id=q_row["response_id"] or f"resp-{q_row['question_id']}",
                    segment_id=binding.get("segment_id"),
                    location_version=q_row["location_version"],
                    booking_revision=q_row["booking_revision"],
                    options=binding.get("candidates", []),
                )

        return ConversationAggregate(
            request_id=request_id,
            state_version=req_row["state_version"],
            owner_generation=req_row["owner_generation"],
            draft=draft,
            conversation_state=conv_state,
            active_session_id=req_row["owner_session_id"],
        )
