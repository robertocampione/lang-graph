from langgraph.graph import StateGraph, END

from app.state.schema import GraphState
from app.nodes.triage import triage
from app.nodes.integration import integration
from app.nodes.policy_retrieval import policy_retrieval
from app.nodes.validation import validation
from app.nodes.recommendation import recommendation
from app.nodes.auto_execute import auto_execute
from app.nodes.human_review import human_review

def route_after_recommendation(state: GraphState) -> str:
    """
    Conditional routing logic based on the deterministic recommendation.
    Returns the name of the next node to execute.
    """
    rec_obj = state.get("recommendation")
    if not rec_obj:
        return "human_review"
        
    decision = getattr(rec_obj, "decision", rec_obj.get("decision") if isinstance(rec_obj, dict) else "UNKNOWN")
    
    # Do NOT auto-execute on REQUEST_INFO, BLOCK or ESCALATE
    if decision == "ALLOW_FOLLOW_ON":
        return "auto_execute"
    else:
        return "human_review"

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
    builder.add_node("triage", triage)
    builder.add_node("integration", integration)
    builder.add_node("policy_retrieval", policy_retrieval)
    builder.add_node("validation", validation)
    builder.add_node("recommendation", recommendation)
    builder.add_node("auto_execute", auto_execute)
    builder.add_node("human_review", human_review)

    # Define standard edges
    builder.set_entry_point("triage")
    builder.add_edge("triage", "integration")
    builder.add_edge("integration", "policy_retrieval")
    builder.add_edge("policy_retrieval", "validation")
    builder.add_edge("validation", "recommendation")
    
    # Conditional Edges for action execution or human escalation
    builder.add_conditional_edges("recommendation", route_after_recommendation)
    
    # Finishing edges
    builder.add_edge("auto_execute", END)
    builder.add_edge("human_review", END)

    # Compile with HITL interrupt
    return builder.compile(interrupt_before=["human_review"])
