import operator
from typing import TypedDict, Annotated, List, Dict, Any, Optional, NotRequired
from pydantic import BaseModel, Field

# --- Core Business Models ---

class TicketStructured(BaseModel):
    """Normalized structured data extracted from the raw BCI ticket text."""
    bci_case_id: Optional[str] = Field(default=None, description="BCI case reference, if present in the ticket.")
    intake_channel: Optional[str] = Field(default=None, description="Channel that created the BCI case, such as Sales Portal, Sales Support Tool, helpdesk, or direct BCI.")
    ticket_type_raw: Optional[str] = Field(default=None, description="Raw/manual ticket type selected by the intake actor.")
    creator_role: Optional[str] = Field(default=None, description="Role that created the case, such as store_employee, helpdesk, or first_line.")
    customer_identifier: Optional[str] = Field(default=None, description="Customer identifier exactly as written in the ticket, before normalization.")
    address_identifier: Optional[str] = Field(default=None, description="Address identifier exactly as written in the ticket, before normalization.")
    salto_order_reference: Optional[str] = Field(default=None, description="SALTO order reference mentioned by the ticket.")
    requested_action: Optional[str] = Field(default=None, description="Requested action extracted from the BCI case text.")
    evidence_text: Optional[str] = Field(default=None, description="Short text evidence supporting the extraction.")
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
    segment: str = Field(default="CBU", description="Business segment such as CBU, EBU, PMIT_FIX, or PMIT_MOBILE")
    account_status: str = Field(default="active", description="High-level account state")
    open_orders: int = Field(description="Total active pending orders")
    oldest_pending_days: int = Field(description="Days since oldest pending order was created.")
    source: str = Field(description="System source of customer data")

class PendingOrderContext(BaseModel):
    """Simulated pending order data loaded by DB integration node."""
    pending_order_id: str
    customer_id: Optional[str] = None
    order_type: str
    order_status: str
    scope_type: str
    scope_id: Optional[str]
    address_id: Optional[str] = None
    bundle_id: Optional[str] = None
    product_family: Optional[str] = None
    planned_execution_date: Optional[str]
    installation_pending: bool = False
    oldest_pending_days: int = 0
    exception_markers: List[str] = Field(default_factory=list)
    exclusion_markers: List[str] = Field(default_factory=list)
    milestone: Optional[str] = None
    delivery_reached: bool = False
    device_return_pending: bool = False
    device_return_days: int = 0
    ponr_reached: bool = False
    final_disconnect: bool = False
    source_system: str = "SALTO"

class InstalledBaseContext(BaseModel):
    """Simulated existing active products loaded by DB integration node."""
    asset_id: str
    customer_id: Optional[str] = None
    address_id: Optional[str] = None
    bundle_id: Optional[str] = None
    scope_type: Optional[str] = None
    scope_id: Optional[str] = None
    product_family: str
    product_name: str
    service_status: str


class BciCaseEvent(BaseModel):
    """One event or remark from the BCI case timeline."""
    event_id: str
    bci_case_id: str
    actor_role: str
    event_type: str
    notes: str = ""
    created_at: Optional[str] = None


class IntakeMetadata(BaseModel):
    """Metadata about the first-line intake path that produced a BCI case."""
    intake_channel: str = "unknown"
    ticket_type_raw: Optional[str] = None
    creator_role: str = "unknown"
    assigned_queue: Optional[str] = None
    data_quality: str = "unknown"


class BciCaseContext(BaseModel):
    """Simulated BCI case loaded before SALTO context resolution."""
    bci_case_id: str
    customer_id: Optional[str] = None
    status: str = "NEW"
    priority: str = "normal"
    intake: IntakeMetadata = Field(default_factory=IntakeMetadata)
    raw_description: str = ""
    assigned_queue: Optional[str] = None
    closure_reason: Optional[str] = None
    events: List[BciCaseEvent] = Field(default_factory=list)


class CustomerAddress(BaseModel):
    """Customer address as resolved from SALTO."""
    address_id: str
    customer_id: str
    label: str
    serviceable: bool = True
    source_system: str = "SALTO"


class OrderMilestone(BaseModel):
    """Simplified SALTO order milestone used by deterministic validation."""
    milestone: str
    reached: bool = False
    reached_at: Optional[str] = None


class SaltoOrderContext(BaseModel):
    """Richer SALTO pending-order context used by the business-aligned PoC."""
    salto_order_id: str
    customer_id: str
    order_type: str
    order_status: str
    scope_type: str
    scope_id: Optional[str] = None
    address_id: Optional[str] = None
    bundle_id: Optional[str] = None
    product_family: Optional[str] = None
    requested_action: Optional[str] = None
    planned_execution_date: Optional[str] = None
    installation_pending: bool = False
    oldest_pending_days: int = 0
    exception_markers: List[str] = Field(default_factory=list)
    exclusion_markers: List[str] = Field(default_factory=list)
    milestones: List[OrderMilestone] = Field(default_factory=list)
    delivery_reached: bool = False
    device_return_pending: bool = False
    device_return_days: int = 0
    ponr_reached: bool = False
    final_disconnect: bool = False
    source_system: str = "SALTO"


class InstalledAssetContext(InstalledBaseContext):
    """Business-aligned name for installed base assets."""


class BundleContext(BaseModel):
    """Bundle or pack membership around a pending order or installed asset."""
    bundle_id: str
    customer_id: str
    address_id: Optional[str] = None
    member_scope_ids: List[str] = Field(default_factory=list)
    member_asset_ids: List[str] = Field(default_factory=list)


class ScopeRef(BaseModel):
    """Normalized target scope for a follow-on request."""
    scope_type: str
    scope_id: Optional[str] = None
    address_id: Optional[str] = None
    bundle_id: Optional[str] = None


class RequestedSecondOrder(BaseModel):
    """Structured second-order request after BCI triage."""
    action: Optional[str] = None
    scope: Optional[ScopeRef] = None
    target_product_family: Optional[str] = None
    source_case_id: Optional[str] = None
    source_channel: Optional[str] = None

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
    decision: str = Field(description="ALLOWED | BLOCKED | NEEDS_INFO")
    reason: str = Field(description="Short human-readable explanation")
    applied_rules: List[str] = Field(description="List of applied rule IDs")
    confidence: float = Field(description="Confidence from 0.0 to 1.0")
    requires_human: bool = Field(description="True if human intervention is necessary")


class ActionPlan(BaseModel):
    """Action bridge between Phase 1 recommendation and Phase 2 dry-run execution."""
    action_type: str
    target_system: str = "BCI"
    summary: str
    required_inputs: List[str] = Field(default_factory=list)
    preconditions: List[str] = Field(default_factory=list)
    operator_steps: List[str] = Field(default_factory=list)
    auto_eligible: bool = False
    blocking_reasons: List[str] = Field(default_factory=list)

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
    ticket_language: NotRequired[str]
    output_language: NotRequired[str]
    correlation_id: NotRequired[str]
    case_id: NotRequired[str]
    thread_id: NotRequired[str]

    # Information Extracted
    ticket_structured: TicketStructured

    # Context Loading
    customer_context: CustomerContext
    pending_order_context: Optional[PendingOrderContext]
    installed_base_context: List[InstalledBaseContext]
    bci_case_context: NotRequired[Optional[BciCaseContext]]
    salto_orders: NotRequired[List[SaltoOrderContext]]
    selected_salto_order: NotRequired[Optional[SaltoOrderContext]]
    customer_addresses: NotRequired[List[CustomerAddress]]
    installed_assets: NotRequired[List[InstalledAssetContext]]
    bundle_context: NotRequired[Optional[BundleContext]]
    requested_second_order: NotRequired[Optional[RequestedSecondOrder]]

    # Knowledge Base / Rules
    retrieved_rules: Dict[str, Any]

    # Deterministic Engine output
    validation_result: Optional[ValidationResult]

    # Final Action format
    recommendation: Optional[Recommendation]
    action_plan: NotRequired[Optional[ActionPlan]]

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
