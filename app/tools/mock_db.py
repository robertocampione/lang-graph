"""
Mock database and integration stubs.
In a real application, these would call out to CRM, Postgres, or external APIs.
"""

MOCK_CUSTOMERS: dict[str, dict] = {
    "C-1001": {
        "name": "Acme Corp",
        "tier": "gold",
        "open_orders": 3,
        "oldest_pending_days": 12,
    },
    "C-1002": {
        "name": "Globex Inc",
        "tier": "silver",
        "open_orders": 1,
        "oldest_pending_days": 2,
    },
}

DEFAULT_CUSTOMER: dict = {
    "name": "Unknown",
    "tier": "standard",
    "open_orders": 0,
    "oldest_pending_days": 0,
}

def fetch_customer_context(customer_id: str | None) -> dict:
    if customer_id and customer_id in MOCK_CUSTOMERS:
        return {**MOCK_CUSTOMERS[customer_id], "source": "mock_crm"}
    return {**DEFAULT_CUSTOMER, "source": "default_fallback"}
