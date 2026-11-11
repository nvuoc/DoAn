"""Unit tests for address merger and component invalidation."""
from src.conversation.reducer.address_merger import merge_location_components
from src.conversation.domain.models import LocationEvidence, LocationComponents


def test_three_turn_merge_and_idempotence():
    # Turn 1: house number and sub alley
    loc1 = merge_location_components(None, {"house_number": "18", "sub_alley": "16"}, raw_utterance="số 18 ngách 16")
    assert loc1.components.house_number == "18"
    assert loc1.components.sub_alley == "16"
    assert loc1.location_version == 1

    # Turn 2: alley and street
    loc2 = merge_location_components(loc1, {"alley": "51", "street": "đường X"}, raw_utterance="ngõ 51 đường X")
    assert loc2.components.house_number == "18"
    assert loc2.components.sub_alley == "16"
    assert loc2.components.alley == "51"
    assert loc2.components.street == "đường X"
    assert loc2.location_version == 2

    # Turn 3: landmark
    loc3 = merge_location_components(loc2, {"landmark": "đối diện quán P"}, raw_utterance="đối diện quán P")
    assert loc3.components.landmark == "đối diện quán P"
    assert loc3.location_version == 3
    assert "đối diện quán P" in loc3.label

    # Retry Turn 2 with identical components -> location_version must NOT change
    loc_retry = merge_location_components(loc3, {"alley": "51", "street": "đường X"})
    assert loc_retry.location_version == loc3.location_version
    assert loc_retry.components == loc3.components


def test_street_change_invalidates_sub_components():
    initial = LocationEvidence(
        label="số 18 ngách 16 ngõ 51 đường X",
        location_version=1,
        verified=True,
        components=LocationComponents(
            house_number="18",
            sub_alley="16",
            alley="51",
            street="đường X",
        ),
    )

    # Change street to "đường Y"
    updated = merge_location_components(initial, {"street": "đường Y"})
    assert updated.components.street == "đường Y"
    assert updated.components.house_number is None
    assert updated.components.sub_alley is None
    assert updated.components.alley is None
    assert updated.verified is False
    assert updated.location_version == 2
