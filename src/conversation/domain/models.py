"""Domain models and aggregate roots for vanuoc conversation core."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, ConfigDict

from src.conversation.contract import BookingStatus
from src.conversation.domain.enums import Precision, CoordinateRole


class LocationComponents(BaseModel):
    model_config = ConfigDict(extra="forbid")

    house_number: Optional[str] = None
    sub_alley: Optional[str] = None
    alley: Optional[str] = None
    street: Optional[str] = None
    landmark: Optional[str] = None
    ward: Optional[str] = None
    district: Optional[str] = None
    province: Optional[str] = None

    def format_label(self) -> str:
        parts = []
        if self.house_number:
            parts.append(f"số {self.house_number}")
        if self.sub_alley:
            parts.append(f"ngách {self.sub_alley}")
        if self.alley:
            parts.append(f"ngõ {self.alley}")
        if self.street:
            parts.append(self.street)
        if self.landmark:
            parts.append(self.landmark)
        if self.ward:
            parts.append(self.ward)
        if self.district:
            parts.append(self.district)
        if self.province:
            parts.append(self.province)
        return " ".join(parts).strip()


class LocationEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    location_version: int = 1
    verified: bool = False
    components: LocationComponents = Field(default_factory=LocationComponents)
    candidate_id: Optional[str] = None
    precision: Precision = Precision.UNKNOWN
    coordinate_role: Optional[CoordinateRole] = None
    coordinate: Optional[Dict[str, float]] = None
    unverified_components: List[str] = Field(default_factory=list)
    raw_utterances: List[str] = Field(default_factory=list)


class BookingDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_id: str
    booking_revision: int = 0
    status: BookingStatus = BookingStatus.COLLECTING
    origin: Optional[LocationEvidence] = None
    destination: Optional[LocationEvidence] = None
    vehicle_type: Optional[str] = None
    passengers: Optional[int] = None
    pickup_time: Optional[str] = None
    driver_note: Optional[str] = None
    stops: List[LocationEvidence] = Field(default_factory=list)
    contact: Optional[str] = None


class SuspendedContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    target: Optional[str] = None
    candidate_id: Optional[str] = None
    location_version: Optional[int] = None
    booking_revision: Optional[int] = None
    status: str = "on_hold"
    reason: Optional[str] = None


class OfferedQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    kind: str
    target: Union[str, Dict[str, Any]]
    response_id: str
    segment_id: Optional[str] = None
    location_version: Optional[int] = None
    booking_revision: Optional[int] = None
    values_digest: Optional[str] = None
    policy_version: Optional[str] = None
    options: List[str] = Field(default_factory=list)


class ConversationPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reply_length: str = "normal"
    speech_rate: float = 1.0


class ConversationState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    focus_endpoint: Optional[str] = None
    offered_question: Optional[OfferedQuestion] = None
    suspended_contexts: List[SuspendedContext] = Field(default_factory=list, max_length=4)
    preferences: ConversationPreferences = Field(default_factory=ConversationPreferences)
    unresolved_issues: List[str] = Field(default_factory=list)
    recent_delivered_history: List[Dict[str, Any]] = Field(default_factory=list)


class ConversationAggregate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    state_version: int = 0
    owner_generation: int = 1
    draft: BookingDraft
    conversation_state: ConversationState = Field(default_factory=ConversationState)
    active_session_id: Optional[str] = None
