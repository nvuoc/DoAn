"""Readiness evaluation function for booking drafts."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict

from src.conversation.domain.models import BookingDraft
from src.conversation.contract import BookingStatus


class ReadinessResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    can_offer_trip_confirmation: bool = False
    can_record_request: bool = False
    can_dispatch: bool = False
    missing_requirements: List[str] = Field(default_factory=list)
    blocking_evidence: List[str] = Field(default_factory=list)
    allowed_next_actions: List[str] = Field(default_factory=list)


def evaluate_readiness(
    draft: BookingDraft,
    policy: Dict[str, Any],
    confirmed_trip: bool = False,
) -> ReadinessResult:
    """Evaluate readiness of a booking draft against policy matrix.
    
    Invariants:
    1. POL-01: can_dispatch is False by default.
    2. POL-02: Origin, Destination, Vehicle type are required.
    3. POL-03: Unverified address blocks can_record_request unless allow_text_only_auto_booking=True.
    """
    missing = []
    blocking = []

    # Check required slots
    if draft.origin is None or not (draft.origin.label or draft.origin.components.street):
        missing.append("origin")
    elif not draft.origin.verified and not policy.get("allow_text_only_auto_booking", False):
        blocking.append("origin_unverified")

    if policy.get("destination_required", True):
        if draft.destination is None or not (draft.destination.label or draft.destination.components.street):
            missing.append("destination")
        elif not draft.destination.verified and not policy.get("allow_text_only_auto_booking", False):
            blocking.append("destination_unverified")

    allowed_vehicles = policy.get("vehicle_catalog", ["4_seat", "7_seat"])
    if not draft.vehicle_type or draft.vehicle_type not in allowed_vehicles:
        missing.append("vehicle_type")

    can_offer = len(missing) == 0
    can_record = can_offer and len(blocking) == 0 and confirmed_trip
    can_dispatch = False  # Always False under POL-01 baseline

    actions = []
    if missing:
        actions.append(f"ask_{missing[0]}")
    elif blocking:
        actions.append("clarify_unverified_location")
    elif not confirmed_trip:
        actions.append("confirm_trip")
    else:
        actions.append("record_request")

    return ReadinessResult(
        can_offer_trip_confirmation=can_offer,
        can_record_request=can_record,
        can_dispatch=can_dispatch,
        missing_requirements=missing,
        blocking_evidence=blocking,
        allowed_next_actions=actions,
    )
