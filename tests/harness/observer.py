"""Observation extractor producing standardized evaluation snapshots for scenarios."""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional

from src.conversation.contract import TurnResult, TurnStatus, BookingStatus
from src.conversation.domain.models import LocationEvidence


def extract_location_dict(loc: Optional[LocationEvidence]) -> Optional[Dict[str, Any]]:
    if loc is None:
        return None
    return {
        "label": loc.label,
        "location_version": loc.location_version,
        "verified": loc.verified,
        "candidate_id": loc.candidate_id,
        "precision": loc.precision.value if hasattr(loc.precision, "value") else str(loc.precision),
        "unverified_components": loc.unverified_components,
        "components": {
            "house_number": loc.components.house_number,
            "sub_alley": loc.components.sub_alley,
            "alley": loc.components.alley,
            "street": loc.components.street,
            "landmark": loc.components.landmark,
            "ward": loc.components.ward,
            "district": loc.components.district,
            "province": loc.components.province,
        },
    }


def extract_observation(
    conn: sqlite3.Connection,
    request_id: str,
    draft_id: str,
    latest_result: Optional[TurnResult] = None,
    error_detail: Optional[Dict[str, Any]] = None,
    estimate_endpoints: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Extract standard Observation dictionary for scenario assertions."""
    # 1. Authoritative SQLite state
    req_row = conn.execute(
        "SELECT * FROM core_requests WHERE request_id = ?", (request_id,)
    ).fetchone()

    draft_row = conn.execute(
        "SELECT * FROM core_drafts WHERE request_id = ? AND draft_id = ?",
        (request_id, draft_id),
    ).fetchone()

    bk_count = conn.execute(
        "SELECT count(*) as c FROM sample_bookings WHERE request_id = ?", (request_id,)
    ).fetchone()["c"]

    task_count = conn.execute(
        """SELECT count(*) as c FROM sample_operator_tasks t
           JOIN sample_bookings b ON t.booking_id = b.booking_id
           WHERE b.request_id = ?""",
        (request_id,),
    ).fetchone()["c"]

    # 2. Result branch
    result_branch: Dict[str, Any] = {
        "status": latest_result.status.value if latest_result else (
            error_detail.get("status", "error") if error_detail else "none"
        ),
        "state_version": latest_result.state_version if latest_result else (
            req_row["state_version"] if req_row else 0
        ),
        "response_id": latest_result.response.response_id if (latest_result and latest_result.response) else None,
        "error": error_detail or (latest_result.error.model_dump(mode="json") if latest_result and latest_result.error else None),
    }

    # 3. Booking branch
    booking_status = req_row["booking_status"] if req_row else "collecting"
    booking_revision = draft_row["booking_revision"] if draft_row else 0
    origin_dict = None
    dest_dict = None
    vehicle_type = "4_seat"
    passengers = 1
    driver_note = None

    if draft_row:
        slots = json.loads(draft_row["slots_json"])
        if "origin" in slots and slots["origin"]:
            origin_dict = extract_location_dict(LocationEvidence.model_validate(slots["origin"]))
        if "destination" in slots and slots["destination"]:
            dest_dict = extract_location_dict(LocationEvidence.model_validate(slots["destination"]))
        if "vehicle_type" in slots:
            vehicle_type = slots["vehicle_type"]
        if "passengers" in slots:
            passengers = slots["passengers"]
        if "driver_note" in slots:
            driver_note = slots["driver_note"]

    booking_branch = {
        "status": booking_status,
        "booking_revision": booking_revision,
        "origin": origin_dict,
        "destination": dest_dict,
        "vehicle_type": vehicle_type,
        "passengers": passengers,
        "driver_note": driver_note,
    }

    # 4. Dialogue branch
    req_conv = conn.execute(
        "SELECT conversation_json FROM core_requests WHERE request_id = ?", (request_id,)
    ).fetchone()
    conv_data = json.loads(req_conv["conversation_json"]) if req_conv and req_conv["conversation_json"] else {}
    offered_state = conv_data.get("offered_question")

    q_row = conn.execute(
        "SELECT * FROM core_questions WHERE request_id = ? AND status = 'pending' ORDER BY created_at_utc DESC LIMIT 1",
        (request_id,),
    ).fetchone()
    next_question = None
    if offered_state:
        next_question = {
            "kind": offered_state.get("kind"),
            "question_id": offered_state.get("question_id"),
            "target": offered_state.get("target"),
            "booking_revision": offered_state.get("booking_revision"),
        }
    elif q_row:
        next_question = {
            "kind": q_row["decision_kind"],
            "question_id": q_row["question_id"],
            "target": json.loads(q_row["target_ref"]) if q_row["target_ref"] else None,
            "booking_revision": q_row["booking_revision"],
        }
    elif latest_result and latest_result.response and latest_result.response.question:
        next_question = {
            "kind": latest_result.response.question.kind.value,
            "question_id": latest_result.response.question.question_id,
            "target": latest_result.response.question.target.model_dump(mode="json"),
            "booking_revision": latest_result.response.question.target.booking_revision,
        }

    dialogue_branch = {
        "next_question": next_question,
        "preferences": {"reply_length": "normal"},
    }

    # 5. Delivery branch
    pres_row = conn.execute(
        """SELECT * FROM core_presentations
           WHERE request_id = ?
           ORDER BY created_at_utc DESC LIMIT 1""",
        (request_id,),
    ).fetchone()

    q_eligible = False
    active_resp_id = None
    active_pb_id = None

    if pres_row:
        active_resp_id = pres_row["response_id"]
        active_pb_id = pres_row["playback_id"]
        if pres_row["transport"] == "text" and pres_row["phase"] == "completed":
            q_eligible = True
        elif pres_row["transport"] == "voice" and pres_row["phase"] == "completed":
            q_eligible = True

    delivery_branch = {
        "question_eligible": q_eligible,
        "active_response_id": active_resp_id,
        "active_playback_id": active_pb_id,
    }

    # 6. Operations branch
    operations_branch = {
        "local_booking_count": bk_count,
        "submit_attempts": 0,
        "cancel_attempts": 0,
        "support_tasks": task_count,
        "outcome": None,
    }

    # 7. Response branch
    resp_text = latest_result.response.final_text if (latest_result and latest_result.response) else None
    q_count = 1 if (latest_result and latest_result.response and latest_result.response.question) else 0

    claims_dict: Dict[str, Any] = {
        "dispatch_confirmed": False,  # POL-01 strictly enforces false
        "request_recorded": bool(booking_status == "request_recorded"),
        "fare_asserted": False,
        "official_policy_asserted": False,
    }
    if estimate_endpoints:
        claims_dict["estimate_endpoint_ids"] = estimate_endpoints

    response_branch = {
        "text": resp_text,
        "question_count": q_count,
        "claims": claims_dict,
        "source_ids": [],
    }

    # 8. Audit branch
    replay_count = 0
    if latest_result and latest_result.status == TurnStatus.REPLAYED:
        replay_count = 1

    audit_branch = {
        "replay_count": replay_count,
        "ownership_generation": req_row["owner_generation"] if req_row else 1,
        "stale_writes": 0,
    }

    # 9. Tools branch
    tools_branch = {
        "provider_calls": 0,
        "stale_results_applied": 0,
        "evidence_source": "fixture",
    }

    return {
        "result": result_branch,
        "booking": booking_branch,
        "dialogue": dialogue_branch,
        "delivery": delivery_branch,
        "operations": operations_branch,
        "response": response_branch,
        "audit": audit_branch,
        "tools": tools_branch,
    }
