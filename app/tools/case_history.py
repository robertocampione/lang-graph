from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from app.db.connection import fetch_all

logger = logging.getLogger(__name__)


def _safe_fetch_all(query: str, params: tuple = ()) -> list[dict[str, Any]]:
    try:
        return [dict(row) for row in fetch_all(query, params)]
    except Exception as exc:
        logger.error(f"Case history lookup failed: {exc}")
        return []


def fetch_prior_cases(case_id: str | None = None, correlation_id: str | None = None, limit: int = 5) -> list[dict[str, Any]]:
    """Fetch recent audit events for the same case/correlation identifiers."""
    if not case_id and not correlation_id:
        return []

    query = """
        SELECT timestamp::text, node_name, actor_type, summary, correlation_id, case_id, thread_id, payload_summary
        FROM audit_events
        WHERE (%s IS NOT NULL AND case_id = %s)
           OR (%s IS NOT NULL AND correlation_id = %s)
        ORDER BY timestamp DESC
        LIMIT %s
    """
    return _safe_fetch_all(query, (case_id, case_id, correlation_id, correlation_id, limit))


def fetch_prior_human_reviews(ticket_raw: str | None = None, limit: int = 5) -> list[dict[str, Any]]:
    """Fetch recent human review decisions, optionally matching the same raw ticket text."""
    if ticket_raw:
        query = """
            SELECT created_at::text, decision, suggested_human_action, missing_fields
            FROM human_reviews
            WHERE ticket_raw = %s
            ORDER BY created_at DESC
            LIMIT %s
        """
        return _safe_fetch_all(query, (ticket_raw, limit))

    query = """
        SELECT created_at::text, decision, suggested_human_action, missing_fields
        FROM human_reviews
        ORDER BY created_at DESC
        LIMIT %s
    """
    return _safe_fetch_all(query, (limit,))


def fetch_prior_executions(ticket_raw: str | None = None, limit: int = 5) -> list[dict[str, Any]]:
    """Fetch recent execution outcomes, optionally matching the same raw ticket text."""
    if ticket_raw:
        query = """
            SELECT created_at::text, action_taken, detail, status
            FROM execution_log
            WHERE ticket_raw = %s
            ORDER BY created_at DESC
            LIMIT %s
        """
        return _safe_fetch_all(query, (ticket_raw, limit))

    query = """
        SELECT created_at::text, action_taken, detail, status
        FROM execution_log
        ORDER BY created_at DESC
        LIMIT %s
    """
    return _safe_fetch_all(query, (limit,))


def fetch_missing_info_patterns(limit: int = 5) -> list[dict[str, Any]]:
    """Return the most common missing fields seen in human review records."""
    rows = _safe_fetch_all(
        """
        SELECT missing_fields
        FROM human_reviews
        WHERE missing_fields IS NOT NULL
        ORDER BY created_at DESC
        LIMIT 100
        """
    )
    counter: Counter[str] = Counter()
    for row in rows:
        for field in row.get("missing_fields") or []:
            counter[str(field)] += 1

    return [
        {"field": field, "count": count}
        for field, count in counter.most_common(limit)
    ]


def build_memory_context(state: dict[str, Any], limit: int = 5) -> dict[str, Any]:
    """Build a lightweight, non-authoritative memory context for operator visibility."""
    ticket = state.get("ticket_structured")
    customer_id = getattr(ticket, "customer_id", None) if ticket else None
    case_id = state.get("case_id") or customer_id
    correlation_id = state.get("correlation_id") or case_id

    return {
        "case_id": case_id,
        "correlation_id": correlation_id,
        "prior_cases": fetch_prior_cases(case_id=case_id, correlation_id=correlation_id, limit=limit),
        "prior_human_reviews": fetch_prior_human_reviews(state.get("ticket_raw"), limit=limit),
        "prior_executions": fetch_prior_executions(state.get("ticket_raw"), limit=limit),
        "missing_info_patterns": fetch_missing_info_patterns(limit=limit),
        "principle": "memory_informs_validation_decides_audit_persists",
    }
