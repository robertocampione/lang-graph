def send_notification(case_id: str, channel: str, recipient_role: str, message: str) -> dict:
    """
    Mock notification tool to simulate pushing approval requests to communication platforms like Teams.
    """
    return {
        "channel": channel,
        "recipient_role": recipient_role,
        "message": message,
        "simulated_delivery_to": f"{channel}://{recipient_role.lower().replace(' ', '_')}"
    }
