from app.state.schema import GraphState, Recommendation
from app.tools.audit import write_audit_event
import logging

logger = logging.getLogger(__name__)

def recommendation(state: GraphState) -> dict:
    """
    Produce a human-readable recommendation format based purely on the deterministic ValidationResult.
    The LLM is no longer making autonomous business decisions here.
    """
    validation_result = state.get("validation_result")

    if not validation_result:
        # Fallback if validation somehow didn't run
        return {
            "messages": ["[recommendation] ERROR: No ValidationResult found in state."],
            "recommendation": Recommendation(
                decision="ERROR",
                rationale="Validation node did not produce a result.",
                suggested_human_action="Review system logs.",
                missing_fields=[],
                executable_action_possible=False,
                confidence=0.0
            )
        }

    status = validation_result.status

    # Map validation status to recommendation decision
    if status == "NEED_INFO":
        decision = "REQUEST_INFO"
        suggested_action = f"Contact customer to request missing information: {', '.join(validation_result.missing_info)}."
        executable = False
    elif status == "BLOCK":
        decision = "HOLD_CASE"
        suggested_action = "Review the blocking conditions and check with the backoffice team if an exception can be made."
        executable = False
    elif status == "ESCALATE":
        decision = "ESCALATE"
        suggested_action = "Escalate immediately to 2nd Line Support per SLA policies."
        executable = False
    elif status == "ALLOW":
        decision = "ALLOW_FOLLOW_ON"
        suggested_action = "Approve the follow-on request. Auto-execution may proceed."
        executable = True
    else:
        decision = "UNKNOWN"
        suggested_action = "Manual review required due to unknown validation status."
        executable = False

    rationale = f"Validation Status: {status}\n"
    if validation_result.reason_codes:
        rationale += f"Reasons: {', '.join(validation_result.reason_codes)}\n"
    if validation_result.blocking_conditions:
        rationale += "Details:\n - " + "\n - ".join(validation_result.blocking_conditions)

    rec = Recommendation(
        decision=decision,
        rationale=rationale.strip(),
        suggested_human_action=suggested_action,
        missing_fields=list(validation_result.missing_info),
        executable_action_possible=executable,
        confidence=validation_result.confidence
    )

    write_audit_event("recommendation", f"Decision: {rec.decision}. Executable: {rec.executable_action_possible}")

    return {
        "messages": [f"[recommendation] Generated decision: {rec.decision} (Executable: {rec.executable_action_possible})"],
        "recommendation": rec
    }
