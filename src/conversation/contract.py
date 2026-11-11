"""Vanuoc v3.0 core contract DTOs, schemas, and canonical validation logic."""
from __future__ import annotations

from enum import Enum
import hashlib
import json
import re
from typing import Any, Dict, List, Literal, Optional, Union
import uuid

from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator

from src.conversation.errors import ErrorCode, ErrorDetail

ID_REGEX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


def validate_id(v: str) -> str:
    if not (1 <= len(v) <= 128) or not ID_REGEX.match(v):
        raise ValueError(f"Invalid ID format: '{v}' (must match {ID_REGEX.pattern} and length 1-128)")
    return v


# ==========================================
# Enums
# ==========================================

class Channel(str, Enum):
    VOICE = "voice"
    WEB = "web"
    CLI = "cli"


class ActorType(str, Enum):
    CUSTOMER = "customer"
    OPERATOR = "operator"
    SYSTEM = "system"


class AuthorizedScope(str, Enum):
    CONVERSATION_READ = "conversation:read"
    CONVERSATION_WRITE = "conversation:write"
    DELIVERY_WRITE = "delivery:write"
    OWNERSHIP_WRITE = "ownership:write"
    REQUEST_RESUME = "request:resume"


class InputTimingOverlap(str, Enum):
    NO_OVERLAP = "no_overlap"
    OVERLAPPING = "overlapping"
    UNKNOWN = "unknown"


class InputTimingBasis(str, Enum):
    VOICE_ADAPTER = "voice_adapter"
    TEXT_ADAPTER = "text_adapter"
    UNKNOWN = "unknown"


class TurnStatus(str, Enum):
    COMMITTED = "committed"
    REPLAYED = "replayed"
    CANCELLED = "cancelled"
    STALE = "stale"
    DEADLINE_EXCEEDED = "deadline_exceeded"
    RETRYABLE_ERROR = "retryable_error"
    REJECTED = "rejected"


class BookingStatus(str, Enum):
    COLLECTING = "collecting"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    SUBMITTING = "submitting"
    REQUEST_RECORDED = "request_recorded"
    CANCEL_PENDING = "cancel_pending"
    CANCELLED = "cancelled"
    OPERATOR_REQUIRED = "operator_required"
    SUBMIT_FAILED = "submit_failed"


class Profile(str, Enum):
    FIXTURE = "fixture"
    SANDBOX = "sandbox"
    CONNECTED = "connected"


class BusinessOutcomeKind(str, Enum):
    NONE = "none"
    DRAFT_UPDATED = "draft_updated"
    REQUEST_RECORDED = "request_recorded"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    OPERATOR_REQUIRED = "operator_required"
    SUBMIT_FAILED = "submit_failed"
    UNKNOWN_OUTCOME = "unknown_outcome"
    DISPATCH_CONFIRMED = "dispatch_confirmed"


class DispatchStatus(str, Enum):
    NOT_REQUESTED = "not_requested"
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    FAILED = "failed"


class DeliveryReason(str, Enum):
    COMMITTED_CURRENT = "committed_current"
    REPLAYED_CURRENT = "replayed_current"
    SUPERSEDED = "superseded"
    NO_RESPONSE = "no_response"
    NOT_COMMITTED = "not_committed"


class SegmentKind(str, Enum):
    ANSWER = "answer"
    ACKNOWLEDGMENT = "acknowledgment"
    STATUS = "status"
    QUESTION = "question"


class ClaimScope(str, Enum):
    CONVERSATION = "conversation"
    INTAKE = "intake"
    DISPATCH = "dispatch"
    ESTIMATE = "estimate"
    NONE = "none"


class QuestionKind(str, Enum):
    CONFIRM_LOCATION = "confirm_location"
    CONFIRM_TRIP = "confirm_trip"
    CHOOSE_CANDIDATE = "choose_candidate"
    DISAMBIGUATE_LOCATION = "disambiguate_location"
    CLARIFY_SLOT = "clarify_slot"
    CONFIRM_CANCEL = "confirm_cancel"
    RESUME_CHOICE = "resume_choice"
    SUPPORT_CHOICE = "support_choice"
    CLARIFY_REFERENCE = "clarify_reference"


class ControlEventKind(str, Enum):
    DELIVERY = "delivery"
    INTERRUPT = "interrupt"
    TIMEOUT = "timeout"
    SESSION_END = "session_end"
    OWNERSHIP_CHANGED = "ownership_changed"


class DeliveryEventType(str, Enum):
    PLAYBACK_STARTED = "playback_started"
    PLAYBACK_COMPLETED = "playback_completed"
    OUTPUT_AVAILABLE = "output_available"
    OUTPUT_UNAVAILABLE = "output_unavailable"
    PLAYBACK_INTERRUPTED = "playback_interrupted"
    PLAYBACK_FAILED = "playback_failed"
    TEXT_PRESENTED = "text_presented"


class DeliveryMode(str, Enum):
    VOICE = "voice"
    TEXT = "text"


class DeliveryReporter(str, Enum):
    SERVER_ADAPTER = "server_adapter"
    CLIENT_ADAPTER = "client_adapter"


# ==========================================
# TurnInput Models
# ==========================================

class Actor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor_id: str
    actor_type: ActorType
    authorized_scopes: List[AuthorizedScope] = Field(default_factory=list, max_length=32)

    @field_validator("actor_id")
    def check_actor_id(cls, v: str) -> str:
        return validate_id(v)


class PresentationRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    response_id: str
    segment_id: str
    playback_id: Optional[str] = None
    presentation_event_id: str

    @field_validator("question_id", "response_id", "segment_id", "presentation_event_id")
    def check_ids(cls, v: str) -> str:
        return validate_id(v)

    @field_validator("playback_id")
    def check_playback_id(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return validate_id(v)
        return None


class ASRAlternative(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., min_length=1, max_length=8000)
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)


class ASRInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(..., min_length=1, max_length=128)
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    alternatives: List[ASRAlternative] = Field(default_factory=list, max_length=5)


class SourceEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel: Channel
    adapter_id: str
    source_segment_ids: List[str] = Field(default_factory=list, max_length=32)
    asr: Optional[ASRInfo] = None

    @field_validator("adapter_id")
    def check_adapter_id(cls, v: str) -> str:
        return validate_id(v)

    @field_validator("source_segment_ids")
    def check_segment_ids(cls, v: List[str]) -> List[str]:
        for item in v:
            validate_id(item)
        if len(set(v)) != len(v):
            raise ValueError("source_segment_ids must be unique")
        return v


class InputTiming(BaseModel):
    model_config = ConfigDict(extra="forbid")

    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    overlap: InputTimingOverlap
    basis: InputTimingBasis


class TrustedEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner_generation: int = Field(..., ge=1)
    turn_epoch: int = Field(..., ge=0)
    state_version: int = Field(..., ge=0)
    booking_revision: int = Field(..., ge=0)
    deadline_at: str
    timezone: Literal["Asia/Ho_Chi_Minh"] = "Asia/Ho_Chi_Minh"
    input_hash: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    actor: Actor
    presented_question: Optional[PresentationRef] = None
    input_timing: InputTiming


class TurnInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["3.0"] = "3.0"
    kind: Literal["user_turn"] = "user_turn"
    session_id: str
    request_id: str
    draft_id: str
    turn_id: str
    input_id: str
    received_at: str
    source: SourceEnvelope
    text: str = Field(..., min_length=1, max_length=8000)
    trusted: TrustedEnvelope

    @field_validator("session_id", "request_id", "draft_id", "input_id")
    def check_id_fields(cls, v: str) -> str:
        return validate_id(v)

    @field_validator("turn_id")
    def check_turn_uuid(cls, v: str) -> str:
        try:
            uuid.UUID(v)
        except ValueError:
            raise ValueError(f"turn_id must be a valid UUID string, got: {v}")
        return v

    @model_validator(mode="after")
    def check_channel_rules(self) -> TurnInput:
        if self.source.channel == Channel.VOICE:
            if self.trusted.input_timing.basis not in (InputTimingBasis.VOICE_ADAPTER, InputTimingBasis.UNKNOWN):
                raise ValueError("voice channel input_timing basis must be voice_adapter or unknown")
        else:
            if self.source.asr is not None:
                raise ValueError("non-voice channel cannot have asr field")
            if self.trusted.input_timing.basis not in (InputTimingBasis.TEXT_ADAPTER, InputTimingBasis.UNKNOWN):
                raise ValueError("non-voice channel input_timing basis must be text_adapter or unknown")
        return self

    def compute_canonical_hash(self) -> str:
        """Compute SHA-256 lowercase hash on UTF-8 canonical compact JSON."""
        return compute_input_hash_from_obj(self)


def compute_input_hash(data: Dict[str, Any]) -> str:
    hash_keys = [
        "schema_version", "kind", "session_id", "request_id", "draft_id",
        "turn_id", "input_id", "source", "text"
    ]
    business_payload = {k: data[k] for k in hash_keys if k in data}
    if isinstance(business_payload.get("source"), dict):
        source = dict(business_payload["source"])
        if source.get("asr") is None:
            source.pop("asr", None)
        business_payload["source"] = source
    canonical = json.dumps(business_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_input_hash_from_obj(obj: TurnInput) -> str:
    raw = obj.model_dump(mode="json")
    return compute_input_hash(raw)


# ==========================================
# TurnResult Models
# ==========================================

class BusinessOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: BusinessOutcomeKind
    record_id: Optional[str] = None
    operation_id: Optional[str] = None
    dispatch_status: DispatchStatus = DispatchStatus.NOT_REQUESTED
    backend_reference: Optional[str] = None


class QuestionTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: str = Field(..., min_length=1, max_length=64)
    slot: Optional[str] = None
    entity_id: Optional[str] = None
    location_version: Optional[int] = Field(None, ge=0)
    booking_revision: Optional[int] = Field(None, ge=0)
    values_digest: Optional[str] = Field(None, pattern=r"^[0-9a-f]{64}$")
    policy_version: Optional[str] = None


class QuestionDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    kind: QuestionKind
    target: QuestionTarget
    segment_id: str
    candidate_ids: List[str] = Field(default_factory=list, max_length=16)

    @field_validator("question_id", "segment_id")
    def check_ids(cls, v: str) -> str:
        return validate_id(v)


class ResponseSegment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segment_id: str
    index: int = Field(..., ge=0)
    kind: SegmentKind
    text: str = Field(..., min_length=1, max_length=8000)
    source_refs: List[str] = Field(default_factory=list, max_length=32)
    claim_scope: ClaimScope = ClaimScope.NONE

    @field_validator("segment_id")
    def check_segment_id(cls, v: str) -> str:
        return validate_id(v)


class ResponsePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    response_id: str
    created_at: str
    locale: Literal["vi-VN"] = "vi-VN"
    speech_rate: float = Field(1.0, ge=0.5, le=2.0)
    segments: List[ResponseSegment] = Field(..., min_length=1, max_length=16)
    final_text: str = Field(..., min_length=1, max_length=16000)
    question: Optional[QuestionDefinition] = None

    @field_validator("response_id")
    def check_response_id(cls, v: str) -> str:
        return validate_id(v)

    @model_validator(mode="after")
    def validate_segments_and_question(self) -> ResponsePayload:
        # Check segment IDs unique
        seg_ids = [s.segment_id for s in self.segments]
        if len(set(seg_ids)) != len(seg_ids):
            raise ValueError("All segment_ids must be unique")
        
        # Check final text is exact join
        expected_final = " ".join(s.text for s in self.segments)
        if self.final_text != expected_final:
            raise ValueError(f"final_text does not match joined segment texts. Expected: '{expected_final}'")
        
        # At most one question segment
        question_segs = [s for s in self.segments if s.kind == SegmentKind.QUESTION]
        if len(question_segs) > 1:
            raise ValueError(f"At most one question segment allowed, found {len(question_segs)}")
        
        if self.question is not None:
            if len(question_segs) != 1:
                raise ValueError("question definition provided but question segment count != 1")
            if self.question.segment_id != question_segs[0].segment_id:
                raise ValueError(f"question.segment_id '{self.question.segment_id}' does not match question segment '{question_segs[0].segment_id}'")
        else:
            if len(question_segs) != 0:
                raise ValueError("question segment present without question definition object")
        return self


class DeliveryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed: bool
    reason: DeliveryReason


class ExecutionTimings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prepare_ms: float = Field(..., ge=0.0)
    commit_ms: float = Field(..., ge=0.0)
    total_ms: float = Field(..., ge=0.0)


class TurnResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["3.0"] = "3.0"
    session_id: str
    request_id: str
    draft_id: str
    turn_id: str
    input_id: str
    status: TurnStatus
    new_commit: bool
    state_version: Optional[int] = Field(None, ge=0)
    observed_state_version: Optional[int] = Field(None, ge=0)
    booking_revision: Optional[int] = Field(None, ge=0)
    booking_status: Optional[BookingStatus] = None
    profile: Profile
    business_outcome: BusinessOutcome
    response: Optional[ResponsePayload] = None
    delivery: DeliveryResult
    error: Optional[ErrorDetail] = None
    trace_id: str = Field(..., min_length=1, max_length=128)
    timings: ExecutionTimings

    @field_validator("session_id", "request_id", "draft_id", "input_id", "trace_id")
    def check_id_fields(cls, v: str) -> str:
        return validate_id(v)

    @field_validator("turn_id")
    def check_turn_uuid(cls, v: str) -> str:
        try:
            uuid.UUID(v)
        except ValueError:
            raise ValueError(f"turn_id must be a valid UUID string: {v}")
        return v

    @model_validator(mode="after")
    def validate_status_rules(self) -> TurnResult:
        if self.status != TurnStatus.COMMITTED and self.status != TurnStatus.REPLAYED:
            if self.response is not None:
                raise ValueError(f"Turn status {self.status.value} must have response=null")
            if self.business_outcome.kind != BusinessOutcomeKind.NONE:
                raise ValueError(f"Turn status {self.status.value} must have business_outcome.kind='none'")
            if self.delivery.allowed:
                raise ValueError(f"Turn status {self.status.value} must have delivery.allowed=false")
        return self


# ==========================================
# ControlEvent Models
# ==========================================

class TrustedControlEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner_generation: int = Field(..., ge=1)
    actor: Actor
    adapter_id: str

    @field_validator("adapter_id")
    def check_adapter_id(cls, v: str) -> str:
        return validate_id(v)


class DeliveryPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: DeliveryEventType
    response_id: str
    segment_id: str
    playback_id: Optional[str] = None
    mode: DeliveryMode
    reporter: DeliveryReporter
    reason: Optional[str] = Field(None, max_length=128)

    @field_validator("response_id", "segment_id")
    def check_ids(cls, v: str) -> str:
        return validate_id(v)

    @field_validator("playback_id")
    def check_playback_id(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return validate_id(v)
        return None

    @model_validator(mode="after")
    def validate_mode_rules(self) -> DeliveryPayload:
        if self.mode == DeliveryMode.VOICE:
            if self.playback_id is None:
                raise ValueError("voice delivery event must have playback_id")
            if self.event_type == DeliveryEventType.TEXT_PRESENTED:
                raise ValueError("voice delivery mode cannot have event_type='text_presented'")
        else:
            if self.event_type != DeliveryEventType.TEXT_PRESENTED:
                raise ValueError("text delivery mode must have event_type='text_presented'")
            if self.playback_id is not None:
                raise ValueError("text delivery mode must have playback_id=null")
        return self


class ControlEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["3.0"] = "3.0"
    kind: ControlEventKind
    session_id: str
    request_id: str
    input_id: str
    occurred_at: str
    trusted: TrustedControlEnvelope
    payload: Dict[str, Any]

    @field_validator("session_id", "request_id", "input_id")
    def check_ids(cls, v: str) -> str:
        return validate_id(v)
