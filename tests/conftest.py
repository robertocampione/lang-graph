import pytest
from unittest.mock import MagicMock
from langchain_core.runnables import RunnableLambda
from app.state.schema import TicketStructured, CustomerContext, Recommendation
import app.nodes.triage as triage_module
import app.nodes.recommendation as rec_module

@pytest.fixture
def mock_ticket_raw():
    return "Customer C-1001 is reporting a delay in order shipment."

@pytest.fixture
def base_state_triage():
    return {
        "messages": [],
        "ticket_raw": "Customer C-1001 is reporting a delay in order shipment.",
        "ticket_structured": TicketStructured(),
        "customer_context": CustomerContext(),
    }

@pytest.fixture
def mock_llm_triage_result():
    return TicketStructured(
        customer_id="C-1001",
        subject="Delayed order shipment",
        missing_info=[]
    )

@pytest.fixture
def mock_llm_recommendation_result():
    return Recommendation(
        action="ALLOW_FOLLOW_ON",
        reason="No blocking issues found, processing authorized."
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

@pytest.fixture
def patch_llm_chain_recommendation(monkeypatch, mock_llm_recommendation_result):
    mock_structured_llm = RunnableLambda(lambda x: mock_llm_recommendation_result)
    
    mock_llm_obj = MagicMock()
    mock_llm_obj.with_structured_output.return_value = mock_structured_llm
    monkeypatch.setattr(rec_module, "default_llm", mock_llm_obj)
    
    return mock_structured_llm

@pytest.fixture(autouse=True)
def mock_vector_store(monkeypatch):
    """
    Mock the actual Google Embeddings / VectorStore initialization to keep tests offline.
    """
    import app.tools.policy_retriever as policy_mod
    from unittest.mock import MagicMock
    from langchain_core.documents import Document
    
    mock_vs = MagicMock()
    mock_vs.similarity_search.return_value = [
        Document(page_content="MOCKED POLICY: If Tier=Gold, threshold is 3 days. Action: ALLOW_FOLLOW_ON.", metadata={"subject": "Mocked"})
    ]
    
    monkeypatch.setattr(policy_mod, "_get_vector_store", lambda: mock_vs)
    return True
