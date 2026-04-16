from app.state.schema import GraphState
from app.tools.policy_retriever import retrieve_policy_for_tier

def policy_retrieval(state: GraphState) -> dict:
    """
    RAG node that retrieves policies contextually based on the customer ticket.
    Injects realistic business context into the graph state for the Recommendation node.
    """
    customer_context = state.get("customer_context")
    tier = getattr(customer_context, "tier", "standard") if customer_context else "standard"
    
    ticket_raw = state.get("ticket_raw", "")
    
    # Costruiamo una query semantica ricca per colpire bene lo spazio vettoriale
    semantic_query = f"Tier: {tier}. Problem: {ticket_raw}"
    
    rules = retrieve_policy_for_tier(semantic_query)
    
    return {
        "messages": [f"[policy_retrieval] Queried VectorStore with: '{semantic_query}'"],
        "retrieved_rules": rules
    }
