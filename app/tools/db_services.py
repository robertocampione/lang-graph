from typing import Any, Dict, List, Optional

from app.db.connection import fetch_all, fetch_one


def _rows(query: str, params: tuple = ()) -> List[Dict[str, Any]]:
    return [dict(row) for row in fetch_all(query, params)]


def _row(query: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
    row = fetch_one(query, params)
    return dict(row) if row else None


def fetch_customer_context(customer_id: Optional[str]) -> Dict[str, Any]:
    """Backward-compatible customer lookup used by old and new graph fields."""
    if not customer_id:
        return _default_customer()

    try:
        row = _row(
            """
            SELECT customer_id, name, tier, segment, account_status, open_orders, oldest_pending_days, source
            FROM customers
            WHERE customer_id = %s
            """,
            (customer_id,),
        )
    except Exception:
        row = _row(
            """
            SELECT customer_id, name, tier, open_orders, oldest_pending_days, source
            FROM customers
            WHERE customer_id = %s
            """,
            (customer_id,),
        )

    if row:
        row.setdefault("segment", "CBU")
        row.setdefault("account_status", "active")
        return row

    return _default_customer()


def fetch_salto_customer_context(customer_id: Optional[str]) -> Dict[str, Any]:
    """SALTO-flavoured customer lookup. Kept explicit for PoC storytelling."""
    return fetch_customer_context(customer_id)


def fetch_pending_order_context(customer_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """Backward-compatible single pending order lookup."""
    if not customer_id:
        return None

    try:
        row = _row(
            """
            SELECT pending_order_id, customer_id, order_type, order_status, scope_type, scope_id,
                   address_id, bundle_id, product_family, planned_execution_date::text,
                   installation_pending, oldest_pending_days, exception_markers, exclusion_markers,
                   milestone, delivery_reached, device_return_pending, device_return_days,
                   ponr_reached, final_disconnect, source_system
            FROM pending_orders
            WHERE customer_id = %s
            ORDER BY oldest_pending_days DESC
            LIMIT 1
            """,
            (customer_id,),
        )
    except Exception:
        row = _row(
            """
            SELECT pending_order_id, customer_id, order_type, order_status, scope_type, scope_id,
                   planned_execution_date::text, installation_pending, oldest_pending_days, exception_markers
            FROM pending_orders
            WHERE customer_id = %s
            ORDER BY oldest_pending_days DESC
            LIMIT 1
            """,
            (customer_id,),
        )

    return _normalize_pending_order(row) if row else None


def fetch_salto_orders(customer_id: Optional[str]) -> List[Dict[str, Any]]:
    """Fetch all simulated SALTO orders for a customer."""
    if not customer_id:
        return []

    try:
        rows = _rows(
            """
            SELECT salto_order_id, customer_id, order_type, order_status, scope_type, scope_id,
                   address_id, bundle_id, product_family, requested_action, planned_execution_date::text,
                   installation_pending, oldest_pending_days, exception_markers, exclusion_markers,
                   delivery_reached, device_return_pending, device_return_days, ponr_reached,
                   final_disconnect, source_system
            FROM salto_orders
            WHERE customer_id = %s
            ORDER BY oldest_pending_days DESC, salto_order_id
            """,
            (customer_id,),
        )
    except Exception:
        return []

    for row in rows:
        row["milestones"] = fetch_order_milestones(row["salto_order_id"])
    return rows


def fetch_order_milestones(salto_order_id: str) -> List[Dict[str, Any]]:
    """Fetch milestones for a simulated SALTO order."""
    try:
        return _rows(
            """
            SELECT milestone, reached, reached_at::text
            FROM order_milestones
            WHERE salto_order_id = %s
            ORDER BY id
            """,
            (salto_order_id,),
        )
    except Exception:
        return []


def fetch_customer_addresses(customer_id: Optional[str]) -> List[Dict[str, Any]]:
    """Fetch SALTO customer addresses."""
    if not customer_id:
        return []
    try:
        return _rows(
            """
            SELECT address_id, customer_id, label, serviceable, source_system
            FROM customer_addresses
            WHERE customer_id = %s
            ORDER BY address_id
            """,
            (customer_id,),
        )
    except Exception:
        return []


def fetch_installed_base_context(customer_id: Optional[str]) -> List[Dict[str, Any]]:
    """Backward-compatible installed base lookup."""
    return fetch_installed_assets(customer_id)


def fetch_installed_assets(customer_id: Optional[str]) -> List[Dict[str, Any]]:
    """Fetch SALTO installed assets for a customer."""
    if not customer_id:
        return []

    try:
        return _rows(
            """
            SELECT asset_id, customer_id, address_id, bundle_id, scope_type, scope_id,
                   product_family, product_name, service_status
            FROM installed_base_assets
            WHERE customer_id = %s
            ORDER BY asset_id
            """,
            (customer_id,),
        )
    except Exception:
        rows = _rows(
            """
            SELECT asset_id, customer_id, product_family, product_name, service_status
            FROM installed_base_assets
            WHERE customer_id = %s
            ORDER BY asset_id
            """,
            (customer_id,),
        )
        for row in rows:
            row.setdefault("address_id", None)
            row.setdefault("bundle_id", None)
            row.setdefault("scope_type", None)
            row.setdefault("scope_id", None)
        return rows


def fetch_bundle_context(bundle_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """Fetch bundle/pack membership for a bundle id."""
    if not bundle_id:
        return None

    try:
        rows = _rows(
            """
            SELECT bundle_id, customer_id, address_id, asset_id, scope_id
            FROM bundle_memberships
            WHERE bundle_id = %s
            ORDER BY asset_id
            """,
            (bundle_id,),
        )
    except Exception:
        return None
    if not rows:
        return None

    first = rows[0]
    return {
        "bundle_id": first["bundle_id"],
        "customer_id": first["customer_id"],
        "address_id": first["address_id"],
        "member_scope_ids": [row["scope_id"] for row in rows if row.get("scope_id")],
        "member_asset_ids": [row["asset_id"] for row in rows if row.get("asset_id")],
    }


def fetch_bci_case_context(bci_case_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """Fetch a simulated BCI case plus its timeline events."""
    if not bci_case_id:
        return None

    try:
        row = _row(
            """
            SELECT bci_case_id, customer_id, status, priority, intake_channel, ticket_type_raw,
                   creator_role, assigned_queue, data_quality, raw_description, closure_reason
            FROM bci_cases
            WHERE bci_case_id = %s
            """,
            (bci_case_id,),
        )
    except Exception:
        return None
    if not row:
        return None

    row["intake"] = {
        "intake_channel": row.pop("intake_channel") or "unknown",
        "ticket_type_raw": row.pop("ticket_type_raw"),
        "creator_role": row.pop("creator_role") or "unknown",
        "assigned_queue": row.get("assigned_queue"),
        "data_quality": row.pop("data_quality") or "unknown",
    }
    try:
        row["events"] = _rows(
            """
            SELECT event_id, bci_case_id, actor_role, event_type, notes, created_at::text
            FROM bci_case_events
            WHERE bci_case_id = %s
            ORDER BY created_at, event_id
            """,
            (bci_case_id,),
        )
    except Exception:
        row["events"] = []
    return row


def fetch_compatibility_decision(
    segment: Optional[str],
    pending_order_type: Optional[str],
    follow_on_action: Optional[str],
) -> Optional[Dict[str, Any]]:
    """Fetch the PMIT Mobile style Accept/Block matrix decision."""
    if not segment or not pending_order_type or not follow_on_action:
        return None

    try:
        return _row(
            """
            SELECT segment, pending_order_type, follow_on_action, decision, reason
            FROM compatibility_matrix
            WHERE lower(segment) = lower(%s)
              AND lower(pending_order_type) = lower(%s)
              AND lower(follow_on_action) = lower(%s)
            LIMIT 1
            """,
            (segment, pending_order_type, follow_on_action),
        )
    except Exception:
        return None


def _normalize_pending_order(row: Dict[str, Any]) -> Dict[str, Any]:
    row.setdefault("address_id", None)
    row.setdefault("bundle_id", None)
    row.setdefault("product_family", None)
    row.setdefault("exclusion_markers", [])
    row.setdefault("milestone", None)
    row.setdefault("delivery_reached", False)
    row.setdefault("device_return_pending", False)
    row.setdefault("device_return_days", 0)
    row.setdefault("ponr_reached", False)
    row.setdefault("final_disconnect", False)
    row.setdefault("source_system", "SALTO")
    return row


def _default_customer() -> Dict[str, Any]:
    return {
        "name": "Unknown",
        "tier": "standard",
        "segment": "CBU",
        "account_status": "unknown",
        "open_orders": 0,
        "oldest_pending_days": 0,
        "source": "default_fallback",
    }
