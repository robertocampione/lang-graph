import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.nodes import policy_retrieval as policy_retrieval_module
from app.nodes import recommendation as recommendation_module
from app.nodes import validation as validation_module
from app.nodes.policy_retrieval import policy_retrieval
from app.nodes.recommendation import recommendation
from app.nodes.validation import validation
from app.state.schema import CustomerContext, InstalledBaseContext, PendingOrderContext, TicketStructured


DEFAULT_FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "golden_cases.json"


def _model_dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, list):
        return [_model_dump(item) for item in value]
    if isinstance(value, dict):
        return {key: _model_dump(item) for key, item in value.items()}
    return value


def _patch_writes_for_eval() -> None:
    def no_audit(node_name: str, summary: str, *_args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "node_name": node_name,
            "summary": summary,
            "actor_type": kwargs.get("actor_type", "SYSTEM"),
            "payload_summary": kwargs.get("payload", {}),
        }

    policy_retrieval_module.write_audit_event = no_audit
    validation_module.write_audit_event = no_audit
    recommendation_module.write_audit_event = no_audit


def load_cases(path: str | Path = DEFAULT_FIXTURE) -> list[dict[str, Any]]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_state(case: dict[str, Any]) -> dict[str, Any]:
    ticket = TicketStructured(**case["ticket_structured"])
    pending_order_data = case.get("pending_order_context")
    installed_base_data = case.get("installed_base_context") or []

    return {
        "messages": [],
        "case_id": case["case_id"],
        "correlation_id": case["case_id"],
        "thread_id": f"golden-{case['case_id']}",
        "ticket_raw": case["ticket_raw"],
        "ticket_structured": ticket,
        "customer_context": CustomerContext(**case["customer_context"]),
        "pending_order_context": PendingOrderContext(**pending_order_data) if pending_order_data else None,
        "installed_base_context": [InstalledBaseContext(**item) for item in installed_base_data],
        "retrieved_rules": {},
        "memory_context": {
            "case_id": case["case_id"],
            "correlation_id": case["case_id"],
            "prior_cases": [],
            "prior_human_reviews": [],
            "prior_executions": [],
            "missing_info_patterns": [],
            "principle": "golden_eval_memory_is_non_authoritative",
        },
        "confidence_summary": {"triage": ticket.confidence_score, "overall": ticket.confidence_score},
    }


def _merge(state: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    messages = list(state.get("messages", []))
    messages.extend(update.get("messages", []))
    audit_log = list(state.get("audit_log", []))
    audit_log.extend(update.get("audit_log", []))

    merged = {**state, **update}
    merged["messages"] = messages
    if audit_log:
        merged["audit_log"] = audit_log
    return merged


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    state = build_state(case)
    state = _merge(state, policy_retrieval(state))
    state = _merge(state, validation(state))
    state = _merge(state, recommendation(state))

    validation_result = state["validation_result"]
    recommendation_result = state["recommendation"]
    guardrails = state["execution_guardrails"]

    return {
        "case_id": case["case_id"],
        "title": case["title"],
        "scenario": case["scenario"],
        "validation_status": validation_result.status,
        "reason_codes": list(validation_result.reason_codes),
        "recommendation_decision": recommendation_result.decision,
        "guardrails_allowed": guardrails.allowed,
        "hitl_required": guardrails.required_human_review,
        "state": state,
    }


def compare_case_result(case: dict[str, Any], result: dict[str, Any]) -> list[str]:
    expected = case["expected"]
    mismatches: list[str] = []

    comparisons = [
        ("validation_status", expected["validation_status"], result["validation_status"]),
        ("recommendation_decision", expected["recommendation_decision"], result["recommendation_decision"]),
        ("guardrails_allowed", expected["guardrails_allowed"], result["guardrails_allowed"]),
        ("hitl_required", expected["hitl_required"], result["hitl_required"]),
    ]
    for field, expected_value, actual_value in comparisons:
        if expected_value != actual_value:
            mismatches.append(f"{field}: expected {expected_value!r}, got {actual_value!r}")

    expected_codes = list(expected["reason_codes"])
    actual_codes = list(result["reason_codes"])
    if expected_codes != actual_codes:
        mismatches.append(f"reason_codes: expected {expected_codes!r}, got {actual_codes!r}")

    return mismatches


def evaluate_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    _patch_writes_for_eval()
    results = []
    passed = 0

    for case in cases:
        result = run_case(case)
        mismatches = compare_case_result(case, result)
        result["passed"] = not mismatches
        result["mismatches"] = mismatches
        result.pop("state", None)
        results.append(result)
        if not mismatches:
            passed += 1

    return {
        "total": len(cases),
        "passed": passed,
        "failed": len(cases) - passed,
        "results": results,
    }


def _print_report(summary: dict[str, Any]) -> None:
    print("=" * 88)
    print("Golden Evaluation Report")
    print(f"Passed: {summary['passed']}/{summary['total']} | Failed: {summary['failed']}")
    print("-" * 88)

    for result in summary["results"]:
        status = "PASS" if result["passed"] else "FAIL"
        print(f"{status} {result['case_id']} - {result['title']}")
        print(f"  validation={result['validation_status']} reasons={', '.join(result['reason_codes']) or 'none'}")
        print(f"  recommendation={result['recommendation_decision']} guardrails_allowed={result['guardrails_allowed']} hitl_required={result['hitl_required']}")
        for mismatch in result["mismatches"]:
            print(f"  mismatch: {mismatch}")
    print("=" * 88)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate deterministic Pending Orders golden cases.")
    parser.add_argument(
        "--source",
        choices=["offline"],
        default="offline",
        help="Only offline fixtures are supported. Default: offline.",
    )
    parser.add_argument(
        "--fixture",
        default=str(DEFAULT_FIXTURE),
        help="Path to golden_cases.json.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable evaluation output.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cases = load_cases(args.fixture)
    summary = evaluate_cases(cases)

    if args.json:
        print(json.dumps(summary, indent=2, default=str))
    else:
        _print_report(summary)

    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
