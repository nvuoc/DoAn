"""Unit tests for policy invariants."""
from copy import deepcopy
from src.conversation.contract import BookingStatus
from src.conversation.domain.models import BookingDraft, LocationEvidence
from src.conversation.policy.baseline import get_default_policy
from src.conversation.policy.evaluator import (
    check_pol_t01_pure_inquiry_preserves_booking,
    check_pol_t02_unverified_address_blocks_auto_book,
    check_pol_t07_missing_tariff_no_fare,
)


def test_policy_invariants():
    draft1 = BookingDraft(
        draft_id="d-1",
        booking_revision=1,
        origin=LocationEvidence(label="Hà Nội", verified=True),
        destination=LocationEvidence(label="Hải Phòng", verified=True),
        vehicle_type="4_seat",
    )
    draft2 = deepcopy(draft1)
    
    # POL-T01: pure inquiry preserves booking slots
    assert check_pol_t01_pure_inquiry_preserves_booking(draft1, draft2) is True

    # POL-T02: unverified address cannot be REQUEST_RECORDED under baseline
    policy = get_default_policy()
    draft_unverified = deepcopy(draft1)
    draft_unverified.origin.verified = False
    draft_unverified.status = BookingStatus.REQUEST_RECORDED
    assert check_pol_t02_unverified_address_blocks_auto_book(draft_unverified, policy) is False

    # POL-T07: missing tariff must have no fare
    assert check_pol_t07_missing_tariff_no_fare(None, policy) is True
    assert check_pol_t07_missing_tariff_no_fare(150000, policy) is False
