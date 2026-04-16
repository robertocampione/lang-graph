import operator
from typing import TypedDict, Annotated, List, Dict, Any, Optional, NotRequired
from pydantic import BaseModel, Field

# --- Core Business Models ---

class TicketStructured(BaseModel):
    """Normalized structured data extracted from the raw BCI ticket text."""
    customer_id: Optional[str] = Field(description="Unique id of the customer, if found.")
    address_id: Optional[str] = Field(description="Target address ID for the request, if detectable.")
    request_type: Optional[str] = Field(description="The generic category of the request (e.g. status_update, modification, cancellation).")
    pending_order_type: Optional[str] = Field(description="The underlying pending order type if mentioned (e.g. provision, move).")
    scope_type: Optional[str] = Field(description="What business domain is impacted (e.g. fiber, mobile, tv).")
    scope_id: Optional[str] = Field(description="The unique identifier of the resource if present.")
    requested_follow_on_action: Optional[str] = Field(description="Action requested by the customer (e.g. expedite, cancel_follow_on).")
    product_family: Optional[str] = Field(description="Family of product like Internet, Mobile.")
    subject: str = Field(description="A short 3-5 word summary of the user's issue.")
    missing_info: List[str] = Field(description="List of fields essential to identify the order but missing from text.")
    ambiguities: List[str] = Field(description="Any confusing or contradictory information found in the text.")
    confidence_score: float = Field(description="Confidence from 0.0 to 1.0 of extraction accuracy.")

class CustomerContext(BaseModel):
    """Simulated CRM data loaded by DB integration node."""
    name: str = Field(description="Customer full name or company name")
    tier: str = Field(description="Customer SLA tier like standard, gold, platinum")
    open_orders: int = Field(description="Total active pending orders")
    oldest_pending_days: int = Field(description="Days since oldest pending order was created.")
    source: str = Field(description="System source of customer data")

class PendingOrderContext(BaseModel):
    """Simulated pending order data loaded by DB integration node."""
    pending_order_id: str
    order_type: str
    order_status: str
    scope_type: str
    scope_id: Optional[str]
    planned_execution_date: Optional[str]
    installation_pending: bool = False
    oldest_pending_days: int = 0
    exception_markers: List[str] = Field(default_factory=list)

class InstalledBaseContext(BaseModel):
    """Simulated existing active products loaded by DB integration node."""
    asset_id: str
    product_family: str
    product_name: str
    service_status: str

# --- Orchestrator Control Models ---

class ValidationResult(BaseModel):
    """Deterministic validation output generated entirely via python business logic."""
    status: str = Field(description="Must be ALLOW, BLOCK, NEED_INFO, or ESCALATE")
    reason_codes: List[str] = Field(description="Short technical code for the decision (e.g. SAME_SCOPE_PENDING)")
    blocking_conditions: List[str] = Field(description="Human readable explanation of why it was blocked or escalated")
    missing_info: List[str] = Field(description="Required fields missing to proceed")
    rules_used: List[str] = Field(description="References to rule IDs deterministically applied by validation")
    confidence: float = Field(description="1.0 when deterministic rule checks produced the decision")

class Recommendation(BaseModel):
    """The final actionable resolution, formatted for the human operator."""
    decision: str = Field(description="The exact executable action to take (e.g. FLAG_FOR_MANUAL_REVIEW, REQUEST_ID, etc.)")
    rationale: str = Field(description="Clear multi-line explanation translated from the validation node code.")
    suggested_human_action: str = Field(description="Advice for the frontoffice human reviewer (e.g. 'Call the customer and ask for an invoice').")
    missing_fields: List[str] = Field(description="Same as validation missing_info")
    executable_action_possible: bool = Field(description="True if auto-execute tool can handle it.")
    confidence: float = Field(description="Confidence translation")

class ExecutionGuardrailResult(BaseModel):
    """Deterministic guardrail outcome before automated execution."""
    allowed: bool = Field(description="True only if automatic execution is permitted")
    reasons: List[str] = Field(description="Technical reasons that allowed or blocked execution")
    required_human_review: bool = Field(description="True when the graph should route to HITL")
    min_confidence: float = Field(description="Configured minimum confidence for auto-execution")
    observed_confidence: float = Field(description="Recommendation or validation confidence observed")

# --- LangGraph Root State ---

class GraphState(TypedDict):
    """
    Main state Dictionary for the orchestrator.
    Keys map to the business lifecycle.
    """
    messages: Annotated[list, operator.add]
    ticket_raw: str
    correlation_id: NotRequired[str]
    case_id: NotRequired[str]
    thread_id: NotRequired[str]

    # Information Extracted
    ticket_structured: TicketStructured

    # Context Loading
    customer_context: CustomerContext
    pending_order_context: Optional[PendingOrderContext]
    installed_base_context: List[InstalledBaseContext]

    # Knowledge Base / Rules
    retrieved_rules: Dict[str, Any]

    # Deterministic Engine output
    validation_result: Optional[ValidationResult]

    # Final Action format
    recommendation: Optional[Recommendation]

    # Human Override / Final Execution
    human_review: str
    execution_result: str
    execution_guardrails: NotRequired[ExecutionGuardrailResult]
    human_review_payload: NotRequired[Dict[str, Any]]

    # Optional observability fields
    audit_log: Annotated[list, operator.add]
    memory_context: NotRequired[Dict[str, Any]]
    llm_trace: NotRequired[Dict[str, Any]]
    confidence_summary: NotRequired[Dict[str, Any]]
    errors: NotRequired[List[Dict[str, Any]]]
