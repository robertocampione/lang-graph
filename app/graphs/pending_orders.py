from langgraph.graph import StateGraph, START, END

from app.state.schema import GraphState
from app.nodes.chat_wrapper import chat_wrapper
from app.nodes.triage import triage
from app.nodes.integration import integration
from app.nodes.policy_retrieval import policy_retrieval
from app.nodes.validation import validation
from app.nodes.recommendation import recommendation
from app.nodes.approval import approval_level_1, approval_level_2
from app.nodes.auto_execute import auto_execute
from app.nodes.human_review import human_review
from app.tools.execution_guardrails import evaluate_execution_guardrails

def route_to_approval(state: GraphState) -> str:
    """
    Conditional routing logic based on the deterministic recommendation and guardrails.
    Routes to the approval layer (L1/L2) or human_review.
    """
    rec_obj = state.get("recommendation")
    if not rec_obj:
        return "human_review"

    guardrails = evaluate_execution_guardrails(state)
    if not guardrails.allowed:
        return "human_review"

    # Auto-execution is eligible, but route to the approval layer first
    confidence = state.get("confidence_summary", {}).get("overall", 1.0)
    if confidence < 0.7:
        return "approval_level_2"

    return "approval_level_1"

def route_after_approval(state: GraphState) -> str:
    """
    Conditional routing after human approval interactions.
    """
    if state.get("approval_status") == "rejected":
        return END
    return "auto_execute"

def build_pending_orders_graph():
    """
    Constructs and compiles the pending orders orchestrator graph.
    Flow: triage → integration → policy_retrieval → validation → recommendation → (conditional edge)
    Conditional targets: auto_execute OR human_review.
    Note: LangGraph Studio automatically handles persistence.
    We inject interrupt_before=["human_review"] to trigger Human-in-the-Loop.
    """
    builder = StateGraph(GraphState)

    # Add nodes
    builder.add_node("chat_wrapper", chat_wrapper)
    builder.add_node("triage", triage)
    builder.add_node("integration", integration)
    builder.add_node("policy_retrieval", policy_retrieval)
    builder.add_node("validation", validation)
    builder.add_node("recommendation", recommendation)
    builder.add_node("approval_level_1", approval_level_1)
    builder.add_node("approval_level_2", approval_level_2)
    builder.add_node("auto_execute", auto_execute)
    builder.add_node("human_review", human_review)

    # Define standard edges
    builder.add_edge(START, "chat_wrapper")
    builder.add_edge("chat_wrapper", "triage")
    builder.add_edge("triage", "integration")
    builder.add_edge("integration", "policy_retrieval")
    builder.add_edge("policy_retrieval", "validation")
    builder.add_edge("validation", "recommendation")
    
    # Conditional Edges for action execution or human escalation
    builder.add_conditional_edges("recommendation", route_to_approval)
    builder.add_conditional_edges("approval_level_1", route_after_approval)
    builder.add_conditional_edges("approval_level_2", route_after_approval)
    
    # Finishing edges
    builder.add_edge("auto_execute", END)
    builder.add_edge("human_review", END)

    # Compile with HITL interrupt for approvals and human review
    return builder.compile(interrupt_before=["human_review", "approval_level_1", "approval_level_2"])
