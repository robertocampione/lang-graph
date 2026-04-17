from app.state.schema import GraphState
from app.tools.audit import write_audit_event
from app.tools.notification import send_notification

def approval_level_1(state: GraphState) -> dict:
    """
    Level 1 Operational Approval Node.
    Mock trigger for back-office agent review.
    """
    status = state.get("approval_status", "approved")
    role = "L1 Agent"
    
    # Simulate notification
    send_notification(
        state.get("case_id", "unknown"),
        "teams",
        role,
        f"Approval required for L1. Current status: {status}"
    )
    
    audit_entry = write_audit_event(
        "approval_level_1",
        f"L1 approval completed. Status: {status}",
        state=state,
        payload={"approval_status": status, "approver_role": role}
    )

    return {
        "approval_status": status,
        "current_approver_role": role,
        "messages": [f"Approval (L1): {status}"],
        "audit_log": [audit_entry]
    }


def approval_level_2(state: GraphState) -> dict:
    """
    Level 2 Supervisor Approval Node.
    Triggered for low-confidence or high-impact cases.
    """
    status = state.get("approval_status", "approved")
    role = "Supervisor"
    
    # Simulate notification
    send_notification(
        state.get("case_id", "unknown"),
        "teams",
        role,
        f"Supervisor approval required. Current status: {status}"
    )
    
    audit_entry = write_audit_event(
        "approval_level_2",
        f"L2 approval completed. Status: {status}",
        state=state,
        payload={"approval_status": status, "approver_role": role}
    )

    return {
        "approval_status": status,
        "current_approver_role": role,
        "messages": [f"Approval (L2): {status}"],
        "audit_log": [audit_entry]
    }
