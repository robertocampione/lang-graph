from langchain_core.prompts import ChatPromptTemplate
from app.state.schema import GraphState, TicketStructured
from app.config.llm import default_llm
from app.config.settings import settings
from app.tools.audit import write_audit_event
from pydantic import ValidationError
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


SCOPE_KEYWORDS = {
    "fiber": {"fiber", "fibre", "internet", "broadband", "line"},
    "mobile": {"mobile", "sim", "subscription", "porting", "data"},
    "tv": {"tv", "television", "decoder"},
    "billing": {"billing", "invoice", "payment"},
}

CUSTOMER_ID_PATTERN = re.compile(r"\bC-\d{4,}\b", re.IGNORECASE)
BCI_CASE_PATTERN = re.compile(r"\bBCI-\d{4,}\b", re.IGNORECASE)
SALTO_ORDER_PATTERN = re.compile(r"\bPO-\d{4,}\b", re.IGNORECASE)


def _safe_ticket(
    *,
    subject: str,
    missing_info: list[str],
    ambiguities: list[str],
    confidence_score: float,
    customer_id: str | None = None,
    bci_case_id: str | None = None,
    intake_channel: str | None = None,
    ticket_type_raw: str | None = None,
    creator_role: str | None = None,
    customer_identifier: str | None = None,
    address_identifier: str | None = None,
    salto_order_reference: str | None = None,
    requested_action: str | None = None,
    evidence_text: str | None = None,
    address_id: str | None = None,
    request_type: str | None = None,
    pending_order_type: str | None = None,
    scope_type: str | None = None,
    scope_id: str | None = None,
    requested_follow_on_action: str | None = None,
    product_family: str | None = None,
) -> TicketStructured:
    return TicketStructured(
        bci_case_id=bci_case_id,
        intake_channel=intake_channel,
        ticket_type_raw=ticket_type_raw,
        creator_role=creator_role,
        customer_identifier=customer_identifier,
        address_identifier=address_identifier,
        salto_order_reference=salto_order_reference,
        requested_action=requested_action,
        evidence_text=evidence_text,
        customer_id=customer_id,
        address_id=address_id,
        request_type=request_type,
        pending_order_type=pending_order_type,
        scope_type=scope_type,
        scope_id=scope_id,
        requested_follow_on_action=requested_follow_on_action,
        product_family=product_family,
        subject=subject,
        missing_info=missing_info,
        ambiguities=ambiguities,
        confidence_score=confidence_score,
    )


def _coerce_ticket(raw_result: Any) -> tuple[TicketStructured | None, list[str]]:
    issues: list[str] = []
    if isinstance(raw_result, TicketStructured):
        return raw_result, issues

    if isinstance(raw_result, dict):
        try:
            return TicketStructured(**raw_result), issues
        except ValidationError as exc:
            issues.append(f"structured_output_validation_failed: {exc.errors()[0].get('msg', 'invalid shape')}")
            return None, issues

    issues.append(f"unexpected_llm_output_type: {type(raw_result).__name__}")
    return None, issues


def _normalized_list(values: list[str] | None) -> list[str]:
    normalized = []
    for value in values or []:
        text = str(value).strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _detected_scopes(raw: str) -> list[str]:
    lowered = raw.lower()
    detected = []
    for scope, keywords in SCOPE_KEYWORDS.items():
        if any(re.search(rf"\b{re.escape(keyword)}\b", lowered) for keyword in keywords):
            detected.append(scope)
    return detected


def _fallback_customer_id(raw: str) -> str | None:
    match = CUSTOMER_ID_PATTERN.search(raw)
    return match.group(0).upper() if match else None


def _fallback_bci_case_id(raw: str) -> str | None:
    match = BCI_CASE_PATTERN.search(raw)
    return match.group(0).upper() if match else None


def _fallback_salto_order_reference(raw: str) -> str | None:
    match = SALTO_ORDER_PATTERN.search(raw)
    return match.group(0).upper() if match else None


def _post_process_ticket(ticket: TicketStructured, raw: str, issues: list[str]) -> TicketStructured:
    missing_info = _normalized_list(ticket.missing_info)
    ambiguities = _normalized_list(ticket.ambiguities)

    if not ticket.customer_id:
        fallback_id = _fallback_customer_id(raw)
        if fallback_id:
            ticket.customer_id = fallback_id
            ticket.customer_identifier = ticket.customer_identifier or fallback_id
            issues.append("customer_id_recovered_by_regex")

    if not ticket.bci_case_id:
        fallback_case_id = _fallback_bci_case_id(raw)
        if fallback_case_id:
            ticket.bci_case_id = fallback_case_id
            issues.append("bci_case_id_recovered_by_regex")

    if not ticket.salto_order_reference:
        fallback_order_ref = _fallback_salto_order_reference(raw)
        if fallback_order_ref:
            ticket.salto_order_reference = fallback_order_ref
            issues.append("salto_order_reference_recovered_by_regex")

    if ticket.customer_id:
        missing_info = [field for field in missing_info if field != "customer_id"]

    if not ticket.customer_id and "customer_id" not in missing_info:
        missing_info.append("customer_id")

    if not ticket.subject.strip():
        ticket.subject = "Unspecified pending order request"
        issues.append("subject_missing")

    detected_scopes = _detected_scopes(raw)
    if len(detected_scopes) > 1:
        ambiguity = f"Multiple possible scopes mentioned: {', '.join(detected_scopes)}"
        if ambiguity not in ambiguities:
            ambiguities.append(ambiguity)

    if ticket.scope_type and detected_scopes and ticket.scope_type.lower() not in detected_scopes:
        ambiguities.append(f"Extracted scope '{ticket.scope_type}' not clearly supported by ticket text.")

    confidence = max(0.0, min(float(ticket.confidence_score or 0.0), 1.0))
    if missing_info:
        confidence = min(confidence, 0.75)
    if ambiguities:
        confidence = min(confidence, 0.65)
    if issues:
        confidence = min(confidence, 0.55)

    ticket.missing_info = missing_info
    ticket.ambiguities = ambiguities
    ticket.confidence_score = confidence
    return ticket


def _trace_payload(*, success: bool, ticket: TicketStructured, issues: list[str]) -> dict[str, Any]:
    return {
        "triage": {
            "model_role": "triage",
            "model_name": settings.TRIAGE_MODEL,
            "success": success,
            "confidence": ticket.confidence_score,
            "issues": issues,
        }
    }


def _observability_update(*, success: bool, ticket: TicketStructured, issues: list[str], errors: list[dict[str, Any]]) -> dict[str, Any]:
    update: dict[str, Any] = {
        "confidence_summary": {"triage": ticket.confidence_score, "overall": ticket.confidence_score},
        "errors": errors,
    }
    if settings.ENABLE_LLM_TRACE:
        update["llm_trace"] = _trace_payload(success=success, ticket=ticket, issues=issues)
    return update


def triage(state: GraphState) -> dict:
    """
    Parse the raw ticket and produce a structured representation using LLM.
    Extracts all fields required by TicketStructured Pydantic model.
    """
    raw = state.get("ticket_raw", "").strip()

    if not raw:
        ticket = _safe_ticket(
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
            confidence_score=0.0,
        )
        audit_entry = write_audit_event(
            "triage",
            "No raw ticket provided.",
            state={**state, "ticket_structured": ticket},
            payload={"confidence": 0.0, "issues": ["empty_ticket"]},
        )
        return {
            "messages": ["Triage: No raw ticket provided."],
            "audit_log": [audit_entry],
            "ticket_structured": ticket,
            **_observability_update(
                success=False,
                ticket=ticket,
                issues=["empty_ticket"],
                errors=[{"node": "triage", "code": "EMPTY_TICKET", "message": "No raw ticket provided."}],
            ),
        }

    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "You are a telecom pending-order triage extractor. Your only job is structured extraction.\n"
         "Do not make business decisions, do not approve actions, and do not invent identifiers.\n"
         "Extract BCI intake fields when present: bci_case_id, intake_channel, ticket_type_raw, creator_role, customer_identifier, address_identifier, salto_order_reference, requested_action, evidence_text.\n"
         "Expected customer_id format: C-1001. Expected scope_type examples: fiber, mobile, tv, billing.\n"
         "Expected bci_case_id format: BCI-9001. Expected SALTO order reference format: PO-1001.\n"
         "Expected request_type examples: status_update, modification, cancellation, device_return, sim_swap.\n"
         "Expected requested_action examples: introduce_second_order, add_roaming_option, sim_swap, device_return, modify_mobile_subscription, remove_tv_option.\n"
         "Expected pending_order_type examples: provision, move, modification, cancellation.\n"
         "Use null for unknown optional fields. If a required identifier is absent, add its field name to missing_info.\n"
         "Always add customer_id to missing_info when no customer ID is present.\n"
         "Use ambiguities for contradictory scopes, unclear requested actions, or weak evidence.\n"
         "Set confidence_score from 0.0 to 1.0. Lower it when fields are missing or ambiguous.\n"
         "Return only the structured object requested by the schema."
        ),
        ("human", "Ticket details:\n{ticket}")
    ])

    structured_llm = default_llm.with_structured_output(TicketStructured)
    chain = prompt | structured_llm

    issues: list[str] = []
    success = True
    try:
        raw_result = chain.invoke({"ticket": raw})
        result, coerce_issues = _coerce_ticket(raw_result)
        issues.extend(coerce_issues)
        if result is None:
            success = False
            result = _safe_ticket(
                customer_id=_fallback_customer_id(raw),
                bci_case_id=_fallback_bci_case_id(raw),
                salto_order_reference=_fallback_salto_order_reference(raw),
                subject="Extraction failed",
                missing_info=["customer_id", "extraction_failed"],
                ambiguities=["Malformed structured extraction"],
                confidence_score=0.0,
            )
    except Exception as e:
        logger.error(f"LLM extraction failed: {e}")
        success = False
        issues.append(type(e).__name__)
        result = _safe_ticket(
            customer_id=_fallback_customer_id(raw),
            bci_case_id=_fallback_bci_case_id(raw),
            salto_order_reference=_fallback_salto_order_reference(raw),
            subject="Extraction failed",
            missing_info=["customer_id", "extraction_failed"],
            ambiguities=["LLM extraction failed"],
            confidence_score=0.0,
        )

    result = _post_process_ticket(result, raw, issues)
    errors = []
    if not success:
        errors.append({"node": "triage", "code": "LLM_EXTRACTION_FAILED", "message": "; ".join(issues)})

    audit_state = {**state, "ticket_structured": result}
    audit_entry = write_audit_event(
        "triage",
        f"Parsed ticket. role=triage model={settings.TRIAGE_MODEL} customer_id={result.customer_id} conf={result.confidence_score}",
        actor_type="LLM",
        state=audit_state,
        payload={"confidence": result.confidence_score, "issues": issues},
    )
    case_id = state.get("case_id") or result.bci_case_id or result.customer_id
    correlation_id = state.get("correlation_id") or case_id

    return {
        "messages": [f"Triage: Extracted customer_id={result.customer_id}, confidence={result.confidence_score}"],
        "case_id": case_id,
        "correlation_id": correlation_id,
        "audit_log": [audit_entry],
        "ticket_structured": result,
        **_observability_update(success=success, ticket=result, issues=issues, errors=errors),
    }
