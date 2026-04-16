from app.state.schema import GraphState
from app.tools.mock_db import fetch_customer_context

def integration(state: GraphState) -> dict:
    """
    Enrich the ticket with simulated customer and order context.

    Looks up the customer_id in a mock registry; falls back to
    a default profile if the customer is unknown or missing.
    """
    structured = state.get("ticket_structured", {})
    customer_id = getattr(structured, "customer_id", structured.get("customer_id") if isinstance(structured, dict) else None)

    context = fetch_customer_context(customer_id)

    return {
        "messages": [
            f"[integration] Context loaded for "
            f"{context.get('name', 'Unknown')} ({customer_id or 'n/a'})."
        ],
        "customer_context": context,
    }
