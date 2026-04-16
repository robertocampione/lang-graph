from app.state.schema import GraphState
from app.tools.execution_guardrails import evaluate_execution_guardrails
from app.tools.audit import write_audit_event
from app.db.connection import execute_query
import json
import logging

logger = logging.getLogger(__name__)

def auto_execute(state: GraphState) -> dict:
    """
    Executes the automated action and persists the result to execution_log.
    Fired conditionally when Recommendation == 'ALLOW_FOLLOW_ON'.
    """
    rec_obj = state.get("recommendation")
    decision = getattr(rec_obj, "decision", rec_obj.get("decision") if isinstance(rec_obj, dict) else "UNKNOWN")
    ticket_raw = state.get("ticket_raw", "")
    guardrails = evaluate_execution_guardrails(state)

    if not guardrails.allowed:
        detail = f"Auto-execution blocked by guardrails: {', '.join(guardrails.reasons)}"
        audit_entry = write_audit_event(
            "auto_execute",
            detail,
            state=state,
            payload={"status": "blocked_by_guardrails", "guardrail_reasons": guardrails.reasons},
        )
        execution_res_str = json.dumps({
            "status": "blocked_by_guardrails",
            "action_taken": decision,
            "detail": detail,
            "guardrail_reasons": guardrails.reasons,
        })
        return {
            "messages": [f"[auto_execute] {detail}"],
            "audit_log": [audit_entry],
            "execution_guardrails": guardrails,
            "execution_result": execution_res_str,
        }

    execution_detail = f"Executed Action: {decision}. Systems synced successfully."

    # Persist to execution_log table
    try:
        execute_query(
            "INSERT INTO execution_log (ticket_raw, action_taken, detail, status) VALUES (%s, %s, %s, %s)",
            (ticket_raw, decision, execution_detail, "success")
        )
    except Exception as e:
        logger.error(f"Failed to persist execution log: {e}")

    audit_entry = write_audit_event(
        "auto_execute",
        f"Action: {decision}. Detail: {execution_detail}",
        state=state,
        payload={"status": "success", "action_taken": decision, "guardrail_reasons": guardrails.reasons},
    )

    execution_res_str = json.dumps({
        "status": "success",
        "action_taken": decision,
        "detail": execution_detail,
        "guardrail_reasons": guardrails.reasons,
    })

    return {
        "messages": [f"[auto_execute] {execution_detail}"],
        "audit_log": [audit_entry],
        "execution_guardrails": guardrails,
        "execution_result": execution_res_str
    }
