"""Authoritative Geo port and mock resolver honoring Vietnamese address constraints."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from src.conversation.domain.enums import Precision, CoordinateRole
from src.conversation.domain.models import LocationComponents, LocationEvidence


class GeoCandidate:
    def __init__(
        self,
        candidate_id: str,
        label: str,
        components: LocationComponents,
        verified: bool = True,
        precision: Precision = Precision.EXACT_POI,
        coordinate_role: CoordinateRole = CoordinateRole.ENTRANCE,
        coordinate: Optional[Dict[str, float]] = None,
        unverified_components: Optional[List[str]] = None,
        parent_poi: Optional[str] = None,
    ):
        self.candidate_id = candidate_id
        self.label = label
        self.components = components
        self.verified = verified
        self.precision = precision
        self.coordinate_role = coordinate_role
        self.coordinate = coordinate or {"lat": 21.0285, "lng": 105.8542}
        self.unverified_components = unverified_components or []
        self.parent_poi = parent_poi


# Standard fixture catalog for testing & conservative development baseline
FIXTURE_CATALOG: Dict[str, GeoCandidate] = {
    "12 phố huế": GeoCandidate(
        candidate_id="poi-12-pho-hue",
        label="12 Phố Huế, Hoàn Kiếm, Hà Nội",
        components=LocationComponents(
            house_number="12",
            street="Phố Huế",
            district="Hoàn Kiếm",
            province="Hà Nội",
        ),
        verified=True,
        precision=Precision.ENTRANCE,
        coordinate_role=CoordinateRole.ENTRANCE,
        coordinate={"lat": 21.0185, "lng": 105.8525},
    ),
    "bờ hồ": GeoCandidate(
        candidate_id="poi-bo-ho",
        label="Hồ Hoàn Kiếm (Bờ Hồ), Hà Nội",
        components=LocationComponents(
            landmark="Hồ Hoàn Kiếm",
            district="Hoàn Kiếm",
            province="Hà Nội",
        ),
        verified=True,
        precision=Precision.EXACT_POI,
        coordinate_role=CoordinateRole.POI_POINT,
        coordinate={"lat": 21.0287, "lng": 105.8523},
    ),
    "hồ hoàn kiếm": GeoCandidate(
        candidate_id="poi-bo-ho",
        label="Hồ Hoàn Kiếm (Bờ Hồ), Hà Nội",
        components=LocationComponents(
            landmark="Hồ Hoàn Kiếm",
            district="Hoàn Kiếm",
            province="Hà Nội",
        ),
        verified=True,
        precision=Precision.EXACT_POI,
        coordinate_role=CoordinateRole.POI_POINT,
        coordinate={"lat": 21.0287, "lng": 105.8523},
    ),
    "sân bay nội bài": GeoCandidate(
        candidate_id="poi-san-bay-noi-bai",
        label="Cảng hàng không quốc tế Nội Bài, Sóc Sơn, Hà Nội",
        components=LocationComponents(
            landmark="Sân bay Nội Bài",
            district="Sóc Sơn",
            province="Hà Nội",
        ),
        verified=True,
        precision=Precision.EXACT_POI,
        coordinate_role=CoordinateRole.ACCESS_POINT,
        coordinate={"lat": 21.2212, "lng": 105.8072},
    ),
    "bệnh viện bạch mai": GeoCandidate(
        candidate_id="poi-bv-bach-mai",
        label="Bệnh viện Bạch Mai, 78 Giải Phóng, Phương Mai, Đống Đa, Hà Nội",
        components=LocationComponents(
            house_number="78",
            street="Giải Phóng",
            landmark="Bệnh viện Bạch Mai",
            ward="Phương Mai",
            district="Đống Đa",
            province="Hà Nội",
        ),
        verified=True,
        precision=Precision.EXACT_POI,
        coordinate_role=CoordinateRole.ENTRANCE,
        coordinate={"lat": 20.9998, "lng": 105.8407},
    ),
    "ngõ 132 cầu diễn": GeoCandidate(
        candidate_id="poi-ngo-132-cau-dien",
        label="Ngõ 132 Cầu Diễn, Bắc Từ Liêm, Hà Nội",
        components=LocationComponents(
            alley="132",
            street="Cầu Diễn",
            district="Bắc Từ Liêm",
            province="Hà Nội",
        ),
        verified=True,
        precision=Precision.ALLEY,
        coordinate_role=CoordinateRole.ROUTE_ANCHOR,
        coordinate={"lat": 21.0425, "lng": 105.7531},
    ),
    "keangnam": GeoCandidate(
        candidate_id="poi-keangnam",
        label="Keangnam Landmark 72, Phạm Hùng, Nam Từ Liêm, Hà Nội",
        components=LocationComponents(
            landmark="Keangnam Landmark 72",
            street="Phạm Hùng",
            district="Nam Từ Liêm",
            province="Hà Nội",
        ),
        verified=True,
        precision=Precision.EXACT_POI,
        coordinate_role=CoordinateRole.ACCESS_POINT,
        coordinate={"lat": 21.0173, "lng": 105.7838},
    ),
}


class GeoPort:
    def __init__(self, catalog: Optional[Dict[str, GeoCandidate]] = None):
        self.catalog = catalog or FIXTURE_CATALOG

    def resolve_location(
        self,
        query: str,
        components: Optional[LocationComponents] = None,
    ) -> LocationEvidence:
        """Resolve location query and components into verified/unverified LocationEvidence.

        Enforces Number Guard:
        - Exact number check: '185 phố Huế' does not match '18 phố Huế'.
        - If house/alley number is not found in catalog, return unverified components.
        """
        clean_query = query.lower().strip()
        comps = components.model_copy() if components else LocationComponents()

        # 1. Exact catalog match
        for key, cand in self.catalog.items():
            if key in clean_query or clean_query in key:
                # Number Guard check: if user asked for a house number, verify it matches candidate
                if comps.house_number:
                    if cand.components.house_number and cand.components.house_number != comps.house_number:
                        # Mismatched house number! E.g. 185 vs 18
                        continue
                if comps.alley:
                    if cand.components.alley and cand.components.alley != comps.alley:
                        continue

                return LocationEvidence(
                    label=cand.label,
                    location_version=1,
                    verified=cand.verified,
                    components=cand.components.model_copy(),
                    candidate_id=cand.candidate_id,
                    precision=cand.precision,
                    coordinate_role=cand.coordinate_role,
                    coordinate=cand.coordinate,
                    unverified_components=cand.unverified_components,
                )

        # 2. Number guard fallback for unverified house numbers or alleys
        # E.g. "185 phố Huế" when map only has "phố Huế"
        m_house = re.search(r"(?:số\s+)?(\d+[a-zA-Z]?)(?:\s+(?:phố|đường)\s+([\w\s]+))?", clean_query)
        if m_house and not comps.house_number:
            comps.house_number = m_house.group(1)
            if m_house.group(2) and not comps.street:
                comps.street = m_house.group(2).strip().title()

        m_alley = re.search(r"ngõ\s+(\d+[a-zA-Z]?)", clean_query)
        if m_alley and not comps.alley:
            comps.alley = m_alley.group(1)

        m_sub = re.search(r"ngách\s+(\d+[a-zA-Z]?)", clean_query)
        if m_sub and not comps.sub_alley:
            comps.sub_alley = m_sub.group(1)

        unverified = []
        if comps.house_number:
            unverified.append("house_number")
        if comps.sub_alley:
            unverified.append("sub_alley")
        if comps.alley and not any(key for key in self.catalog if f"ngõ {comps.alley}" in key):
            unverified.append("alley")

        label = comps.format_label() or query
        precision = Precision.STREET if comps.street else Precision.TEXT_ONLY
        if comps.alley:
            precision = Precision.ALLEY

        return LocationEvidence(
            label=label,
            location_version=1,
            verified=(len(unverified) == 0 and bool(comps.street or comps.landmark)),
            components=comps,
            candidate_id=None,
            precision=precision,
            coordinate_role=CoordinateRole.ROUTE_ANCHOR,
            coordinate={"lat": 21.0285, "lng": 105.8542},
            unverified_components=unverified,
        )
