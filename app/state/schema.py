import operator
from typing import TypedDict, Annotated
from pydantic import BaseModel, Field

class TicketStructured(BaseModel):
    customer_id: str | None = Field(default=None, description="The extracted customer ID, e.g., C-1001")
    subject: str = Field(default="", description="A short summary of the ticket topic")
    missing_info: list[str] = Field(default_factory=list, description="Any identified missing info, e.g. customer_id, order_number")

class CustomerContext(BaseModel):
    name: str = Field(default="Unknown")
    tier: str = Field(default="standard")
    open_orders: int = Field(default=0)
    oldest_pending_days: int = Field(default=0)
    source: str = Field(default="mock_crm")

class Recommendation(BaseModel):
    action: str = Field(description="The recommended action (e.g., REQUEST_INFO, HOLD_CASE, ALLOW_FOLLOW_ON)")
    reason: str = Field(description="The underlying reason and reasoning process for the action")

class GraphState(TypedDict):
    """
    Comprehensive state passed between nodes throughout the pending orders graph execution.
    It holds all context accumulated during triage, integration, rule evaluation, and review.
    """
    # Using Annotated and operator.add for messages to support appending values correctly in graphs
    messages: Annotated[list[str], operator.add]
    ticket_raw: str
    ticket_structured: TicketStructured
    customer_context: CustomerContext
    pending_order_context: dict
    retrieved_rules: dict
    validation_result: dict
    recommendation: Recommendation
    human_review: dict
    execution_result: dict
