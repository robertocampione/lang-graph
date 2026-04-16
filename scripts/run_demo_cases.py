import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.graphs.pending_orders import route_after_recommendation
from app.nodes import auto_execute as auto_execute_module
from app.nodes import human_review as human_review_module
from app.nodes import integration as integration_module
from app.nodes import policy_retrieval as policy_retrieval_module
from app.nodes import recommendation as recommendation_module
from app.nodes import validation as validation_module
from app.nodes.auto_execute import auto_execute
from app.nodes.human_review import human_review
from app.nodes.integration import integration
from app.nodes.policy_retrieval import policy_retrieval
from app.nodes.recommendation import recommendation
from app.nodes.validation import validation
from app.state.schema import CustomerContext, InstalledBaseContext, PendingOrderContext, Recommendation, TicketStructured, ValidationResult
from app.tools.execution_guardrails import evaluate_execution_guardrails


@dataclass(frozen=True)
class DemoCase:
    case_id: str
    title: str
    scenario: str
    thread_id: str
    ticket_raw: str
    ticket_structured: TicketStructured
    iterations: list[str] = field(default_factory=list)


def _ticket(
    *,
    customer_id: str | None,
    subject: str,
    request_type: str | None,
    pending_order_type: str | None,
    scope_type: str | None,
    scope_id: str | None = None,
    requested_follow_on_action: str | None = None,
    product_family: str | None = None,
    missing_info: list[str] | None = None,
    ambiguities: list[str] | None = None,
    confidence_score: float = 0.95,
) -> TicketStructured:
    return TicketStructured(
        customer_id=customer_id,
        address_id=None,
        request_type=request_type,
        pending_order_type=pending_order_type,
        scope_type=scope_type,
        scope_id=scope_id,
        requested_follow_on_action=requested_follow_on_action,
        product_family=product_family,
        subject=subject,
        missing_info=missing_info or [],
        ambiguities=ambiguities or [],
        confidence_score=confidence_score,
    )


DEMO_CASES = [
    # Scenario: directive 06 guardrail. A follow-on action must be held because
    # integration shows physical installation is still open.
    DemoCase(
        case_id="installation-delay-block",
        title="Installation still pending blocks follow-on action",
        scenario="Directive 06: HITL guardrail blocks auto-execution when installation_pending is true.",
        thread_id="demo-c-1001",
        ticket_raw="Customer C-1001 reports that the fiber installation is delayed and asks to proceed with a follow-on change.",
        ticket_structured=_ticket(
            customer_id="C-1001",
            subject="Fiber installation delayed",
            request_type="modification",
            pending_order_type="provision",
            scope_type="fiber",
            requested_follow_on_action="follow_on_change",
            product_family="Internet",
            missing_info=["address_id", "scope_id"],
            confidence_score=0.90,
        ),
        iterations=[
            "Follow-up note: customer called again and asks whether backoffice can approve an exception.",
        ],
    ),
    # Scenario: directive 04/06 interaction. Same-scope conflict is a
    # deterministic blocker and must route to human review.
    DemoCase(
        case_id="same-scope-block",
        title="Same mobile scope blocks a second mobile modification",
        scenario="Directive 06: same-scope deterministic block routes to human review.",
        thread_id="demo-c-1002",
        ticket_raw="Customer C-1002 wants a mobile subscription modification while the mobile order is still pending.",
        ticket_structured=_ticket(
            customer_id="C-1002",
            subject="Mobile modification while pending",
            request_type="modification",
            pending_order_type="modification",
            scope_type="mobile",
            scope_id="MOB-888",
            product_family="Mobile",
        ),
    ),
    # Scenario: directive 06 green path. Different-scope request has no blockers
    # and should pass auto-execution guardrails.
    DemoCase(
        case_id="different-scope-allow",
        title="Different scope allows automated follow-on",
        scenario="Directive 06: allowed recommendation passes execution guardrails and routes to auto_execute.",
        thread_id="demo-c-1002",
        ticket_raw="Customer C-1002 asks for a fiber information update while the current pending order is mobile.",
        ticket_structured=_ticket(
            customer_id="C-1002",
            subject="Fiber information update",
            request_type="status_update",
            pending_order_type="modification",
            scope_type="fiber",
            product_family="Internet",
        ),
        iterations=[
            "Follow-up note: operator confirms the request is informational and not tied to the mobile order.",
        ],
    ),
    # Scenario: directive 04/06 blocking behavior for scheduled work.
    # Future-dated pending order must not execute automatically.
    DemoCase(
        case_id="future-dated-block",
        title="Future-dated order blocks automated changes",
        scenario="Directive 06: future-dated pending order is blocked and requires HITL.",
        thread_id="demo-c-1005",
        ticket_raw="Customer C-1005 asks to change the TV cancellation before the planned future execution date.",
        ticket_structured=_ticket(
            customer_id="C-1005",
            subject="Future dated TV change",
            request_type="modification",
            pending_order_type="cancellation",
            scope_type="tv",
            scope_id="TV-999",
            product_family="TV",
        ),
    ),
    # Scenario: directive 05 missing-info path plus directive 06 guardrails.
    # Missing customer id must request info and never auto-execute.
    DemoCase(
        case_id="missing-customer-info",
        title="Missing customer identifier requests more information",
        scenario="Directive 05/06: missing customer_id produces REQUEST_INFO and human review.",
        thread_id="demo-missing-customer",
        ticket_raw="The customer asks for an update on the pending order but did not provide any customer identifier.",
        ticket_structured=_ticket(
            customer_id=None,
            subject="Pending order update",
            request_type="status_update",
            pending_order_type=None,
            scope_type=None,
            missing_info=["customer_id"],
            confidence_score=0.35,
        ),
    ),
]


OFFLINE_CUSTOMERS = {
    "C-1001": CustomerContext(name="Acme Corp", tier="gold", open_orders=3, oldest_pending_days=12, source="offline_fixture"),
    "C-1002": CustomerContext(name="Globex Inc", tier="silver", open_orders=1, oldest_pending_days=2, source="offline_fixture"),
    "C-1005": CustomerContext(name="Cyberdyne Systems", tier="gold", open_orders=2, oldest_pending_days=5, source="offline_fixture"),
}

OFFLINE_ORDERS = {
    "C-1001": PendingOrderContext(
        pending_order_id="PO-1001",
        order_type="provision",
        order_status="in_progress",
        scope_type="fiber",
        scope_id="FIB-555",
        planned_execution_date="2026-05-01",
        installation_pending=True,
        oldest_pending_days=12,
        exception_markers=["delay_reported"],
    ),
    "C-1002": PendingOrderContext(
        pending_order_id="PO-1002",
        order_type="modification",
        order_status="on_hold",
        scope_type="mobile",
        scope_id="MOB-888",
        planned_execution_date="2026-04-20",
        installation_pending=False,
        oldest_pending_days=2,
        exception_markers=[],
    ),
    "C-1005": PendingOrderContext(
        pending_order_id="PO-1005",
        order_type="cancellation",
        order_status="open",
        scope_type="tv",
        scope_id="TV-999",
        planned_execution_date="2027-01-01",
        installation_pending=False,
        oldest_pending_days=5,
        exception_markers=["future_dated"],
    ),
}

OFFLINE_ASSETS = {
    "C-1001": [
        InstalledBaseContext(asset_id="AST-111", product_family="Internet", product_name="Proximus Fiber Boost", service_status="active")
    ],
    "C-1005": [
        InstalledBaseContext(asset_id="AST-444", product_family="TV", product_name="Proximus TV Extra", service_status="active")
    ],
}


def _patch_writes_for_dry_run() -> None:
    def no_audit(*_args: Any, **_kwargs: Any) -> None:
        return None

    def no_execute(*_args: Any, **_kwargs: Any) -> None:
        return None

    integration_module.write_audit_event = no_audit
    policy_retrieval_module.write_audit_event = no_audit
    validation_module.write_audit_event = no_audit
    recommendation_module.write_audit_event = no_audit
    auto_execute_module.write_audit_event = no_audit
    human_review_module.write_audit_event = no_audit
    auto_execute_module.execute_query = no_execute
    human_review_module.execute_query = no_execute


def _offline_integration(state: dict[str, Any]) -> dict[str, Any]:
    ticket = state.get("ticket_structured")
    customer_id = getattr(ticket, "customer_id", None)
    customer = OFFLINE_CUSTOMERS.get(
        customer_id,
        CustomerContext(name="Unknown", tier="standard", open_orders=0, oldest_pending_days=0, source="offline_fallback"),
    )
    order = OFFLINE_ORDERS.get(customer_id)
    assets = OFFLINE_ASSETS.get(customer_id, [])
    order_id = order.pending_order_id if order else "None"
    return {
        "messages": [f"[integration:offline] Context loaded. Customer: {customer.name} ({customer_id or 'n/a'}). Pending Orders: {order_id}. Installed Base size: {len(assets)}."],
        "customer_context": customer,
        "pending_order_context": order,
        "installed_base_context": assets,
        "memory_context": {
            "case_id": state.get("case_id") or customer_id,
            "correlation_id": state.get("correlation_id") or state.get("case_id") or customer_id,
            "prior_cases": [],
            "prior_human_reviews": [],
            "prior_executions": [],
            "missing_info_patterns": [],
            "principle": "offline_demo_memory_is_non_authoritative",
        },
    }


def _merge(state: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    messages = list(state.get("messages", []))
    messages.extend(update.get("messages", []))
    merged = {**state, **update}
    merged["messages"] = messages
    return merged


def _model_dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, list):
        return [_model_dump(item) for item in value]
    if isinstance(value, dict):
        return {key: _model_dump(item) for key, item in value.items()}
    return value


def _run_pipeline(case: DemoCase, *, source: str, persist_actions: bool, prior_messages: list[str]) -> dict[str, Any]:
    state: dict[str, Any] = {
        "messages": list(prior_messages),
        "case_id": case.case_id,
        "correlation_id": case.case_id,
        "thread_id": case.thread_id,
        "ticket_raw": case.ticket_raw,
        "ticket_structured": case.ticket_structured,
        "retrieved_rules": {},
        "confidence_summary": {
            "triage": case.ticket_structured.confidence_score,
            "overall": case.ticket_structured.confidence_score,
        },
    }

    if source == "offline":
        state = _merge(state, _offline_integration(state))
    else:
        state = _merge(state, integration(state))

    state = _merge(state, policy_retrieval(state))
    state = _merge(state, validation(state))
    state = _merge(state, recommendation(state))

    state["execution_guardrails"] = evaluate_execution_guardrails(state)
    route = route_after_recommendation(state)
    state["route"] = route

    if route == "auto_execute":
        if persist_actions:
            state = _merge(state, auto_execute(state))
        else:
            state["execution_result"] = json.dumps({
                "status": "dry_run",
                "action_taken": state["recommendation"].decision,
                "detail": "Auto-execution was skipped because --persist-actions was not set.",
            })
    else:
        if persist_actions:
            state = _merge(state, human_review(state))
        else:
            state["human_review"] = f"Dry-run review required: {state['recommendation'].decision}"

    return state


def _print_case_result(case: DemoCase, state: dict[str, Any], *, iteration: int, prior_message_count: int) -> None:
    validation_result: ValidationResult = state["validation_result"]
    rec: Recommendation = state["recommendation"]
    retrieved = state.get("retrieved_rules", {})
    pending_order = state.get("pending_order_context")
    guardrails = state.get("execution_guardrails")

    print("=" * 92)
    print(f"Case: {case.case_id} | Iteration: {iteration} | Thread: {case.thread_id}")
    print(f"Title: {case.title}")
    print(f"Scenario: {case.scenario}")
    print(f"Prior thread messages carried into this run: {prior_message_count}")
    print("-" * 92)
    print(f"Ticket: {state['ticket_raw']}")
    print(f"Customer: {getattr(state.get('ticket_structured'), 'customer_id', None) or 'missing'}")
    print(f"Pending order: {getattr(pending_order, 'pending_order_id', None) or 'none'}")
    print(f"Retrieved rules: {', '.join(retrieved.get('matched_rule_ids', [])) or 'none'}")
    print(f"Validation: {validation_result.status}")
    print(f"Reason codes: {', '.join(validation_result.reason_codes) or 'none'}")
    print(f"Applied rules: {', '.join(validation_result.rules_used) or 'none'}")
    print(f"Missing fields: {', '.join(validation_result.missing_info) or 'none'}")
    print(f"Recommendation: {rec.decision} | executable={rec.executable_action_possible}")
    print(f"Execution guardrails: {', '.join(guardrails.reasons) if guardrails else 'not evaluated'}")
    print(f"Route: {state.get('route')}")
    print(f"Human/action result: {state.get('human_review') or state.get('execution_result') or 'none'}")
    print()


def _as_json_summary(case: DemoCase, state: dict[str, Any], *, iteration: int, prior_message_count: int) -> dict[str, Any]:
    return {
        "case_id": case.case_id,
        "scenario": case.scenario,
        "iteration": iteration,
        "thread_id": case.thread_id,
        "prior_message_count": prior_message_count,
        "ticket_raw": state["ticket_raw"],
        "pending_order_context": _model_dump(state.get("pending_order_context")),
        "retrieved_rule_ids": state.get("retrieved_rules", {}).get("matched_rule_ids", []),
        "validation_result": _model_dump(state.get("validation_result")),
        "recommendation": _model_dump(state.get("recommendation")),
        "execution_guardrails": _model_dump(state.get("execution_guardrails")),
        "memory_context": _model_dump(state.get("memory_context")),
        "route": state.get("route"),
        "human_review": state.get("human_review"),
        "execution_result": state.get("execution_result"),
    }


def run_demo_cases(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.dry_run:
        _patch_writes_for_dry_run()

    summaries: list[dict[str, Any]] = []
    thread_messages: dict[str, list[str]] = {}
    selected = {case_id.strip() for case_id in args.case if case_id.strip()}
    cases = [case for case in DEMO_CASES if not selected or case.case_id in selected]

    for case in cases:
        iteration_tickets = [case.ticket_raw]
        if args.continuous:
            iteration_tickets.extend(case.iterations)

        for index, ticket_raw in enumerate(iteration_tickets, start=1):
            run_case = DemoCase(
                case_id=case.case_id,
                title=case.title,
                scenario=case.scenario,
                thread_id=case.thread_id,
                ticket_raw=ticket_raw,
                ticket_structured=case.ticket_structured,
                iterations=[],
            )
            prior_messages = thread_messages.get(case.thread_id, [])
            state = _run_pipeline(
                run_case,
                source=args.source,
                persist_actions=args.persist_actions and not args.dry_run,
                prior_messages=prior_messages,
            )
            new_messages = state.get("messages", [])[len(prior_messages):]
            thread_messages[case.thread_id] = prior_messages + new_messages
            prior_count = len(prior_messages)

            if args.json:
                summaries.append(_as_json_summary(run_case, state, iteration=index, prior_message_count=prior_count))
            else:
                _print_case_result(run_case, state, iteration=index, prior_message_count=prior_count)

    if args.json:
        print(json.dumps(summaries, indent=2, default=str))

    if not args.json:
        print("=" * 92)
        print("Continuity note")
        print("This script carries node messages across repeated iterations of the same thread.")
        print("That demonstrates state continuity for demo purposes; durable checkpoint memory is not yet configured in the compiled graph.")
        if args.dry_run:
            print("Dry-run mode was enabled, so audit/execution/review writes were skipped.")
        elif not args.persist_actions:
            print("Action persistence was disabled; pass --persist-actions to write execution/review records.")
        print("=" * 92)

    return summaries


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run deterministic Pending Orders demo scenarios in English.",
    )
    parser.add_argument(
        "--source",
        choices=["db", "offline"],
        default="db",
        help="Use real PostgreSQL reads or embedded offline fixtures. Default: db.",
    )
    parser.add_argument(
        "--case",
        action="append",
        default=[],
        help="Run only one case id. Can be passed multiple times.",
    )
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Run follow-up iterations and carry thread messages between iterations.",
    )
    parser.add_argument(
        "--persist-actions",
        action="store_true",
        help="Persist auto_execute/human_review rows. Disabled by default.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Skip audit/execution/review writes. Enabled by default.",
    )
    parser.add_argument(
        "--write",
        dest="dry_run",
        action="store_false",
        help="Allow audit writes. Combine with --persist-actions to write action/review rows.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON summaries instead of the console report.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    run_demo_cases(parse_args())
