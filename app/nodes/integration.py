from app.state.schema import GraphState, CustomerContext, PendingOrderContext, InstalledBaseContext
from app.tools.db_services import fetch_customer_context, fetch_pending_order_context, fetch_installed_base_context
from app.tools.case_history import build_memory_context
from app.tools.audit import write_audit_event
from typing import List
import logging

logger = logging.getLogger(__name__)

def integration(state: GraphState) -> dict:
    """
    Enrich the ticket with customer, pending order, and installed base context from Postgres.
    Maps dictionaries returned by DB tools to proper Pydantic schemas.
    """
    structured = state.get("ticket_structured")
    customer_id = structured.customer_id if structured else None

    # Load Customer
    c_data = fetch_customer_context(customer_id)
    customer_context = CustomerContext(**c_data)

    # Load Pending Orders
    po_data = fetch_pending_order_context(customer_id)
    pending_order_context = PendingOrderContext(**po_data) if po_data else None

    # Load Installed Base
    ib_data = fetch_installed_base_context(customer_id)
    installed_base_context: List[InstalledBaseContext] = [InstalledBaseContext(**item) for item in ib_data]

    summary = (f"Customer: {customer_context.name} ({customer_id or 'n/a'}). "
               f"Pending Orders: {po_data.get('pending_order_id') if po_data else 'None'}. "
               f"Installed Base size: {len(installed_base_context)}.")

    updated_state = {
        **state,
        "customer_context": customer_context,
        "pending_order_context": pending_order_context,
        "installed_base_context": installed_base_context,
    }
    memory_context = build_memory_context(updated_state)
    audit_entry = write_audit_event(
        "integration",
        f"Context loaded. {summary}",
        state=updated_state,
        payload={
            "pending_order_id": po_data.get("pending_order_id") if po_data else None,
            "installed_base_size": len(installed_base_context),
        },
    )

    return {
        "messages": [f"[integration] Context loaded. {summary}"],
        "audit_log": [audit_entry],
        "memory_context": memory_context,
        "customer_context": customer_context,
        "pending_order_context": pending_order_context,
        "installed_base_context": installed_base_context
    }
