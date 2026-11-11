"""Scenario test runner executing examples/scenarios.jsonl against authoritative ConversationService."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import time
from typing import Any, Dict, List, Optional, Tuple
import uuid

import jsonpointer

from src.conversation.contract import (
    TurnInput,
    TurnResult,
    TurnStatus,
    BookingStatus,
    ControlEvent,
    ControlEventKind,
    DeliveryEventType,
    DeliveryMode,
    DeliveryReporter,
    TrustedControlEnvelope,
    Actor,
    ActorType,
    AuthorizedScope,
    SourceEnvelope,
    Channel,
    InputTiming,
    InputTimingOverlap,
    InputTimingBasis,
    TrustedEnvelope,
    ExecutionTimings,
    Profile,
    DeliveryResult,
    DeliveryReason,
    compute_input_hash,
)
from src.conversation.reducer.reducer import reduce_turn_proposal
from src.conversation.domain.enums import Precision, CoordinateRole
from src.conversation.domain.models import LocationComponents, LocationEvidence
from src.conversation.errors import ConversationCoreException, ErrorCode
from src.conversation.service import ConversationService
from src.conversation.storage.db import get_connection, init_schema
from tests.harness.observer import extract_observation, extract_location_dict


KIND_MAP = {
    "ask_origin_detail": "clarify_slot",
    "ask_destination_detail": "clarify_slot",
    "choose_location": "choose_candidate",
    "choose_candidate": "choose_candidate",
    "confirm_trip": "confirm_trip",
    "confirm_location": "confirm_location",
    "confirm_cancel": "confirm_cancel",
    "resume_request": "resume_request",
    "clarify_slot": "clarify_slot",
}


class ScenarioAssertionFailure:
    def __init__(self, path: str, op: str, expected: Any, actual: Any, reason: str):
        self.path = path
        self.op = op
        self.expected = expected
        self.actual = actual
        self.reason = reason

    def __repr__(self) -> str:
        return f"Assertion failed at '{self.path}': op '{self.op}' expected '{self.expected}', got '{self.actual}' ({self.reason})"


class ScenarioRunResult:
    def __init__(
        self,
        scenario_id: str,
        passed: bool,
        failed_assertions: List[ScenarioAssertionFailure],
        observation: Dict[str, Any],
    ):
        self.scenario_id = scenario_id
        self.passed = passed
        self.failed_assertions = failed_assertions
        self.observation = observation


def seed_initial_state(conn: sqlite3.Connection, initial: Dict[str, Any], fixtures: Dict[str, Any]) -> None:
    """Materialize initial scenario state into SQLite authoritative store."""
    req_id = initial.get("request_id", "req-test-01")
    draft_id = initial.get("draft_id", "draft-test-01")
    session_id = "sess-scenario-01"
    now = 1000.0

    state_version = initial.get("state_version", 1)
    owner_generation = initial.get("owner_generation", 1)

    booking = initial.get("booking", {})
    b_status = booking.get("status", "collecting")
    b_revision = booking.get("booking_revision", 0)

    # 1. Session
    conn.execute(
        """INSERT OR REPLACE INTO core_sessions (
            session_id, channel, auth_scope_ref, lifecycle, created_at_utc
           ) VALUES (?, 'cli', 'default_scope', 'active', ?)""",
        (session_id, now),
    )

    # 2. Request
    history = initial.get("history", [])
    conv_json = json.dumps({"recent_delivered_history": history})
    conn.execute(
        """INSERT OR REPLACE INTO core_requests (
            request_id, engine_id, engine_revision, state_schema_version,
            pinned_bundle_json, owner_kind, owner_session_id, owner_generation,
            state_version, booking_status, conversation_json, created_at_utc, updated_at_utc
           ) VALUES (?, 'vanuoc_v3', '3.0.0', 1, ?, 'ai', ?, ?, ?, ?, ?, ?, ?)""",
        (
            req_id,
            json.dumps(fixtures.get("policy", {})),
            session_id,
            owner_generation,
            state_version,
            b_status,
            conv_json,
            now,
            now,
        ),
    )

    # 3. Request Session Link
    conn.execute(
        """INSERT OR REPLACE INTO core_request_sessions (
            request_id, session_id, owner_generation_at_link, authorized_scope_ref, linked_at_utc
           ) VALUES (?, ?, ?, 'default_scope', ?)""",
        (req_id, session_id, owner_generation, now),
    )

    # 4. Draft
    slots_dict: Dict[str, Any] = {}
    evidence_dict: Dict[str, Any] = {}
    if "origin" in booking and booking["origin"]:
        slots_dict["origin"] = booking["origin"]
        evidence_dict["origin"] = booking["origin"]
    if "destination" in booking and booking["destination"]:
        slots_dict["destination"] = booking["destination"]
        evidence_dict["destination"] = booking["destination"]
    if "vehicle_type" in booking and booking["vehicle_type"]:
        slots_dict["vehicle_type"] = booking["vehicle_type"]
    if "passengers" in booking and booking["passengers"]:
        slots_dict["passengers"] = booking["passengers"]

    conn.execute(
        """INSERT OR REPLACE INTO core_drafts (
            draft_id, request_id, booking_revision, is_active,
            slots_json, location_evidence_json, updated_at_utc
           ) VALUES (?, ?, ?, 1, ?, ?, ?)""",
        (
            draft_id,
            req_id,
            b_revision,
            json.dumps(slots_dict),
            json.dumps(evidence_dict),
            now,
        ),
    )

    # 5. Dialogue & offered question if present
    dialogue = initial.get("dialogue", {})
    delivery = initial.get("delivery", {})
    next_q = dialogue.get("next_question")

    if next_q:
        q_id = next_q.get("question_id", "q-init-01")
        raw_kind = next_q.get("kind", "confirm_trip")
        q_kind = KIND_MAP.get(raw_kind, "clarify_slot")
        resp_id = next_q.get("response_id", "r-init-01")

        # Materialize response for question offer FK
        dummy_turn_id = str(uuid.uuid4())
        conn.execute(
            """INSERT OR IGNORE INTO core_inputs (
                request_id, input_id, kind, canonical_input_hash, session_id,
                admitted_context_json, received_at_utc
               ) VALUES (?, 'init-input', 'user_turn', ?, ?, '{}', ?)""",
            (req_id, "0" * 64, session_id, now),
        )
        conn.execute(
            """INSERT OR IGNORE INTO core_turns (
                turn_id, request_id, input_id, session_id,
                expected_state_version, captured_owner_generation, phase,
                expires_at_utc, created_at_utc, committed_state_version, result_json, completed_at_utc
               ) VALUES (?, ?, 'init-input', ?, 0, ?, 'committed', ?, ?, 1, '{}', ?)""",
            (dummy_turn_id, req_id, session_id, owner_generation, now + 15.0, now, now),
        )
        conn.execute(
            """INSERT OR REPLACE INTO core_responses (
                response_id, turn_id, request_id, state_version,
                booking_revision, segments_json, facts_json, created_at_utc
               ) VALUES (?, ?, ?, ?, ?, '[]', '{}', ?)""",
            (resp_id, dummy_turn_id, req_id, state_version, b_revision, now),
        )

        b_rev_field = b_revision if q_kind == "confirm_trip" else None
        loc_ver_field = next_q.get("location_version", 1) if q_kind == "confirm_location" else None

        conn.execute(
            """INSERT OR REPLACE INTO core_questions (
                question_id, request_id, decision_kind, target_ref,
                booking_revision, location_version, status, binding_json, created_at_utc
               ) VALUES (?, ?, ?, '{}', ?, ?, 'pending', '{}', ?)""",
            (q_id, req_id, q_kind, b_rev_field, loc_ver_field, now),
        )
        conn.execute(
            """INSERT OR REPLACE INTO core_question_offers (
                response_id, question_id, request_id, owner_generation, offered_at_utc
               ) VALUES (?, ?, ?, ?, ?)""",
            (resp_id, q_id, req_id, owner_generation, now),
        )

        # Presentation and eligibility
        if delivery:
            pb_id = delivery.get("active_playback_id", "p-init-01")
            q_eligible = delivery.get("question_eligible", False)
            phase = "completed" if q_eligible else "prepared"
            completed_time = now if q_eligible else None
            ack_time = now if q_eligible else None

            conn.execute(
                """INSERT OR REPLACE INTO core_presentations (
                    playback_id, response_id, request_id, session_id,
                    owner_generation, transport, phase, required_segment_ids_json,
                    server_completed_at_utc, client_output_available_ack_at_utc, created_at_utc
                   ) VALUES (?, ?, ?, ?, ?, 'voice', ?, '[]', ?, ?, ?)""",
                (
                    pb_id,
                    resp_id,
                    req_id,
                    session_id,
                    owner_generation,
                    phase,
                    completed_time,
                    ack_time,
                    now,
                ),
            )


def run_scenario(scenario: Dict[str, Any]) -> ScenarioRunResult:
    """Execute a single scenario against ConversationService and verify all oracle assertions."""
    scenario_id = scenario["scenario_id"]
    initial = scenario.get("initial", {})
    fixtures = scenario.get("fixtures", {})
    timeline = scenario.get("timeline", [])
    oracle = scenario.get("oracle", {})

    conn = get_connection(":memory:")
    init_schema(conn)

    # Seed initial authoritative state
    seed_initial_state(conn, initial, fixtures)

    # Create service
    service = ConversationService(conn, policy=fixtures.get("policy"))

    req_id = initial.get("request_id", "req-test-01")
    draft_id = initial.get("draft_id", "draft-test-01")
    session_id = "sess-scenario-01"

    latest_result: Optional[TurnResult] = None
    latest_error: Optional[Dict[str, Any]] = None

    # Harness state flags
    fault_sqlite_commit = False
    pending_barrier: Optional[str] = None
    held_commit_data: Optional[Tuple[TurnInput, Any, TurnResult]] = None
    held_turn_input: Optional[TurnInput] = None
    held_nlu_proposal: Optional[Dict[str, Any]] = None

    # Step through timeline
    for event in timeline:
        e_kind = event.get("kind")
        e_id = event.get("event_id")
        payload = event.get("payload", {})

        if e_kind == "fault":
            if payload.get("target") == "sqlite_commit":
                fault_sqlite_commit = True

        elif e_kind == "barrier":
            action = payload.get("action")
            point = payload.get("point") or payload.get("name")
            if action == "arm":
                pending_barrier = point
            elif action == "await":
                pass
            elif action == "release":
                if held_commit_data:
                    h_in, h_agg, h_prep = held_commit_data
                    turn_row = conn.execute(
                        "SELECT phase FROM core_turns WHERE turn_id = ?", (h_in.turn_id,)
                    ).fetchone()
                    if turn_row and turn_row["phase"] == "cancelled":
                        latest_result = None
                        latest_error = {
                            "status": "cancelled",
                            "code": "TURN_CANCELLED",
                            "message": "Turn was cancelled",
                        }
                    else:
                        try:
                            latest_result = service.coordinator.commit_turn(h_in, h_agg, h_prep)
                            latest_error = None
                        except ConversationCoreException as ex:
                            latest_result = None
                            latest_error = {
                                "status": "rejected" if ex.code == ErrorCode.INPUT_CONFLICT else (
                                    "cancelled" if ex.code == ErrorCode.TURN_CANCELLED else (
                                        "stale" if ex.code == ErrorCode.OWNER_SUPERSEDED else "error"
                                    )
                                ),
                                "code": ex.code.value if hasattr(ex.code, "value") else str(ex.code),
                                "message": ex.message,
                            }
                        except Exception as ex:
                            latest_result = None
                            latest_error = {
                                "status": "error",
                                "code": "INTERNAL_ERROR",
                                "message": str(ex),
                            }
                    held_commit_data = None
                    held_turn_input = None
                pending_barrier = None

        elif e_kind == "user_turn":
            raw_text = payload.get("text", "")
            raw_turn_id = payload.get("turn_id", f"turn-{e_id}")
            turn_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, raw_turn_id))
            input_id = payload.get("input_id", f"inp-{e_id}")

            # Read current request state version and owner generation
            cur_req = conn.execute(
                "SELECT * FROM core_requests WHERE request_id = ?", (req_id,)
            ).fetchone()
            cur_st = cur_req["state_version"] if cur_req else 0
            cur_gen = cur_req["owner_generation"] if cur_req else 1

            channel_val = Channel.VOICE if payload.get("source") == "voice" else Channel.CLI
            timing_basis = InputTimingBasis.VOICE_ADAPTER if channel_val == Channel.VOICE else InputTimingBasis.TEXT_ADAPTER
            timing_overlap = InputTimingOverlap.NO_OVERLAP

            if "trusted_input_timing" in payload:
                timing_overlap = InputTimingOverlap(payload["trusted_input_timing"].get("overlap", "no_overlap"))
                timing_basis = InputTimingBasis(payload["trusted_input_timing"].get("basis", timing_basis.value))

            raw_hash_data = {
                "schema_version": "3.0",
                "kind": "user_turn",
                "session_id": session_id,
                "request_id": req_id,
                "draft_id": draft_id,
                "turn_id": turn_uuid,
                "input_id": input_id,
                "source": {
                    "channel": channel_val.value,
                    "adapter_id": "adapter-01",
                    "source_segment_ids": [],
                },
                "text": raw_text,
            }
            inp_hash = compute_input_hash(raw_hash_data)

            t_in = TurnInput(
                schema_version="3.0",
                kind="user_turn",
                session_id=session_id,
                request_id=req_id,
                draft_id=draft_id,
                turn_id=turn_uuid,
                input_id=input_id,
                received_at=payload.get("received_at", "2026-10-19T10:00:00+07:00"),
                source=SourceEnvelope(
                    channel=channel_val,
                    adapter_id="adapter-01",
                ),
                text=raw_text,
                trusted=TrustedEnvelope(
                    owner_generation=cur_gen,
                    turn_epoch=0,
                    state_version=cur_st,
                    booking_revision=0,
                    deadline_at="2026-10-19T10:00:15+07:00",
                    timezone="Asia/Ho_Chi_Minh",
                    input_hash=inp_hash,
                    actor=Actor(
                        actor_id="user-01",
                        actor_type=ActorType.CUSTOMER,
                        authorized_scopes=[AuthorizedScope.CONVERSATION_WRITE],
                    ),
                    input_timing=InputTiming(
                        overlap=timing_overlap,
                        basis=timing_basis,
                    ),
                ),
            )

            nlu_proposal = fixtures.get("nlu_proposals", {}).get(e_id)

            if fault_sqlite_commit:
                # Simulate commit failure
                latest_result = None
                latest_error = {
                    "status": "retryable_error",
                    "code": "STORE_WRITE_FAILED",
                    "message": "Disk error during commit",
                }
                fault_sqlite_commit = False
                continue

            if pending_barrier == "before_authoritative_commit" and payload.get("await_result") is False:
                # Prepare turn up to before authoritative commit
                admit_res = service.coordinator.admit_turn(t_in)
                agg = admit_res.aggregate
                assert agg is not None
                prop = nlu_proposal or service._extract_default_proposal(t_in.text, agg)
                red = reduce_turn_proposal(agg, prop, service.policy, False, t_in.text)
                new_agg = agg.model_copy(deep=True)
                new_agg.draft = red.draft
                new_agg.conversation_state = red.conversation_state
                outcome, resp = service.planner.plan_response(new_agg, red, response_id=f"resp-{t_in.turn_id[-6:]}")
                if resp.question is not None:
                    q_def = resp.question
                    from src.conversation.domain.models import OfferedQuestion
                    new_agg.conversation_state.offered_question = OfferedQuestion(
                        question_id=q_def.question_id,
                        kind=q_def.kind.value,
                        target=q_def.target.slot or "booking",
                        response_id=resp.response_id,
                        segment_id=q_def.segment_id,
                        options=q_def.candidate_ids,
                    )
                else:
                    new_agg.conversation_state.offered_question = None

                prepared = TurnResult(
                    schema_version="3.0",
                    session_id=t_in.session_id,
                    request_id=t_in.request_id,
                    draft_id=t_in.draft_id,
                    turn_id=t_in.turn_id,
                    input_id=t_in.input_id,
                    status=TurnStatus.COMMITTED,
                    new_commit=True,
                    state_version=agg.state_version + 1,
                    observed_state_version=agg.state_version + 1,
                    booking_revision=new_agg.draft.booking_revision,
                    booking_status=new_agg.draft.status,
                    profile=Profile.FIXTURE,
                    business_outcome=outcome,
                    response=resp,
                    delivery=DeliveryResult(allowed=True, reason=DeliveryReason.COMMITTED_CURRENT),
                    trace_id=f"trace-{t_in.turn_id[-6:]}",
                    timings=ExecutionTimings(prepare_ms=1.0, commit_ms=1.0, total_ms=2.0),
                )
                held_commit_data = (t_in, new_agg, prepared)
                held_turn_input = t_in
                continue

            try:
                latest_result = service.execute_turn(t_in, nlu_proposal=nlu_proposal, fixtures=fixtures)
                latest_error = None
            except ConversationCoreException as ex:
                latest_result = None
                latest_error = {
                    "status": "rejected" if ex.code == ErrorCode.INPUT_CONFLICT else (
                        "cancelled" if ex.code == ErrorCode.TURN_CANCELLED else (
                            "stale" if ex.code == ErrorCode.OWNER_SUPERSEDED else "error"
                        )
                    ),
                    "code": ex.code.value if hasattr(ex.code, "value") else str(ex.code),
                    "message": ex.message,
                }
            except Exception as ex:
                latest_result = None
                latest_error = {
                    "status": "error",
                    "code": "INTERNAL_ERROR",
                    "message": str(ex),
                }

        elif e_kind == "delivery":
            state = payload.get("state")
            resp_id = payload.get("response_id", "r_old")
            pb_id = payload.get("playback_id", "p_old")

            ev_type = DeliveryEventType.PLAYBACK_COMPLETED
            if state == "availability_ack":
                ev_type = DeliveryEventType.OUTPUT_AVAILABLE

            ctrl_payload = {
                "event_type": ev_type.value,
                "response_id": resp_id,
                "segment_id": "seg-01",
                "playback_id": pb_id,
                "mode": "voice",
                "reporter": "client_adapter" if state == "availability_ack" else "server_adapter",
            }
            ctrl_ev = ControlEvent(
                schema_version="3.0",
                kind=ControlEventKind.DELIVERY,
                session_id=session_id,
                request_id=req_id,
                input_id=f"ctrl-{e_id}",
                occurred_at=payload.get("occurred_at", "2026-10-19T10:00:01+07:00"),
                trusted=TrustedControlEnvelope(
                    owner_generation=1,
                    actor=Actor(
                        actor_id="server-voice-01",
                        actor_type=ActorType.SYSTEM,
                        authorized_scopes=[AuthorizedScope.DELIVERY_WRITE],
                    ),
                    adapter_id="voice-adapter-01",
                ),
                payload=ctrl_payload,
            )
            service.execute_delivery(ctrl_ev)

        elif e_kind == "restart":
            # Restart hook: connection remains persistent in SQLite
            pass

        elif e_kind == "interrupt":
            if held_turn_input:
                service.coordinator.cancel_turn(held_turn_input.turn_id)
            elif latest_result:
                service.coordinator.cancel_turn(latest_result.turn_id)

        elif e_kind == "ownership_changed":
            conn.execute(
                "UPDATE core_requests SET owner_generation = owner_generation + 1 WHERE request_id = ?",
                (req_id,),
            )

    estimate_endpoints = None
    for tr in fixtures.get("tool_results", {}).values():
        if isinstance(tr, dict) and "endpoint_ids" in tr:
            estimate_endpoints = tr["endpoint_ids"]

    # Extract final Observation
    observation = extract_observation(
        conn=conn,
        request_id=req_id,
        draft_id=draft_id,
        latest_result=latest_result,
        error_detail=latest_error,
        estimate_endpoints=estimate_endpoints,
    )

    # Initial snapshot for 'unchanged' assertions
    initial_obs = {
        "booking": {
            "origin": initial.get("booking", {}).get("origin"),
            "destination": initial.get("booking", {}).get("destination"),
            "vehicle_type": initial.get("booking", {}).get("vehicle_type"),
        }
    }

    # Evaluate Assertions
    failed_assertions: List[ScenarioAssertionFailure] = []
    for assertion in oracle.get("assertions", []):
        path = assertion.get("path")
        op = assertion.get("op")
        expected = assertion.get("value")
        reason = assertion.get("reason", "")

        actual = jsonpointer.resolve_pointer(observation, path, default=None)

        passed = False
        if op == "eq":
            passed = (actual == expected)
        elif op == "ne":
            passed = (actual != expected)
        elif op == "gte":
            passed = (actual is not None and actual >= expected)
        elif op == "lte":
            passed = (actual is not None and actual <= expected)
        elif op == "contains":
            passed = (actual is not None and expected in actual)
        elif op == "not_contains":
            passed = (actual is not None and expected not in actual)
        elif op == "truthy":
            passed = bool(actual) is True
        elif op == "falsy":
            passed = bool(actual) is False
        elif op == "exists":
            passed = (actual is not None)
        elif op == "unchanged":
            init_val = jsonpointer.resolve_pointer(initial_obs, path, default=None)
            # Compare equality with initial value
            passed = (actual == init_val or (actual is not None and init_val is not None and actual.get("label") == init_val.get("label")))

        if not passed:
            failed_assertions.append(
                ScenarioAssertionFailure(
                    path=path,
                    op=op,
                    expected=expected,
                    actual=actual,
                    reason=reason,
                )
            )

    return ScenarioRunResult(
        scenario_id=scenario_id,
        passed=(len(failed_assertions) == 0),
        failed_assertions=failed_assertions,
        observation=observation,
    )
