"""Backward compatibility facade bridge matching legacy runner expectations."""
from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Dict, List, Optional
import uuid

from src.conversation.contract import (
    TurnInput,
    TurnResult,
    SourceEnvelope,
    TrustedEnvelope,
    Actor,
    ActorType,
    AuthorizedScope,
    InputTiming,
    InputTimingOverlap,
    InputTimingBasis,
    Channel,
    compute_input_hash,
)
from src.conversation.service import ConversationService
from src.conversation.storage.db import get_connection, init_schema


class SessionRunnerBridge:
    """Compatibility adapter matching legacy SessionRunner interfaces."""

    def __init__(
        self,
        db_path: str = ":memory:",
        policy: Optional[Dict[str, Any]] = None,
    ):
        self.conn = get_connection(db_path)
        init_schema(self.conn)
        self.service = ConversationService(self.conn, policy=policy)
        self.session_id = f"sess-{uuid.uuid4().hex[:8]}"
        self.request_id = f"req-{uuid.uuid4().hex[:8]}"
        self.draft_id = f"draft-{uuid.uuid4().hex[:8]}"
        self.turn_counter = 0
        self.latest_result: Optional[TurnResult] = None

    def process_utterance(
        self,
        text: str,
        channel: str = "cli",
        nlu_proposal: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Process a user message and return a legacy-compatible dict output."""
        self.turn_counter += 1
        turn_id = str(uuid.uuid4())
        input_id = f"inp-{self.turn_counter}-{uuid.uuid4().hex[:6]}"

        channel_enum = Channel.VOICE if channel.lower() == "voice" else Channel.CLI
        timing_basis = (
            InputTimingBasis.VOICE_ADAPTER
            if channel_enum == Channel.VOICE
            else InputTimingBasis.TEXT_ADAPTER
        )

        raw_hash_data = {
            "schema_version": "3.0",
            "kind": "user_turn",
            "session_id": self.session_id,
            "request_id": self.request_id,
            "draft_id": self.draft_id,
            "turn_id": turn_id,
            "input_id": input_id,
            "source": {
                "channel": channel_enum.value,
                "adapter_id": "bridge-adapter-01",
                "source_segment_ids": [],
            },
            "text": text,
        }
        inp_hash = compute_input_hash(raw_hash_data)

        req_row = self.conn.execute(
            "SELECT state_version, owner_generation FROM core_requests WHERE request_id = ?",
            (self.request_id,),
        ).fetchone()
        st_ver = req_row["state_version"] if req_row else 0
        gen = req_row["owner_generation"] if req_row else 1

        t_in = TurnInput(
            schema_version="3.0",
            kind="user_turn",
            session_id=self.session_id,
            request_id=self.request_id,
            draft_id=self.draft_id,
            turn_id=turn_id,
            input_id=input_id,
            received_at="2026-10-19T10:00:00+07:00",
            source=SourceEnvelope(channel=channel_enum, adapter_id="bridge-adapter-01"),
            text=text,
            trusted=TrustedEnvelope(
                owner_generation=gen,
                turn_epoch=0,
                state_version=st_ver,
                booking_revision=0,
                deadline_at="2026-10-19T10:00:15+07:00",
                timezone="Asia/Ho_Chi_Minh",
                input_hash=inp_hash,
                actor=Actor(
                    actor_id="bridge-user",
                    actor_type=ActorType.CUSTOMER,
                    authorized_scopes=[AuthorizedScope.CONVERSATION_WRITE],
                ),
                input_timing=InputTiming(
                    overlap=InputTimingOverlap.NO_OVERLAP,
                    basis=timing_basis,
                ),
            ),
        )

        result = self.service.execute_turn(t_in, nlu_proposal=nlu_proposal)
        self.latest_result = result

        resp_text = result.response.final_text if result.response else ""
        return {
            "status": result.status.value,
            "response": resp_text,
            "booking_status": result.booking_status.value,
            "booking_revision": result.booking_revision,
            "state_version": result.state_version,
            "outcome": result.business_outcome.kind.value,
            "dispatch_status": result.business_outcome.dispatch_status.value,
        }

    def get_draft(self) -> Dict[str, Any]:
        """Return current booking draft state."""
        agg = self.service.coordinator.repo.load_aggregate(self.request_id)
        if agg is None:
            return {"origin": None, "destination": None, "status": "collecting", "booking_revision": 0}
        return agg.draft.model_dump(mode="json")

    def get_booking_status(self) -> str:
        """Return current booking status."""
        agg = self.service.coordinator.repo.load_aggregate(self.request_id)
        if agg is None:
            return "collecting"
        return agg.draft.status.value

    def get_history(self) -> List[Dict[str, Any]]:
        """Return conversation history."""
        agg = self.service.coordinator.repo.load_aggregate(self.request_id)
        if agg is None:
            return []
        return agg.conversation_state.recent_delivered_history

    def reset_session(self) -> None:
        """Start a new clean session request."""
        self.request_id = f"req-{uuid.uuid4().hex[:8]}"
        self.draft_id = f"draft-{uuid.uuid4().hex[:8]}"
        self.latest_result = None
        self.turn_counter = 0
