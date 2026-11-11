"""Policy matrix rule evaluator for POL-T01 through POL-T10."""
from __future__ import annotations

from typing import Any, Dict
from src.conversation.domain.models import BookingDraft
from src.conversation.contract import BookingStatus


def check_pol_t01_pure_inquiry_preserves_booking(
    before_draft: BookingDraft,
    after_draft: BookingDraft,
) -> bool:
    """POL-T01: Pure inquiry preserves booking slots and semantic revision."""
    return (
        before_draft.booking_revision == after_draft.booking_revision
        and before_draft.origin == after_draft.origin
        and before_draft.destination == after_draft.destination
        and before_draft.vehicle_type == after_draft.vehicle_type
    )


def check_pol_t02_unverified_address_blocks_auto_book(
    draft: BookingDraft,
    policy: Dict[str, Any],
) -> bool:
    """POL-T02: customer_confirmed of unverified address still blocked from auto-booking."""
    if not policy.get("allow_text_only_auto_booking", False):
        if draft.origin and not draft.origin.verified:
            return draft.status != BookingStatus.REQUEST_RECORDED
        if draft.destination and not draft.destination.verified:
            return draft.status != BookingStatus.REQUEST_RECORDED
    return True


def check_pol_t07_missing_tariff_no_fare(
    fare_estimate: Any,
    policy: Dict[str, Any],
) -> bool:
    """POL-T07: When tariff is missing or null, fare estimate must be null / unavailable."""
    if policy.get("tariff") is None:
        return fare_estimate is None
    return True
