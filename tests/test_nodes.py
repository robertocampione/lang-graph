import pytest
from app.graphs.pending_orders import build_pending_orders_graph
from app.nodes.triage import triage
from app.nodes.integration import integration
from app.nodes.recommendation import recommendation
from app.state.schema import CustomerContext, Recommendation

def test_graph_compiles_successfully():
    """
    Simula the instantiation and compiling of the workflow graph to ensure
    all references, states, and checkpointers are properly configured.
    """
    graph = build_pending_orders_graph()
    assert "triage" in graph.nodes
    assert "integration" in graph.nodes
    assert "recommendation" in graph.nodes
    assert graph.name == "LangGraph"

def test_triage_node(base_state_triage, patch_llm_chain_triage, mock_llm_triage_result):
    """
    Test the triage node parsing leveraging the mocked LLM.
    """
    result = triage(base_state_triage)
    
    assert "ticket_structured" in result
    parsed_ticket = result["ticket_structured"]
    
    # Check that our mock logic returned the expected structured output
    assert parsed_ticket.customer_id == mock_llm_triage_result.customer_id
    assert parsed_ticket.subject == mock_llm_triage_result.subject
    assert len(parsed_ticket.missing_info) == 0

def test_integration_node(base_state_triage):
    """
    Test the integration node fetching context based on ticket info.
    We pass a state with customer_id set.
    """
    # Overwrite ticket_structured in base state to have a customer_id
    base_state_triage["ticket_structured"].customer_id = "C-1001"
    
    result = integration(base_state_triage)
    
    assert "customer_context" in result
    # C-1001 exists in mock database
    assert result["customer_context"]["name"] == "Acme Corp"
    assert result["customer_context"]["tier"] == "gold"
    assert result["customer_context"]["oldest_pending_days"] == 12


from app.nodes.policy_retrieval import policy_retrieval
from app.nodes.auto_execute import auto_execute
from app.nodes.human_review import human_review
from app.graphs.pending_orders import route_after_recommendation

def test_policy_retrieval_node(base_state_triage):
    """
    Test that the RAG mock successfully retrieves policy rules based on context.
    """
    # Simulate a Gold customer context
    base_state_triage["customer_context"] = CustomerContext(
        name="Acme Corp", tier="gold", open_orders=3, oldest_pending_days=12, source="mock_crm"
    )
    
    result = policy_retrieval(base_state_triage)
    
    assert "retrieved_rules" in result
    rules = result["retrieved_rules"]
    assert "query_used" in rules
    assert "3 days" in rules["policy_text"]

def test_recommendation_node(base_state_triage, patch_llm_chain_recommendation, mock_llm_recommendation_result):
    """
    Test the recommendation logic by injecting context, mocked rules, and asserting LLM outcome.
    """
    # Set explicit context to simulate previous nodes 
    base_state_triage["ticket_structured"].customer_id = "C-1001"
    base_state_triage["customer_context"] = CustomerContext(
        name="Acme Corp", tier="gold", open_orders=3, oldest_pending_days=12, source="mock_crm"
    )
    from app.tools.policy_retriever import retrieve_policy_for_tier
    base_state_triage["retrieved_rules"] = retrieve_policy_for_tier("gold")
    
    result = recommendation(base_state_triage)
    
    assert "recommendation" in result
    rec = result["recommendation"]
    
    assert rec.action == mock_llm_recommendation_result.action
    assert rec.reason == mock_llm_recommendation_result.reason

def test_auto_execute_node(base_state_triage, mock_llm_recommendation_result):
    """
    Test that the auto execution correctly parses the recommendation action.
    """
    base_state_triage["recommendation"] = mock_llm_recommendation_result
    
    result = auto_execute(base_state_triage)
    
    assert "execution_result" in result
    assert result["execution_result"]["action_taken"] == "ALLOW_FOLLOW_ON"
    assert result["execution_result"]["status"] == "success"

def test_routing_logic(base_state_triage):
    """
    Test the conditional routing based on Recommendation parsing.
    """
    base_state_triage["recommendation"] = Recommendation(action="ESCALATE", reason="Test")
    assert route_after_recommendation(base_state_triage) == "human_review"
    
    base_state_triage["recommendation"] = Recommendation(action="ALLOW_FOLLOW_ON", reason="Test")
    assert route_after_recommendation(base_state_triage) == "auto_execute"

def test_end_to_end_graph(base_state_triage, patch_llm_chain_triage, patch_llm_chain_recommendation):
    """
    Test the full workflow execution from start to finish via Graph.invoke().
    Relies on mocked LLMs to avoid external API calls.
    """
    graph = build_pending_orders_graph()
    
    # LangGraph requires a dict that matches GraphState schema
    initial_state = {
        "messages": [],
        "ticket_raw": "Customer C-1001 is asking for updates regarding delayed items",
        "ticket_structured": {},
        "customer_context": {},
    }
    
    config = {"configurable": {"thread_id": "test_thread_1"}}
    final_state = graph.invoke(initial_state, config=config)
    
    assert final_state is not None
    assert "recommendation" in final_state
    assert "retrieved_rules" in final_state
    
    rec = final_state["recommendation"]
    rec_action = getattr(rec, "action", rec.get("action") if isinstance(rec, dict) else None)
    
    # We mocked Recommendation with ALLOW_FOLLOW_ON. Thus the auto_execute node runs.
    assert rec_action == "ALLOW_FOLLOW_ON"
    assert "execution_result" in final_state
    assert final_state["execution_result"]["action_taken"] == "ALLOW_FOLLOW_ON"
