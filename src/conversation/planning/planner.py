"""Authoritative dialogue and response planner."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import uuid

from src.conversation.contract import (
    BusinessOutcome,
    BusinessOutcomeKind,
    DispatchStatus,
    ResponsePayload,
    BookingStatus,
)
from src.conversation.domain.models import ConversationAggregate
from src.conversation.planning.renderer import ResponseRenderer
from src.conversation.reducer.reducer import ReductionResult


class ResponsePlanner:
    def __init__(self, renderer: Optional[ResponseRenderer] = None):
        self.renderer = renderer or ResponseRenderer()

    def plan_response(
        self,
        aggregate: ConversationAggregate,
        turn_output: ReductionResult,
        response_id: Optional[str] = None,
    ) -> Tuple[BusinessOutcome, ResponsePayload]:
        """Plan business outcome and rendered response based on aggregate and reducer output."""
        draft = aggregate.draft

        # 1. Determine Business Outcome
        if draft.status == BookingStatus.REQUEST_RECORDED:
            outcome = BusinessOutcome(
                kind=BusinessOutcomeKind.REQUEST_RECORDED,
                record_id=f"bk-{draft.draft_id}",
                operation_id=f"op-{draft.draft_id}-intake",
                dispatch_status=DispatchStatus.NOT_REQUESTED,
            )
            resp = self.renderer.render_request_recorded(
                draft=draft,
                record_id=outcome.record_id,
                response_id=response_id,
            )
            return outcome, resp

        if draft.status == BookingStatus.CANCELLED:
            outcome = BusinessOutcome(
                kind=BusinessOutcomeKind.CANCELLED,
                dispatch_status=DispatchStatus.NOT_REQUESTED,
            )
            resp = self.renderer.render_inquiry_answer(
                answer_text="Yêu cầu đặt xe của anh/chị đã được hủy ạ.",
                response_id=response_id,
            )
            return outcome, resp

        outcome = BusinessOutcome(
            kind=BusinessOutcomeKind.DRAFT_UPDATED,
            dispatch_status=DispatchStatus.NOT_REQUESTED,
        )

        if turn_output.intended_action == "recall":
            history = aggregate.conversation_state.recent_delivered_history
            prev_user_text = next((h["text"] for h in reversed(history) if h.get("role") == "user"), None)
            if prev_user_text:
                resp = self.renderer.render_inquiry_answer(
                    answer_text=f"Dạ câu trước anh/chị vừa nói là: \"{prev_user_text}\" ạ.",
                    response_id=response_id,
                )
            else:
                resp = self.renderer.render_inquiry_answer(
                    answer_text="Dạ em chưa ghi nhận câu nói trước đó của anh/chị ạ.",
                    response_id=response_id,
                )
            return outcome, resp

        if turn_output.next_question_kind == "disambiguate_location":
            slot_target = "destination" if (not draft.destination or not draft.destination.verified) else "origin"
            resp = self.renderer.render_disambiguate_location(
                slot_name=slot_target,
                response_id=response_id,
            )
            return outcome, resp

        # 2. Render appropriate dialogue action
        if draft.status == BookingStatus.AWAITING_CONFIRMATION:
            resp = self.renderer.render_confirm_trip(draft, response_id=response_id)
            return outcome, resp

        # Clarifications or questions
        if turn_output.intended_action == "clarify" or turn_output.next_question_kind in (
            "clarify_location",
            "disambiguate_location",
        ):
            if draft.origin and draft.origin.unverified_components:
                resp = self.renderer.render_clarify_unverified_location(
                    slot_name="origin",
                    label=draft.origin.label,
                    response_id=response_id,
                )
                return outcome, resp

        if not draft.destination:
            unverified = bool(draft.origin and draft.origin.unverified_components)
            resp = self.renderer.render_ask_destination(
                origin_label=draft.origin.label if draft.origin else None,
                unverified_note=unverified,
                response_id=response_id,
            )
            return outcome, resp

        if not draft.origin:
            resp = self.renderer.render_ask_origin(
                destination_label=draft.destination.label if draft.destination else None,
                response_id=response_id,
            )
            return outcome, resp

        # Both present, await confirmation
        resp = self.renderer.render_confirm_trip(draft, response_id=response_id)
        return outcome, resp
