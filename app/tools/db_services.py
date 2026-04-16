from typing import Optional, List, Dict, Any
from app.db.connection import fetch_one, fetch_all

def fetch_customer_context(customer_id: Optional[str]) -> Dict[str, Any]:
    """Retrieve customer context from the database."""
    if not customer_id:
        return _default_customer()
        
    query = """
        SELECT customer_id, name, tier, open_orders, oldest_pending_days, source 
        FROM customers
        WHERE customer_id = %s
    """
    row = fetch_one(query, (customer_id,))
    if row:
        return dict(row)
    
    return _default_customer()

def fetch_pending_order_context(customer_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """Retrieve pending order context from the database."""
    if not customer_id:
        return None
        
    query = """
        SELECT pending_order_id, customer_id, order_type, order_status, 
               scope_type, scope_id, planned_execution_date::text, 
               installation_pending, oldest_pending_days, exception_markers
        FROM pending_orders
        WHERE customer_id = %s
        ORDER BY oldest_pending_days DESC
        LIMIT 1
    """
    row = fetch_one(query, (customer_id,))
    if row:
        return dict(row)
        
    return None

def fetch_installed_base_context(customer_id: Optional[str]) -> List[Dict[str, Any]]:
    """Retrieve installed base context from the database."""
    if not customer_id:
        return []
        
    query = """
        SELECT asset_id, customer_id, product_family, product_name, service_status
        FROM installed_base_assets
        WHERE customer_id = %s
    """
    rows = fetch_all(query, (customer_id,))
    return [dict(row) for row in rows]

def _default_customer() -> Dict[str, Any]:
    return {
        "name": "Unknown",
        "tier": "standard",
        "open_orders": 0,
        "oldest_pending_days": 0,
        "source": "default_fallback"
    }
