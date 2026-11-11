"""Unit tests for Geo port and number guard."""
import pytest

from src.conversation.domain.enums import Precision, CoordinateRole
from src.conversation.domain.models import LocationComponents
from src.conversation.ports.geo import GeoPort


def test_exact_catalog_match():
    geo = GeoPort()

    ev_origin = geo.resolve_location("12 phố Huế")
    assert ev_origin.verified is True
    assert ev_origin.candidate_id == "poi-12-pho-hue"
    assert ev_origin.components.house_number == "12"
    assert ev_origin.components.street == "Phố Huế"
    assert ev_origin.precision == Precision.ENTRANCE

    ev_dest = geo.resolve_location("Bờ Hồ")
    assert ev_dest.verified is True
    assert ev_dest.candidate_id == "poi-bo-ho"
    assert ev_dest.precision == Precision.EXACT_POI


def test_number_guard_blocks_mismatched_candidate():
    geo = GeoPort()

    # User asks for house 185 phố Huế (which does not exist in catalog; catalog only has house 12)
    comps = LocationComponents(house_number="185", street="Phố Huế")
    ev = geo.resolve_location("185 phố Huế", components=comps)

    # Number guard must ensure it does NOT match house 12!
    assert ev.candidate_id != "poi-12-pho-hue"
    assert ev.verified is False
    assert "house_number" in ev.unverified_components
    assert ev.components.house_number == "185"
    assert ev.components.street == "Phố Huế"
