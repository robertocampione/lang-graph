from __future__ import annotations

from typing import Any

from app.config.settings import settings
from app.state.schema import ExecutionGuardrailResult


def _get_value(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def evaluate_execution_guardrails(state: dict[str, Any]) -> ExecutionGuardrailResult:
    """
    Deterministically decide whether automated execution is allowed.

    This helper is intentionally independent from LLM output. It is used by both
    graph routing and the execution node, so direct calls to auto_execute are
    guarded as well.
    """
    recommendation = state.get("recommendation")
    validation_result = state.get("validation_result")
    confidence_summary = state.get("confidence_summary") or {}
    reasons: list[str] = []

    if not settings.ENABLE_AUTO_EXECUTE:
        reasons.append("AUTO_EXECUTE_DISABLED")

    if not recommendation:
        reasons.append("MISSING_RECOMMENDATION")
        observed_confidence = 0.0
    else:
        decision = _get_value(recommendation, "decision", "UNKNOWN")
        executable = bool(_get_value(recommendation, "executable_action_possible", False))
        observed_confidence = float(_get_value(recommendation, "confidence", 0.0) or 0.0)

        if decision != "ALLOW_FOLLOW_ON":
            reasons.append("DECISION_NOT_ALLOW_FOLLOW_ON")
        if not executable:
            reasons.append("EXECUTABLE_FLAG_FALSE")
        if observed_confidence < settings.AUTO_EXECUTE_MIN_CONFIDENCE:
            reasons.append("CONFIDENCE_BELOW_THRESHOLD")

    if not validation_result:
        reasons.append("MISSING_VALIDATION_RESULT")
    else:
        status = _get_value(validation_result, "status", "UNKNOWN")
        missing_info = list(_get_value(validation_result, "missing_info", []) or [])
        blocking_conditions = list(_get_value(validation_result, "blocking_conditions", []) or [])
        validation_confidence = float(_get_value(validation_result, "confidence", 0.0) or 0.0)
        observed_confidence = min(observed_confidence, validation_confidence)

        if status != "ALLOW":
            reasons.append("VALIDATION_NOT_ALLOW")
        if missing_info:
            reasons.append("VALIDATION_HAS_MISSING_INFO")
        if blocking_conditions:
            reasons.append("VALIDATION_HAS_BLOCKING_CONDITIONS")

    if state.get("errors"):
        reasons.append("STATE_ERRORS_PRESENT")

    triage_confidence = confidence_summary.get("triage")
    if triage_confidence is not None:
        observed_confidence = min(observed_confidence, float(triage_confidence or 0.0))
        if float(triage_confidence or 0.0) < settings.AUTO_EXECUTE_MIN_CONFIDENCE:
            reasons.append("TRIAGE_CONFIDENCE_BELOW_THRESHOLD")

    allowed = len(reasons) == 0
    if allowed:
        reasons.append("AUTO_EXECUTE_GUARDRAILS_PASSED")

    return ExecutionGuardrailResult(
        allowed=allowed,
        reasons=reasons,
        required_human_review=not allowed,
        min_confidence=settings.AUTO_EXECUTE_MIN_CONFIDENCE,
        observed_confidence=observed_confidence,
    )
