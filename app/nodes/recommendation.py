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


def _translate_reason(decision: str, codes: list, lang: str) -> str:
    templates = {
        "ALLOWED": {
            "en": "Order allowed. Applied rules: {codes}",
            "fr": "Commande autorisée. Règles respectées: {codes}",
            "nl": "Bestelling toegestaan. Regels toegepast: {codes}"
        },
        "BLOCKED": {
            "en": "Order blocked due to: {codes}",
            "fr": "Commande bloquée (raison: {codes})",
            "nl": "Bestelling geblokkeerd (reden: {codes})"
        },
        "NEEDS_INFO": {
            "en": "Needs information: {codes}",
            "fr": "Nécessite des informations: {codes}",
            "nl": "Heeft informatie nodig: {codes}"
        }
    }
    lang = lang.lower() if lang else "en"
    if lang not in ["en", "fr", "nl"]:
        lang = "en"
    
    code_str = ", ".join(codes) if codes else "general checks"
    return templates.get(decision, templates["BLOCKED"])[lang].format(codes=code_str)


def recommendation(state: GraphState) -> dict:
    validation_result = state.get("validation_result")
    lang = state.get("output_language", "en")

    if not validation_result:
        rec = Recommendation(
            decision="BLOCKED",
            reason="Validation failed to produce an output.",
            applied_rules=["SYSTEM_ERROR"],
            confidence=0.0,
            requires_human=True,
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
            "messages": ["[recommendation] ERROR: No ValidationResult found."],
            "recommendation": rec,
            "action_plan": action_plan,
            "execution_guardrails": guardrails,
        }

    action_plan = _build_action_plan(validation_result, state)
    status = validation_result.status
    codes = validation_result.reason_codes

    if status == "NEED_INFO":
        decision = "NEEDS_INFO"
        requires_human = True
    elif status == "BLOCK" or status == "ESCALATE":
        decision = "BLOCKED"
        requires_human = True
    elif status == "ALLOW":
        decision = "ALLOWED"
        requires_human = False
    else:
        decision = "BLOCKED"
        requires_human = True
        
    reason = _translate_reason(decision, codes, lang)

    rec = Recommendation(
        decision=decision,
        reason=reason,
        applied_rules=validation_result.rules_used,
        confidence=validation_result.confidence,
        requires_human=requires_human
    )

    guardrails = evaluate_execution_guardrails({**state, "recommendation": rec, "action_plan": action_plan})
    audit_entry = write_audit_event(
        "recommendation",
        f"Decision: {rec.decision}. Auto eligible: {action_plan.auto_eligible}",
        state={**state, "recommendation": rec, "action_plan": action_plan, "execution_guardrails": guardrails},
        payload={
            "decision": rec.decision,
            "reason": rec.reason,
            "requires_human": rec.requires_human,
            "action_type": action_plan.action_type,
            "auto_eligible": action_plan.auto_eligible
        },
    )

    return {
        "messages": [f"Recommendation: {rec.decision} ({rec.reason})"],
        "audit_log": [audit_entry],
        "recommendation": rec,
        "action_plan": action_plan,
        "execution_guardrails": guardrails,
    }
