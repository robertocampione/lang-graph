from app.state.schema import GraphState

def auto_execute(state: GraphState) -> dict:
    """
    Simulates executing an automated action (e.g., sending an email or updating DB).
    Fired conditionally when Recommendation != 'HOLD_CASE' (and != 'ESCALATE').
    """
    rec_obj = state.get("recommendation")
    # Handling dictionary and Pydantic objects safely
    action = getattr(rec_obj, "action", rec_obj.get("action") if isinstance(rec_obj, dict) else "UNKNOWN")
    
    execution_detail = f"Executed Action: {action}. Systems synced successfully."
    
    return {
        "messages": [f"[auto_execute] {execution_detail}"],
        "execution_result": {
            "status": "success",
            "action_taken": action,
            "detail": execution_detail
        }
    }
