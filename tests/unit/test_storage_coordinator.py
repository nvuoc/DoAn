"""Unit tests for TransactionCoordinator and SQLite authoritative storage."""
import json
import pytest

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
    QuestionDefinition,
    QuestionKind,
    QuestionTarget,
    ResponsePayload,
    ResponseSegment,
    SegmentKind,
    Actor,
    ActorType,
    AuthorizedScope,
    SourceEnvelope,
    Channel,
    InputTiming,
    InputTimingOverlap,
    InputTimingBasis,
    TrustedEnvelope,
    compute_input_hash,
)
from src.conversation.domain.enums import ActType, SlotName
from src.conversation.domain.models import (
    BookingDraft,
    ConversationAggregate,
    ConversationState,
    LocationComponents,
    LocationEvidence,
)
from src.conversation.errors import ErrorCode, ConversationCoreException
from src.conversation.storage.db import get_connection, init_schema
from src.conversation.storage.coordinator import TransactionCoordinator


def make_turn_input(
    turn_id: str = "018b7a20-1111-4111-8111-000000000001",
    input_id: str = "input-01",
    request_id: str = "req-01",
    draft_id: str = "draft-01",
    session_id: str = "sess-01",
    text: str = "Cho tôi xe từ 12 phố Huế đi Bờ Hồ",
    state_version: int = 0,
    owner_generation: int = 1,
    turn_epoch: int = 0,
) -> TurnInput:
    raw_hash_data = {
        "schema_version": "3.0",
        "kind": "user_turn",
        "session_id": session_id,
        "request_id": request_id,
        "draft_id": draft_id,
        "turn_id": turn_id,
        "input_id": input_id,
        "source": {
            "channel": "cli",
            "adapter_id": "cli-adapter",
            "source_segment_ids": [],
        },
        "text": text,
    }
    input_hash = compute_input_hash(raw_hash_data)

    return TurnInput(
        schema_version="3.0",
        kind="user_turn",
        session_id=session_id,
        request_id=request_id,
        draft_id=draft_id,
        turn_id=turn_id,
        input_id=input_id,
        received_at="2026-10-19T10:00:00+07:00",
        source=SourceEnvelope(
            channel=Channel.CLI,
            adapter_id="cli-adapter",
        ),
        text=text,
        trusted=TrustedEnvelope(
            owner_generation=owner_generation,
            turn_epoch=turn_epoch,
            state_version=state_version,
            booking_revision=0,
            deadline_at="2026-10-19T10:00:15+07:00",
            timezone="Asia/Ho_Chi_Minh",
            input_hash=input_hash,
            actor=Actor(
                actor_id="cust-01",
                actor_type=ActorType.CUSTOMER,
                authorized_scopes=[AuthorizedScope.CONVERSATION_WRITE],
            ),
            input_timing=InputTiming(
                overlap=InputTimingOverlap.NO_OVERLAP,
                basis=InputTimingBasis.TEXT_ADAPTER,
            ),
        ),
    )


def make_turn_result(turn_input: TurnInput, response_text: str = "Dạ em đã nhận yêu cầu.") -> TurnResult:
    return TurnResult(
        schema_version="3.0",
        session_id=turn_input.session_id,
        request_id=turn_input.request_id,
        draft_id=turn_input.draft_id,
        turn_id=turn_input.turn_id,
        input_id=turn_input.input_id,
        status=TurnStatus.COMMITTED,
        new_commit=True,
        state_version=1,
        observed_state_version=1,
        booking_revision=0,
        booking_status=BookingStatus.COLLECTING,
        profile=Profile.FIXTURE,
        business_outcome=BusinessOutcome(
            kind=BusinessOutcomeKind.DRAFT_UPDATED,
            dispatch_status=DispatchStatus.NOT_REQUESTED,
        ),
        response=ResponsePayload(
            response_id=f"resp-{turn_input.turn_id[-6:]}",
            created_at="2026-10-19T10:00:01+07:00",
            segments=[
                ResponseSegment(
                    segment_id=f"seg-{turn_input.turn_id[-6:]}-1",
                    index=0,
                    kind=SegmentKind.ANSWER,
                    text=response_text,
                )
            ],
            final_text=response_text,
        ),
        delivery=DeliveryResult(allowed=True, reason=DeliveryReason.COMMITTED_CURRENT),
        trace_id="trace-01",
        timings=ExecutionTimings(prepare_ms=50.0, commit_ms=5.0, total_ms=55.0),
    )


def test_admit_and_commit_happy_path():
    conn = get_connection(":memory:")
    init_schema(conn)
    coord = TransactionCoordinator(conn)

    t_in = make_turn_input()
    admit_res = coord.admit_turn(t_in)

    assert admit_res.status == "admitted"
    assert admit_res.aggregate is not None
    assert admit_res.aggregate.state_version == 0
    assert admit_res.aggregate.request_id == "req-01"

    prepared = make_turn_result(t_in)
    committed = coord.commit_turn(t_in, admit_res.aggregate, prepared)

    assert committed.status == TurnStatus.COMMITTED
    assert committed.new_commit is True
    assert committed.state_version == 1

    # Verify SQLite DB authoritative state
    req_row = conn.execute("SELECT * FROM core_requests WHERE request_id = 'req-01'").fetchone()
    assert req_row["state_version"] == 1
    assert req_row["booking_status"] == "collecting"

    turn_row = conn.execute("SELECT * FROM core_turns WHERE turn_id = ?", (t_in.turn_id,)).fetchone()
    assert turn_row["phase"] == "committed"
    assert turn_row["committed_state_version"] == 1

    outbox_count = conn.execute("SELECT count(*) as c FROM sample_dashboard_outbox").fetchone()["c"]
    assert outbox_count == 1


def test_idempotent_replay_and_hash_conflict():
    conn = get_connection(":memory:")
    init_schema(conn)
    coord = TransactionCoordinator(conn)

    t_in = make_turn_input()
    admit_res = coord.admit_turn(t_in)
    prepared = make_turn_result(t_in)
    coord.commit_turn(t_in, admit_res.aggregate, prepared)

    # 1. Re-admit exact same turn input -> Replayed
    replay_res = coord.admit_turn(t_in)
    assert replay_res.status == "replayed"
    assert replay_res.replayed_result is not None
    assert replay_res.replayed_result.status == TurnStatus.REPLAYED
    assert replay_res.replayed_result.new_commit is False

    # 2. Re-admit with same request_id & input_id but different text/hash -> INPUT_CONFLICT
    t_in_conflict = make_turn_input(text="Tôi muốn đổi ý đi Nội Bài")
    with pytest.raises(ConversationCoreException) as exc_info:
        coord.admit_turn(t_in_conflict)
    assert exc_info.value.code == ErrorCode.INPUT_CONFLICT


def test_cas_concurrency_conflict():
    conn = get_connection(":memory:")
    init_schema(conn)
    coord = TransactionCoordinator(conn)

    # Turn A
    t_in_a = make_turn_input(
        turn_id="018b7a20-1111-4111-8111-000000000001",
        input_id="input-01",
        state_version=0,
    )
    admit_a = coord.admit_turn(t_in_a)
    prepared_a = make_turn_result(t_in_a)
    coord.commit_turn(t_in_a, admit_a.aggregate, prepared_a)

    # Turn B (arrived with stale state_version=0 after Turn A already committed)
    t_in_b = make_turn_input(
        turn_id="018b7a20-2222-4111-8111-000000000002",
        input_id="input-02",
        state_version=0,
    )
    with pytest.raises(ConversationCoreException) as exc_info:
        coord.admit_turn(t_in_b)
    assert exc_info.value.code == ErrorCode.STATE_CONFLICT


def test_cancellation_fence():
    conn = get_connection(":memory:")
    init_schema(conn)
    coord = TransactionCoordinator(conn)

    t_in = make_turn_input()
    admit_res = coord.admit_turn(t_in)

    # Cancel turn durable
    coord.cancel_turn(t_in.turn_id)

    # Attempting to commit cancelled turn must fail and rollback
    prepared = make_turn_result(t_in)
    with pytest.raises(ConversationCoreException) as exc_info:
        coord.commit_turn(t_in, admit_res.aggregate, prepared)
    assert exc_info.value.code == ErrorCode.TURN_CANCELLED

    # Verify turn is still cancelled and request state_version remained 0
    req_row = conn.execute("SELECT * FROM core_requests WHERE request_id = 'req-01'").fetchone()
    assert req_row["state_version"] == 0


def test_local_intake_creates_booking_and_operator_task():
    conn = get_connection(":memory:")
    init_schema(conn)
    coord = TransactionCoordinator(conn)

    t_in = make_turn_input()
    admit_res = coord.admit_turn(t_in)

    admit_res.aggregate.draft.status = BookingStatus.REQUEST_RECORDED
    admit_res.aggregate.draft.origin = LocationEvidence(
        label="12 Phố Huế",
        components=LocationComponents(house_number="12", street="Phố Huế"),
    )
    admit_res.aggregate.draft.destination = LocationEvidence(
        label="Bờ Hồ",
        components=LocationComponents(landmark="Bờ Hồ"),
    )

    prepared = make_turn_result(t_in)
    prepared.business_outcome = BusinessOutcome(
        kind=BusinessOutcomeKind.REQUEST_RECORDED,
        record_id="bk-draft-01",
        operation_id="op-draft-01-intake",
        dispatch_status=DispatchStatus.NOT_REQUESTED,
    )

    committed = coord.commit_turn(t_in, admit_res.aggregate, prepared)
    assert committed.booking_status == BookingStatus.REQUEST_RECORDED

    # Verify core_operations
    op_row = conn.execute("SELECT * FROM core_operations WHERE operation_id = 'op-draft-01-intake'").fetchone()
    assert op_row is not None
    assert op_row["operation_kind"] == "local_intake"
    assert op_row["phase"] == "succeeded"

    # Verify sample_bookings
    bk_row = conn.execute("SELECT * FROM sample_bookings WHERE booking_id = 'bk-draft-01'").fetchone()
    assert bk_row is not None
    assert bk_row["status"] == "confirmed"
    assert bk_row["dispatch_status"] == "not_integrated"

    # Verify sample_operator_tasks
    task_row = conn.execute("SELECT * FROM sample_operator_tasks WHERE booking_id = 'bk-draft-01'").fetchone()
    assert task_row is not None
    assert task_row["kind"] == "new_booking"
    assert task_row["status"] == "open"
