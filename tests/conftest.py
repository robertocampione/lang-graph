import pytest
from unittest.mock import MagicMock, patch
from langchain_core.runnables import RunnableLambda
from app.state.schema import TicketStructured, CustomerContext, ValidationResult
import app.nodes.triage as triage_module

@pytest.fixture
def mock_ticket_raw():
    return "Customer C-1001 is reporting a delay in order shipment."

@pytest.fixture
def base_state_triage():
    return {
        "messages": [],
        "ticket_raw": "Customer C-1001 is reporting a delay in order shipment.",
        "ticket_structured": TicketStructured(
            customer_id=None,
            address_id=None,
            request_type=None,
            pending_order_type=None,
            scope_type=None,
            scope_id=None,
            requested_follow_on_action=None,
            product_family=None,
            subject="delayed shipment",
            missing_info=["customer_id"],
            ambiguities=[],
            confidence_score=0.0
        ),
        "customer_context": CustomerContext(
            name="Unknown", tier="standard", open_orders=0, oldest_pending_days=0, source="unknown"
        ),
        "pending_order_context": None,
        "installed_base_context": [],
        "retrieved_rules": {},
    }

@pytest.fixture
def mock_llm_triage_result():
    return TicketStructured(
        customer_id="C-1001",
        address_id=None,
        request_type="status_update",
        pending_order_type="provision",
        scope_type="fiber",
        scope_id="FIB-555",
        requested_follow_on_action=None,
        product_family="Internet",
        subject="Delayed order shipment",
        missing_info=[],
        ambiguities=[],
        confidence_score=0.9
    )

@pytest.fixture
def patch_llm_chain_triage(monkeypatch, mock_llm_triage_result):
    """
    Mock the returned object from default_llm.with_structured_output.
    """
    mock_structured_llm = RunnableLambda(lambda x: mock_llm_triage_result)
    
    mock_llm_obj = MagicMock()
    mock_llm_obj.with_structured_output.return_value = mock_structured_llm
    
    monkeypatch.setattr(triage_module, "default_llm", mock_llm_obj)
    
    return mock_structured_llm

@pytest.fixture(autouse=True)
def mock_vector_store(monkeypatch):
    """
    Mock the actual Google Embeddings / VectorStore initialization to keep tests offline.
    """
    import app.tools.policy_retriever as policy_mod
    from langchain_core.documents import Document
    
    mock_vs = MagicMock()
    mock_vs.similarity_search.return_value = [
        Document(page_content="MOCKED POLICY: If Tier=Gold, threshold is 3 days. Action: ALLOW_FOLLOW_ON.", metadata={"subject": "Mocked"})
    ]
    
    monkeypatch.setattr(policy_mod, "_get_vector_store", lambda: mock_vs)
    return True

@pytest.fixture(autouse=True)
def mock_db_layer(monkeypatch):
    """
    Mock all PostgreSQL interactions so unit tests run without a live database.
    Mocks: db_services (fetch_*), audit (write_audit_event), connection (execute_query).
    """
    import app.tools.db_services as db_svc_mod
    import app.tools.audit as audit_mod
    import app.db.connection as conn_mod

    # Mock db_services to return data matching the old mock_db behavior
    monkeypatch.setattr(db_svc_mod, "fetch_customer_context", lambda cid: {
        "C-1001": {"name": "Acme Corp", "tier": "gold", "open_orders": 3, "oldest_pending_days": 12, "source": "mock_crm"},
        "C-1002": {"name": "Globex Inc", "tier": "silver", "open_orders": 1, "oldest_pending_days": 2, "source": "mock_crm"},
    }.get(cid, {"name": "Unknown", "tier": "standard", "open_orders": 0, "oldest_pending_days": 0, "source": "default_fallback"}))

    monkeypatch.setattr(db_svc_mod, "fetch_pending_order_context", lambda cid: {
        "C-1001": {
            "pending_order_id": "PO-9991", "order_type": "provision", "order_status": "in_progress",
            "scope_type": "fiber", "scope_id": "FIB-555", "planned_execution_date": "2026-05-01",
            "installation_pending": True, "oldest_pending_days": 12, "exception_markers": ["delay_reported"]
        },
        "C-1002": {
            "pending_order_id": "PO-9992", "order_type": "modification", "order_status": "on_hold",
            "scope_type": "mobile", "scope_id": "MOB-888", "planned_execution_date": "2026-04-20",
            "installation_pending": False, "oldest_pending_days": 2, "exception_markers": []
        },
    }.get(cid, None))

    monkeypatch.setattr(db_svc_mod, "fetch_installed_base_context", lambda cid: {
        "C-1001": [{"asset_id": "AST-111", "product_family": "Internet", "product_name": "Proximus Fiber Boost", "service_status": "active"}],
    }.get(cid, []))

    # Mock audit — just swallow the call
    monkeypatch.setattr(audit_mod, "write_audit_event", lambda *args, **kwargs: None)

    # Mock execute_query — swallow DB writes from auto_execute / human_review
    monkeypatch.setattr(conn_mod, "execute_query", lambda *args, **kwargs: None)
