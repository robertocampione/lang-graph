import os
import sys

# Ensure app is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db.connection import get_connection
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SCHEMA_SQL = """
DROP TABLE IF EXISTS audit_events CASCADE;
DROP TABLE IF EXISTS execution_log CASCADE;
DROP TABLE IF EXISTS human_reviews CASCADE;
DROP TABLE IF EXISTS installed_base_assets CASCADE;
DROP TABLE IF EXISTS pending_orders CASCADE;
DROP TABLE IF EXISTS customers CASCADE;

CREATE TABLE customers (
    customer_id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(150),
    tier VARCHAR(50),
    open_orders INT,
    oldest_pending_days INT,
    source VARCHAR(50)
);

CREATE TABLE pending_orders (
    pending_order_id VARCHAR(50) PRIMARY KEY,
    customer_id VARCHAR(50) REFERENCES customers(customer_id),
    order_type VARCHAR(50),
    order_status VARCHAR(50),
    scope_type VARCHAR(50),
    scope_id VARCHAR(50),
    planned_execution_date DATE,
    installation_pending BOOLEAN,
    oldest_pending_days INT,
    exception_markers TEXT[]
);

CREATE TABLE installed_base_assets (
    asset_id VARCHAR(50) PRIMARY KEY,
    customer_id VARCHAR(50) REFERENCES customers(customer_id),
    product_family VARCHAR(50),
    product_name VARCHAR(100),
    service_status VARCHAR(50)
);

CREATE TABLE human_reviews (
    id SERIAL PRIMARY KEY,
    ticket_raw TEXT,
    decision VARCHAR(50),
    rationale TEXT,
    suggested_human_action TEXT,
    missing_fields TEXT[],
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE execution_log (
    id SERIAL PRIMARY KEY,
    ticket_raw TEXT,
    action_taken VARCHAR(50),
    detail TEXT,
    status VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE audit_events (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    node_name VARCHAR(50),
    summary TEXT,
    actor_type VARCHAR(50),
    correlation_id VARCHAR(100),
    case_id VARCHAR(100),
    thread_id VARCHAR(100),
    payload_summary JSONB
);
"""

SEED_DATA_CUSTOMERS = [
    ("C-1001", "Acme Corp", "gold", 3, 12, "CRM_PROD"),
    ("C-1002", "Globex Inc", "silver", 1, 2, "CRM_PROD"),
    ("C-1003", "Stark Industries", "platinum", 5, 20, "CRM_PROD"),
    ("C-1004", "Wayne Enterprises", "standard", 0, 0, "CRM_PROD"),
    ("C-1005", "Cyberdyne Systems", "gold", 2, 5, "CRM_PROD"),
    ("C-1006", "Umbrella Corp", "platinum", 1, 35, "CRM_PROD"),
    ("C-1007", "Massive Dynamic", "standard", 1, 1, "CRM_PROD"),
    ("C-1008", "Tyrell Corporation", "silver", 2, 10, "CRM_PROD")
]

SEED_DATA_ORDERS = [
    # PO-1001: Same scope conflict for C-1001 (Fiber)
    ("PO-1001", "C-1001", "provision", "in_progress", "fiber", "FIB-555", "2026-05-01", True, 12, ["delay_reported"]),
    # PO-1002: Mobile modification for C-1002
    ("PO-1002", "C-1002", "modification", "on_hold", "mobile", "MOB-888", "2026-04-20", False, 2, []),
    # PO-1003: High oldest_pending_days for C-1003 (Platinum) - Will trigger escalation
    ("PO-1003", "C-1003", "move", "in_progress", "fiber", "FIB-111", "2026-04-25", False, 20, []),
    # PO-1005: Future dated order
    ("PO-1005", "C-1005", "cancellation", "open", "tv", "TV-999", "2027-01-01", False, 5, ["future_dated"]),
    # PO-1006: Extreme pendency
    ("PO-1006", "C-1006", "provision", "blocked", "fiber", "FIB-222", "2026-03-01", True, 35, ["technician_no_show"]),
    # PO-1007: Safe to allow
    ("PO-1007", "C-1007", "modification", "open", "mobile", "MOB-444", "2026-06-01", False, 1, []),
    # PO-1008: PMIT Mobile simulated
    ("PO-1008", "C-1008", "provision", "in_progress", "mobile", "MOB-555", "2026-04-18", False, 10, ["pmit_sync"])
]

SEED_DATA_ASSETS = [
    ("AST-111", "C-1001", "Internet", "Proximus Fiber Boost", "active"),
    ("AST-222", "C-1003", "Internet", "Proximus Fiber Max", "active"),
    ("AST-223", "C-1003", "Mobile", "Enterprise Mobile Plan", "active"),
    ("AST-444", "C-1005", "TV", "Proximus TV Extra", "active"),
    ("AST-555", "C-1008", "Mobile", "Business Mobile Gold", "active")
]

def main():
    logger.info("Connecting to PostgreSQL to seed Data Backbone...")
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # 1. Create Schema
                logger.info("Recreating schema...")
                cur.execute(SCHEMA_SQL)
                
                # 2. Insert Customers
                logger.info("Inserting customers...")
                cur.executemany(
                    "INSERT INTO customers (customer_id, name, tier, open_orders, oldest_pending_days, source) VALUES (%s, %s, %s, %s, %s, %s)",
                    SEED_DATA_CUSTOMERS
                )

                # 3. Insert Pending Orders
                logger.info("Inserting pending orders...")
                cur.executemany(
                    "INSERT INTO pending_orders (pending_order_id, customer_id, order_type, order_status, scope_type, scope_id, planned_execution_date, installation_pending, oldest_pending_days, exception_markers) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    SEED_DATA_ORDERS
                )

                # 4. Insert Installed Base
                logger.info("Inserting installed base assets...")
                cur.executemany(
                    "INSERT INTO installed_base_assets (asset_id, customer_id, product_family, product_name, service_status) VALUES (%s, %s, %s, %s, %s)",
                    SEED_DATA_ASSETS
                )
                
            conn.commit()
            logger.info("Database seed completed successfully!")

    except Exception as e:
        logger.error(f"Seeding failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
