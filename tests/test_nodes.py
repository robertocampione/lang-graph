import pytest
from app.graphs.pending_orders import build_pending_orders_graph
from app.nodes.triage import triage
from app.nodes.integration import integration
from app.nodes.recommendation import recommendation
from app.nodes.validation import validation
from app.state.schema import CustomerContext, PendingOrderContext, Recommendation, ValidationResult

def test_graph_compiles_successfully():
    """
    Simula the instantiation and compiling of the workflow graph to ensure
    all references, states, and checkpointers are properly configured.
    """
    graph = build_pending_orders_graph()
    assert "triage" in graph.nodes
    assert "integration" in graph.nodes
    assert "validation" in graph.nodes
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
    assert "pending_order_context" in result
    assert "installed_base_context" in result

    # C-1001 exists in mock database
    assert result["customer_context"].name == "Acme Corp"
    assert result["customer_context"].tier == "gold"
    assert result["customer_context"].oldest_pending_days == 12
    assert result["pending_order_context"].order_type == "provision"


from app.nodes.policy_retrieval import policy_retrieval
from app.nodes.auto_execute import auto_execute
from app.nodes.human_review import human_review
from app.graphs.pending_orders import route_after_recommendation
from app.tools.rule_loader import load_rule_documents

def test_policy_retrieval_node(base_state_triage):
    """
    Test that local rule retrieval returns traceable rule metadata.
    """
    base_state_triage["customer_context"] = CustomerContext(
        name="Acme Corp", tier="gold", open_orders=3, oldest_pending_days=12, source="mock_crm"
    )
    base_state_triage["ticket_structured"].missing_info = []
    base_state_triage["ticket_structured"].scope_type = "fiber"
    base_state_triage["ticket_structured"].request_type = "modification"
    base_state_triage["ticket_structured"].pending_order_type = "provision"

    result = policy_retrieval(base_state_triage)
    assert "retrieved_rules" in result
    rules = result["retrieved_rules"]
    assert "query_used" in rules
    assert rules["source"] == "local_rule_corpus"
    assert "matched_rule_ids" in rules
    assert "core.same_scope_pending" in rules["matched_rule_ids"]

def test_rule_loader_reads_local_corpus():
    rules = load_rule_documents()
    rule_ids = {rule.rule_id for rule in rules}

    assert "core.same_scope_pending" in rule_ids
    assert "core.required_fields" in rule_ids
    assert "installation.one_active_installation" in rule_ids
    assert "exceptions.explicit_non_conflicting_exception" in rule_ids

def test_validation_node(base_state_triage):
    """
    Test the deterministic validation logic.
    """
    # 1. Test missing info
    base_state_triage["ticket_structured"].missing_info = ["customer_id"]
    res1 = validation(base_state_triage)
    assert res1["validation_result"].status == "NEED_INFO"
    assert res1["validation_result"].rules_used == ["core.required_fields"]

    # 2. Test Block due to same scope
    base_state_triage["ticket_structured"].missing_info = []
    base_state_triage["ticket_structured"].scope_type = "fiber"
    base_state_triage["pending_order_context"] = PendingOrderContext(
        pending_order_id="PO-123", order_type="move", order_status="open",
        scope_type="fiber", scope_id="F-9", oldest_pending_days=1, planned_execution_date=None
    )
    res2 = validation(base_state_triage)
    assert res2["validation_result"].status == "BLOCK"
    assert "SAME_SCOPE_PENDING" in res2["validation_result"].reason_codes

    # 3. Test ALLOW
    base_state_triage["ticket_structured"].scope_type = "mobile"
    res3 = validation(base_state_triage)
    assert res3["validation_result"].status == "ALLOW"

def test_validation_blocks_installation_pending(base_state_triage):
    base_state_triage["ticket_structured"].missing_info = []
    base_state_triage["ticket_structured"].scope_type = "fiber"
    base_state_triage["pending_order_context"] = PendingOrderContext(
        pending_order_id="PO-456", order_type="provision", order_status="in_progress",
        scope_type="tv", scope_id="TV-9", oldest_pending_days=1, planned_execution_date=None,
        installation_pending=True
    )

    result = validation(base_state_triage)

    assert result["validation_result"].status == "BLOCK"
    assert "INSTALLATION_STILL_PENDING" in result["validation_result"].reason_codes
    assert "installation.one_active_installation" in result["validation_result"].rules_used

def test_validation_uses_db_context_to_resolve_llm_missing_fields(base_state_triage):
    base_state_triage["ticket_structured"].customer_id = "C-1001"
    base_state_triage["ticket_structured"].missing_info = ["address_id", "scope_id"]
    base_state_triage["ticket_structured"].scope_type = "fiber"
    base_state_triage["pending_order_context"] = PendingOrderContext(
        pending_order_id="PO-1001", order_type="provision", order_status="in_progress",
        scope_type="fiber", scope_id="FIB-555", oldest_pending_days=12,
        planned_execution_date="2026-05-01", installation_pending=True,
        exception_markers=["delay_reported"]
    )

    result = validation(base_state_triage)

    assert result["validation_result"].status == "BLOCK"
    assert result["validation_result"].missing_info == []
    assert "INSTALLATION_STILL_PENDING" in result["validation_result"].reason_codes
    assert result["validation_result"].rules_used == ["installation.one_active_installation"]

def test_validation_allows_explicit_exception(base_state_triage):
    base_state_triage["ticket_structured"].missing_info = []
    base_state_triage["ticket_structured"].scope_type = "mobile"
    base_state_triage["ticket_structured"].request_type = "sim_swap"
    base_state_triage["pending_order_context"] = PendingOrderContext(
        pending_order_id="PO-789", order_type="provision", order_status="in_progress",
        scope_type="mobile", scope_id="MOB-9", oldest_pending_days=1, planned_execution_date=None,
        installation_pending=False, exception_markers=["sim_exception"]
    )

    result = validation(base_state_triage)

    assert result["validation_result"].status == "ALLOW"
    assert "EXPLICIT_EXCEPTION_ALLOWED" in result["validation_result"].reason_codes
    assert "exceptions.explicit_non_conflicting_exception" in result["validation_result"].rules_used

def test_recommendation_node(base_state_triage):
    """
    Test the recommendation formatting logic from validation result.
    """
    base_state_triage["validation_result"] = ValidationResult(
        status="BLOCK",
        reason_codes=["SAME_SCOPE_PENDING"],
        blocking_conditions=["Same scope."],
        missing_info=[],
        rules_used=[],
        confidence=1.0
    )

    result = recommendation(base_state_triage)

    assert "recommendation" in result
    rec = result["recommendation"]

    assert rec.decision == "HOLD_CASE"
    assert "SAME_SCOPE_PENDING" in rec.rationale

def test_auto_execute_node(base_state_triage):
    """
    Test that the auto execution correctly logs action.
    """
    base_state_triage["recommendation"] = Recommendation(
        decision="ALLOW_FOLLOW_ON", rationale="test", suggested_human_action="test", missing_fields=[], executable_action_possible=True, confidence=1.0
    )

    result = auto_execute(base_state_triage)

    import json
    assert "execution_result" in result
    res_dict = json.loads(result["execution_result"])
    assert res_dict["action_taken"] == "ALLOW_FOLLOW_ON"
    assert res_dict["status"] == "success"

def test_routing_logic(base_state_triage):
    """
    Test the conditional routing based on Recommendation parsing.
    """
    # Escalate / hold -> human_review
    base_state_triage["recommendation"] = Recommendation(
        decision="HOLD_CASE", rationale="test", suggested_human_action="test", missing_fields=[], executable_action_possible=False, confidence=1.0
    )
    assert route_after_recommendation(base_state_triage) == "human_review"

    # Allow -> auto_execute
    base_state_triage["recommendation"] = Recommendation(
        decision="ALLOW_FOLLOW_ON", rationale="test", suggested_human_action="test", missing_fields=[], executable_action_possible=True, confidence=1.0
    )
    assert route_after_recommendation(base_state_triage) == "auto_execute"

def test_end_to_end_graph(base_state_triage, patch_llm_chain_triage):
    """
    Test the full workflow execution from start to finish via Graph.invoke().
    Relies on mocked LLMs for Triage.
    """
    graph = build_pending_orders_graph()

    initial_state = {
        "messages": [],
        "ticket_raw": "Customer C-1001 is asking for updates regarding delayed items",
        "ticket_structured": {},
        "customer_context": {},
        "retrieved_rules": {},
    }

    config = {"configurable": {"thread_id": "test_thread_1"}}
    final_state = graph.invoke(initial_state, config=config)

    assert final_state is not None
    assert "recommendation" in final_state

    rec = final_state["recommendation"]
    decision = getattr(rec, "decision", rec.get("decision") if isinstance(rec, dict) else None)

    # Based on MOCK_PENDING_ORDERS, C-1001 has "installation_pending": True, so it should BLOCK!
    assert decision == "HOLD_CASE"
