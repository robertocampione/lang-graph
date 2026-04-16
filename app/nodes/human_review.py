from app.state.schema import GraphState
from app.tools.execution_guardrails import evaluate_execution_guardrails
from app.tools.audit import write_audit_event
from app.db.connection import execute_query
import logging

logger = logging.getLogger(__name__)

def human_review(state: GraphState) -> dict:
    """
    Node that represents human review. It executes only AFTER the interrupt has been resumed.
    Persists the review record to the human_reviews table.
    """
    rec_obj = state.get("recommendation")
    ticket_raw = state.get("ticket_raw", "")

    decision = getattr(rec_obj, "decision", "UNKNOWN") if rec_obj else "UNKNOWN"
    rationale = getattr(rec_obj, "rationale", "") if rec_obj else ""
    suggested = getattr(rec_obj, "suggested_human_action", "") if rec_obj else ""
    missing = list(getattr(rec_obj, "missing_fields", [])) if rec_obj else []
    validation_result = state.get("validation_result")
    action_plan = state.get("action_plan")
    guardrails = evaluate_execution_guardrails(state)
    review_payload = {
        "decision": decision,
        "validation_status": getattr(validation_result, "status", "UNKNOWN") if validation_result else "UNKNOWN",
        "reason_codes": list(getattr(validation_result, "reason_codes", [])) if validation_result else [],
        "missing_fields": missing,
        "guardrail_reasons": guardrails.reasons,
        "suggested_human_action": suggested,
        "action_type": getattr(action_plan, "action_type", None) if action_plan else None,
        "target_system": getattr(action_plan, "target_system", None) if action_plan else None,
        "auto_eligible": getattr(action_plan, "auto_eligible", False) if action_plan else False,
        "memory_context": state.get("memory_context", {}),
    }

    # Persist to human_reviews table
    try:
        execute_query(
            "INSERT INTO human_reviews (ticket_raw, decision, rationale, suggested_human_action, missing_fields) VALUES (%s, %s, %s, %s, %s)",
            (ticket_raw, decision, rationale, suggested, missing)
        )
    except Exception as e:
        logger.error(f"Failed to persist human review: {e}")

    audit_entry = write_audit_event(
        "human_review",
        f"Case held for human review. Decision: {decision}",
        actor_type="HUMAN",
        state=state,
        payload=review_payload,
    )

    return {
        "messages": [f"[human_review] Case reviewed by a human agent. Decision: {decision}"],
        "audit_log": [audit_entry],
        "execution_guardrails": guardrails,
        "human_review_payload": review_payload,
        "human_review": f"Reviewed: {decision}. Guardrails: {', '.join(guardrails.reasons)}"
    }
