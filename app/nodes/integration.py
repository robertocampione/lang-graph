from typing import List, Optional

from app.state.schema import (
    BciCaseContext,
    BundleContext,
    CustomerAddress,
    CustomerContext,
    InstalledAssetContext,
    InstalledBaseContext,
    PendingOrderContext,
    RequestedSecondOrder,
    SaltoOrderContext,
    ScopeRef,
    GraphState,
)
from app.tools.audit import write_audit_event
from app.tools.case_history import build_memory_context
from app.tools.db_services import (
    fetch_bci_case_context,
    fetch_bundle_context,
    fetch_customer_addresses,
    fetch_customer_context,
    fetch_installed_base_context,
    fetch_installed_assets,
    fetch_pending_order_context,
    fetch_salto_orders,
)


def _ticket_value(ticket, name: str) -> Optional[str]:
    return getattr(ticket, name, None) if ticket else None


def _candidate_bci_case_id(state: GraphState) -> Optional[str]:
    ticket = state.get("ticket_structured")
    bci_case_id = _ticket_value(ticket, "bci_case_id")
    case_id = state.get("case_id")
    if bci_case_id:
        return bci_case_id
    if case_id and str(case_id).upper().startswith("BCI-"):
        return str(case_id)
    return None


def _select_salto_order(ticket, orders: List[SaltoOrderContext]) -> Optional[SaltoOrderContext]:
    """Select the most relevant SALTO order using explicit identifiers first."""
    if not orders:
        return None

    order_ref = _ticket_value(ticket, "salto_order_reference")
    if order_ref:
        for order in orders:
            if order.salto_order_id.lower() == order_ref.lower():
                return order

    ticket_scope = _ticket_value(ticket, "scope_type")
    ticket_scope_id = _ticket_value(ticket, "scope_id")
    ticket_address = _ticket_value(ticket, "address_id") or _ticket_value(ticket, "address_identifier")

    for order in orders:
        if ticket_scope_id and order.scope_id == ticket_scope_id:
            return order

    for order in orders:
        if ticket_scope and order.scope_type == ticket_scope and (not ticket_address or order.address_id == ticket_address):
            return order

    return orders[0]


def _pending_alias(order: Optional[SaltoOrderContext], legacy_data: Optional[dict]) -> Optional[PendingOrderContext]:
    if order:
        return PendingOrderContext(
            pending_order_id=order.salto_order_id,
            customer_id=order.customer_id,
            order_type=order.order_type,
            order_status=order.order_status,
            scope_type=order.scope_type,
            scope_id=order.scope_id,
            address_id=order.address_id,
            bundle_id=order.bundle_id,
            product_family=order.product_family,
            planned_execution_date=order.planned_execution_date,
            installation_pending=order.installation_pending,
            oldest_pending_days=order.oldest_pending_days,
            exception_markers=list(order.exception_markers),
            exclusion_markers=list(order.exclusion_markers),
            milestone=order.milestones[0].milestone if order.milestones else None,
            delivery_reached=order.delivery_reached,
            device_return_pending=order.device_return_pending,
            device_return_days=order.device_return_days,
            ponr_reached=order.ponr_reached,
            final_disconnect=order.final_disconnect,
            source_system=order.source_system,
        )

    return PendingOrderContext(**legacy_data) if legacy_data else None


def _requested_second_order(ticket, bci_case: Optional[BciCaseContext]) -> RequestedSecondOrder:
    scope_type = _ticket_value(ticket, "scope_type")
    scope = None
    if scope_type:
        scope = ScopeRef(
            scope_type=scope_type,
            scope_id=_ticket_value(ticket, "scope_id"),
            address_id=_ticket_value(ticket, "address_id") or _ticket_value(ticket, "address_identifier"),
        )

    return RequestedSecondOrder(
        action=_ticket_value(ticket, "requested_action") or _ticket_value(ticket, "requested_follow_on_action") or _ticket_value(ticket, "request_type"),
        scope=scope,
        target_product_family=_ticket_value(ticket, "product_family"),
        source_case_id=bci_case.bci_case_id if bci_case else _ticket_value(ticket, "bci_case_id"),
        source_channel=bci_case.intake.intake_channel if bci_case else _ticket_value(ticket, "intake_channel"),
    )


def integration(state: GraphState) -> dict:
    """
    Load BCI case data and SALTO context.

    The new PoC flow is case-first, then SALTO. Old aliases are still populated
    because they keep the existing tests, demo runner, and validation call sites simple.
    """
    ticket = state.get("ticket_structured")
    bci_case_id = _candidate_bci_case_id(state)
    bci_data = fetch_bci_case_context(bci_case_id)
    bci_case = BciCaseContext(**bci_data) if bci_data else None

    customer_id = (
        _ticket_value(ticket, "customer_id")
        or _ticket_value(ticket, "customer_identifier")
        or (bci_case.customer_id if bci_case else None)
    )

    customer_context = CustomerContext(**fetch_customer_context(customer_id))
    addresses = [CustomerAddress(**item) for item in fetch_customer_addresses(customer_id)]
    salto_orders = [SaltoOrderContext(**item) for item in fetch_salto_orders(customer_id)]
    selected_order = _select_salto_order(ticket, salto_orders)

    legacy_pending_data = None if selected_order else fetch_pending_order_context(customer_id)
    pending_alias = _pending_alias(selected_order, legacy_pending_data)

    installed_assets = [InstalledAssetContext(**item) for item in fetch_installed_assets(customer_id)]
    installed_base_context: List[InstalledBaseContext] = [InstalledBaseContext(**item.model_dump()) for item in installed_assets]

    bundle_id = selected_order.bundle_id if selected_order else getattr(pending_alias, "bundle_id", None)
    bundle_data = fetch_bundle_context(bundle_id)
    bundle_context = BundleContext(**bundle_data) if bundle_data else None
    requested_second_order = _requested_second_order(ticket, bci_case)

    summary = (
        f"BCI: {bci_case.bci_case_id if bci_case else 'none'}. "
        f"Customer: {customer_context.name} ({customer_id or 'n/a'}). "
        f"SALTO orders: {len(salto_orders)}. "
        f"Selected: {selected_order.salto_order_id if selected_order else getattr(pending_alias, 'pending_order_id', 'None')}. "
        f"Installed assets: {len(installed_assets)}."
    )

    updated_state = {
        **state,
        "bci_case_context": bci_case,
        "customer_context": customer_context,
        "customer_addresses": addresses,
        "salto_orders": salto_orders,
        "selected_salto_order": selected_order,
        "pending_order_context": pending_alias,
        "installed_assets": installed_assets,
        "installed_base_context": installed_base_context,
        "bundle_context": bundle_context,
        "requested_second_order": requested_second_order,
    }
    memory_context = build_memory_context(updated_state)
    audit_entry = write_audit_event(
        "integration",
        f"Context loaded. {summary}",
        state=updated_state,
        payload={
            "bci_case_id": bci_case.bci_case_id if bci_case else None,
            "customer_id": customer_id,
            "salto_order_id": selected_order.salto_order_id if selected_order else None,
            "installed_asset_count": len(installed_assets),
        },
    )

    return {
        "messages": [f"Integration: Context loaded. {summary}"],
        "audit_log": [audit_entry],
        "memory_context": memory_context,
        "bci_case_context": bci_case,
        "customer_context": customer_context,
        "customer_addresses": addresses,
        "salto_orders": salto_orders,
        "selected_salto_order": selected_order,
        "pending_order_context": pending_alias,
        "installed_assets": installed_assets,
        "installed_base_context": installed_base_context,
        "bundle_context": bundle_context,
        "requested_second_order": requested_second_order,
    }
