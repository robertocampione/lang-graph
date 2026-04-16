from app.state.schema import ActionPlan, GraphState, Recommendation
from app.tools.audit import write_audit_event
from app.tools.execution_guardrails import evaluate_execution_guardrails


def _build_action_plan(validation_result, state: GraphState) -> ActionPlan:
    codes = set(validation_result.reason_codes)
    selected_order = state.get("selected_salto_order") or state.get("pending_order_context")
    order_id = getattr(selected_order, "salto_order_id", None) or getattr(selected_order, "pending_order_id", None)

    if validation_result.status == "NEED_INFO":
        return ActionPlan(
            action_type="REQUEST_MISSING_INFO",
            target_system="BCI",
            summary="Ask the intake owner or customer for the missing identifiers before SALTO action.",
            required_inputs=list(validation_result.missing_info),
            operator_steps=["Update the BCI case with the missing information request."],
            auto_eligible=False,
            blocking_reasons=list(validation_result.reason_codes),
        )

    if validation_result.status == "ESCALATE":
        return ActionPlan(
            action_type="ESCALATE_TO_BACK_OFFICE",
            target_system="BCI",
            summary="Escalate the case to the back-office queue.",
            operator_steps=["Assign the BCI case to the pending-orders back-office queue."],
            auto_eligible=False,
            blocking_reasons=list(validation_result.reason_codes),
        )

    if validation_result.status == "BLOCK":
        return ActionPlan(
            action_type="HOLD_BCI_CASE",
            target_system="BCI",
            summary="Hold the BCI case with the deterministic SALTO blocking reason.",
            preconditions=[f"SALTO order: {order_id or 'unknown'}"],
            operator_steps=["Add a BCI remark with the blocking reason.", "Recheck SALTO when the pending order progresses."],
            auto_eligible=False,
            blocking_reasons=list(validation_result.reason_codes),
        )

    if codes.intersection({"DEVICE_RETURN_ONLY_ALLOWED", "EXPLICIT_EXCEPTION_ALLOWED", "PMIT_MATRIX_ACCEPT", "NO_CONFLICTS"}):
        return ActionPlan(
            action_type="INTRODUCE_SECOND_ORDER_DRY_RUN",
            target_system="SALTO",
            summary="Dry-run introduction of the eligible second order in SALTO.",
            preconditions=[f"SALTO order: {order_id or 'none'}", "No deterministic blockers remain."],
            operator_steps=["Review the dry-run payload.", "Confirm the BCI case remark after dry-run."],
            auto_eligible=True,
            blocking_reasons=[],
        )

    return ActionPlan(
        action_type="PREPARE_SECOND_ORDER",
        target_system="SALTO",
        summary="Prepare a second-order action for human execution.",
        operator_steps=["Review SALTO context and complete the order manually."],
        auto_eligible=False,
        blocking_reasons=[],
    )


def recommendation(state: GraphState) -> dict:
    """
    Produce a Phase 1 operator recommendation and a Phase 2 action plan.

    This node formats deterministic validation output. It does not make policy.
    """
    validation_result = state.get("validation_result")

    if not validation_result:
        rec = Recommendation(
            decision="ERROR",
            rationale="Validation node did not produce a result.",
            suggested_human_action="Review system logs.",
            missing_fields=[],
            executable_action_possible=False,
            confidence=0.0,
        )
        action_plan = ActionPlan(
            action_type="ESCALATE_TO_BACK_OFFICE",
            target_system="BCI",
            summary="Validation failed to produce an output.",
            auto_eligible=False,
            blocking_reasons=["MISSING_VALIDATION_RESULT"],
        )
        guardrails = evaluate_execution_guardrails({**state, "recommendation": rec, "action_plan": action_plan})
        return {
            "messages": ["[recommendation] ERROR: No ValidationResult found in state."],
            "recommendation": rec,
            "action_plan": action_plan,
            "execution_guardrails": guardrails,
        }

    action_plan = _build_action_plan(validation_result, state)
    status = validation_result.status

    if status == "NEED_INFO":
        decision = "REQUEST_INFO"
        suggested_action = f"Contact the intake owner or customer to request: {', '.join(validation_result.missing_info)}."
    elif status == "BLOCK":
        decision = "HOLD_CASE"
        suggested_action = "Hold the BCI case and add the SALTO blocking reason as a remark."
    elif status == "ESCALATE":
        decision = "ESCALATE"
        suggested_action = "Escalate immediately to the back-office queue."
    elif status == "ALLOW":
        decision = "ALLOW_FOLLOW_ON"
        suggested_action = "Proceed with the action plan. Dry-run automation may continue if guardrails pass."
    else:
        decision = "UNKNOWN"
        suggested_action = "Manual review required due to unknown validation status."

    rationale = f"Validation Status: {status}\n"
    if validation_result.reason_codes:
        rationale += f"Reasons: {', '.join(validation_result.reason_codes)}\n"
    if validation_result.blocking_conditions:
        rationale += "Details:\n - " + "\n - ".join(validation_result.blocking_conditions)
    rationale += f"\nAction Plan: {action_plan.action_type} on {action_plan.target_system}"

    rec = Recommendation(
        decision=decision,
        rationale=rationale.strip(),
        suggested_human_action=suggested_action,
        missing_fields=list(validation_result.missing_info),
        executable_action_possible=action_plan.auto_eligible,
        confidence=validation_result.confidence,
    )

    guardrails = evaluate_execution_guardrails({**state, "recommendation": rec, "action_plan": action_plan})
    audit_entry = write_audit_event(
        "recommendation",
        f"Decision: {rec.decision}. Action: {action_plan.action_type}. Auto eligible: {action_plan.auto_eligible}",
        state={**state, "recommendation": rec, "action_plan": action_plan, "execution_guardrails": guardrails},
        payload={
            "decision": rec.decision,
            "action_type": action_plan.action_type,
            "target_system": action_plan.target_system,
            "auto_eligible": action_plan.auto_eligible,
            "guardrail_reasons": guardrails.reasons,
            "memory_context": state.get("memory_context", {}),
        },
    )

    return {
        "messages": [f"[recommendation] Decision: {rec.decision}. Action plan: {action_plan.action_type}."],
        "audit_log": [audit_entry],
        "recommendation": rec,
        "action_plan": action_plan,
        "execution_guardrails": guardrails,
    }
