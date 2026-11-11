"""Deterministic state reducer for whole-turn processing."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

from src.conversation.contract import BookingStatus
from src.conversation.domain.enums import ActType, SlotName, Precision
from src.conversation.domain.models import (
    BookingDraft,
    ConversationAggregate,
    ConversationState,
    LocationEvidence,
    LocationComponents,
    OfferedQuestion,
    SuspendedContext,
)
from src.conversation.reducer.address_merger import merge_location_components
from src.conversation.reducer.readiness import evaluate_readiness


class ReductionResult:
    def __init__(
        self,
        draft: BookingDraft,
        conversation_state: ConversationState,
        intended_action: str,
        confirmed_trip: bool = False,
        trip_summary_invalidated: bool = False,
        next_question_kind: Optional[str] = None,
    ):
        self.draft = draft
        self.conversation_state = conversation_state
        self.intended_action = intended_action
        self.confirmed_trip = confirmed_trip
        self.trip_summary_invalidated = trip_summary_invalidated
        self.next_question_kind = next_question_kind


def reduce_turn_proposal(
    aggregate: ConversationAggregate,
    proposal: Dict[str, Any],
    policy: Dict[str, Any],
    question_eligible_at_admission: bool,
    raw_utterance: str,
) -> ReductionResult:
    """Fold a validated whole-turn proposal into domain state.
    
    Adheres strictly to whole-turn ordering and dependency invariants:
    - Pure inquiry/repeat does not mutate booking draft or booking_revision.
    - Confirm + edit within the same turn invalidates trip confirmation; does not submit old summary.
    - Confirm location does not auto-confirm trip.
    - Ambiguous 'yes' after choice does not select previous pending.
    """
    draft = deepcopy(aggregate.draft)
    conv_state = deepcopy(aggregate.conversation_state)
    
    acts: List[Dict[str, Any]] = proposal.get("acts", [])
    uncertainties: List[str] = proposal.get("uncertainties", [])
    rejected_candidates: List[str] = proposal.get("rejected_candidates", [])
    hypotheses: List[Dict[str, Any]] = proposal.get("hypotheses", [])

    # Check for pure non-mutating turn
    non_mutating_acts = {
        ActType.ASK_INFORMATION.value,
        ActType.REQUEST_REPEAT.value,
        ActType.REQUEST_RECALL.value,
        ActType.SOCIAL_RESPONSE.value,
        ActType.SET_PREFERENCE.value,
    }
    has_mutation = any(
        act.get("type") not in non_mutating_acts
        for act in acts
    )

    if not has_mutation:
        # No mutating acts (e.g. pure inquiry, repeat, social)
        if any(act.get("type") == ActType.REQUEST_RECALL.value for act in acts):
            return ReductionResult(
                draft=draft,
                conversation_state=conv_state,
                intended_action="recall",
            )
        if "MULTIPLE_LIVE_OPTIONS" in uncertainties or (conv_state.offered_question and conv_state.offered_question.options):
            return ReductionResult(
                draft=draft,
                conversation_state=conv_state,
                intended_action="clarify",
                next_question_kind="disambiguate_location",
            )
        return ReductionResult(
            draft=draft,
            conversation_state=conv_state,
            intended_action="none",
        )

    # Track slot changes during this turn
    slots_modified = set()
    trip_confirm_attempted = False
    location_confirm_attempted = False
    confirmed_trip = False
    trip_summary_invalidated = False
    next_question_kind = None

    # Step 1: Process acts in order
    for act in acts:
        act_type = act.get("type")
        target = act.get("target")
        value = act.get("value")

        if act_type in (ActType.SET_SLOT.value, ActType.REPLACE_SLOT.value):
            if target == SlotName.ORIGIN.value:
                draft.origin = merge_location_components(draft.origin, value, raw_utterance=raw_utterance)
                slots_modified.add("origin")
                draft.booking_revision += 1
            elif target == SlotName.DESTINATION.value:
                draft.destination = merge_location_components(draft.destination, value, raw_utterance=raw_utterance)
                slots_modified.add("destination")
                draft.booking_revision += 1
            elif target == SlotName.VEHICLE_TYPE.value:
                draft.vehicle_type = str(value)
                slots_modified.add("vehicle_type")
                draft.booking_revision += 1
            elif target == SlotName.PASSENGERS.value:
                draft.passengers = int(value)
                slots_modified.add("passengers")
                draft.booking_revision += 1
            elif target == SlotName.DRIVER_NOTE.value:
                draft.driver_note = str(value)
                slots_modified.add("driver_note")
                draft.booking_revision += 1
            elif target == SlotName.PICKUP_TIME.value:
                draft.pickup_time = str(value)
                slots_modified.add("pickup_time")
                draft.booking_revision += 1

        elif act_type == ActType.MERGE_SLOT_COMPONENT.value:
            if target == SlotName.ORIGIN.value:
                draft.origin = merge_location_components(draft.origin, value, raw_utterance=raw_utterance)
                slots_modified.add("origin")
                draft.booking_revision += 1
            elif target == SlotName.DESTINATION.value:
                draft.destination = merge_location_components(draft.destination, value, raw_utterance=raw_utterance)
                slots_modified.add("destination")
                draft.booking_revision += 1

        elif act_type == ActType.CLEAR_SLOT.value:
            if target == SlotName.ORIGIN.value:
                draft.origin = None
                slots_modified.add("origin")
                draft.booking_revision += 1
            elif target == SlotName.DESTINATION.value:
                draft.destination = None
                slots_modified.add("destination")
                draft.booking_revision += 1

        elif act_type == ActType.REQUEST_CANCEL.value:
            if draft.status in (BookingStatus.COLLECTING, BookingStatus.AWAITING_CONFIRMATION):
                draft.status = BookingStatus.CANCELLED
                draft.booking_revision += 1
                return ReductionResult(
                    draft=draft,
                    conversation_state=conv_state,
                    intended_action="cancel_draft",
                )

        elif act_type == ActType.CONFIRM_PENDING.value:
            # Check eligibility at admission
            if question_eligible_at_admission and conv_state.offered_question:
                q = conv_state.offered_question
                if q.kind == "confirm_trip":
                    trip_confirm_attempted = True
                elif q.kind == "confirm_location":
                    location_confirm_attempted = True
                    target_slot = q.target if isinstance(q.target, str) else q.target.get("slot")
                    if target_slot == "origin" and "origin" not in slots_modified and draft.origin:
                        draft.origin.verified = True
                    elif target_slot == "destination" and "destination" not in slots_modified and draft.destination:
                        draft.destination.verified = True

        elif act_type == ActType.REJECT_PENDING.value:
            if conv_state.offered_question:
                q = conv_state.offered_question
                target_slot = q.target if isinstance(q.target, str) else q.target.get("slot")
                if target_slot == "origin" and draft.origin:
                    draft.origin.verified = False
                elif target_slot == "destination" and draft.destination:
                    draft.destination.verified = False

        elif act_type == ActType.ASK_INFORMATION.value:
            topic = act.get("topic")
            referents = act.get("referents", [])
            # Pure inquiry does not change booking slots or destination
            conv_state.focus_endpoint = "inquiry"

        elif act_type == ActType.REQUEST_RECALL.value:
            conv_state.focus_endpoint = "recall"

        elif act_type == ActType.EXPRESS_UNCERTAINTY.value:
            uncertainties.append("EXPRESS_UNCERTAINTY")

    # Step 2: Whole-turn Causality & Dependency Checks
    if trip_confirm_attempted:
        if slots_modified:
            # Confirm + edit in the same turn!
            # The old trip summary is INVALIDATED. We do NOT submit the old booking.
            trip_summary_invalidated = True
            draft.status = BookingStatus.AWAITING_CONFIRMATION
            next_question_kind = "confirm_trip"
        else:
            # Valid trip confirmation without conflicting edits
            confirmed_trip = True

    # Step 3: Handle ambiguous ack or multiple live options
    if "MULTIPLE_LIVE_OPTIONS" in uncertainties:
        next_question_kind = "disambiguate_location"

    # Step 4: Handle branch ambiguity
    if hypotheses:
        for hyp in hypotheses:
            if hyp.get("kind") == "spoken_alias":
                next_question_kind = "disambiguate_location"
                if draft.destination:
                    draft.destination.verified = False

    # Step 5: Check Readiness
    readiness = evaluate_readiness(draft, policy, confirmed_trip=confirmed_trip)
    
    intended_action = "none"
    if any(act.get("type") == ActType.REQUEST_RECALL.value for act in acts):
        intended_action = "recall"
    elif next_question_kind == "disambiguate_location":
        draft.status = BookingStatus.COLLECTING
        intended_action = "clarify"
    elif readiness.can_record_request:
        draft.status = BookingStatus.REQUEST_RECORDED
        intended_action = "record_request"
    elif readiness.can_offer_trip_confirmation:
        draft.status = BookingStatus.AWAITING_CONFIRMATION
        if not next_question_kind:
            next_question_kind = "confirm_trip"
        intended_action = "offer_confirmation"
    elif readiness.missing_requirements:
        draft.status = BookingStatus.COLLECTING
        if not next_question_kind:
            next_question_kind = f"ask_{readiness.missing_requirements[0]}"
        intended_action = "collect_info"

    return ReductionResult(
        draft=draft,
        conversation_state=conv_state,
        intended_action=intended_action,
        confirmed_trip=confirmed_trip,
        trip_summary_invalidated=trip_summary_invalidated,
        next_question_kind=next_question_kind,
    )
