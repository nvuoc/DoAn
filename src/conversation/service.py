"""Authoritative ConversationService orchestrating Coordinator, Reducer, Ports, and Delivery."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
import sqlite3
import time
import uuid

from src.conversation.contract import (
    TurnInput,
    TurnResult,
    TurnStatus,
    BookingStatus,
    BusinessOutcome,
    BusinessOutcomeKind,
    ControlEvent,
    ControlEventKind,
    DeliveryResult,
    DeliveryReason,
    ExecutionTimings,
    Profile,
)
from src.conversation.delivery.tracker import DeliveryTracker, DeliveryAck
from src.conversation.domain.enums import ActType, SlotName, Precision
from src.conversation.domain.models import (
    BookingDraft,
    ConversationAggregate,
    ConversationState,
    LocationComponents,
    LocationEvidence,
)
from src.conversation.planning.planner import ResponsePlanner
from src.conversation.ports.geo import GeoPort
from src.conversation.reducer.reducer import reduce_turn_proposal, ReductionResult
from src.conversation.storage.coordinator import TransactionCoordinator, TurnAdmissionResult
from src.conversation.understanding.normalizer import normalize_vietnamese_numbers


class ConversationService:
    def __init__(
        self,
        conn: sqlite3.Connection,
        geo_port: Optional[GeoPort] = None,
        policy: Optional[Dict[str, Any]] = None,
    ):
        self.conn = conn
        self.coordinator = TransactionCoordinator(conn)
        self.geo_port = geo_port or GeoPort()
        self.delivery_tracker = DeliveryTracker(conn)
        self.planner = ResponsePlanner()
        self.policy = policy or {
            "policy_version": "development_conservative_3_0",
            "destination_required": True,
            "allow_text_only_auto_booking": False,
            "vehicle_catalog": ["4_seat", "7_seat"],
        }

    def execute_turn(
        self,
        turn_input: TurnInput,
        nlu_proposal: Optional[Dict[str, Any]] = None,
        fixtures: Optional[Dict[str, Any]] = None,
    ) -> TurnResult:
        """Execute a full turn through admission, reduction, planning, and commit."""
        start_time = time.time()

        # 1. Admit turn
        admit_res = self.coordinator.admit_turn(turn_input)
        if admit_res.status == "replayed":
            assert admit_res.replayed_result is not None
            return admit_res.replayed_result

        aggregate = admit_res.aggregate
        assert aggregate is not None

        # 2. Extract or use NLU proposal
        proposal = nlu_proposal or self._extract_default_proposal(turn_input.text, aggregate)

        # 3. Handle fixture catalog resolution if present
        if fixtures and "catalog" in fixtures and fixtures["catalog"]:
            catalog = fixtures["catalog"]
            rejected = proposal.get("rejected_candidates", [])
            for act in proposal.get("acts", []):
                val = str(act.get("value", "")).lower()
                matches = []
                for item in catalog:
                    item_id = item.get("id")
                    item_name = item.get("name", "").lower()
                    aliases = [a.lower() for a in item.get("spoken_aliases", [])]
                    if item_id in rejected:
                        continue
                    # Match by name or alias
                    if (item_name and (item_name in val or val in item_name)) or any(
                        a and (a in val or val in a) for a in aliases
                    ):
                        matches.append(item)
                if len(matches) == 1:
                    item_id = matches[0]["id"]
                    if act.get("target") == "destination":
                        act["candidate_id"] = item_id
                    elif act.get("target") == "origin":
                        act["candidate_id"] = item_id
                elif len(matches) > 1:
                    proposal.setdefault("uncertainties", []).append("MULTIPLE_LIVE_OPTIONS")
                    proposal["candidate_options"] = [m["id"] for m in matches]

        # 4. Check delivery eligibility for currently offered question
        question_eligible = False
        if aggregate.conversation_state.offered_question:
            q_id = aggregate.conversation_state.offered_question.question_id
            question_eligible = self.delivery_tracker.is_question_eligible(
                aggregate.request_id, q_id
            )

        # 5. Execute pure deterministic reducer
        reduction = reduce_turn_proposal(
            aggregate=aggregate,
            proposal=proposal,
            policy=self.policy,
            question_eligible_at_admission=question_eligible,
            raw_utterance=turn_input.text,
        )

        # If candidate_id was set from catalog, ensure it reflects on location evidence
        for act in proposal.get("acts", []):
            if "candidate_id" in act:
                if act.get("target") == "destination" and reduction.draft.destination:
                    reduction.draft.destination.candidate_id = act["candidate_id"]
                elif act.get("target") == "origin" and reduction.draft.origin:
                    reduction.draft.origin.candidate_id = act["candidate_id"]

        # 6. Build mutated aggregate
        new_aggregate = aggregate.model_copy(deep=True)
        new_aggregate.draft = reduction.draft
        new_aggregate.conversation_state = reduction.conversation_state

        # 7. Plan response & business outcome
        outcome, response_payload = self.planner.plan_response(
            aggregate=new_aggregate,
            turn_output=reduction,
            response_id=f"resp-{turn_input.turn_id[-6:]}",
        )

        # Sync offered question on conversation state
        if response_payload.question is not None:
            q_def = response_payload.question
            from src.conversation.domain.models import OfferedQuestion
            new_aggregate.conversation_state.offered_question = OfferedQuestion(
                question_id=q_def.question_id,
                kind=q_def.kind.value,
                target=q_def.target.slot or "booking",
                response_id=response_payload.response_id,
                segment_id=q_def.segment_id,
                options=q_def.candidate_ids,
            )
        else:
            new_aggregate.conversation_state.offered_question = None

        prepare_ms = (time.time() - start_time) * 1000.0

        # 8. Construct prepared TurnResult
        prepared = TurnResult(
            schema_version="3.0",
            session_id=turn_input.session_id,
            request_id=turn_input.request_id,
            draft_id=turn_input.draft_id,
            turn_id=turn_input.turn_id,
            input_id=turn_input.input_id,
            status=TurnStatus.COMMITTED,
            new_commit=True,
            state_version=aggregate.state_version + 1,
            observed_state_version=aggregate.state_version + 1,
            booking_revision=new_aggregate.draft.booking_revision,
            booking_status=new_aggregate.draft.status,
            profile=Profile.FIXTURE,
            business_outcome=outcome,
            response=response_payload,
            delivery=DeliveryResult(
                allowed=True,
                reason=DeliveryReason.COMMITTED_CURRENT,
            ),
            trace_id=f"trace-{turn_input.turn_id[-6:]}",
            timings=ExecutionTimings(
                prepare_ms=prepare_ms,
                commit_ms=5.0,
                total_ms=prepare_ms + 5.0,
            ),
        )

        # 9. Atomic SQLite commit
        final_result = self.coordinator.commit_turn(turn_input, new_aggregate, prepared)
        return final_result

    def execute_delivery(self, event: ControlEvent) -> DeliveryAck:
        """Process incoming delivery or control event."""
        return self.delivery_tracker.process_delivery_event(event)

    def _extract_default_proposal(self, text: str, aggregate: ConversationAggregate) -> Dict[str, Any]:
        """Simple deterministic fallback extractor when explicit NLU proposal fixture is not provided."""
        clean = text.lower().strip()
        acts = []
        uncertainties = []

        # Confirm patterns
        if clean in ("đúng rồi", "vâng", "đồng ý", "ừ", "chính xác", "đúng", "ừ đúng rồi"):
            acts.append({"type": ActType.CONFIRM_PENDING.value})
            return {"acts": acts, "uncertainties": uncertainties}

        # Cancel patterns
        if "hủy" in clean or "thôi không đặt" in clean:
            acts.append({"type": ActType.REQUEST_CANCEL.value})
            return {"acts": acts, "uncertainties": uncertainties}

        # Vehicle type changes
        if "7 chỗ" in clean or "bảy chỗ" in clean:
            acts.append({"type": ActType.REPLACE_SLOT.value, "target": "vehicle_type", "value": "7_seat"})
        elif "4 chỗ" in clean or "bốn chỗ" in clean:
            acts.append({"type": ActType.REPLACE_SLOT.value, "target": "vehicle_type", "value": "4_seat"})

        # Locations: "từ A đến B" or "đón ở A" or "đi B"
        norm_text = normalize_vietnamese_numbers(clean)
        if "từ " in norm_text and " đến " in norm_text:
            parts = norm_text.split(" đến ")
            origin_str = parts[0].replace("từ ", "").strip()
            dest_str = parts[1].strip()
            acts.append({"type": ActType.SET_SLOT.value, "target": "origin", "value": origin_str})
            acts.append({"type": ActType.SET_SLOT.value, "target": "destination", "value": dest_str})
        elif "đón" in norm_text:
            origin_str = norm_text
            for prefix in ("đón tôi ở ", "đón ở ", "đón tại ", "đón "):
                if prefix in origin_str:
                    origin_str = origin_str.split(prefix, 1)[1]
                    break
            acts.append({"type": ActType.SET_SLOT.value, "target": "origin", "value": origin_str.strip()})
        elif "đi " in norm_text or "đến " in norm_text:
            dest_str = norm_text
            for prefix in ("cho tôi đi ", "tôi muốn đi ", "đi đến ", "đi ", "đến "):
                if prefix in dest_str:
                    dest_str = dest_str.split(prefix, 1)[1]
                    break
            acts.append({"type": ActType.SET_SLOT.value, "target": "destination", "value": dest_str.strip()})

        if not acts:
            # Fallback to social or inquiry
            acts.append({"type": ActType.SOCIAL_RESPONSE.value})

        return {"acts": acts, "uncertainties": uncertainties}
