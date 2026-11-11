"""Conservative development baseline policy bundle."""
from typing import Any, Dict


DEVELOPMENT_CONSERVATIVE_POLICY: Dict[str, Any] = {
    "policy_version": "development_conservative_3_0",
    "destination_required": True,
    "allow_text_only_auto_booking": False,
    "handoff_enabled": False,
    "vehicle_catalog": ["4_seat", "7_seat"],
    "tariff": None,
    "dispatch_enabled": False,
    "max_clarification_no_progress": 2,
    "max_suspended_contexts": 4,
}


def get_default_policy() -> Dict[str, Any]:
    return dict(DEVELOPMENT_CONSERVATIVE_POLICY)
