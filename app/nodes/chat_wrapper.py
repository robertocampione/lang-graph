from app.state.schema import GraphState
from app.tools.audit import write_audit_event

def chat_wrapper(state: GraphState) -> dict:
    """
    Lightweight entry point for the demo interaction layer.
    Maps an optional 'user_text' chat interface field into the definitive 'ticket_raw' input.
    """
    user_text = state.get("user_text")
    if not user_text:
        return {}

    audit_entry = write_audit_event(
        "chat_wrapper",
        "Mapped user chat text to raw ticket.",
        state=state,
        payload={"mapped_from_chat": True}
    )

    return {
        "messages": ["[chat_wrapper] Received user input, translating to ticket_raw."],
        "audit_log": [audit_entry],
        "ticket_raw": user_text
    }
