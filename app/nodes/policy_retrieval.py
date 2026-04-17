from app.state.schema import GraphState
from app.tools.audit import write_audit_event
from app.tools.rule_retriever import retrieve_rules

def policy_retrieval(state: GraphState) -> dict:
    """
    Retrieve local business rules based on structured ticket and context fields.
    The result informs validation and audit, but deterministic code still decides.
    """
    rules = retrieve_rules(state)
    matched_rule_ids = rules.get("matched_rule_ids", [])
    audit_entry = write_audit_event(
        "policy_retrieval",
        f"Retrieved rules: {', '.join(matched_rule_ids) or 'none'}",
        state=state,
        payload={"matched_rule_ids": matched_rule_ids},
    )

    return {
        "messages": [f"Policy: Retrieved {len(matched_rule_ids)} local rules: {', '.join(matched_rule_ids) or 'none'}"],
        "audit_log": [audit_entry],
        "retrieved_rules": rules
    }
