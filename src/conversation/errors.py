"""Standard error taxonomy and codes for vanuoc v3.0 core."""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field, ConfigDict


class ErrorCode(str, Enum):
    # Input & Schema
    INVALID_INPUT = "INVALID_INPUT"
    UNSUPPORTED_SCHEMA = "UNSUPPORTED_SCHEMA"
    INPUT_CONFLICT = "INPUT_CONFLICT"
    
    # Auth & Ownership
    NOT_AUTHORIZED = "NOT_AUTHORIZED"
    SESSION_ENDED = "SESSION_ENDED"
    OWNER_SUPERSEDED = "OWNER_SUPERSEDED"
    OWNERSHIP_LOST = "OWNERSHIP_LOST"
    
    # Turn & State Fencing
    STATE_CONFLICT = "STATE_CONFLICT"
    TURN_SUPERSEDED = "TURN_SUPERSEDED"
    TURN_CANCELLED = "TURN_CANCELLED"
    DEADLINE_EXCEEDED = "DEADLINE_EXCEEDED"
    TURN_IN_PROGRESS = "TURN_IN_PROGRESS"
    
    # Storage
    STORE_BUSY = "STORE_BUSY"
    STORE_UNAVAILABLE = "STORE_UNAVAILABLE"
    STORE_WRITE_FAILED = "STORE_WRITE_FAILED"
    COMMIT_OUTCOME_UNCERTAIN = "COMMIT_OUTCOME_UNCERTAIN"
    
    # Providers
    PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
    PROVIDER_RATE_LIMIT = "PROVIDER_RATE_LIMIT"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PROVIDER_AUTH = "PROVIDER_AUTH"
    PROVIDER_BAD_REQUEST = "PROVIDER_BAD_REQUEST"
    INVALID_MODEL_OUTPUT = "INVALID_MODEL_OUTPUT"
    
    # Domain & Policy
    UNKNOWN_OPERATION_OUTCOME = "UNKNOWN_OPERATION_OUTCOME"
    POLICY_DATA_MISSING = "POLICY_DATA_MISSING"
    TARIFF_UNAVAILABLE = "TARIFF_UNAVAILABLE"
    NO_MATCH = "NO_MATCH"
    AMBIGUOUS = "AMBIGUOUS"
    UNVERIFIED_DETAIL = "UNVERIFIED_DETAIL"
    HANDOFF_UNAVAILABLE = "HANDOFF_UNAVAILABLE"
    
    # Delivery
    DELIVERY_FAILED = "DELIVERY_FAILED"
    DELIVERY_ACK_MISSING = "DELIVERY_ACK_MISSING"
    
    # NLU validation
    NLU_SCHEMA_ERROR = "NLU_SCHEMA_ERROR"
    NLU_SOURCE_ERROR = "NLU_SOURCE_ERROR"
    NLU_REFERENCE_ERROR = "NLU_REFERENCE_ERROR"


class ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: ErrorCode
    message: str = Field(..., min_length=1, max_length=1000)
    retryable: bool = False
    details: Optional[Dict[str, Any]] = None


class ConversationCoreException(Exception):
    """Base exception for vanuoc conversation core errors."""
    def __init__(self, code: ErrorCode, message: str, retryable: bool = False, details: Optional[Dict[str, Any]] = None):
        super().__init__(f"[{code.value}] {message}")
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or {}

    def to_error_detail(self) -> ErrorDetail:
        return ErrorDetail(
            code=self.code,
            message=self.message,
            retryable=self.retryable,
            details=self.details or None
        )
