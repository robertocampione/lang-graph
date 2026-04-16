from app.state.schema import GraphState
from app.tools.rule_retriever import retrieve_rules

def policy_retrieval(state: GraphState) -> dict:
    """
    Retrieve local business rules based on structured ticket and context fields.
    The result informs validation and audit, but deterministic code still decides.
    """
    rules = retrieve_rules(state)
    matched_rule_ids = rules.get("matched_rule_ids", [])
    
    return {
        "messages": [f"[policy_retrieval] Retrieved {len(matched_rule_ids)} local rules: {', '.join(matched_rule_ids) or 'none'}"],
        "retrieved_rules": rules
    }
