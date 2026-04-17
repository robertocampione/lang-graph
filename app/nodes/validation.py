import logging
from datetime import date
from typing import Any, Optional

from app.state.schema import GraphState, ValidationResult
from app.tools.audit import write_audit_event
from app.tools.db_services import fetch_compatibility_decision

logger = logging.getLogger(__name__)


def _value(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _markers(po_context: Any, field: str = "exception_markers") -> set[str]:
    return {_norm(marker) for marker in (_value(po_context, field, []) or [])}


def _customer_resolved(state: GraphState, ticket: Any) -> bool:
    if _value(ticket, "customer_id"):
        return True
    customer = state.get("customer_context")
    return bool(customer and _value(customer, "name") != "Unknown")


def _effective_missing_info(state: GraphState, ticket: Any, po_context: Any) -> list[str]:
    missing = list(_value(ticket, "missing_info", []) or [])
    effective_missing = []

    for field in missing:
        normalized = str(field).strip()
        if normalized == "customer_id" and _customer_resolved(state, ticket):
            continue
        if normalized == "scope_type" and (_value(ticket, "scope_type") or _value(po_context, "scope_type")):
            continue
        if normalized == "pending_order_type" and (_value(ticket, "pending_order_type") or _value(po_context, "order_type")):
            continue
        if normalized in {"scope_id", "address_id", "pending_order_id", "salto_order_reference"} and po_context:
            continue
        effective_missing.append(normalized)

    return list(dict.fromkeys(effective_missing))


def _scope_matches_pending_order(ticket: Any, po_context: Any) -> bool:
    ticket_scope = _norm(_value(ticket, "scope_type"))
    pending_scope = _norm(_value(po_context, "scope_type"))
    if not ticket_scope or not pending_scope:
        return False

    ticket_scope_id = _value(ticket, "scope_id")
    pending_scope_id = _value(po_context, "scope_id")
    ticket_address = _value(ticket, "address_id") or _value(ticket, "address_identifier")
    pending_address = _value(po_context, "address_id")

    if ticket_address and pending_address and ticket_address != pending_address:
        return False
    if ticket_scope_id and pending_scope_id:
        return ticket_scope_id == pending_scope_id
    return ticket_scope == pending_scope


def _ambiguity_resolved_by_context(ambiguity: str, ticket: Any, po_context: Any) -> bool:
    if not po_context:
        return False

    text = ambiguity.lower()
    hard_markers = [
        "multiple",
        "contradictory",
        "unclear which pending order",
        "which pending order",
        "both fiber and mobile",
    ]
    if any(marker in text for marker in hard_markers):
        return False

    soft_markers = ["inferred", "not explicitly stated", "specific scope_type", "product_family"]
    return _scope_matches_pending_order(ticket, po_context) and any(marker in text for marker in soft_markers)


def _effective_ambiguities(ticket: Any, po_context: Any) -> list[str]:
    ambiguities = [
        str(item).strip()
        for item in (_value(ticket, "ambiguities", []) or [])
        if str(item).strip()
    ]
    return list(dict.fromkeys(
        item for item in ambiguities
        if not _ambiguity_resolved_by_context(item, ticket, po_context)
    ))


def _requested_action(state: GraphState, ticket: Any) -> str:
    requested = state.get("requested_second_order")
    return _norm(
        _value(requested, "action")
        or _value(ticket, "requested_action")
        or _value(ticket, "requested_follow_on_action")
        or _value(ticket, "request_type")
    )


def _is_sim_or_iff_exception(action: str, po_context: Any) -> bool:
    explicit_markers = {
        "sim_exception",
        "sim_only_exception",
        "iff",
        "instant_fulfilment",
        "explicit_exception",
        "backoffice_exception",
        "copper_outphasing",
    }
    explicit_actions = {
        "sim_swap",
        "sim_only",
        "block_sim",
        "unblock_sim",
        "add_data_boost",
        "instant_fulfilment",
        "add_internet_volume",
        "copper_outphasing_action",
    }
    return bool(_markers(po_context).intersection(explicit_markers) or action in explicit_actions)


def _has_sim_exclusion(po_context: Any) -> Optional[str]:
    exclusions = _markers(po_context, "exclusion_markers")
    for marker in ["v1_customer", "oms_customer", "import_export", "change_ownership", "duo_card"]:
        if marker in exclusions:
            return marker.upper()
    return None


def _is_device_return_only(action: str, po_context: Any) -> bool:
    markers = _markers(po_context)
    return bool(
        "device_return_only" in markers
        or action in {"device_return", "return_device"}
        or _value(po_context, "device_return_pending", False)
    )


def _future_date_too_far(po_context: Any) -> bool:
    raw_date = _value(po_context, "planned_execution_date")
    if not raw_date:
        return False
    try:
        planned = date.fromisoformat(str(raw_date)[:10])
    except ValueError:
        return False
    return (planned - date.today()).days > 90


def _delivery_not_reached(po_context: Any) -> bool:
    if not po_context:
        return False
    if _value(po_context, "delivery_reached", False):
        return False
    milestone = _norm(_value(po_context, "milestone"))
    return milestone == "delivery"


def _bundle_member_blocked(state: GraphState, ticket: Any, po_context: Any) -> bool:
    bundle = state.get("bundle_context")
    bundle_id = _value(po_context, "bundle_id")
    if not bundle and _norm(_value(po_context, "scope_type")) != "bundle":
        return False

    ticket_scope_id = _value(ticket, "scope_id")
    ticket_scope_type = _norm(_value(ticket, "scope_type"))
    member_scope_ids = set(_value(bundle, "member_scope_ids", []) or [])

    if ticket_scope_id and ticket_scope_id in member_scope_ids:
        return True
    if _norm(_value(po_context, "scope_type")) == "bundle" and ticket_scope_type in {"fiber", "tv", "mobile"}:
        return True
    return bool(bundle_id and _value(ticket, "scope_id") == bundle_id)


def _compatibility_from_state_or_db(state: GraphState, ticket: Any, po_context: Any) -> Optional[dict[str, Any]]:
    existing = state.get("compatibility_decision")
    if existing:
        return dict(existing)

    customer = state.get("customer_context")
    segment = _value(customer, "segment")
    if _norm(segment) != "pmit_mobile":
        return None

    try:
        return fetch_compatibility_decision(segment, _value(po_context, "order_type"), _requested_action(state, ticket))
    except Exception as exc:
        logger.error(f"Compatibility lookup failed: {exc}")
        return None


def _make_result(status: str, reason_codes: list[str], blocking: list[str], missing: list[str], rules: list[str]) -> ValidationResult:
    return ValidationResult(
        status=status,
        reason_codes=list(dict.fromkeys(reason_codes)),
        blocking_conditions=blocking,
        missing_info=list(dict.fromkeys(missing)),
        rules_used=list(dict.fromkeys(rules)),
        confidence=1.0,
    )


def validation(state: GraphState) -> dict:
    """
    Deterministic business validation for the BCI + SALTO PoC simulation.

    LLM output is treated as extracted evidence only. Final decisions come from
    these explicit checks.
    """
    ticket = state.get("ticket_structured")
    po_context = state.get("selected_salto_order") or state.get("pending_order_context")

    reason_codes: list[str] = []
    blocking_conditions: list[str] = []
    rules_used: list[str] = []
    missing_info = _effective_missing_info(state, ticket, po_context) if ticket else ["ticket_structured"]
    ambiguities = _effective_ambiguities(ticket, po_context) if ticket else []
    action = _requested_action(state, ticket)
    status = "ALLOW"

    if missing_info:
        status = "NEED_INFO"
        reason_codes.append("MISSING_DATA")
        blocking_conditions.append(f"Cannot process ticket due to missing fields: {', '.join(missing_info)}")
        rules_used.append("core.required_fields")

    elif ambiguities:
        status = "NEED_INFO"
        reason_codes.append("AMBIGUOUS_TICKET")
        missing_info.append("clarify_request_scope")
        blocking_conditions.append("Cannot process ticket automatically because the request is ambiguous: " + "; ".join(ambiguities))
        rules_used.append("core.ambiguous_ticket")

    elif po_context:
        compatibility = _compatibility_from_state_or_db(state, ticket, po_context)
        exclusion = _has_sim_exclusion(po_context)

        if _is_sim_or_iff_exception(action, po_context) and exclusion:
            status = "BLOCK"
            reason_codes.append("SIM_EXCEPTION_EXCLUDED")
            blocking_conditions.append(f"Explicit SIM/IFF exception is excluded by SALTO marker: {exclusion}.")
            rules_used.append("exceptions.salto_explicit_exception")

        elif _is_sim_or_iff_exception(action, po_context):
            status = "ALLOW"
            reason_codes.append("EXPLICIT_EXCEPTION_ALLOWED")
            rules_used.append("exceptions.explicit_non_conflicting_exception")

        elif compatibility and _norm(compatibility.get("decision")) == "accept":
            status = "ALLOW"
            reason_codes.append("PMIT_MATRIX_ACCEPT")
            rules_used.append("segment.pmit_mobile_matrix")

        elif compatibility and _norm(compatibility.get("decision")) == "block":
            status = "BLOCK"
            reason_codes.append("PMIT_MATRIX_BLOCK")
            blocking_conditions.append(compatibility.get("reason") or "PMIT Mobile compatibility matrix blocks this follow-on action.")
            rules_used.append("segment.pmit_mobile_matrix")

        elif _is_device_return_only(action, po_context):
            status = "ALLOW"
            reason_codes.append("DEVICE_RETURN_ONLY_ALLOWED")
            if int(_value(po_context, "device_return_days", 0) or 0) > 21:
                reason_codes.append("DEVICE_RETURN_AFTER_21_DAYS")
            rules_used.append("device_return.follow_on_allowed")

        elif _value(po_context, "final_disconnect", False) and not _value(po_context, "ponr_reached", False):
            status = "BLOCK"
            reason_codes.append("PONR_BLOCK")
            blocking_conditions.append("SALTO final disconnect / port-out is before PONR; follow-on actions are unsafe.")
            rules_used.append("ponr.final_disconnect")

        elif _value(po_context, "installation_pending", False):
            status = "BLOCK"
            reason_codes.append("INSTALLATION_STILL_PENDING")
            blocking_conditions.append("The current pending order has an active physical installation that is not yet completed.")
            rules_used.append("installation.one_active_installation")

        elif "future_dated" in _markers(po_context) or _future_date_too_far(po_context):
            status = "BLOCK"
            reason_codes.append("FUTURE_DATED_ORDER")
            if _future_date_too_far(po_context):
                reason_codes.append("FUTURE_DATE_OVER_90_DAYS")
            blocking_conditions.append("The current pending order is future-dated and must not be changed automatically.")
            rules_used.append("core.future_dated_pending_order")

        elif _delivery_not_reached(po_context):
            status = "BLOCK"
            reason_codes.append("DELIVERY_MILESTONE_NOT_REACHED")
            blocking_conditions.append("SALTO delivery milestone has not been reached, so the order is still blocking follow-ons.")
            rules_used.append("activation.delivery_milestone")

        elif _bundle_member_blocked(state, ticket, po_context):
            status = "BLOCK"
            reason_codes.append("BUNDLE_MEMBER_BLOCKED")
            blocking_conditions.append("The pending bundle/pack order blocks changes to dependent bundle members.")
            rules_used.append("bundle.bundle_member_pending")

        elif _scope_matches_pending_order(ticket, po_context):
            status = "BLOCK"
            reason_codes.append("SAME_SCOPE_PENDING")
            blocking_conditions.append(f"An order is already pending on the same scope ({_value(po_context, 'scope_type')}).")
            rules_used.append("core.same_scope_pending")

    if status == "ALLOW" and not reason_codes:
        reason_codes.append("NO_CONFLICTS")
        rules_used.append("scope.different_scope_allowed")

    val_result = _make_result(status, reason_codes, blocking_conditions, missing_info, rules_used)

    audit_entry = write_audit_event(
        "validation",
        f"Status: {status}. Reasons: {', '.join(val_result.reason_codes)}",
        state=state,
        payload={
            "status": status,
            "reason_codes": val_result.reason_codes,
            "rules_used": val_result.rules_used,
            "salto_order_id": _value(po_context, "salto_order_id") or _value(po_context, "pending_order_id"),
            "action": action,
        },
    )

    display_status = "ALLOWED" if status == "ALLOW" else "BLOCKED" if status in ["BLOCK", "ESCALATE"] else "NEEDS_INFO"
    return {
        "messages": [f"Validation: {display_status} ({', '.join(val_result.reason_codes)})"],
        "audit_log": [audit_entry],
        "validation_result": val_result,
    }
