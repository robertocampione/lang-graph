import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.connection import get_connection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


SCHEMA_SQL = """
DROP TABLE IF EXISTS audit_events CASCADE;
DROP TABLE IF EXISTS execution_log CASCADE;
DROP TABLE IF EXISTS human_reviews CASCADE;
DROP TABLE IF EXISTS action_catalog CASCADE;
DROP TABLE IF EXISTS compatibility_matrix CASCADE;
DROP TABLE IF EXISTS bundle_memberships CASCADE;
DROP TABLE IF EXISTS order_milestones CASCADE;
DROP TABLE IF EXISTS salto_orders CASCADE;
DROP TABLE IF EXISTS bci_case_events CASCADE;
DROP TABLE IF EXISTS bci_cases CASCADE;
DROP TABLE IF EXISTS customer_addresses CASCADE;
DROP TABLE IF EXISTS installed_base_assets CASCADE;
DROP TABLE IF EXISTS pending_orders CASCADE;
DROP TABLE IF EXISTS customers CASCADE;

CREATE TABLE customers (
    customer_id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(150),
    tier VARCHAR(50),
    segment VARCHAR(50),
    account_status VARCHAR(50),
    open_orders INT,
    oldest_pending_days INT,
    source VARCHAR(50)
);

CREATE TABLE customer_addresses (
    address_id VARCHAR(50) PRIMARY KEY,
    customer_id VARCHAR(50) REFERENCES customers(customer_id),
    label VARCHAR(150),
    serviceable BOOLEAN,
    source_system VARCHAR(50)
);

CREATE TABLE pending_orders (
    pending_order_id VARCHAR(50) PRIMARY KEY,
    customer_id VARCHAR(50) REFERENCES customers(customer_id),
    order_type VARCHAR(50),
    order_status VARCHAR(50),
    scope_type VARCHAR(50),
    scope_id VARCHAR(50),
    address_id VARCHAR(50),
    bundle_id VARCHAR(50),
    product_family VARCHAR(50),
    planned_execution_date DATE,
    installation_pending BOOLEAN,
    oldest_pending_days INT,
    exception_markers TEXT[],
    exclusion_markers TEXT[],
    milestone VARCHAR(50),
    delivery_reached BOOLEAN,
    device_return_pending BOOLEAN,
    device_return_days INT,
    ponr_reached BOOLEAN,
    final_disconnect BOOLEAN,
    source_system VARCHAR(50)
);

CREATE TABLE salto_orders (
    salto_order_id VARCHAR(50) PRIMARY KEY,
    customer_id VARCHAR(50) REFERENCES customers(customer_id),
    order_type VARCHAR(50),
    order_status VARCHAR(50),
    scope_type VARCHAR(50),
    scope_id VARCHAR(50),
    address_id VARCHAR(50),
    bundle_id VARCHAR(50),
    product_family VARCHAR(50),
    requested_action VARCHAR(80),
    planned_execution_date DATE,
    installation_pending BOOLEAN,
    oldest_pending_days INT,
    exception_markers TEXT[],
    exclusion_markers TEXT[],
    delivery_reached BOOLEAN,
    device_return_pending BOOLEAN,
    device_return_days INT,
    ponr_reached BOOLEAN,
    final_disconnect BOOLEAN,
    source_system VARCHAR(50)
);

CREATE TABLE order_milestones (
    id SERIAL PRIMARY KEY,
    salto_order_id VARCHAR(50) REFERENCES salto_orders(salto_order_id),
    milestone VARCHAR(50),
    reached BOOLEAN,
    reached_at TIMESTAMP NULL
);

CREATE TABLE installed_base_assets (
    asset_id VARCHAR(50) PRIMARY KEY,
    customer_id VARCHAR(50) REFERENCES customers(customer_id),
    address_id VARCHAR(50),
    bundle_id VARCHAR(50),
    scope_type VARCHAR(50),
    scope_id VARCHAR(50),
    product_family VARCHAR(50),
    product_name VARCHAR(100),
    service_status VARCHAR(50)
);

CREATE TABLE bundle_memberships (
    id SERIAL PRIMARY KEY,
    bundle_id VARCHAR(50),
    customer_id VARCHAR(50) REFERENCES customers(customer_id),
    address_id VARCHAR(50),
    asset_id VARCHAR(50),
    scope_type VARCHAR(50),
    scope_id VARCHAR(50)
);

CREATE TABLE bci_cases (
    bci_case_id VARCHAR(50) PRIMARY KEY,
    customer_id VARCHAR(50),
    status VARCHAR(50),
    priority VARCHAR(50),
    intake_channel VARCHAR(80),
    ticket_type_raw VARCHAR(120),
    creator_role VARCHAR(80),
    assigned_queue VARCHAR(80),
    data_quality VARCHAR(50),
    raw_description TEXT,
    closure_reason VARCHAR(120)
);

CREATE TABLE bci_case_events (
    event_id VARCHAR(50) PRIMARY KEY,
    bci_case_id VARCHAR(50) REFERENCES bci_cases(bci_case_id),
    actor_role VARCHAR(80),
    event_type VARCHAR(80),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE compatibility_matrix (
    id SERIAL PRIMARY KEY,
    segment VARCHAR(50),
    pending_order_type VARCHAR(50),
    follow_on_action VARCHAR(80),
    decision VARCHAR(20),
    reason VARCHAR(150)
);

CREATE TABLE action_catalog (
    action_type VARCHAR(80) PRIMARY KEY,
    target_system VARCHAR(50),
    auto_eligible BOOLEAN,
    description TEXT
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
    action_taken VARCHAR(80),
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


CUSTOMERS = [
    ("C-1001", "Synthetic Fiber Home", "gold", "CBU", "active", 3, 12, "SALTO"),
    ("C-1002", "Synthetic Mobile Customer", "silver", "CBU", "active", 1, 2, "SALTO"),
    ("C-1003", "Synthetic Enterprise Fiber", "platinum", "EBU", "active", 5, 20, "SALTO"),
    ("C-1004", "Synthetic No Pending", "standard", "CBU", "active", 0, 0, "SALTO"),
    ("C-1005", "Synthetic Future TV", "gold", "CBU", "active", 2, 5, "SALTO"),
    ("C-1006", "Synthetic Installation Hold", "platinum", "CBU", "active", 1, 35, "SALTO"),
    ("C-1007", "Synthetic Bundle Family", "standard", "CBU", "active", 1, 1, "SALTO"),
    ("C-1008", "Synthetic PMIT Mobile", "silver", "PMIT_MOBILE", "active", 2, 10, "SALTO"),
    ("C-1009", "Synthetic Device Return", "standard", "CBU", "active", 1, 18, "SALTO"),
    ("C-1010", "Synthetic SIM Exclusion", "standard", "CBU", "active", 1, 4, "SALTO"),
    ("C-1011", "Synthetic Port Out", "gold", "CBU", "active", 1, 3, "SALTO"),
    ("C-1012", "Synthetic PMIT Fix", "gold", "PMIT_FIX", "active", 1, 7, "SALTO"),
]

ADDRESSES = [
    ("ADDR-1001-A", "C-1001", "Main service address", True, "SALTO"),
    ("ADDR-1002-A", "C-1002", "Mobile billing address", True, "SALTO"),
    ("ADDR-1003-A", "C-1003", "Enterprise site Brussels", True, "SALTO"),
    ("ADDR-1004-A", "C-1004", "No-pending service address", True, "SALTO"),
    ("ADDR-1005-A", "C-1005", "TV service address", True, "SALTO"),
    ("ADDR-1006-A", "C-1006", "Installation service address", True, "SALTO"),
    ("ADDR-1007-A", "C-1007", "Pack service address", True, "SALTO"),
    ("ADDR-1008-A", "C-1008", "Enterprise mobile account", True, "SALTO"),
    ("ADDR-1009-A", "C-1009", "Device return address", True, "SALTO"),
    ("ADDR-1010-A", "C-1010", "SIM exclusion address", True, "SALTO"),
    ("ADDR-1011-A", "C-1011", "Port-out address", True, "SALTO"),
    ("ADDR-1012-A", "C-1012", "PMIT fix address", True, "SALTO"),
]

SALTO_ORDERS = [
    ("PO-1001", "C-1001", "provision", "in_progress", "fiber", "FIB-555", "ADDR-1001-A", None, "Internet", "new_provide", "2026-05-01", True, 12, ["delay_reported"], [], False, False, 0, False, False, "SALTO"),
    ("PO-1002", "C-1002", "modification", "on_hold", "mobile", "MOB-888", "ADDR-1002-A", None, "Mobile", "modify_mobile_subscription", "2026-04-20", False, 2, [], [], True, False, 0, False, False, "SALTO"),
    ("PO-1003", "C-1003", "move", "in_progress", "fiber", "FIB-111", "ADDR-1003-A", None, "Internet", "move_fiber", "2026-04-25", False, 20, [], [], False, False, 0, False, False, "SALTO"),
    ("PO-1005", "C-1005", "cancellation", "open", "tv", "TV-999", "ADDR-1005-A", None, "TV", "change_cancellation", "2026-07-01", False, 5, ["future_dated"], [], False, False, 0, False, False, "SALTO"),
    ("PO-1006", "C-1006", "provision", "blocked", "fiber", "FIB-222", "ADDR-1006-A", None, "Internet", "new_provide", "2026-03-01", True, 35, ["technician_no_show"], [], False, False, 0, False, False, "SALTO"),
    ("PO-1007", "C-1007", "bundle", "in_progress", "bundle", "BUN-777", "ADDR-1007-A", "BUN-777", "Pack", "install_pack", "2026-06-01", False, 1, [], [], False, False, 0, False, False, "SALTO"),
    ("PO-1008", "C-1008", "provision", "in_progress", "mobile", "MOB-555", "ADDR-1008-A", None, "Mobile", "activate_mobile", "2026-04-18", False, 10, ["pmit_sync"], [], True, False, 0, False, False, "SALTO"),
    ("PO-1009", "C-1009", "cease", "return_pending", "device", "DEV-1009", "ADDR-1009-A", None, "Device", "device_return", "2026-03-20", False, 18, ["device_return_only"], [], True, True, 18, True, False, "SALTO"),
    ("PO-1010", "C-1010", "provision", "in_progress", "mobile", "MOB-1010", "ADDR-1010-A", None, "Mobile", "activate_mobile", "2026-04-22", False, 4, ["sim_exception"], ["duo_card"], True, False, 0, False, False, "SALTO"),
    ("PO-1011", "C-1011", "port_out", "disconnecting", "fiber", "FIB-1011", "ADDR-1011-A", None, "Internet", "final_disconnect", "2026-04-19", False, 3, [], [], False, False, 0, False, True, "SALTO"),
    ("PO-1012", "C-1012", "provision", "in_progress", "fiber", "FIB-1012", "ADDR-1012-A", None, "Internet", "pmit_fix_install", "2026-04-28", False, 7, [], [], False, False, 0, False, False, "SALTO"),
]

MILESTONES = [
    ("PO-1001", "delivery", False, None),
    ("PO-1002", "delivery", True, "2026-04-16 10:00:00"),
    ("PO-1003", "delivery", False, None),
    ("PO-1005", "delivery", False, None),
    ("PO-1007", "delivery", False, None),
    ("PO-1008", "delivery", True, "2026-04-16 09:00:00"),
    ("PO-1009", "execution", True, "2026-03-20 09:00:00"),
    ("PO-1011", "ponr", False, None),
]

ASSETS = [
    ("AST-111", "C-1001", "ADDR-1001-A", None, "fiber", "FIB-555", "Internet", "Proximus Fiber Boost", "active"),
    ("AST-222", "C-1003", "ADDR-1003-A", None, "fiber", "FIB-111", "Internet", "Proximus Fiber Max", "active"),
    ("AST-223", "C-1003", "ADDR-1003-A", None, "mobile", "MOB-223", "Mobile", "Enterprise Mobile Plan", "active"),
    ("AST-444", "C-1005", "ADDR-1005-A", None, "tv", "TV-999", "TV", "Proximus TV Extra", "active"),
    ("AST-555", "C-1008", "ADDR-1008-A", None, "mobile", "MOB-555", "Mobile", "Business Mobile Gold", "active"),
    ("AST-777-I", "C-1007", "ADDR-1007-A", "BUN-777", "fiber", "FIB-777", "Internet", "Pack Internet", "active"),
    ("AST-777-TV", "C-1007", "ADDR-1007-A", "BUN-777", "tv", "TV-777", "TV", "Pack TV", "active"),
    ("AST-1009", "C-1009", "ADDR-1009-A", None, "device", "DEV-1009", "Device", "Internet Box", "return_pending"),
]

BUNDLES = [
    ("BUN-777", "C-1007", "ADDR-1007-A", "AST-777-I", "fiber", "FIB-777"),
    ("BUN-777", "C-1007", "ADDR-1007-A", "AST-777-TV", "tv", "TV-777"),
]

BCI_CASES = [
    ("BCI-9001", "C-1001", "NEW", "high", "Sales Support Tool", "Pending order - second order", "store_employee", "BACK_OFFICE_PENDING", "complete", "Customer asks to introduce a second fiber change while installation is delayed.", None),
    ("BCI-9002", "C-1002", "NEW", "normal", "Sales Portal", "Mobile modification blocked", "helpdesk", "BACK_OFFICE_PENDING", "complete", "Customer needs a SIM swap only while mobile order is pending.", None),
    ("BCI-9003", "C-1007", "NEW", "normal", "BCI Direct", "Pack modification", "first_line", "BACK_OFFICE_PENDING", "complete", "Customer wants to remove TV from a pack with a pending bundle order.", None),
    ("BCI-9004", "C-1008", "NEW", "normal", "Sales Portal", "PMIT mobile change", "helpdesk", "BACK_OFFICE_PENDING", "complete", "PMIT Mobile customer asks for roaming option during pending activation.", None),
    ("BCI-9005", "C-1009", "ON_HOLD", "normal", "Sales Support Tool", "Device return follow-on", "store_employee", "BACK_OFFICE_PENDING", "complete", "Only device return is pending; customer asks for second order.", None),
]

BCI_EVENTS = [
    ("EV-9001-1", "BCI-9001", "STORE_EMPLOYEE", "created", "Ticket created from Sales Support Tool."),
    ("EV-9002-1", "BCI-9002", "HELPDESK", "created", "Helpdesk noted SIM swap only."),
    ("EV-9003-1", "BCI-9003", "FIRST_LINE", "created", "Pack member requested while pack order open."),
    ("EV-9004-1", "BCI-9004", "HELPDESK", "created", "PMIT Mobile matrix case."),
    ("EV-9005-1", "BCI-9005", "BACK_OFFICE_AGENT", "hold", "Waiting for device return window."),
]

MATRIX = [
    ("PMIT_MOBILE", "provision", "add_roaming_option", "ACCEPT", "PMIT Mobile matrix allows roaming option during activation."),
    ("PMIT_MOBILE", "provision", "modify_mobile_subscription", "BLOCK", "PMIT Mobile matrix blocks subscription swap during activation."),
    ("PMIT_MOBILE", "provision", "add_barring_option", "ACCEPT", "PMIT Mobile matrix allows barring option."),
]

ACTIONS = [
    ("REQUEST_MISSING_INFO", "BCI", False, "Ask first line or customer for missing identifiers."),
    ("HOLD_BCI_CASE", "BCI", False, "Hold BCI case with a clear reason."),
    ("CLOSE_BCI_CASE_WITH_REMARK", "BCI", False, "Close BCI case with operator remark."),
    ("PREPARE_SECOND_ORDER", "SALTO", False, "Prepare second order for human execution."),
    ("INTRODUCE_SECOND_ORDER_DRY_RUN", "SALTO", True, "Dry-run autonomous second-order introduction."),
    ("AMEND_ORDER_DRY_RUN", "SALTO", True, "Dry-run amend order in SALTO."),
    ("ESCALATE_TO_BACK_OFFICE", "BCI", False, "Escalate to back-office or supervisor queue."),
]


def _legacy_pending_orders():
    return [
        (
            order[0], order[1], order[2], order[3], order[4], order[5], order[6], order[7], order[8],
            order[10], order[11], order[12], order[13], order[14], "delivery", order[15],
            order[16], order[17], order[18], order[19], order[20],
        )
        for order in SALTO_ORDERS
    ]


def main():
    logger.info("Connecting to PostgreSQL to seed BCI/SALTO simulation data...")
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                logger.info("Recreating schema...")
                cur.execute(SCHEMA_SQL)

                logger.info("Inserting customers and addresses...")
                cur.executemany(
                    """
                    INSERT INTO customers
                        (customer_id, name, tier, segment, account_status, open_orders, oldest_pending_days, source)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    CUSTOMERS,
                )
                cur.executemany(
                    """
                    INSERT INTO customer_addresses
                        (address_id, customer_id, label, serviceable, source_system)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    ADDRESSES,
                )

                logger.info("Inserting SALTO orders and legacy pending-order alias data...")
                cur.executemany(
                    """
                    INSERT INTO salto_orders
                        (salto_order_id, customer_id, order_type, order_status, scope_type, scope_id,
                         address_id, bundle_id, product_family, requested_action, planned_execution_date,
                         installation_pending, oldest_pending_days, exception_markers, exclusion_markers,
                         delivery_reached, device_return_pending, device_return_days, ponr_reached,
                         final_disconnect, source_system)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    SALTO_ORDERS,
                )
                cur.executemany(
                    """
                    INSERT INTO pending_orders
                        (pending_order_id, customer_id, order_type, order_status, scope_type, scope_id,
                         address_id, bundle_id, product_family, planned_execution_date, installation_pending,
                         oldest_pending_days, exception_markers, exclusion_markers, milestone, delivery_reached,
                         device_return_pending, device_return_days, ponr_reached, final_disconnect, source_system)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    _legacy_pending_orders(),
                )
                cur.executemany(
                    """
                    INSERT INTO order_milestones (salto_order_id, milestone, reached, reached_at)
                    VALUES (%s, %s, %s, %s)
                    """,
                    MILESTONES,
                )

                logger.info("Inserting installed base and bundle membership...")
                cur.executemany(
                    """
                    INSERT INTO installed_base_assets
                        (asset_id, customer_id, address_id, bundle_id, scope_type, scope_id, product_family, product_name, service_status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    ASSETS,
                )
                cur.executemany(
                    """
                    INSERT INTO bundle_memberships (bundle_id, customer_id, address_id, asset_id, scope_type, scope_id)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    BUNDLES,
                )

                logger.info("Inserting BCI cases, compatibility matrix, and action catalog...")
                cur.executemany(
                    """
                    INSERT INTO bci_cases
                        (bci_case_id, customer_id, status, priority, intake_channel, ticket_type_raw,
                         creator_role, assigned_queue, data_quality, raw_description, closure_reason)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    BCI_CASES,
                )
                cur.executemany(
                    """
                    INSERT INTO bci_case_events (event_id, bci_case_id, actor_role, event_type, notes)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    BCI_EVENTS,
                )
                cur.executemany(
                    """
                    INSERT INTO compatibility_matrix
                        (segment, pending_order_type, follow_on_action, decision, reason)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    MATRIX,
                )
                cur.executemany(
                    """
                    INSERT INTO action_catalog (action_type, target_system, auto_eligible, description)
                    VALUES (%s, %s, %s, %s)
                    """,
                    ACTIONS,
                )

            conn.commit()
            logger.info("BCI/SALTO database seed completed successfully.")

    except Exception as exc:
        logger.error(f"Seeding failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
