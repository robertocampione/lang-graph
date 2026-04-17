import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.graphs.pending_orders import route_to_approval, route_after_approval
from app.nodes import auto_execute as auto_execute_module
from app.nodes import human_review as human_review_module
from app.nodes import integration as integration_module
from app.nodes import policy_retrieval as policy_retrieval_module
from app.nodes import recommendation as recommendation_module
from app.nodes import validation as validation_module
from app.nodes.chat_wrapper import chat_wrapper
from app.nodes.approval import approval_level_1, approval_level_2
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
    requested_action: str | None = None,
    address_id: str | None = None,
    bci_case_id: str | None = None,
    product_family: str | None = None,
    missing_info: list[str] | None = None,
    ambiguities: list[str] | None = None,
    confidence_score: float = 0.95,
) -> TicketStructured:
    return TicketStructured(
        bci_case_id=bci_case_id,
        requested_action=requested_action,
        customer_id=customer_id,
        address_id=address_id,
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
        title="BCI case: installation still pending blocks second order",
        scenario="Phase 1 recommendation holds the BCI case because SALTO shows an active installation.",
        thread_id="demo-c-1001",
        ticket_raw="Customer C-1001 reports that the fiber installation is delayed and asks to proceed with a follow-on change.",
        ticket_structured=_ticket(
            customer_id="C-1001",
            bci_case_id="BCI-9001",
            subject="Fiber installation delayed",
            request_type="modification",
            pending_order_type="provision",
            scope_type="fiber",
            address_id="ADDR-1001-A",
            requested_follow_on_action="follow_on_change",
            requested_action="introduce_second_order",
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
        title="BCI case: same mobile scope blocks modification",
        scenario="CBU same-scope SALTO blocker routes to human review.",
        thread_id="demo-c-1002",
        ticket_raw="Customer C-1002 wants a mobile subscription modification while the mobile order is still pending.",
        ticket_structured=_ticket(
            customer_id="C-1002",
            subject="Mobile modification while pending",
            request_type="modification",
            pending_order_type="modification",
            scope_type="mobile",
            scope_id="MOB-888",
            address_id="ADDR-1002-A",
            requested_action="modify_mobile_subscription",
            product_family="Mobile",
        ),
    ),
    # Scenario: directive 06 green path. Different-scope request has no blockers
    # and should pass auto-execution guardrails.
    DemoCase(
        case_id="different-scope-allow",
        title="BCI case: different scope allows dry-run second order",
        scenario="Phase 2 dry-run is eligible because the fiber request is independent from the pending mobile order.",
        thread_id="demo-c-1002",
        ticket_raw="Customer C-1002 asks for a fiber information update while the current pending order is mobile.",
        ticket_structured=_ticket(
            customer_id="C-1002",
            subject="Fiber information update",
            request_type="status_update",
            pending_order_type="modification",
            scope_type="fiber",
            address_id="ADDR-1002-A",
            requested_action="introduce_second_order",
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
        title="BCI case: future-dated SALTO order blocks action",
        scenario="SALTO future-dated work is pending immediately and blocks automation.",
        thread_id="demo-c-1005",
        ticket_raw="Customer C-1005 asks to change the TV cancellation before the planned future execution date.",
        ticket_structured=_ticket(
            customer_id="C-1005",
            subject="Future dated TV change",
            request_type="modification",
            pending_order_type="cancellation",
            scope_type="tv",
            scope_id="TV-999",
            address_id="ADDR-1005-A",
            requested_action="change_cancellation",
            product_family="TV",
        ),
    ),
    # Scenario: directive 05 missing-info path plus directive 06 guardrails.
    # Missing customer id must request info and never auto-execute.
    DemoCase(
        case_id="pmit-mobile-matrix-allow",
        title="BCI case: PMIT Mobile matrix allows roaming option",
        scenario="PMIT Mobile uses a cross-order matrix instead of default same-scope blocking.",
        thread_id="demo-c-1008",
        ticket_raw="BCI-9004 Customer C-1008 asks to add roaming option during the PMIT mobile activation.",
        ticket_structured=_ticket(
            customer_id="C-1008",
            bci_case_id="BCI-9004",
            subject="PMIT roaming option",
            request_type="modification",
            pending_order_type="provision",
            scope_type="mobile",
            scope_id="MOB-555",
            address_id="ADDR-1008-A",
            requested_follow_on_action="add_roaming_option",
            requested_action="add_roaming_option",
            product_family="Mobile",
        ),
    ),
    DemoCase(
        case_id="bundle-member-block",
        title="BCI case: pending pack blocks member TV change",
        scenario="SALTO pack parent order blocks changes to dependent bundle members.",
        thread_id="demo-c-1007",
        ticket_raw="BCI-9003 Customer C-1007 wants to remove TV-777 from a pack while bundle order PO-1007 is open.",
        ticket_structured=_ticket(
            customer_id="C-1007",
            bci_case_id="BCI-9003",
            subject="Remove pack TV",
            request_type="modification",
            pending_order_type="bundle",
            scope_type="tv",
            scope_id="TV-777",
            address_id="ADDR-1007-A",
            requested_follow_on_action="remove_tv_option",
            requested_action="remove_tv_option",
            product_family="TV",
        ),
    ),
    DemoCase(
        case_id="device-return-allow",
        title="BCI case: only device return remains",
        scenario="SALTO cease execution is done; only device return is pending, so dry-run second order can proceed.",
        thread_id="demo-c-1009",
        ticket_raw="Customer C-1009 only has device return pending and asks for a second order.",
        ticket_structured=_ticket(
            customer_id="C-1009",
            subject="Device return only",
            request_type="device_return",
            pending_order_type="cease",
            scope_type="device",
            scope_id="DEV-1009",
            address_id="ADDR-1009-A",
            requested_follow_on_action="device_return",
            requested_action="device_return",
            product_family="Device",
        ),
    ),
    DemoCase(
        case_id="missing-customer-info",
        title="BCI case: missing customer identifier requests more information",
        scenario="Poor intake quality produces REQUEST_INFO and keeps the case HITL.",
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
    "C-1001": CustomerContext(name="Synthetic Fiber Home", tier="gold", segment="CBU", open_orders=3, oldest_pending_days=12, source="offline_fixture"),
    "C-1002": CustomerContext(name="Synthetic Mobile Customer", tier="silver", segment="CBU", open_orders=1, oldest_pending_days=2, source="offline_fixture"),
    "C-1005": CustomerContext(name="Synthetic Future TV", tier="gold", segment="CBU", open_orders=2, oldest_pending_days=5, source="offline_fixture"),
    "C-1007": CustomerContext(name="Synthetic Bundle Family", tier="standard", segment="CBU", open_orders=1, oldest_pending_days=1, source="offline_fixture"),
    "C-1008": CustomerContext(name="Synthetic PMIT Mobile", tier="silver", segment="PMIT_MOBILE", open_orders=2, oldest_pending_days=10, source="offline_fixture"),
    "C-1009": CustomerContext(name="Synthetic Device Return", tier="standard", segment="CBU", open_orders=1, oldest_pending_days=18, source="offline_fixture"),
}

OFFLINE_ORDERS = {
    "C-1001": PendingOrderContext(
        pending_order_id="PO-1001",
        order_type="provision",
        order_status="in_progress",
        scope_type="fiber",
        scope_id="FIB-555",
        address_id="ADDR-1001-A",
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
        address_id="ADDR-1002-A",
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
        address_id="ADDR-1005-A",
        planned_execution_date="2026-07-01",
        installation_pending=False,
        oldest_pending_days=5,
        exception_markers=["future_dated"],
    ),
    "C-1007": PendingOrderContext(
        pending_order_id="PO-1007",
        order_type="bundle",
        order_status="in_progress",
        scope_type="bundle",
        scope_id="BUN-777",
        address_id="ADDR-1007-A",
        bundle_id="BUN-777",
        planned_execution_date="2026-06-01",
        installation_pending=False,
        oldest_pending_days=1,
        exception_markers=[],
    ),
    "C-1008": PendingOrderContext(
        pending_order_id="PO-1008",
        order_type="provision",
        order_status="in_progress",
        scope_type="mobile",
        scope_id="MOB-555",
        address_id="ADDR-1008-A",
        planned_execution_date="2026-04-18",
        installation_pending=False,
        oldest_pending_days=10,
        exception_markers=["pmit_sync"],
    ),
    "C-1009": PendingOrderContext(
        pending_order_id="PO-1009",
        order_type="cease",
        order_status="return_pending",
        scope_type="device",
        scope_id="DEV-1009",
        address_id="ADDR-1009-A",
        planned_execution_date="2026-03-20",
        installation_pending=False,
        oldest_pending_days=18,
        exception_markers=["device_return_only"],
        device_return_pending=True,
        device_return_days=18,
        ponr_reached=True,
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
    compatibility_decision = None
    if customer_id == "C-1008" and getattr(ticket, "requested_action", None) == "add_roaming_option":
        compatibility_decision = {
            "segment": "PMIT_MOBILE",
            "pending_order_type": "provision",
            "follow_on_action": "add_roaming_option",
            "decision": "ACCEPT",
            "reason": "PMIT Mobile matrix allows roaming option.",
        }
    bundle_context = None
    if customer_id == "C-1007":
        bundle_context = {
            "bundle_id": "BUN-777",
            "customer_id": "C-1007",
            "address_id": "ADDR-1007-A",
            "member_scope_ids": ["FIB-777", "TV-777"],
            "member_asset_ids": ["AST-777-I", "AST-777-TV"],
        }
    order_id = order.pending_order_id if order else "None"
    return {
        "messages": [f"[integration:offline] Context loaded. Customer: {customer.name} ({customer_id or 'n/a'}). Pending Orders: {order_id}. Installed Base size: {len(assets)}."],
        "customer_context": customer,
        "pending_order_context": order,
        "installed_base_context": assets,
        "compatibility_decision": compatibility_decision,
        "bundle_context": bundle_context,
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
    route = route_to_approval(state)
    state["route"] = route

    if route == "human_review":
        if persist_actions:
            state = _merge(state, human_review(state))
        else:
            state["human_review"] = f"Dry-run review required: {state['recommendation'].decision}"
    else:
        # Approval layer
        if route == "approval_level_1":
            state = _merge(state, approval_level_1(state))
        elif route == "approval_level_2":
            state = _merge(state, approval_level_2(state))

        after_approval = route_after_approval(state)
        
        if after_approval == "auto_execute":
            if persist_actions:
                state = _merge(state, auto_execute(state))
            else:
                action_plan = state.get("action_plan")
                state["execution_result"] = json.dumps({
                    "status": "dry_run",
                    "action_taken": getattr(action_plan, "action_type", state["recommendation"].decision),
                    "target_system": getattr(action_plan, "target_system", "SALTO"),
                    "detail": "Auto-execution was skipped because --persist-actions was not set.",
                })
        else:
            state["execution_result"] = "Execution halted due to approval rejection."

    return state


def _print_case_result(case: DemoCase, state: dict[str, Any], *, iteration: int, prior_message_count: int) -> None:
    validation_result: ValidationResult = state["validation_result"]
    rec: Recommendation = state["recommendation"]
    action_plan = state.get("action_plan")
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
    print(f"Recommendation: {rec.decision} | requires_human={rec.requires_human}")
    if action_plan:
        print(f"Action plan: {action_plan.action_type} on {action_plan.target_system} | auto_eligible={action_plan.auto_eligible}")
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
        "action_plan": _model_dump(state.get("action_plan")),
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
