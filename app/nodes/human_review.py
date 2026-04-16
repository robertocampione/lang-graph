from app.state.schema import GraphState
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

    # Persist to human_reviews table
    try:
        execute_query(
            "INSERT INTO human_reviews (ticket_raw, decision, rationale, suggested_human_action, missing_fields) VALUES (%s, %s, %s, %s, %s)",
            (ticket_raw, decision, rationale, suggested, missing)
        )
    except Exception as e:
        logger.error(f"Failed to persist human review: {e}")

    write_audit_event("human_review", f"Case held for human review. Decision: {decision}", actor_type="HUMAN")

    return {
        "messages": [f"[human_review] Case reviewed by a human agent. Decision: {decision}"],
        "human_review": f"Reviewed: {decision}"
    }
