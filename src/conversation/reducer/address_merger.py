"""Idempotent component-level address merger for Vietnamese locations."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Optional, Union

from src.conversation.domain.models import LocationComponents, LocationEvidence
from src.conversation.domain.enums import Precision


def merge_location_components(
    existing: Optional[LocationEvidence],
    patch: Union[Dict[str, Any], str, LocationComponents],
    raw_utterance: Optional[str] = None,
    candidate_id: Optional[str] = None,
    verified: Optional[bool] = None,
) -> LocationEvidence:
    """Merge address components at component level (MERGE_SLOT_COMPONENT).
    
    Invariants:
    1. If street changes, previous house_number, sub_alley, alley are cleared.
    2. If house_number changes, previous house_number is replaced and verification resets.
    3. Adding landmark does not imply coordinate verification.
    4. Merging is idempotent: applying identical components does not increment location_version.
    """
    if existing is None:
        loc = LocationEvidence(
            label="",
            location_version=1,
            verified=False,
            components=LocationComponents(),
            candidate_id=candidate_id,
            precision=Precision.UNKNOWN,
        )
    else:
        loc = deepcopy(existing)

    if raw_utterance and raw_utterance not in loc.raw_utterances:
        loc.raw_utterances.append(raw_utterance)

    if isinstance(patch, str):
        # Plain text replacement / initial label
        if loc.label != patch:
            loc.label = patch
            loc.location_version += 1
            loc.verified = False if verified is None else verified
        if candidate_id:
            loc.candidate_id = candidate_id
        return loc

    patch_dict = patch.model_dump() if isinstance(patch, LocationComponents) else patch

    changed = False
    
    # 1. Check street change
    new_street = patch_dict.get("street")
    if new_street is not None:
        if loc.components.street != new_street:
            if loc.components.street is not None:
                # An existing street was replaced by another street: invalidate house_number, alley, sub_alley
                loc.components.house_number = None
                loc.components.sub_alley = None
                loc.components.alley = None
                loc.verified = False
            loc.components.street = new_street
            changed = True

    # 2. Check house number
    new_house = patch_dict.get("house_number")
    if new_house is not None:
        if loc.components.house_number != new_house:
            loc.components.house_number = str(new_house)
            loc.verified = False
            changed = True

    # 3. Check alley
    new_alley = patch_dict.get("alley")
    if new_alley is not None:
        if loc.components.alley != str(new_alley):
            loc.components.alley = str(new_alley)
            changed = True

    # 4. Check sub_alley
    new_sub_alley = patch_dict.get("sub_alley")
    if new_sub_alley is not None:
        if loc.components.sub_alley != str(new_sub_alley):
            loc.components.sub_alley = str(new_sub_alley)
            changed = True

    # 5. Check landmark
    new_landmark = patch_dict.get("landmark")
    if new_landmark is not None:
        if loc.components.landmark != new_landmark:
            loc.components.landmark = new_landmark
            changed = True

    # 6. Check ward, district, province
    for field in ("ward", "district", "province"):
        val = patch_dict.get(field)
        if val is not None and getattr(loc.components, field) != val:
            setattr(loc.components, field, val)
            changed = True

    if candidate_id and loc.candidate_id != candidate_id:
        loc.candidate_id = candidate_id
        changed = True

    if verified is not None and loc.verified != verified:
        loc.verified = verified
        changed = True

    if existing is not None and changed:
        loc.location_version += 1

    # Update formatted label if components exist
    formatted = loc.components.format_label()
    if formatted:
        loc.label = formatted
    elif not loc.label and raw_utterance:
        loc.label = raw_utterance

    return loc
