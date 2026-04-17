import pytest
from unittest.mock import MagicMock
from langchain_core.runnables import RunnableLambda
from app.graphs.pending_orders import build_pending_orders_graph
from app.nodes.triage import triage
from app.nodes.integration import integration
from app.nodes.recommendation import recommendation
from app.nodes.validation import validation
from app.state.schema import ActionPlan, CustomerContext, PendingOrderContext, Recommendation, ValidationResult
import app.nodes.triage as triage_module


# Scenario group: graph compilation and directive 05 LLM triage hardening.
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
    assert result["llm_trace"]["triage"]["model_role"] == "triage"
    assert result["confidence_summary"]["triage"] == mock_llm_triage_result.confidence_score

def test_triage_empty_ticket_returns_safe_state():
    result = triage({"messages": [], "ticket_raw": "", "retrieved_rules": {}})

    parsed_ticket = result["ticket_structured"]
    assert parsed_ticket.subject == "Empty Ticket"
    assert parsed_ticket.confidence_score == 0.0
    assert "ticket_raw" in parsed_ticket.missing_info
    assert "customer_id" in parsed_ticket.missing_info
    assert result["llm_trace"]["triage"]["success"] is False
    assert result["errors"][0]["code"] == "EMPTY_TICKET"

def test_triage_enforces_missing_customer_id(monkeypatch):
    llm_result = {
        "customer_id": None,
        "address_id": None,
        "request_type": "status_update",
        "pending_order_type": None,
        "scope_type": "fiber",
        "scope_id": None,
        "requested_follow_on_action": None,
        "product_family": "Internet",
        "subject": "Fiber update",
        "missing_info": [],
        "ambiguities": [],
        "confidence_score": 0.9,
    }
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = RunnableLambda(lambda _x: llm_result)
    monkeypatch.setattr(triage_module, "default_llm", mock_llm)

    result = triage({"messages": [], "ticket_raw": "Customer asks for a fiber update.", "retrieved_rules": {}})

    parsed_ticket = result["ticket_structured"]
    assert parsed_ticket.customer_id is None
    assert "customer_id" in parsed_ticket.missing_info
    assert parsed_ticket.confidence_score == 0.75

def test_triage_detects_ambiguous_scope(monkeypatch):
    llm_result = {
        "customer_id": "C-1002",
        "address_id": None,
        "request_type": "modification",
        "pending_order_type": "modification",
        "scope_type": "fiber",
        "scope_id": None,
        "requested_follow_on_action": None,
        "product_family": "Internet",
        "subject": "Fiber and mobile change",
        "missing_info": [],
        "ambiguities": [],
        "confidence_score": 0.95,
    }
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = RunnableLambda(lambda _x: llm_result)
    monkeypatch.setattr(triage_module, "default_llm", mock_llm)

    result = triage({
        "messages": [],
        "ticket_raw": "Customer C-1002 asks for both fiber and mobile subscription changes.",
        "retrieved_rules": {},
    })

    parsed_ticket = result["ticket_structured"]
    assert any("Multiple possible scopes" in item for item in parsed_ticket.ambiguities)
    assert parsed_ticket.confidence_score == 0.65

def test_triage_malformed_llm_output_falls_back(monkeypatch):
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = RunnableLambda(lambda _x: {"customer_id": "C-1001"})
    monkeypatch.setattr(triage_module, "default_llm", mock_llm)

    result = triage({
        "messages": [],
        "ticket_raw": "Customer C-1001 reports an unclear pending order issue.",
        "retrieved_rules": {},
    })

    parsed_ticket = result["ticket_structured"]
    assert parsed_ticket.customer_id == "C-1001"
    assert "extraction_failed" in parsed_ticket.missing_info
    assert parsed_ticket.confidence_score == 0.0
    assert result["llm_trace"]["triage"]["success"] is False
    assert result["errors"][0]["code"] == "LLM_EXTRACTION_FAILED"


# Scenario group: DB integration, local rule retrieval, and deterministic validation.
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
    assert result["customer_context"].name == "Synthetic Fiber Home"
    assert result["customer_context"].tier == "gold"
    assert result["customer_context"].oldest_pending_days == 12
    assert result["pending_order_context"].order_type == "provision"


from app.nodes.policy_retrieval import policy_retrieval
from app.nodes.auto_execute import auto_execute
from app.nodes.human_review import human_review
from app.graphs.pending_orders import route_after_recommendation
from app.tools.execution_guardrails import evaluate_execution_guardrails
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

    assert "core.ambiguous_ticket" in rule_ids
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
    base_state_triage["ticket_structured"].missing_info = ["address_id", "scope_id", "pending_order_type"]
    base_state_triage["ticket_structured"].scope_type = "fiber"
    base_state_triage["ticket_structured"].pending_order_type = None
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

def test_validation_resolves_pending_order_type_from_db_context(base_state_triage):
    base_state_triage["ticket_structured"].customer_id = "C-1002"
    base_state_triage["ticket_structured"].missing_info = ["pending_order_type"]
    base_state_triage["ticket_structured"].scope_type = "fiber"
    base_state_triage["ticket_structured"].pending_order_type = None
    base_state_triage["pending_order_context"] = PendingOrderContext(
        pending_order_id="PO-1002", order_type="modification", order_status="on_hold",
        scope_type="mobile", scope_id="MOB-888", oldest_pending_days=2,
        planned_execution_date="2026-04-20", installation_pending=False,
        exception_markers=[]
    )

    result = validation(base_state_triage)

    assert result["validation_result"].status == "ALLOW"
    assert result["validation_result"].missing_info == []
    assert result["validation_result"].rules_used == ["scope.different_scope_allowed"]

def test_validation_requires_info_for_ambiguous_ticket(base_state_triage):
    base_state_triage["ticket_structured"].customer_id = "C-1002"
    base_state_triage["ticket_structured"].missing_info = ["address_id", "scope_id"]
    base_state_triage["ticket_structured"].scope_type = "mobile"
    base_state_triage["ticket_structured"].ambiguities = [
        "Unclear which pending order the request should apply to",
        "Multiple possible scopes mentioned: fiber, mobile",
    ]
    base_state_triage["pending_order_context"] = PendingOrderContext(
        pending_order_id="PO-1002", order_type="modification", order_status="on_hold",
        scope_type="mobile", scope_id="MOB-888", oldest_pending_days=2,
        planned_execution_date="2026-04-20", installation_pending=False,
        exception_markers=[]
    )

    result = validation(base_state_triage)

    assert result["validation_result"].status == "NEED_INFO"
    assert "AMBIGUOUS_TICKET" in result["validation_result"].reason_codes
    assert result["validation_result"].missing_info == ["clarify_request_scope"]
    assert result["validation_result"].rules_used == ["core.ambiguous_ticket"]

def test_validation_ignores_soft_ambiguity_resolved_by_db_context(base_state_triage):
    base_state_triage["ticket_structured"].customer_id = "C-1001"
    base_state_triage["ticket_structured"].missing_info = ["address_id", "scope_id"]
    base_state_triage["ticket_structured"].scope_type = "fiber"
    base_state_triage["ticket_structured"].ambiguities = [
        "The specific scope_type and product_family are inferred from installation but not explicitly stated."
    ]
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


def test_validation_blocks_bundle_member(base_state_triage):
    base_state_triage["ticket_structured"].missing_info = []
    base_state_triage["ticket_structured"].scope_type = "tv"
    base_state_triage["ticket_structured"].scope_id = "TV-777"
    base_state_triage["bundle_context"] = {
        "bundle_id": "BUN-777",
        "customer_id": "C-1007",
        "address_id": "ADDR-1007-A",
        "member_scope_ids": ["FIB-777", "TV-777"],
        "member_asset_ids": ["AST-777-I", "AST-777-TV"],
    }
    base_state_triage["pending_order_context"] = PendingOrderContext(
        pending_order_id="PO-1007", order_type="bundle", order_status="in_progress",
        scope_type="bundle", scope_id="BUN-777", bundle_id="BUN-777",
        oldest_pending_days=1, planned_execution_date=None
    )

    result = validation(base_state_triage)

    assert result["validation_result"].status == "BLOCK"
    assert result["validation_result"].reason_codes == ["BUNDLE_MEMBER_BLOCKED"]


def test_validation_uses_pmit_mobile_matrix_accept(base_state_triage):
    base_state_triage["customer_context"].segment = "PMIT_MOBILE"
    base_state_triage["ticket_structured"].missing_info = []
    base_state_triage["ticket_structured"].scope_type = "mobile"
    base_state_triage["ticket_structured"].scope_id = "MOB-555"
    base_state_triage["ticket_structured"].requested_action = "add_roaming_option"
    base_state_triage["pending_order_context"] = PendingOrderContext(
        pending_order_id="PO-1008", order_type="provision", order_status="in_progress",
        scope_type="mobile", scope_id="MOB-555", oldest_pending_days=10,
        planned_execution_date=None, exception_markers=["pmit_sync"]
    )
    base_state_triage["compatibility_decision"] = {
        "decision": "ACCEPT",
        "reason": "Matrix allows roaming.",
    }

    result = validation(base_state_triage)

    assert result["validation_result"].status == "ALLOW"
    assert result["validation_result"].reason_codes == ["PMIT_MATRIX_ACCEPT"]


def test_validation_blocks_sim_exception_exclusion(base_state_triage):
    base_state_triage["ticket_structured"].missing_info = []
    base_state_triage["ticket_structured"].scope_type = "mobile"
    base_state_triage["ticket_structured"].request_type = "sim_swap"
    base_state_triage["pending_order_context"] = PendingOrderContext(
        pending_order_id="PO-1010", order_type="provision", order_status="in_progress",
        scope_type="mobile", scope_id="MOB-1010", oldest_pending_days=1,
        planned_execution_date=None, exception_markers=["sim_exception"],
        exclusion_markers=["duo_card"]
    )

    result = validation(base_state_triage)

    assert result["validation_result"].status == "BLOCK"
    assert result["validation_result"].reason_codes == ["SIM_EXCEPTION_EXCLUDED"]


def test_validation_blocks_ponr_final_disconnect(base_state_triage):
    base_state_triage["ticket_structured"].missing_info = []
    base_state_triage["ticket_structured"].scope_type = "fiber"
    base_state_triage["pending_order_context"] = PendingOrderContext(
        pending_order_id="PO-1011", order_type="port_out", order_status="disconnecting",
        scope_type="fiber", scope_id="FIB-1011", oldest_pending_days=1,
        planned_execution_date=None, final_disconnect=True, ponr_reached=False
    )

    result = validation(base_state_triage)

    assert result["validation_result"].status == "BLOCK"
    assert result["validation_result"].reason_codes == ["PONR_BLOCK"]

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

    assert rec.decision == "BLOCKED"
    assert "SAME_SCOPE_PENDING" in rec.reason
    assert result["execution_guardrails"].required_human_review is True


# Scenario group: directive 06 HITL and auto-execution guardrails.
def test_auto_execute_node(base_state_triage):
    """
    Test that the auto execution correctly logs action.
    """
    base_state_triage["validation_result"] = ValidationResult(
        status="ALLOW",
        reason_codes=["NO_CONFLICTS"],
        blocking_conditions=[],
        missing_info=[],
        rules_used=["scope.different_scope_allowed"],
        confidence=1.0
    )
    base_state_triage["recommendation"] = Recommendation(
        decision="ALLOWED", reason="test", applied_rules=["scope.different_scope_allowed"], requires_human=False, confidence=1.0
    )

    result = auto_execute(base_state_triage)

    import json
    assert "execution_result" in result
    res_dict = json.loads(result["execution_result"])
    assert res_dict["action_taken"] == "ALLOWED"
    assert res_dict["status"] == "success"
    assert result["execution_guardrails"].allowed is True

def test_auto_execute_blocks_unsafe_direct_call(base_state_triage):
    base_state_triage["validation_result"] = ValidationResult(
        status="BLOCK",
        reason_codes=["SAME_SCOPE_PENDING"],
        blocking_conditions=["Same scope"],
        missing_info=[],
        rules_used=["core.same_scope_pending"],
        confidence=1.0
    )
    base_state_triage["recommendation"] = Recommendation(
        decision="ALLOWED", reason="stale", applied_rules=[], requires_human=False, confidence=1.0
    )

    result = auto_execute(base_state_triage)

    import json
    res_dict = json.loads(result["execution_result"])
    assert res_dict["status"] == "blocked_by_guardrails"
    assert "VALIDATION_NOT_ALLOW" in res_dict["guardrail_reasons"]
    assert result["execution_guardrails"].required_human_review is True

def test_execution_guardrails_require_allow_validation(base_state_triage):
    base_state_triage["validation_result"] = ValidationResult(
        status="BLOCK",
        reason_codes=["SAME_SCOPE_PENDING"],
        blocking_conditions=["Same scope"],
        missing_info=[],
        rules_used=["core.same_scope_pending"],
        confidence=1.0
    )
    base_state_triage["recommendation"] = Recommendation(
        decision="ALLOWED", reason="stale", applied_rules=[], requires_human=False, confidence=1.0
    )

    guardrails = evaluate_execution_guardrails(base_state_triage)

    assert guardrails.allowed is False
    assert "VALIDATION_NOT_ALLOW" in guardrails.reasons
    assert "VALIDATION_HAS_BLOCKING_CONDITIONS" in guardrails.reasons

def test_execution_guardrails_block_low_confidence(base_state_triage):
    base_state_triage["validation_result"] = ValidationResult(
        status="ALLOW",
        reason_codes=["NO_CONFLICTS"],
        blocking_conditions=[],
        missing_info=[],
        rules_used=["scope.different_scope_allowed"],
        confidence=1.0
    )
    base_state_triage["recommendation"] = Recommendation(
        decision="ALLOWED", reason="weak", applied_rules=[], requires_human=False, confidence=0.5
    )

    guardrails = evaluate_execution_guardrails(base_state_triage)

    assert guardrails.allowed is False
    assert "CONFIDENCE_BELOW_THRESHOLD" in guardrails.reasons

def test_execution_guardrails_block_low_triage_confidence(base_state_triage):
    base_state_triage["confidence_summary"] = {"triage": 0.6, "overall": 0.6}
    base_state_triage["validation_result"] = ValidationResult(
        status="ALLOW",
        reason_codes=["NO_CONFLICTS"],
        blocking_conditions=[],
        missing_info=[],
        rules_used=["scope.different_scope_allowed"],
        confidence=1.0
    )
    base_state_triage["recommendation"] = Recommendation(
        decision="ALLOWED", reason="weak triage", applied_rules=[], requires_human=False, confidence=1.0
    )

    guardrails = evaluate_execution_guardrails(base_state_triage)

    assert guardrails.allowed is False
    assert guardrails.observed_confidence == 0.6
    assert "TRIAGE_CONFIDENCE_BELOW_THRESHOLD" in guardrails.reasons


def test_execution_guardrails_require_dry_run_action_plan(base_state_triage):
    base_state_triage["validation_result"] = ValidationResult(
        status="ALLOW",
        reason_codes=["NO_CONFLICTS"],
        blocking_conditions=[],
        missing_info=[],
        rules_used=["scope.different_scope_allowed"],
        confidence=1.0
    )
    base_state_triage["recommendation"] = Recommendation(
        decision="ALLOWED", reason="test", applied_rules=[], requires_human=False, confidence=1.0
    )
    base_state_triage["action_plan"] = ActionPlan(
        action_type="PREPARE_SECOND_ORDER",
        target_system="SALTO",
        summary="Human-only action",
        auto_eligible=False,
    )

    guardrails = evaluate_execution_guardrails(base_state_triage)

    assert guardrails.allowed is False
    assert "ACTION_PLAN_NOT_AUTO_ELIGIBLE" in guardrails.reasons
    assert "ACTION_PLAN_NOT_DRY_RUN" in guardrails.reasons

def test_routing_logic(base_state_triage):
    """
    Test the conditional routing based on Recommendation parsing.
    """
    # Escalate / hold -> human_review
    base_state_triage["recommendation"] = Recommendation(
        decision="BLOCKED", reason="test", applied_rules=[], requires_human=True, confidence=1.0
    )
    assert route_after_recommendation(base_state_triage) == "human_review"

    # Allow -> auto_execute
    base_state_triage["validation_result"] = ValidationResult(
        status="ALLOW",
        reason_codes=["NO_CONFLICTS"],
        blocking_conditions=[],
        missing_info=[],
        rules_used=["scope.different_scope_allowed"],
        confidence=1.0
    )
    base_state_triage["recommendation"] = Recommendation(
        decision="ALLOWED", reason="test", applied_rules=[], requires_human=False, confidence=1.0
    )
    assert route_after_recommendation(base_state_triage) == "auto_execute"

    # Allow-looking but non-executable -> human_review
    base_state_triage["recommendation"] = Recommendation(
        decision="ALLOWED", reason="test", applied_rules=[], requires_human=True, confidence=1.0
    )
    assert route_after_recommendation(base_state_triage) == "human_review"

def test_human_review_payload_includes_guardrails(base_state_triage):
    base_state_triage["validation_result"] = ValidationResult(
        status="NEED_INFO",
        reason_codes=["MISSING_DATA"],
        blocking_conditions=["Missing customer"],
        missing_info=["customer_id"],
        rules_used=["core.required_fields"],
        confidence=1.0
    )
    base_state_triage["recommendation"] = Recommendation(
        decision="NEEDS_INFO", reason="test", applied_rules=[], requires_human=True, confidence=1.0
    )

    result = human_review(base_state_triage)

    assert result["execution_guardrails"].required_human_review is True
    assert result["human_review_payload"]["validation_status"] == "NEED_INFO"
    assert "DECISION_NOT_ALLOW_FOLLOW_ON" in result["human_review_payload"]["guardrail_reasons"]

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
    assert decision == "BLOCKED"
