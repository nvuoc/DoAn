"""Domain enums for vanuoc conversation core."""
from enum import Enum


class ActType(str, Enum):
    REQUEST_BOOKING = "REQUEST_BOOKING"
    SET_SLOT = "SET_SLOT"
    REPLACE_SLOT = "REPLACE_SLOT"
    MERGE_SLOT_COMPONENT = "MERGE_SLOT_COMPONENT"
    CLEAR_SLOT = "CLEAR_SLOT"
    REQUEST_CANCEL = "REQUEST_CANCEL"
    CONFIRM_PENDING = "CONFIRM_PENDING"
    REJECT_PENDING = "REJECT_PENDING"
    ASK_INFORMATION = "ASK_INFORMATION"
    REQUEST_REPEAT = "REQUEST_REPEAT"
    REQUEST_RECALL = "REQUEST_RECALL"
    SET_PREFERENCE = "SET_PREFERENCE"
    DECLINE_TO_ANSWER = "DECLINE_TO_ANSWER"
    EXPRESS_UNCERTAINTY = "EXPRESS_UNCERTAINTY"
    REQUEST_OPERATOR = "REQUEST_OPERATOR"
    SOCIAL_RESPONSE = "SOCIAL_RESPONSE"


class SlotName(str, Enum):
    ORIGIN = "origin"
    DESTINATION = "destination"
    VEHICLE_TYPE = "vehicle_type"
    PASSENGERS = "passengers"
    PICKUP_TIME = "pickup_time"
    STOPS = "stops"
    DRIVER_NOTE = "driver_note"
    CONTACT = "contact"
    PICKUP_LANDMARK = "pickup_landmark"


class SlotKnowledgeStatus(str, Enum):
    MISSING = "missing"
    KNOWN = "known"
    UNKNOWN_BY_CUSTOMER = "unknown_by_customer"
    DECLINED = "declined"
    INFERRED_UNCONFIRMED = "inferred_unconfirmed"
    NOT_APPLICABLE = "not_applicable"


class Precision(str, Enum):
    ENTRANCE = "ENTRANCE"
    EXACT_POI = "EXACT_POI"
    ALLEY = "ALLEY"
    STREET = "STREET"
    WARD = "WARD"
    AREA = "AREA"
    TEXT_ONLY = "TEXT_ONLY"
    UNKNOWN = "UNKNOWN"


class CoordinateRole(str, Enum):
    ENTRANCE = "entrance"
    ACCESS_POINT = "access_point"
    POI_POINT = "poi_point"
    AREA_REPRESENTATIVE = "area_representative"
    ROUTE_ANCHOR = "route_anchor"


class PlaceMentionUsage(str, Enum):
    BOOKING_ORIGIN = "BOOKING_ORIGIN"
    BOOKING_DESTINATION = "BOOKING_DESTINATION"
    BOOKING_STOP = "BOOKING_STOP"
    INFORMATION_LOOKUP = "INFORMATION_LOOKUP"
    ESTIMATE_ENDPOINT = "ESTIMATE_ENDPOINT"
    SEARCH_REGION = "SEARCH_REGION"
    DIALOGUE_FOCUS_ONLY = "DIALOGUE_FOCUS_ONLY"
    UNRESOLVED = "UNRESOLVED"
