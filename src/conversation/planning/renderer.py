"""Authoritative Response Renderer for vanuoc conversation core.

Enforces:
- Exact segment join equality: final_text == " ".join(s.text for s in segments)
- At most one question segment, positioned at the end
- Claim scope assignment matching policy invariants (POL-01, POL-02)
- Strict Vietnamese wording without unsupported commitments
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
import uuid

from src.conversation.contract import (
    ClaimScope,
    QuestionDefinition,
    QuestionKind,
    QuestionTarget,
    ResponsePayload,
    ResponseSegment,
    SegmentKind,
)
from src.conversation.domain.models import BookingDraft, ConversationAggregate


class ResponseRenderer:
    def __init__(self, speech_rate: float = 1.0):
        self.speech_rate = speech_rate

    def render_ask_destination(
        self,
        origin_label: Optional[str] = None,
        unverified_note: bool = False,
        response_id: Optional[str] = None,
    ) -> ResponsePayload:
        rid = response_id or f"resp-{uuid.uuid4().hex[:12]}"
        segments: List[ResponseSegment] = []
        idx = 0

        if origin_label:
            ack_text = f"Em đã ghi nhận điểm đón tại {origin_label}."
            if unverified_note:
                ack_text = f"Em đã ghi nhận địa chỉ anh/chị vừa đọc; bản đồ thử nghiệm chưa xác minh được số nhà và ngách."
            segments.append(
                ResponseSegment(
                    segment_id=f"seg-{rid}-{idx}",
                    index=idx,
                    kind=SegmentKind.ANSWER,
                    text=ack_text,
                    source_refs=["origin_slot"],
                    claim_scope=ClaimScope.CONVERSATION,
                )
            )
            idx += 1

        q_seg_id = f"seg-{rid}-{idx}"
        q_text = "Anh/chị muốn đi đến đâu ạ?"
        segments.append(
            ResponseSegment(
                segment_id=q_seg_id,
                index=idx,
                kind=SegmentKind.QUESTION,
                text=q_text,
                source_refs=[],
                claim_scope=ClaimScope.NONE,
            )
        )

        q_def = QuestionDefinition(
            question_id=f"q-{rid}",
            kind=QuestionKind.CLARIFY_SLOT,
            target=QuestionTarget(
                scope="booking",
                slot="destination",
            ),
            segment_id=q_seg_id,
            candidate_ids=[],
        )

        final_text = " ".join(s.text for s in segments)
        return ResponsePayload(
            response_id=rid,
            created_at="2026-10-19T10:00:00+07:00",
            locale="vi-VN",
            speech_rate=self.speech_rate,
            segments=segments,
            final_text=final_text,
            question=q_def,
        )

    def render_ask_origin(
        self,
        destination_label: Optional[str] = None,
        response_id: Optional[str] = None,
    ) -> ResponsePayload:
        rid = response_id or f"resp-{uuid.uuid4().hex[:12]}"
        segments: List[ResponseSegment] = []
        idx = 0

        if destination_label:
            segments.append(
                ResponseSegment(
                    segment_id=f"seg-{rid}-{idx}",
                    index=idx,
                    kind=SegmentKind.ANSWER,
                    text=f"Em đã ghi nhận điểm đến tại {destination_label}.",
                    source_refs=["destination_slot"],
                    claim_scope=ClaimScope.CONVERSATION,
                )
            )
            idx += 1

        q_seg_id = f"seg-{rid}-{idx}"
        q_text = "Anh/chị muốn đón ở đâu ạ?"
        segments.append(
            ResponseSegment(
                segment_id=q_seg_id,
                index=idx,
                kind=SegmentKind.QUESTION,
                text=q_text,
                source_refs=[],
                claim_scope=ClaimScope.NONE,
            )
        )

        q_def = QuestionDefinition(
            question_id=f"q-{rid}",
            kind=QuestionKind.CLARIFY_SLOT,
            target=QuestionTarget(
                scope="booking",
                slot="origin",
            ),
            segment_id=q_seg_id,
            candidate_ids=[],
        )

        final_text = " ".join(s.text for s in segments)
        return ResponsePayload(
            response_id=rid,
            created_at="2026-10-19T10:00:00+07:00",
            locale="vi-VN",
            speech_rate=self.speech_rate,
            segments=segments,
            final_text=final_text,
            question=q_def,
        )

    def render_clarify_unverified_location(
        self,
        slot_name: str,
        label: str,
        response_id: Optional[str] = None,
    ) -> ResponsePayload:
        rid = response_id or f"resp-{uuid.uuid4().hex[:12]}"
        segments = [
            ResponseSegment(
                segment_id=f"seg-{rid}-0",
                index=0,
                kind=SegmentKind.ANSWER,
                text=f"Em đã ghi nhận địa chỉ anh/chị vừa đọc; bản đồ thử nghiệm chưa xác minh được số nhà và ngách.",
                source_refs=[f"{slot_name}_slot"],
                claim_scope=ClaimScope.CONVERSATION,
            ),
            ResponseSegment(
                segment_id=f"seg-{rid}-1",
                index=1,
                kind=SegmentKind.QUESTION,
                text="Gần điểm đón có cửa hàng hoặc biển hiệu nào dễ nhận biết không ạ?",
                source_refs=[],
                claim_scope=ClaimScope.NONE,
            ),
        ]
        q_def = QuestionDefinition(
            question_id=f"q-{rid}",
            kind=QuestionKind.CLARIFY_SLOT,
            target=QuestionTarget(
                scope="location",
                slot=slot_name,
            ),
            segment_id=f"seg-{rid}-1",
            candidate_ids=[],
        )
        final_text = " ".join(s.text for s in segments)
        return ResponsePayload(
            response_id=rid,
            created_at="2026-10-19T10:00:00+07:00",
            locale="vi-VN",
            speech_rate=self.speech_rate,
            segments=segments,
            final_text=final_text,
            question=q_def,
        )

    def render_disambiguate_location(
        self,
        slot_name: str = "destination",
        response_id: Optional[str] = None,
    ) -> ResponsePayload:
        rid = response_id or f"resp-{uuid.uuid4().hex[:12]}"
        q_seg_id = f"seg-{rid}-0"
        q_text = "Dạ anh/chị muốn chọn địa điểm hay cơ sở nào cụ thể ạ?"
        segments = [
            ResponseSegment(
                segment_id=q_seg_id,
                index=0,
                kind=SegmentKind.QUESTION,
                text=q_text,
                source_refs=[],
                claim_scope=ClaimScope.NONE,
            )
        ]
        q_def = QuestionDefinition(
            question_id=f"q-{rid}",
            kind=QuestionKind.DISAMBIGUATE_LOCATION,
            target=QuestionTarget(
                scope="location",
                slot=slot_name,
            ),
            segment_id=q_seg_id,
            candidate_ids=[],
        )
        final_text = q_text
        return ResponsePayload(
            response_id=rid,
            created_at="2026-10-19T10:00:00+07:00",
            locale="vi-VN",
            speech_rate=self.speech_rate,
            segments=segments,
            final_text=final_text,
            question=q_def,
        )

    def render_confirm_trip(
        self,
        draft: BookingDraft,
        response_id: Optional[str] = None,
    ) -> ResponsePayload:
        rid = response_id or f"resp-{uuid.uuid4().hex[:12]}"
        origin_str = draft.origin.label if draft.origin else "điểm đón"
        dest_str = draft.destination.label if draft.destination else "điểm đến"
        vehicle_str = f", xe {draft.vehicle_type} chỗ" if draft.vehicle_type else ""

        q_seg_id = f"seg-{rid}-0"
        q_text = f"Anh/chị xác nhận đặt chuyến từ {origin_str} đến {dest_str}{vehicle_str} đúng không ạ?"
        segments = [
            ResponseSegment(
                segment_id=q_seg_id,
                index=0,
                kind=SegmentKind.QUESTION,
                text=q_text,
                source_refs=["trip_summary"],
                claim_scope=ClaimScope.NONE,
            )
        ]

        q_def = QuestionDefinition(
            question_id=f"q-{rid}",
            kind=QuestionKind.CONFIRM_TRIP,
            target=QuestionTarget(
                scope="booking",
                booking_revision=draft.booking_revision,
            ),
            segment_id=q_seg_id,
            candidate_ids=[],
        )

        final_text = " ".join(s.text for s in segments)
        return ResponsePayload(
            response_id=rid,
            created_at="2026-10-19T10:00:00+07:00",
            locale="vi-VN",
            speech_rate=self.speech_rate,
            segments=segments,
            final_text=final_text,
            question=q_def,
        )

    def render_request_recorded(
        self,
        draft: BookingDraft,
        record_id: str,
        response_id: Optional[str] = None,
    ) -> ResponsePayload:
        rid = response_id or f"resp-{uuid.uuid4().hex[:12]}"
        origin_str = draft.origin.label if draft.origin else ""
        dest_str = draft.destination.label if draft.destination else ""

        ack_text = (
            f"Em đã ghi nhận yêu cầu đặt xe từ {origin_str} đến {dest_str}. "
            f"Mã đặt xe của anh/chị là {record_id} (thử nghiệm, chưa điều xe thật)."
        )

        segments = [
            ResponseSegment(
                segment_id=f"seg-{rid}-0",
                index=0,
                kind=SegmentKind.STATUS,
                text=ack_text,
                source_refs=[record_id],
                claim_scope=ClaimScope.INTAKE,
            )
        ]

        final_text = " ".join(s.text for s in segments)
        return ResponsePayload(
            response_id=rid,
            created_at="2026-10-19T10:00:00+07:00",
            locale="vi-VN",
            speech_rate=self.speech_rate,
            segments=segments,
            final_text=final_text,
            question=None,
        )

    def render_inquiry_answer(
        self,
        answer_text: str,
        question_text: Optional[str] = None,
        question_def: Optional[QuestionDefinition] = None,
        response_id: Optional[str] = None,
    ) -> ResponsePayload:
        rid = response_id or f"resp-{uuid.uuid4().hex[:12]}"
        segments = [
            ResponseSegment(
                segment_id=f"seg-{rid}-0",
                index=0,
                kind=SegmentKind.ANSWER,
                text=answer_text,
                source_refs=["inquiry_source"],
                claim_scope=ClaimScope.CONVERSATION,
            )
        ]

        if question_text and question_def:
            segments.append(
                ResponseSegment(
                    segment_id=question_def.segment_id,
                    index=1,
                    kind=SegmentKind.QUESTION,
                    text=question_text,
                    source_refs=[],
                    claim_scope=ClaimScope.NONE,
                )
            )

        final_text = " ".join(s.text for s in segments)
        return ResponsePayload(
            response_id=rid,
            created_at="2026-10-19T10:00:00+07:00",
            locale="vi-VN",
            speech_rate=self.speech_rate,
            segments=segments,
            final_text=final_text,
            question=question_def if question_text else None,
        )
