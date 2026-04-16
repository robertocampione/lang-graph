from langchain_core.prompts import ChatPromptTemplate
from app.state.schema import GraphState, Recommendation
from app.config.llm import default_llm

def recommendation(state: GraphState) -> dict:
    """
    Produce an action recommendation using LLM reasoning over gathered context.
    """
    structured: dict | getattr = state.get("ticket_structured")
    context: dict | getattr = state.get("customer_context")
    rules: dict = state.get("retrieved_rules", {})
    
    # We might get Pydantic models directly due to TypedDict/Pydantic usage, so handle dict/model gracefully
    ticket_dict = structured.model_dump() if hasattr(structured, 'model_dump') else structured
    context_dict = context.model_dump() if hasattr(context, 'model_dump') else context

    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an expert customer service orchestrator. Analyze the incoming ticket, the customer context, and the Company Shipping Policies.\n"
                   "Company Shipping Policies:\n{policy_data}\n\n"
                   "Decision Logic:\n"
                   "1. If missing_info is not empty, action MUST be 'REQUEST_INFO'.\n"
                   "2. Evaluate open orders and pending days against the Policy. If it violates boundaries, action MUST be 'ESCALE' or 'HOLD_CASE'.\n"
                   "3. Otherwise, action is 'ALLOW_FOLLOW_ON'.\n"
                   "Provide the action and the detailed reasoning for your choice."),
        ("human", "Ticket Data: {ticket_data}\n\nCustomer Context: {context_data}")
    ])

    structured_llm = default_llm.with_structured_output(Recommendation)
    chain = prompt | structured_llm

    result: Recommendation = chain.invoke({
        "ticket_data": ticket_dict,
        "context_data": context_dict,
        "policy_data": rules
    })

    return {
        "messages": [f"[recommendation] {result.action} — {result.reason}"],
        "recommendation": result,
    }
