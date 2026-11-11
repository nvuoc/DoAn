"""Unit tests for contract models, canonical hash, and schema validation."""
from __future__ import annotations

from copy import deepcopy
import pytest
from pydantic import ValidationError

from src.conversation.contract import (
    TurnInput,
    TurnResult,
    ControlEvent,
    DeliveryPayload,
    compute_input_hash,
    compute_input_hash_from_obj,
    TurnStatus,
    BusinessOutcomeKind,
    SegmentKind,
    DeliveryMode,
    DeliveryEventType,
)


def test_turn_input_valid(sample_turn_input_dict: dict):
    turn_input = TurnInput.model_validate(sample_turn_input_dict)
    assert turn_input.schema_version == "3.0"
    assert turn_input.kind == "user_turn"
    assert turn_input.session_id == "session-demo-01"
    assert turn_input.turn_id == "018b7a20-1111-4111-8111-000000000001"
    
    # Check canonical hash computation matches trusted input_hash
    computed_hash = compute_input_hash(sample_turn_input_dict)
    assert computed_hash == sample_turn_input_dict["trusted"]["input_hash"]
    assert turn_input.compute_canonical_hash() == computed_hash


def test_turn_input_negative_cases(sample_turn_input_dict: dict):
    # 1. Empty text
    bad = deepcopy(sample_turn_input_dict)
    bad["text"] = ""
    with pytest.raises(ValidationError):
        TurnInput.model_validate(bad)

    # 2. Invalid UUID for turn_id
    bad = deepcopy(sample_turn_input_dict)
    bad["turn_id"] = "not-a-uuid"
    with pytest.raises(ValidationError):
        TurnInput.model_validate(bad)

    # 3. Non-voice channel cannot have ASR
    bad = deepcopy(sample_turn_input_dict)
    bad["source"]["channel"] = "web"
    bad["source"]["asr"] = {"provider": "test_asr"}
    bad["trusted"]["input_timing"]["basis"] = "text_adapter"
    with pytest.raises(ValidationError):
        TurnInput.model_validate(bad)

    # 4. Voice channel cannot have text_adapter basis
    bad = deepcopy(sample_turn_input_dict)
    bad["trusted"]["input_timing"]["basis"] = "text_adapter"
    with pytest.raises(ValidationError):
        TurnInput.model_validate(bad)

    # 5. Invalid ID character
    bad = deepcopy(sample_turn_input_dict)
    bad["session_id"] = "invalid id with spaces"
    with pytest.raises(ValidationError):
        TurnInput.model_validate(bad)


def test_turn_result_valid(sample_turn_result_dict: dict):
    result = TurnResult.model_validate(sample_turn_result_dict)
    assert result.status == TurnStatus.COMMITTED
    assert result.new_commit is True
    assert result.response is not None
    assert result.response.final_text == " ".join(s.text for s in result.response.segments)
    assert len(result.response.segments) == 2
    assert result.response.segments[1].kind == SegmentKind.QUESTION
    assert result.response.question is not None
    assert result.response.question.segment_id == result.response.segments[1].segment_id


def test_turn_result_negative_cases(sample_turn_result_dict: dict):
    # 1. Non-committed turn with response payload must fail validation
    bad = deepcopy(sample_turn_result_dict)
    bad["status"] = "cancelled"
    with pytest.raises(ValidationError):
        TurnResult.model_validate(bad)

    # 2. Question definition with mismatching segment_id
    bad = deepcopy(sample_turn_result_dict)
    bad["response"]["question"]["segment_id"] = "segment-demo-01"
    with pytest.raises(ValidationError):
        TurnResult.model_validate(bad)

    # 3. Final text not matching joined segments
    bad = deepcopy(sample_turn_result_dict)
    bad["response"]["final_text"] = "Different text entirely."
    with pytest.raises(ValidationError):
        TurnResult.model_validate(bad)


def test_delivery_event_valid(sample_delivery_event_dict: dict):
    event = ControlEvent.model_validate(sample_delivery_event_dict)
    assert event.kind.value == "delivery"
    assert event.session_id == "session-demo-01"
    
    # Parse payload as DeliveryPayload
    delivery = DeliveryPayload.model_validate(event.payload)
    assert delivery.mode == DeliveryMode.VOICE
    assert delivery.event_type == DeliveryEventType.PLAYBACK_COMPLETED
    assert delivery.playback_id is not None


def test_delivery_event_negative_cases(sample_delivery_event_dict: dict):
    # Voice mode without playback_id
    bad = deepcopy(sample_delivery_event_dict["payload"])
    bad["playback_id"] = None
    with pytest.raises(ValidationError):
        DeliveryPayload.model_validate(bad)

    # Text mode with voice event_type
    bad = deepcopy(sample_delivery_event_dict["payload"])
    bad["mode"] = "text"
    bad["playback_id"] = None
    bad["event_type"] = "playback_completed"
    with pytest.raises(ValidationError):
        DeliveryPayload.model_validate(bad)
