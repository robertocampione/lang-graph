from __future__ import annotations

from typing import Any

from app.tools.rule_loader import RuleDocument, load_rule_documents


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _contains(values: list[str], value: str) -> bool:
    normalized = {_norm(item) for item in values}
    return "all" in normalized or _norm(value) in normalized


def _keyword_score(rule: RuleDocument, query_text: str) -> int:
    if not query_text:
        return 0

    haystack = f"{rule.rule_id} {rule.title} {' '.join(rule.tags)} {rule.body}".lower()
    keywords = {
        token.strip(".,:;!?()[]").lower()
        for token in query_text.split()
        if len(token.strip(".,:;!?()[]")) >= 4
    }
    return min(sum(1 for token in keywords if token in haystack), 5)


def _score_rule(rule: RuleDocument, context: dict[str, Any]) -> int:
    score = 0

    segment = _norm(context.get("segment"))
    scope_type = _norm(context.get("scope_type"))
    request_type = _norm(context.get("request_type"))
    pending_order_type = _norm(context.get("pending_order_type"))

    if segment and _contains(rule.segments, segment):
        score += 3 if segment != "all" else 1
    elif "all" in {_norm(item) for item in rule.segments}:
        score += 1

    if scope_type and _contains(rule.scope_types, scope_type):
        score += 4
    elif "all" in {_norm(item) for item in rule.scope_types}:
        score += 1

    if request_type and _contains(rule.request_types, request_type):
        score += 3
    elif "all" in {_norm(item) for item in rule.request_types}:
        score += 1

    if pending_order_type and _contains(rule.pending_order_types, pending_order_type):
        score += 3
    elif "all" in {_norm(item) for item in rule.pending_order_types}:
        score += 1

    score += _keyword_score(rule, _norm(context.get("query_text")))
    return score


def build_rule_context(state: dict[str, Any]) -> dict[str, Any]:
    ticket = state.get("ticket_structured")
    customer_context = state.get("customer_context")
    pending_order_context = state.get("selected_salto_order") or state.get("pending_order_context")
    requested = state.get("requested_second_order")
    requested_scope = getattr(requested, "scope", None) if requested else None

    return {
        "segment": getattr(customer_context, "segment", None) or getattr(customer_context, "tier", None) or "all",
        "scope_type": (
            getattr(ticket, "scope_type", None)
            or getattr(requested_scope, "scope_type", None)
            or getattr(pending_order_context, "scope_type", None)
        ),
        "request_type": getattr(ticket, "requested_action", None) or getattr(ticket, "request_type", None),
        "pending_order_type": (
            getattr(ticket, "pending_order_type", None)
            or getattr(pending_order_context, "order_type", None)
        ),
        "query_text": " ".join(
            item
            for item in [
                state.get("ticket_raw", ""),
                getattr(ticket, "subject", "") if ticket else "",
                getattr(ticket, "requested_action", "") if ticket else "",
            ]
            if item
        ),
    }


def retrieve_rules(state: dict[str, Any], limit: int = 5) -> dict[str, Any]:
    """
    Retrieve local business rules via deterministic metadata and keyword matching.

    This returns context for validation and audit. It does not make the final
    business decision.
    """
    context = build_rule_context(state)
    scored_rules = [
        (rule, _score_rule(rule, context))
        for rule in load_rule_documents()
    ]
    scored_rules = [
        (rule, score)
        for rule, score in scored_rules
        if score > 0
    ]
    scored_rules.sort(key=lambda item: (-item[1], -item[0].priority, item[0].rule_id))

    matched_rules = [rule.to_dict(score=score) for rule, score in scored_rules[:limit]]
    policy_text = "\n\n".join(
        f"[{rule['rule_id']}] {rule['title']}\n{rule['body']}"
        for rule in matched_rules
    )

    return {
        "source": "local_rule_corpus",
        "query_used": context,
        "matched_rule_ids": [rule["rule_id"] for rule in matched_rules],
        "matched_rules": matched_rules,
        "policy_text": policy_text,
        "action_guidance": "Use retrieved rules as explainable context; deterministic validation code makes the decision.",
    }
