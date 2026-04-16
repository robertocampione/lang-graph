import logging
from datetime import datetime, timezone
from typing import Any

from psycopg.types.json import Jsonb

from app.db.connection import execute_query

logger = logging.getLogger(__name__)


def _get_value(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _state_ids(state: dict[str, Any] | None) -> tuple[str | None, str | None, str | None]:
    if not state:
        return None, None, None

    ticket = state.get("ticket_structured")
    customer_id = _get_value(ticket, "customer_id")
    case_id = state.get("case_id") or customer_id
    correlation_id = state.get("correlation_id") or case_id
    thread_id = state.get("thread_id")
    return correlation_id, case_id, thread_id


def build_audit_entry(
    node_name: str,
    summary: str,
    actor_type: str = "SYSTEM",
    state: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the audit payload shared by DB persistence and tests."""
    correlation_id, case_id, thread_id = _state_ids(state)
    payload_summary = dict(payload or {})
    if state:
        ticket = state.get("ticket_structured")
        bci_case = state.get("bci_case_context")
        order = state.get("selected_salto_order") or state.get("pending_order_context")
        action_plan = state.get("action_plan")
        payload_summary.setdefault("bci_case_id", _get_value(bci_case, "bci_case_id") or _get_value(ticket, "bci_case_id"))
        payload_summary.setdefault("customer_id", _get_value(ticket, "customer_id") or _get_value(bci_case, "customer_id"))
        payload_summary.setdefault("salto_order_id", _get_value(order, "salto_order_id") or _get_value(order, "pending_order_id"))
        payload_summary.setdefault("actor_role", _get_value(ticket, "creator_role"))
        payload_summary.setdefault("target_system", _get_value(action_plan, "target_system"))
        payload_summary.setdefault("action_type", _get_value(action_plan, "action_type"))
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "node_name": node_name,
        "actor_type": actor_type,
        "correlation_id": correlation_id,
        "case_id": case_id,
        "thread_id": thread_id,
        "summary": summary,
        "payload_summary": payload_summary,
    }


def write_audit_event(
    node_name: str,
    summary: str,
    actor_type: str = "SYSTEM",
    state: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
):
    """
    Safely logs an audit event to the PostgreSQL database.
    Catches exceptions to prevent breaking the orchestrator flow if the DB is unavaliable.
    """
    entry = build_audit_entry(node_name, summary, actor_type=actor_type, state=state, payload=payload)
    try:
        query = """
            INSERT INTO audit_events
                (node_name, summary, actor_type, correlation_id, case_id, thread_id, payload_summary)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        execute_query(
            query,
            (
                entry["node_name"],
                entry["summary"],
                entry["actor_type"],
                entry["correlation_id"],
                entry["case_id"],
                entry["thread_id"],
                Jsonb(entry["payload_summary"]),
            ),
        )
    except Exception as e:
        try:
            execute_query(
                "INSERT INTO audit_events (node_name, summary, actor_type) VALUES (%s, %s, %s)",
                (entry["node_name"], entry["summary"], entry["actor_type"]),
            )
        except Exception as fallback_error:
            logger.error(f"Audit log failed for {node_name}: {e}; fallback failed: {fallback_error}")
    return entry
