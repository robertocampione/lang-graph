from langchain_core.prompts import ChatPromptTemplate
from app.state.schema import GraphState, TicketStructured
from app.config.llm import default_llm
from app.tools.audit import write_audit_event
import logging

logger = logging.getLogger(__name__)

def triage(state: GraphState) -> dict:
    """
    Parse the raw ticket and produce a structured representation using LLM.
    Extracts all fields required by TicketStructured Pydantic model.
    """
    raw = state.get("ticket_raw", "").strip()

    if not raw:
        return {
            "messages": ["[triage] No raw ticket provided."],
            "ticket_structured": TicketStructured(
                customer_id=None,
                address_id=None,
                request_type=None,
                pending_order_type=None,
                scope_type=None,
                scope_id=None,
                requested_follow_on_action=None,
                product_family=None,
                subject="Empty Ticket",
                missing_info=["ticket_raw", "customer_id"],
                ambiguities=[],
                confidence_score=0.0
            ),
        }

    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "You are an expert telecom triage assistant. Extract structured info from the customer ticket.\n"
         "Extract customer_id (e.g. C-1001), address_id, scope_type (e.g. fiber, mobile), "
         "scope_id, request_type, pending_order_type.\n"
         "If the customer ID is missing, YOU MUST add 'customer_id' to missing_info list.\n"
         "Assign a confidence_score between 0.0 and 1.0 representing your extraction certainty.\n"
         "List any ambiguities found."
        ),
        ("human", "Ticket details:\n{ticket}")
    ])

    structured_llm = default_llm.with_structured_output(TicketStructured)
    chain = prompt | structured_llm

    try:
        result: TicketStructured = chain.invoke({"ticket": raw})
    except Exception as e:
        logger.error(f"LLM extraction failed: {e}")
        # Fallback to safe mode
        result = TicketStructured(
            customer_id=None,
            subject="Extraction failed",
            missing_info=["customer_id", "extraction_failed"],
            ambiguities=["Unparseable ticket"],
            confidence_score=0.0,
            address_id=None,
            request_type=None,
            pending_order_type=None,
            scope_type=None,
            scope_id=None,
            requested_follow_on_action=None,
            product_family=None
        )

    # Validate logical constraints explicitly
    if not result.customer_id and "customer_id" not in result.missing_info:
        result.missing_info.append("customer_id")

    write_audit_event("triage", f"Parsed ticket. customer_id={result.customer_id} conf={result.confidence_score}", actor_type="LLM")

    return {
        "messages": [f"[triage] Ticket parsed by LLM. customer_id={result.customer_id} conf={result.confidence_score}"],
        "ticket_structured": result,
    }
