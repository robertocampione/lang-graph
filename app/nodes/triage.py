from langchain_core.prompts import ChatPromptTemplate
from app.state.schema import GraphState, TicketStructured
from app.config.llm import default_llm

def triage(state: GraphState) -> dict:
    """
    Parse the raw ticket and produce a structured representation using LLM.
    Extracts customer_id and identifies the main subject of the request.
    Flags missing information using the TicketStructured Pydantic model.
    """
    raw = state.get("ticket_raw", "").strip()

    if not raw:
        return {
            "messages": ["[triage] No raw ticket provided."],
            "ticket_structured": TicketStructured(
                customer_id=None,
                subject="",
                missing_info=["ticket_raw"]
            ),
        }

    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an intelligent triage assistant. Your job is to extract structured information from customer tickets. "
                   "Specifically extract the customer ID (usually in the format C-XXXX) and a short summary subject. "
                   "If the customer ID is missing, be sure to list 'customer_id' in missing_info."),
        ("human", "Ticket details:\n{ticket}")
    ])

    structured_llm = default_llm.with_structured_output(TicketStructured)
    chain = prompt | structured_llm

    result: TicketStructured = chain.invoke({"ticket": raw})

    # Validate logical constraints explicitly
    if not result.customer_id and "customer_id" not in result.missing_info:
        result.missing_info.append("customer_id")

    return {
        "messages": [f"[triage] Ticket parsed by LLM. customer_id={result.customer_id}"],
        "ticket_structured": result,
    }
