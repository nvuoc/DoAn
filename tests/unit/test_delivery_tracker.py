"""Unit tests for DeliveryTracker and DEL-01..12 protocol."""
import json
import pytest

from src.conversation.contract import (
    ControlEvent,
    ControlEventKind,
    DeliveryEventType,
    DeliveryMode,
    DeliveryPayload,
    DeliveryReporter,
    TrustedControlEnvelope,
    Actor,
    ActorType,
    AuthorizedScope,
)
from src.conversation.delivery.tracker import DeliveryTracker, DeliveryAckStatus
from src.conversation.storage.db import get_connection, init_schema


def setup_db_with_request_and_response(conn):
    now = 1000.0
    conn.execute(
        """INSERT INTO core_sessions (session_id, channel, auth_scope_ref, lifecycle, created_at_utc)
           VALUES ('sess-01', 'voice', 'scope-01', 'active', ?)""",
        (now,),
    )
    conn.execute(
        """INSERT INTO core_requests (
            request_id, engine_id, engine_revision, state_schema_version,
            pinned_bundle_json, owner_kind, owner_session_id, owner_generation,
            state_version, booking_status, conversation_json, created_at_utc, updated_at_utc
           ) VALUES ('req-01', 'vanuoc_v3', '3.0.0', 1, '{}', 'ai', 'sess-01', 1, 1, 'collecting', '{}', ?, ?)""",
        (now, now),
    )
    conn.execute(
        """INSERT INTO core_inputs (
            request_id, input_id, kind, canonical_input_hash, session_id,
            admitted_context_json, received_at_utc
           ) VALUES ('req-01', 'inp-01', 'user_turn', ?, 'sess-01', '{}', ?)""",
        ("a" * 64, now),
    )
    conn.execute(
        """INSERT INTO core_turns (
            turn_id, request_id, input_id, session_id,
            expected_state_version, captured_owner_generation, phase,
            expires_at_utc, created_at_utc, committed_state_version, result_json, completed_at_utc
           ) VALUES ('turn-01', 'req-01', 'inp-01', 'sess-01', 0, 1, 'committed', ?, ?, 1, '{}', ?)""",
        (now + 15.0, now, now),
    )
    conn.execute(
        """INSERT INTO core_responses (
            response_id, turn_id, request_id, state_version,
            booking_revision, segments_json, facts_json, created_at_utc
           ) VALUES ('resp-01', 'turn-01', 'req-01', 1, 0, '[]', '{}', ?)""",
        (now,),
    )
    conn.execute(
        """INSERT INTO core_questions (
            question_id, request_id, decision_kind, target_ref, booking_revision, status, binding_json, created_at_utc
           ) VALUES ('q-01', 'req-01', 'confirm_trip', '{}', 0, 'pending', '{}', ?)""",
        (now,),
    )
    conn.execute(
        """INSERT INTO core_question_offers (
            response_id, question_id, request_id, owner_generation, offered_at_utc
           ) VALUES ('resp-01', 'q-01', 'req-01', 1, ?)""",
        (now,),
    )


def make_delivery_event(
    event_type: DeliveryEventType,
    input_id: str,
    playback_id: str = "pb-01",
    mode: DeliveryMode = DeliveryMode.VOICE,
    generation: int = 1,
) -> ControlEvent:
    payload = {
        "event_type": event_type.value,
        "response_id": "resp-01",
        "segment_id": "seg-01",
        "playback_id": playback_id if mode == DeliveryMode.VOICE else None,
        "mode": mode.value,
        "reporter": "server_adapter" if event_type != DeliveryEventType.OUTPUT_AVAILABLE else "client_adapter",
    }

    return ControlEvent(
        schema_version="3.0",
        kind=ControlEventKind.DELIVERY,
        session_id="sess-01",
        request_id="req-01",
        input_id=input_id,
        occurred_at="2026-10-19T10:00:01+07:00",
        trusted=TrustedControlEnvelope(
            owner_generation=generation,
            actor=Actor(
                actor_id="server-voice-01",
                actor_type=ActorType.SYSTEM,
                authorized_scopes=[AuthorizedScope.DELIVERY_WRITE],
            ),
            adapter_id="voice-adapter-01",
        ),
        payload=payload,
    )


def test_del_01_and_02_voice_eligibility():
    conn = get_connection(":memory:")
    init_schema(conn)
    setup_db_with_request_and_response(conn)
    tracker = DeliveryTracker(conn)

    # 1. Started event -> not eligible yet
    ev_start = make_delivery_event(DeliveryEventType.PLAYBACK_STARTED, "ctrl-01")
    ack1 = tracker.process_delivery_event(ev_start)
    assert ack1.status == DeliveryAckStatus.ACCEPTED
    assert ack1.eligible is False
    assert tracker.is_question_eligible("req-01", "q-01") is False

    # 2. Completed event alone -> not eligible yet (needs output ACK)
    ev_comp = make_delivery_event(DeliveryEventType.PLAYBACK_COMPLETED, "ctrl-02")
    ack2 = tracker.process_delivery_event(ev_comp)
    assert ack2.status == DeliveryAckStatus.ACCEPTED
    assert ack2.eligible is False
    assert tracker.is_question_eligible("req-01", "q-01") is False

    # 3. Output available ACK received -> now both exist -> eligible!
    ev_ack = make_delivery_event(DeliveryEventType.OUTPUT_AVAILABLE, "ctrl-03")
    ack3 = tracker.process_delivery_event(ev_ack)
    assert ack3.status == DeliveryAckStatus.ACCEPTED
    assert ack3.eligible is True
    assert tracker.is_question_eligible("req-01", "q-01") is True


def test_del_04_playback_interrupted_is_terminal():
    conn = get_connection(":memory:")
    init_schema(conn)
    setup_db_with_request_and_response(conn)
    tracker = DeliveryTracker(conn)

    ev_start = make_delivery_event(DeliveryEventType.PLAYBACK_STARTED, "ctrl-01")
    tracker.process_delivery_event(ev_start)

    # Interrupted
    ev_interrupt = make_delivery_event(DeliveryEventType.PLAYBACK_INTERRUPTED, "ctrl-02")
    ack_int = tracker.process_delivery_event(ev_interrupt)
    assert ack_int.reason == "interrupted"
    assert ack_int.eligible is False

    # Late completion after interrupt must NOT revive eligibility
    ev_late_comp = make_delivery_event(DeliveryEventType.PLAYBACK_COMPLETED, "ctrl-03")
    ack_late = tracker.process_delivery_event(ev_late_comp)
    assert ack_late.status == DeliveryAckStatus.IGNORED
    assert ack_late.reason == "attempt_terminal"
    assert ack_late.eligible is False
    assert tracker.is_question_eligible("req-01", "q-01") is False


def test_del_05_stale_generation_is_ignored():
    conn = get_connection(":memory:")
    init_schema(conn)
    setup_db_with_request_and_response(conn)
    tracker = DeliveryTracker(conn)

    # Bump request owner_generation to 2
    conn.execute("UPDATE core_requests SET owner_generation = 2 WHERE request_id = 'req-01'")

    # Event from generation 1
    ev_stale = make_delivery_event(DeliveryEventType.PLAYBACK_STARTED, "ctrl-01", generation=1)
    ack = tracker.process_delivery_event(ev_stale)
    assert ack.status == DeliveryAckStatus.IGNORED
    assert ack.reason == "stale_generation"


def test_text_mode_presentation():
    conn = get_connection(":memory:")
    init_schema(conn)
    setup_db_with_request_and_response(conn)
    tracker = DeliveryTracker(conn)

    ev_text = make_delivery_event(
        DeliveryEventType.TEXT_PRESENTED,
        "ctrl-text-01",
        mode=DeliveryMode.TEXT,
    )
    ack = tracker.process_delivery_event(ev_text)
    assert ack.status == DeliveryAckStatus.ACCEPTED
    assert ack.eligible is True
    assert tracker.is_question_eligible("req-01", "q-01") is True
