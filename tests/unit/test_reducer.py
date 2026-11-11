"""Unit tests for deterministic state reducer and whole-turn invariants."""
from src.conversation.contract import BookingStatus
from src.conversation.domain.enums import ActType, SlotName
from src.conversation.domain.models import (
    BookingDraft,
    ConversationAggregate,
    ConversationState,
    LocationEvidence,
    LocationComponents,
    OfferedQuestion,
)
from src.conversation.policy.baseline import get_default_policy
from src.conversation.reducer.reducer import reduce_turn_proposal


def test_pure_query_does_not_mutate_booking():
    aggregate = ConversationAggregate(
        request_id="req-1",
        state_version=1,
        owner_generation=1,
        draft=BookingDraft(
            draft_id="draft-1",
            booking_revision=1,
            origin=LocationEvidence(label="Điểm A", verified=True),
            destination=LocationEvidence(label="Điểm B", verified=True),
            vehicle_type="4_seat",
            passengers=2,
        ),
    )
    proposal = {
        "acts": [
            {
                "type": ActType.ASK_INFORMATION.value,
                "topic": "admin_geo_query",
                "referents": ["Bích Động"],
            }
        ]
    }
    policy = get_default_policy()

    res = reduce_turn_proposal(aggregate, proposal, policy, question_eligible_at_admission=False, raw_utterance="Phường Bích Động giờ thuộc đâu?")
    assert res.draft.destination.label == "Điểm B"
    assert res.draft.booking_revision == 1
    assert res.intended_action == "none"


def test_confirm_then_edit_invalidates_summary():
    aggregate = ConversationAggregate(
        request_id="req-1",
        state_version=1,
        owner_generation=1,
        draft=BookingDraft(
            draft_id="draft-1",
            booking_revision=1,
            status=BookingStatus.AWAITING_CONFIRMATION,
            origin=LocationEvidence(label="Điểm A", verified=True),
            destination=LocationEvidence(label="Điểm B", verified=True),
            vehicle_type="4_seat",
            passengers=2,
        ),
        conversation_state=ConversationState(
            offered_question=OfferedQuestion(
                question_id="q1",
                kind="confirm_trip",
                target="req-1",
                response_id="r1",
                booking_revision=1,
            )
        ),
    )
    proposal = {
        "acts": [
            {"type": ActType.CONFIRM_PENDING.value, "reference": "q1"},
            {"type": ActType.REPLACE_SLOT.value, "target": "vehicle_type", "value": "7_seat"},
        ]
    }
    policy = get_default_policy()

    res = reduce_turn_proposal(aggregate, proposal, policy, question_eligible_at_admission=True, raw_utterance="Đúng rồi, nhưng đổi xe bảy chỗ giúp anh.")
    assert res.draft.vehicle_type == "7_seat"
    assert res.draft.booking_revision >= 2
    assert res.trip_summary_invalidated is True
    assert res.confirmed_trip is False
    assert res.draft.status == BookingStatus.AWAITING_CONFIRMATION
    assert res.next_question_kind == "confirm_trip"


def test_confirm_origin_add_destination():
    aggregate = ConversationAggregate(
        request_id="req-1",
        state_version=1,
        owner_generation=1,
        draft=BookingDraft(
            draft_id="draft-1",
            booking_revision=1,
            status=BookingStatus.COLLECTING,
            origin=LocationEvidence(label="Điểm A", verified=False),
            destination=None,
            vehicle_type="4_seat",
            passengers=2,
        ),
        conversation_state=ConversationState(
            offered_question=OfferedQuestion(
                question_id="q_origin",
                kind="confirm_location",
                target="origin",
                response_id="r1",
                location_version=1,
            )
        ),
    )
    proposal = {
        "acts": [
            {"type": ActType.CONFIRM_PENDING.value, "reference": "q_origin"},
            {"type": ActType.SET_SLOT.value, "target": "destination", "value": "Điểm C"},
        ]
    }
    policy = get_default_policy()

    res = reduce_turn_proposal(aggregate, proposal, policy, question_eligible_at_admission=True, raw_utterance="Đúng điểm đón đó, cho tôi đến Điểm C nữa.")
    assert res.draft.origin.verified is True
    assert res.draft.destination is not None
    assert res.draft.destination.label == "Điểm C"
    assert res.draft.destination.verified is False
    assert res.intended_action != "record_request"


def test_unverified_alley_blocks_auto_book():
    aggregate = ConversationAggregate(
        request_id="req-1",
        state_version=1,
        owner_generation=1,
        draft=BookingDraft(
            draft_id="draft-1",
            booking_revision=1,
            status=BookingStatus.COLLECTING,
            origin=LocationEvidence(
                label="ngõ 185 đường X",
                verified=False,
                components=LocationComponents(alley="185", street="đường X"),
            ),
            destination=LocationEvidence(label="Điểm B", verified=True),
            vehicle_type="4_seat",
            passengers=2,
        ),
    )
    proposal = {
        "acts": [
            {"type": ActType.REQUEST_BOOKING.value},
            {"type": ActType.SET_SLOT.value, "target": "driver_note", "value": "Khách khẳng định ngõ 185"},
        ]
    }
    policy = get_default_policy()

    res = reduce_turn_proposal(aggregate, proposal, policy, question_eligible_at_admission=False, raw_utterance="Đúng ngõ 185, cứ đặt đi.")
    assert res.draft.origin.components.alley == "185"
    assert res.draft.origin.verified is False
    assert res.intended_action != "record_request"
    assert res.draft.status != BookingStatus.REQUEST_RECORDED


def test_ambiguous_yes_on_hold():
    aggregate = ConversationAggregate(
        request_id="req-1",
        state_version=1,
        owner_generation=1,
        draft=BookingDraft(
            draft_id="draft-1",
            booking_revision=1,
            status=BookingStatus.COLLECTING,
            origin=LocationEvidence(label="Điểm A", verified=True),
            destination=LocationEvidence(label="Điểm B", verified=True),
            vehicle_type="4_seat",
            passengers=2,
        ),
        conversation_state=ConversationState(
            offered_question=OfferedQuestion(
                question_id="q_choice",
                kind="choose_location",
                target="destination",
                response_id="r_choice",
                options=["fixture:108", "fixture:103"],
            )
        ),
    )
    proposal = {
        "acts": [{"type": ActType.SOCIAL_RESPONSE.value}],
        "uncertainties": ["MULTIPLE_LIVE_OPTIONS"],
    }
    policy = get_default_policy()

    res = reduce_turn_proposal(aggregate, proposal, policy, question_eligible_at_admission=True, raw_utterance="Ừ đúng rồi.")
    assert res.next_question_kind == "disambiguate_location"
    assert res.intended_action != "record_request"
    assert res.draft.destination.label == "Điểm B"
