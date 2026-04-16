from app.state.schema import GraphState, ValidationResult
from app.tools.audit import write_audit_event
import logging

logger = logging.getLogger(__name__)


def _exception_markers(po_context) -> set[str]:
    markers = getattr(po_context, "exception_markers", []) or []
    return {str(marker).strip().lower() for marker in markers}


def _has_explicit_non_conflicting_exception(ticket, po_context) -> bool:
    markers = _exception_markers(po_context)
    request_type = str(getattr(ticket, "request_type", "") or "").lower()
    requested_action = str(getattr(ticket, "requested_follow_on_action", "") or "").lower()

    explicit_markers = {
        "sim_exception",
        "sim_only_exception",
        "device_return_only",
        "explicit_exception",
        "backoffice_exception",
    }
    explicit_actions = {
        "device_return",
        "return_device",
        "sim_swap",
        "sim_only",
    }

    return bool(
        markers.intersection(explicit_markers)
        or request_type in explicit_actions
        or requested_action in explicit_actions
    )


def _effective_missing_info(ticket, po_context) -> list[str]:
    """
    Remove fields the integration node resolved from authoritative DB context.
    The LLM may flag address_id/scope_id as missing, but validation can still
    proceed when the customer and pending order have already been identified.
    """
    missing = list(getattr(ticket, "missing_info", []) or [])
    effective_missing = []

    for field in missing:
        normalized = str(field).strip()
        if normalized == "customer_id" and getattr(ticket, "customer_id", None):
            continue
        if normalized == "scope_type" and (
            getattr(ticket, "scope_type", None) or getattr(po_context, "scope_type", None)
        ):
            continue
        if normalized in {"scope_id", "address_id", "pending_order_id"} and po_context:
            continue
        effective_missing.append(normalized)

    return list(dict.fromkeys(effective_missing))


def validation(state: GraphState) -> dict:
    """
    Deterministic validation node.
    No LLM is used here. Applies hardcoded business rules to the context
    and structural ticket representation to define if the request is ALLOWed, BLOCKed or NEEDS_INFO.
    """
    ticket = state.get("ticket_structured")
    po_context = state.get("pending_order_context")
    
    status = "ALLOW"
    reason_codes = []
    blocking_conditions = []
    missing_info = _effective_missing_info(ticket, po_context) if ticket else []
    rules_used = []
    
    # 1. Missing Info check
    if missing_info:
        status = "NEED_INFO"
        reason_codes.append("MISSING_DATA")
        blocking_conditions.append(f"Cannot process ticket due to missing fields: {', '.join(missing_info)}")
        rules_used.append("core.required_fields")
        
    # 2. Deterministic Pending Order checks (Only if we have required info)
    elif po_context and ticket:
        markers = _exception_markers(po_context)

        if _has_explicit_non_conflicting_exception(ticket, po_context):
            status = "ALLOW"
            reason_codes.append("EXPLICIT_EXCEPTION_ALLOWED")
            rules_used.append("exceptions.explicit_non_conflicting_exception")

        elif getattr(po_context, "installation_pending", False):
            status = "BLOCK"
            reason_codes.append("INSTALLATION_STILL_PENDING")
            blocking_conditions.append("The current pending order has an active physical installation that is not yet completed.")
            rules_used.append("installation.one_active_installation")

        elif "future_dated" in markers:
            status = "BLOCK"
            reason_codes.append("FUTURE_DATED_ORDER")
            blocking_conditions.append("The current pending order is future-dated and must not be changed automatically.")
            rules_used.append("core.future_dated_pending_order")
            
        elif getattr(po_context, "scope_type", "") == getattr(ticket, "scope_type", ""):
            status = "BLOCK"
            reason_codes.append("SAME_SCOPE_PENDING")
            blocking_conditions.append(f"An order is already pending on the same scope type ({po_context.scope_type}).")
            rules_used.append("core.same_scope_pending")

    if status == "ALLOW":
        if not reason_codes:
            reason_codes.append("NO_CONFLICTS")
            rules_used.append("scope.different_scope_allowed")

    rules_used = list(dict.fromkeys(rules_used))

    val_result = ValidationResult(
        status=status,
        reason_codes=reason_codes,
        blocking_conditions=blocking_conditions,
        missing_info=missing_info,
        rules_used=rules_used,
        confidence=1.0 # 100% deterministic rules
    )

    write_audit_event("validation", f"Status: {status}. Reasons: {', '.join(reason_codes)}")

    return {
        "messages": [f"[validation] Completed. Status: {status}. Reasons: {', '.join(reason_codes)}"],
        "validation_result": val_result
    }
