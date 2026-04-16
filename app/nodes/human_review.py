from app.state.schema import GraphState

def human_review(state: GraphState) -> dict:
    """
    Node that represents human review. It executes only AFTER the interrupt has been resumed.
    The user can inject a new decision or simply approve the ESCALATE/HOLD_CASE.
    """
    return {
        "messages": ["[human_review] Case reviewed by a human agent."]
    }
