"""Authoritative SQLite transaction coordinator for vanuoc conversation core.

Enforces:
- Input deduplication and idempotent replay
- Single-turn active concurrency lease
- CAS state_version updates
- Owner generation fencing
- Atomic single-writer SQLite transactions for turns, drafts, operations, bookings, tasks, and outbox
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
import uuid

from src.conversation.contract import (
    TurnInput,
    TurnResult,
    TurnStatus,
    BookingStatus,
    BusinessOutcome,
    BusinessOutcomeKind,
    DispatchStatus,
    DeliveryResult,
    DeliveryReason,
    ExecutionTimings,
    Profile,
    SegmentKind,
    Channel,
)
from src.conversation.domain.models import (
    BookingDraft,
    ConversationAggregate,
    ConversationState,
    LocationEvidence,
)
from src.conversation.errors import ErrorCode, ConversationCoreException
from src.conversation.storage.repository import StorageRepository


class TurnAdmissionResult:
    def __init__(
        self,
        status: str,
        aggregate: Optional[ConversationAggregate] = None,
        replayed_result: Optional[TurnResult] = None,
    ):
        self.status = status  # "admitted" or "replayed"
        self.aggregate = aggregate
        self.replayed_result = replayed_result


class TransactionCoordinator:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.repo = StorageRepository(conn)
        self._locks: Dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()
        self._turn_epochs: Dict[str, int] = {}

    def _get_request_lock(self, request_id: str) -> threading.Lock:
        with self._global_lock:
            if request_id not in self._locks:
                self._locks[request_id] = threading.Lock()
            return self._locks[request_id]

    def invalidate_turn_epoch(self, request_id: str) -> int:
        """Bump local in-process turn epoch to immediately invalidate active executors."""
        with self._global_lock:
            current = self._turn_epochs.get(request_id, 0)
            self._turn_epochs[request_id] = current + 1
            return self._turn_epochs[request_id]

    def get_turn_epoch(self, request_id: str) -> int:
        with self._global_lock:
            return self._turn_epochs.get(request_id, 0)

    def admit_turn(self, turn_input: TurnInput, lease_seconds: float = 15.0) -> TurnAdmissionResult:
        """Admit turn with input dedup, canonical hash verification, and concurrency lease."""
        req_lock = self._get_request_lock(turn_input.request_id)
        with req_lock:
            now = time.time()

            # 1. Check local turn epoch
            current_epoch = self.get_turn_epoch(turn_input.request_id)
            if turn_input.trusted.turn_epoch < current_epoch:
                raise ConversationCoreException(
                    ErrorCode.TURN_CANCELLED,
                    f"Turn epoch {turn_input.trusted.turn_epoch} superseded by local epoch {current_epoch}",
                )

            # 2. Check input deduplication
            existing_input = self.repo.find_input(turn_input.request_id, turn_input.input_id)
            if existing_input is not None:
                # Validate canonical hash
                expected_hash = turn_input.trusted.input_hash
                stored_hash = existing_input["canonical_input_hash"]
                if expected_hash != stored_hash:
                    raise ConversationCoreException(
                        ErrorCode.INPUT_CONFLICT,
                        f"Input hash conflict for request '{turn_input.request_id}' input '{turn_input.input_id}'",
                        retryable=False,
                    )

                # Check turn record
                existing_turn = self.repo.find_turn_by_input(turn_input.request_id, turn_input.input_id)
                if existing_turn is not None:
                    phase = existing_turn["phase"]
                    if phase == "committed":
                        # Replay committed result
                        result_dict = json.loads(existing_turn["result_json"])
                        replayed = TurnResult.model_validate(result_dict)
                        # Replay result semantics
                        replayed.status = TurnStatus.REPLAYED
                        replayed.new_commit = False
                        
                        # Load current aggregate to check observed state version
                        current_req = self.conn.execute(
                            "SELECT state_version FROM core_requests WHERE request_id = ?",
                            (turn_input.request_id,),
                        ).fetchone()
                        if current_req:
                            replayed.observed_state_version = current_req["state_version"]
                            if current_req["state_version"] > (replayed.state_version or 0):
                                replayed.delivery = DeliveryResult(
                                    allowed=False,
                                    reason=DeliveryReason.SUPERSEDED,
                                )
                            else:
                                replayed.delivery = DeliveryResult(
                                    allowed=True,
                                    reason=DeliveryReason.REPLAYED_CURRENT,
                                )
                        return TurnAdmissionResult(status="replayed", replayed_result=replayed)
                    elif phase in ("admitted", "preparing"):
                        # Lease check
                        lease_exp = existing_turn["executor_lease_expires_at_utc"]
                        if lease_exp and lease_exp > now:
                            raise ConversationCoreException(
                                ErrorCode.TURN_IN_PROGRESS,
                                f"Turn '{existing_turn['turn_id']}' is already in progress with valid lease",
                                retryable=True,
                            )
                        # Lease expired, mark as deadline exceeded
                        self.conn.execute(
                            "UPDATE core_turns SET phase = 'deadline_exceeded', completed_at_utc = ? WHERE turn_id = ?",
                            (now, existing_turn["turn_id"]),
                        )
                    else:
                        raise ConversationCoreException(
                            ErrorCode.TURN_SUPERSEDED,
                            f"Input '{turn_input.input_id}' already terminated with phase '{phase}'",
                            retryable=False,
                        )

            # 3. Check if another turn for this request is actively in progress
            active_turn = self.conn.execute(
                """SELECT * FROM core_turns
                   WHERE request_id = ? AND phase IN ('admitted', 'preparing')
                   ORDER BY created_at_utc DESC LIMIT 1""",
                (turn_input.request_id,),
            ).fetchone()
            if active_turn is not None:
                lease_exp = active_turn["executor_lease_expires_at_utc"]
                if lease_exp and lease_exp > now:
                    raise ConversationCoreException(
                        ErrorCode.TURN_IN_PROGRESS,
                        f"Another turn '{active_turn['turn_id']}' is currently in progress for request '{turn_input.request_id}'",
                        retryable=True,
                    )
                else:
                    self.conn.execute(
                        "UPDATE core_turns SET phase = 'deadline_exceeded', completed_at_utc = ? WHERE turn_id = ?",
                        (now, active_turn["turn_id"]),
                    )

            # 4. Check or create session, request, draft
            session = self.repo.get_or_create_session(
                turn_input.session_id, channel=turn_input.source.channel.value
            )
            if session["lifecycle"] != "active":
                raise ConversationCoreException(
                    ErrorCode.SESSION_ENDED,
                    f"Session '{turn_input.session_id}' lifecycle is '{session['lifecycle']}'",
                )

            req = self.repo.get_or_create_request(
                turn_input.request_id,
                turn_input.session_id,
                initial_owner_generation=turn_input.trusted.owner_generation,
            )

            # Validate owner generation
            if turn_input.trusted.owner_generation < req["owner_generation"]:
                raise ConversationCoreException(
                    ErrorCode.OWNER_SUPERSEDED,
                    f"Input owner_generation {turn_input.trusted.owner_generation} is stale (active: {req['owner_generation']})",
                )

            # Validate state version expectation
            if turn_input.trusted.state_version != req["state_version"]:
                raise ConversationCoreException(
                    ErrorCode.STATE_CONFLICT,
                    f"Input expected state_version {turn_input.trusted.state_version} does not match current {req['state_version']}",
                )

            self.repo.get_or_create_draft(turn_input.draft_id, turn_input.request_id)

            # Parse deadline UTC
            try:
                # Default 15s deadline if not parsable
                deadline_utc = now + 15.0
            except Exception:
                deadline_utc = now + 15.0

            # 5. Insert core_inputs
            self.conn.execute(
                """INSERT INTO core_inputs (
                    request_id, input_id, kind, canonical_input_hash, session_id,
                    protected_payload_json, admitted_context_json, received_at_utc
                   ) VALUES (?, ?, 'user_turn', ?, ?, ?, ?, ?)""",
                (
                    turn_input.request_id,
                    turn_input.input_id,
                    turn_input.trusted.input_hash,
                    turn_input.session_id,
                    json.dumps({"text": turn_input.text}),
                    json.dumps(turn_input.model_dump(mode="json")),
                    now,
                ),
            )

            # 6. Insert core_turns
            self.conn.execute(
                """INSERT INTO core_turns (
                    turn_id, request_id, input_id, session_id,
                    expected_state_version, captured_owner_generation, phase,
                    executor_claim_token, executor_lease_expires_at_utc, expires_at_utc,
                    attempt_count, created_at_utc
                   ) VALUES (?, ?, ?, ?, ?, ?, 'preparing', ?, ?, ?, 1, ?)""",
                (
                    turn_input.turn_id,
                    turn_input.request_id,
                    turn_input.input_id,
                    turn_input.session_id,
                    req["state_version"],
                    req["owner_generation"],
                    f"claim-{turn_input.turn_id}",
                    now + lease_seconds,
                    deadline_utc,
                    now,
                ),
            )

            aggregate = self.repo.load_aggregate(turn_input.request_id)
            return TurnAdmissionResult(status="admitted", aggregate=aggregate)

    def commit_turn(
        self,
        turn_input: TurnInput,
        aggregate: ConversationAggregate,
        prepared_result: TurnResult,
        domain_events: Optional[List[Dict[str, Any]]] = None,
    ) -> TurnResult:
        """Atomic single-writer transaction committing turn, state CAS, draft, operations, and response."""
        req_lock = self._get_request_lock(turn_input.request_id)
        with req_lock:
            now = time.time()

            # 1. Check local turn epoch
            current_epoch = self.get_turn_epoch(turn_input.request_id)
            if turn_input.trusted.turn_epoch < current_epoch:
                self.conn.execute(
                    "UPDATE core_turns SET phase = 'cancelled', completed_at_utc = ? WHERE turn_id = ?",
                    (now, turn_input.turn_id),
                )
                raise ConversationCoreException(
                    ErrorCode.TURN_CANCELLED,
                    f"Turn was invalidated by local turn epoch ({turn_input.trusted.turn_epoch} < {current_epoch})",
                )

            # 2. Begin immediate atomic transaction
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                # 3. Verify turn phase and identity
                turn_row = self.conn.execute(
                    "SELECT * FROM core_turns WHERE turn_id = ?", (turn_input.turn_id,)
                ).fetchone()
                if turn_row is None:
                    raise ConversationCoreException(
                        ErrorCode.STORE_WRITE_FAILED, f"Turn '{turn_input.turn_id}' not found"
                    )
                if turn_row["phase"] != "preparing":
                    raise ConversationCoreException(
                        ErrorCode.TURN_CANCELLED
                        if turn_row["phase"] == "cancelled"
                        else ErrorCode.STORE_WRITE_FAILED,
                        f"Turn '{turn_input.turn_id}' is in terminal phase '{turn_row['phase']}'",
                    )

                # 4. Verify request CAS state and owner generation
                req_row = self.conn.execute(
                    "SELECT * FROM core_requests WHERE request_id = ?", (turn_input.request_id,)
                ).fetchone()
                if req_row is None:
                    raise ConversationCoreException(
                        ErrorCode.STORE_WRITE_FAILED, f"Request '{turn_input.request_id}' not found"
                    )

                if req_row["owner_generation"] != turn_row["captured_owner_generation"]:
                    self.conn.execute(
                        "UPDATE core_turns SET phase = 'stale', completed_at_utc = ? WHERE turn_id = ?",
                        (now, turn_input.turn_id),
                    )
                    raise ConversationCoreException(
                        ErrorCode.OWNER_SUPERSEDED,
                        f"Request owner generation {req_row['owner_generation']} changed from captured {turn_row['captured_owner_generation']}",
                    )

                if req_row["state_version"] != turn_row["expected_state_version"]:
                    self.conn.execute(
                        "UPDATE core_turns SET phase = 'stale', completed_at_utc = ? WHERE turn_id = ?",
                        (now, turn_input.turn_id),
                    )
                    raise ConversationCoreException(
                        ErrorCode.STATE_CONFLICT,
                        f"Request state_version {req_row['state_version']} changed from expected {turn_row['expected_state_version']}",
                    )

                # 5. CAS update on core_requests (increment state_version)
                new_state_version = req_row["state_version"] + 1
                conv_json = aggregate.conversation_state.model_dump_json()
                new_booking_status = aggregate.draft.status.value

                cursor = self.conn.execute(
                    """UPDATE core_requests
                       SET state_version = ?,
                           booking_status = ?,
                           conversation_json = ?,
                           updated_at_utc = ?
                       WHERE request_id = ? AND state_version = ?""",
                    (
                        new_state_version,
                        new_booking_status,
                        conv_json,
                        now,
                        turn_input.request_id,
                        req_row["state_version"],
                    ),
                )
                if cursor.rowcount != 1:
                    raise ConversationCoreException(
                        ErrorCode.STATE_CONFLICT,
                        f"CAS update failed for request '{turn_input.request_id}' at state_version {req_row['state_version']}",
                    )

                # 6. Update core_drafts
                slots_dict: Dict[str, Any] = {}
                if aggregate.draft.origin:
                    slots_dict["origin"] = aggregate.draft.origin.model_dump(mode="json")
                if aggregate.draft.destination:
                    slots_dict["destination"] = aggregate.draft.destination.model_dump(mode="json")
                if aggregate.draft.vehicle_type:
                    slots_dict["vehicle_type"] = aggregate.draft.vehicle_type
                if aggregate.draft.passengers:
                    slots_dict["passengers"] = aggregate.draft.passengers
                if aggregate.draft.driver_note:
                    slots_dict["driver_note"] = aggregate.draft.driver_note

                evidence_dict: Dict[str, Any] = {}
                if aggregate.draft.origin:
                    evidence_dict["origin"] = aggregate.draft.origin.model_dump(mode="json")
                if aggregate.draft.destination:
                    evidence_dict["destination"] = aggregate.draft.destination.model_dump(mode="json")

                self.conn.execute(
                    """UPDATE core_drafts
                       SET booking_revision = ?,
                           slots_json = ?,
                           location_evidence_json = ?,
                           updated_at_utc = ?
                       WHERE draft_id = ? AND request_id = ?""",
                    (
                        aggregate.draft.booking_revision,
                        json.dumps(slots_dict),
                        json.dumps(evidence_dict),
                        now,
                        aggregate.draft.draft_id,
                        turn_input.request_id,
                    ),
                )

                # 7. Record Business Operations & Sample Bookings / Tasks if applicable
                outcome = prepared_result.business_outcome
                if outcome.kind == BusinessOutcomeKind.REQUEST_RECORDED:
                    op_id = outcome.operation_id or f"op-{turn_input.draft_id}-intake"
                    idempotency_key = f"{turn_input.request_id}:{turn_input.draft_id}:{aggregate.draft.booking_revision}:local_intake"
                    payload_raw = json.dumps(slots_dict, sort_keys=True)
                    payload_hash = hashlib.sha256(payload_raw.encode("utf-8")).hexdigest()
                    outcome_data = {"kind": "request_recorded", "dispatch_status": "not_requested"}

                    # Insert operation
                    self.conn.execute(
                        """INSERT OR IGNORE INTO core_operations (
                            operation_id, request_id, draft_id, booking_revision,
                            operation_kind, idempotency_key, payload_hash, protected_payload_json,
                            phase, outcome_json, attempt_count, created_at_utc, updated_at_utc
                           ) VALUES (?, ?, ?, ?, 'local_intake', ?, ?, ?, 'succeeded', ?, 1, ?, ?)""",
                        (
                            op_id,
                            turn_input.request_id,
                            turn_input.draft_id,
                            aggregate.draft.booking_revision,
                            idempotency_key,
                            payload_hash,
                            payload_raw,
                            json.dumps(outcome_data),
                            now,
                            now,
                        ),
                    )

                    # Insert sample_bookings
                    booking_id = outcome.record_id or f"bk-{turn_input.draft_id}"
                    self.conn.execute(
                        """INSERT OR IGNORE INTO sample_bookings (
                            booking_id, request_id, draft_id, operation_id, session_id,
                            booking_revision, status, dispatch_status, protected_booking_json, created_at_utc
                           ) VALUES (?, ?, ?, ?, ?, ?, 'confirmed', 'not_integrated', ?, ?)""",
                        (
                            booking_id,
                            turn_input.request_id,
                            turn_input.draft_id,
                            op_id,
                            turn_input.session_id,
                            aggregate.draft.booking_revision,
                            payload_raw,
                            now,
                        ),
                    )

                    # Insert sample_operator_tasks (kind = 'new_booking')
                    task_id = f"task-{booking_id}"
                    self.conn.execute(
                        """INSERT OR IGNORE INTO sample_operator_tasks (
                            task_id, booking_id, kind, status, version,
                            protected_detail_json, created_at_utc, updated_at_utc
                           ) VALUES (?, ?, 'new_booking', 'open', 0, ?, ?, ?)""",
                        (
                            task_id,
                            booking_id,
                            json.dumps({"reason": "intake_recorded", "slots": slots_dict}),
                            now,
                            now,
                        ),
                    )
                elif outcome.kind in (BusinessOutcomeKind.CANCEL_REQUESTED, BusinessOutcomeKind.CANCELLED):
                    booking_row = self.conn.execute(
                        "SELECT * FROM sample_bookings WHERE request_id = ? AND draft_id = ?",
                        (turn_input.request_id, turn_input.draft_id),
                    ).fetchone()
                    if booking_row:
                        self.conn.execute(
                            "UPDATE sample_bookings SET status = 'canceled' WHERE booking_id = ?",
                            (booking_row["booking_id"],),
                        )
                        task_id = f"task-cancel-{booking_row['booking_id']}-{int(now)}"
                        self.conn.execute(
                            """INSERT OR IGNORE INTO sample_operator_tasks (
                                task_id, booking_id, kind, request_kind, status, version,
                                protected_detail_json, created_at_utc, updated_at_utc
                               ) VALUES (?, ?, 'follow_up', 'cancel', 'open', 0, '{}', ?, ?)""",
                            (task_id, booking_row["booking_id"], now, now),
                        )

                # 8. Domain Events
                seq_row = self.conn.execute(
                    "SELECT COALESCE(MAX(event_sequence), 0) as max_seq FROM core_domain_events WHERE request_id = ?",
                    (turn_input.request_id,),
                ).fetchone()
                next_seq = (seq_row["max_seq"] if seq_row else 0) + 1

                events_to_write = domain_events or []
                for ev in events_to_write:
                    ev_id = ev.get("event_id") or str(uuid.uuid4())
                    self.conn.execute(
                        """INSERT INTO core_domain_events (
                            request_id, event_sequence, event_id, turn_id, state_version,
                            event_kind, reason_code, payload_json, created_at_utc
                           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            turn_input.request_id,
                            next_seq,
                            ev_id,
                            turn_input.turn_id,
                            new_state_version,
                            ev.get("kind", "state_updated"),
                            ev.get("reason_code", "turn_processed"),
                            json.dumps(ev.get("payload", {})),
                            now,
                        ),
                    )
                    next_seq += 1

                # 9. Response & Question offers
                if prepared_result.response is not None:
                    resp = prepared_result.response
                    self.conn.execute(
                        """INSERT INTO core_responses (
                            response_id, turn_id, request_id, state_version,
                            booking_revision, segments_json, facts_json, created_at_utc
                           ) VALUES (?, ?, ?, ?, ?, ?, '{}', ?)""",
                        (
                            resp.response_id,
                            turn_input.turn_id,
                            turn_input.request_id,
                            new_state_version,
                            aggregate.draft.booking_revision,
                            json.dumps([s.model_dump(mode="json") for s in resp.segments]),
                            now,
                        ),
                    )

                    if resp.question is not None:
                        q = resp.question
                        # Invalidate existing pending questions for this request
                        self.conn.execute(
                            "UPDATE core_questions SET status = 'invalidated' WHERE request_id = ? AND status = 'pending'",
                            (turn_input.request_id,),
                        )

                        self.conn.execute(
                            """INSERT INTO core_questions (
                                question_id, request_id, decision_kind, target_ref,
                                booking_revision, location_version, status, binding_json,
                                expires_at_utc, created_at_utc
                               ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)""",
                            (
                                q.question_id,
                                turn_input.request_id,
                                "choose_candidate" if q.kind.value == "disambiguate_location" else q.kind.value,
                                json.dumps(q.target.model_dump(mode="json")),
                                q.target.booking_revision,
                                q.target.location_version,
                                json.dumps({"segment_id": q.segment_id, "candidates": q.candidate_ids}),
                                now + 300.0,
                                now,
                            ),
                        )

                        self.conn.execute(
                            """INSERT INTO core_question_offers (
                                response_id, question_id, request_id, owner_generation, offered_at_utc
                               ) VALUES (?, ?, ?, ?, ?)""",
                            (
                                resp.response_id,
                                q.question_id,
                                turn_input.request_id,
                                turn_row["captured_owner_generation"],
                                now,
                            ),
                        )



                # 10. Dashboard Outbox
                outbox_event_id = str(uuid.uuid4())
                outbox_payload = {
                    "turn_id": turn_input.turn_id,
                    "state_version": new_state_version,
                    "booking_status": aggregate.draft.status.value,
                }
                self.conn.execute(
                    """INSERT INTO sample_dashboard_outbox (
                        event_id, request_id, topic, payload_json, phase, created_at_utc
                       ) VALUES (?, ?, 'conversation.turn_committed', ?, 'pending', ?)""",
                    (outbox_event_id, turn_input.request_id, json.dumps(outbox_payload), now),
                )

                # 11. Finalize Turn Result
                final_result = prepared_result.model_copy(deep=True)
                final_result.status = TurnStatus.COMMITTED
                final_result.new_commit = True
                final_result.state_version = new_state_version
                final_result.observed_state_version = new_state_version
                final_result.booking_status = aggregate.draft.status
                final_result.delivery = DeliveryResult(
                    allowed=True,
                    reason=DeliveryReason.COMMITTED_CURRENT,
                )

                result_json_str = final_result.model_dump_json()

                # 12. Mark turn committed
                self.conn.execute(
                    """UPDATE core_turns
                       SET phase = 'committed',
                           committed_state_version = ?,
                           result_json = ?,
                           completed_at_utc = ?
                       WHERE turn_id = ?""",
                    (new_state_version, result_json_str, now, turn_input.turn_id),
                )

                # Commit SQLite transaction
                self.conn.execute("COMMIT")
                return final_result

            except Exception:
                self.conn.execute("ROLLBACK")
                raise

    def cancel_turn(self, turn_id: str, reason: str = "interrupted") -> None:
        """Durable turn cancellation fence."""
        now = time.time()
        self.conn.execute(
            """UPDATE core_turns
               SET phase = 'cancelled', completed_at_utc = ?
               WHERE turn_id = ? AND phase IN ('admitted', 'preparing')""",
            (now, turn_id),
        )
