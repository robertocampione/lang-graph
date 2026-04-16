import importlib
import json
from pathlib import Path

import app.nodes.integration as integration_module
import app.tools.audit as audit_module
import app.tools.case_history as case_history_module
from app.nodes.integration import integration
from app.nodes.validation import validation
from app.state.schema import PendingOrderContext
from app.tools.audit import build_audit_entry
from scripts.evaluate_golden_cases import compare_case_result, evaluate_cases, load_cases


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "golden_cases.json"


# Scenario group: directive 07 auditability and case-memory helpers.
def test_build_audit_entry_tolerates_missing_trace_ids():
    entry = build_audit_entry(
        "validation",
        "Status: NEED_INFO",
        state={"ticket_raw": "No identifiers here"},
        payload={"status": "NEED_INFO"},
    )

    assert entry["node_name"] == "validation"
    assert entry["actor_type"] == "SYSTEM"
    assert entry["correlation_id"] is None
    assert entry["case_id"] is None
    assert entry["thread_id"] is None
    assert entry["payload_summary"]["status"] == "NEED_INFO"


def test_audit_write_failure_does_not_crash(monkeypatch):
    reloaded_audit = importlib.reload(audit_module)

    def raise_db_error(*_args, **_kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(reloaded_audit, "execute_query", raise_db_error)

    entry = reloaded_audit.write_audit_event(
        "recommendation",
        "Decision: REQUEST_INFO",
        state={"case_id": "CASE-1", "correlation_id": "CORR-1"},
        payload={"decision": "REQUEST_INFO"},
    )

    assert entry["case_id"] == "CASE-1"
    assert entry["correlation_id"] == "CORR-1"
    assert entry["payload_summary"]["decision"] == "REQUEST_INFO"


def test_case_history_lookup_with_mocked_rows(monkeypatch):
    def fake_fetch_all(query, params=()):
        if "FROM audit_events" in query:
            return [
                {
                    "timestamp": "2026-04-17 10:00:00",
                    "node_name": "validation",
                    "actor_type": "SYSTEM",
                    "summary": "Status: BLOCK",
                    "correlation_id": params[2],
                    "case_id": params[0],
                    "thread_id": "thread-1",
                    "payload_summary": {"status": "BLOCK"},
                }
            ]
        if "FROM human_reviews" in query:
            return [
                {
                    "created_at": "2026-04-17 10:01:00",
                    "decision": "HOLD_CASE",
                    "suggested_human_action": "Review with backoffice",
                    "missing_fields": [],
                }
            ]
        if "FROM execution_log" in query:
            return [
                {
                    "created_at": "2026-04-17 10:02:00",
                    "action_taken": "ALLOW_FOLLOW_ON",
                    "detail": "Executed",
                    "status": "success",
                }
            ]
        return []

    monkeypatch.setattr(case_history_module, "fetch_all", fake_fetch_all)

    prior_cases = case_history_module.fetch_prior_cases(case_id="CASE-1", correlation_id="CORR-1")
    prior_reviews = case_history_module.fetch_prior_human_reviews("same ticket")
    prior_executions = case_history_module.fetch_prior_executions("same ticket")

    assert prior_cases[0]["node_name"] == "validation"
    assert prior_cases[0]["payload_summary"]["status"] == "BLOCK"
    assert prior_reviews[0]["decision"] == "HOLD_CASE"
    assert prior_executions[0]["status"] == "success"


def test_recurring_missing_info_patterns(monkeypatch):
    monkeypatch.setattr(
        case_history_module,
        "fetch_all",
        lambda *_args, **_kwargs: [
            {"missing_fields": ["customer_id", "scope_id"]},
            {"missing_fields": ["scope_id"]},
            {"missing_fields": ["pending_order_id"]},
        ],
    )

    patterns = case_history_module.fetch_missing_info_patterns()

    assert patterns[0] == {"field": "scope_id", "count": 2}
    assert {"field": "customer_id", "count": 1} in patterns


def test_memory_context_is_returned_by_integration(monkeypatch, base_state_triage):
    monkeypatch.setattr(
        integration_module,
        "fetch_customer_context",
        lambda _customer_id: {"name": "Acme Corp", "tier": "gold", "open_orders": 3, "oldest_pending_days": 12, "source": "mock"},
    )
    monkeypatch.setattr(
        integration_module,
        "fetch_pending_order_context",
        lambda _customer_id: {
            "pending_order_id": "PO-1001",
            "order_type": "provision",
            "order_status": "in_progress",
            "scope_type": "fiber",
            "scope_id": "FIB-555",
            "planned_execution_date": "2026-05-01",
            "installation_pending": True,
            "oldest_pending_days": 12,
            "exception_markers": ["delay_reported"],
        },
    )
    monkeypatch.setattr(integration_module, "fetch_installed_base_context", lambda _customer_id: [])
    monkeypatch.setattr(
        integration_module,
        "build_memory_context",
        lambda _state: {"prior_human_reviews": [{"decision": "HOLD_CASE"}], "principle": "test"},
    )
    monkeypatch.setattr(integration_module, "write_audit_event", lambda *args, **kwargs: {"node_name": args[0]})

    base_state_triage["ticket_structured"].customer_id = "C-1001"
    result = integration(base_state_triage)

    assert result["memory_context"]["prior_human_reviews"][0]["decision"] == "HOLD_CASE"
    assert result["audit_log"][0]["node_name"] == "integration"


def test_prior_human_review_memory_does_not_change_validation(base_state_triage):
    base_state_triage["memory_context"] = {
        "prior_human_reviews": [{"decision": "ALLOW_FOLLOW_ON"}],
        "principle": "memory_informs_validation_decides_audit_persists",
    }
    base_state_triage["ticket_structured"].missing_info = []
    base_state_triage["ticket_structured"].scope_type = "mobile"
    base_state_triage["pending_order_context"] = PendingOrderContext(
        pending_order_id="PO-1002",
        order_type="modification",
        order_status="on_hold",
        scope_type="mobile",
        scope_id="MOB-888",
        planned_execution_date="2026-04-20",
        installation_pending=False,
        oldest_pending_days=2,
        exception_markers=[],
    )

    result = validation(base_state_triage)

    assert result["validation_result"].status == "BLOCK"
    assert result["validation_result"].reason_codes == ["SAME_SCOPE_PENDING"]


def test_unknown_customer_remains_need_info(base_state_triage):
    base_state_triage["ticket_structured"].customer_id = "C-9999"
    base_state_triage["ticket_structured"].missing_info = ["pending_order_id"]
    base_state_triage["ticket_structured"].scope_type = None
    base_state_triage["pending_order_context"] = None

    result = validation(base_state_triage)

    assert result["validation_result"].status == "NEED_INFO"
    assert result["validation_result"].reason_codes == ["MISSING_DATA"]


# Scenario group: directive 08 golden dataset and deterministic evaluation harness.
def test_golden_fixture_schema_valid():
    cases = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    assert 12 <= len(cases) <= 16
    for case in cases:
        assert {"case_id", "title", "scenario", "ticket_raw", "ticket_structured", "expected"} <= set(case)
        assert {"validation_status", "reason_codes", "recommendation_decision", "guardrails_allowed", "hitl_required"} <= set(case["expected"])


def test_golden_evaluation_comparison_logic_reports_mismatch():
    case = {
        "expected": {
            "validation_status": "ALLOW",
            "reason_codes": ["NO_CONFLICTS"],
            "recommendation_decision": "ALLOW_FOLLOW_ON",
            "guardrails_allowed": True,
            "hitl_required": False,
        }
    }
    result = {
        "validation_status": "BLOCK",
        "reason_codes": ["SAME_SCOPE_PENDING"],
        "recommendation_decision": "HOLD_CASE",
        "guardrails_allowed": False,
        "hitl_required": True,
    }

    mismatches = compare_case_result(case, result)

    assert any(item.startswith("validation_status") for item in mismatches)
    assert any(item.startswith("reason_codes") for item in mismatches)


def test_golden_evaluation_passes_offline_fixture():
    summary = evaluate_cases(load_cases(FIXTURE_PATH))

    assert summary["failed"] == 0
    assert summary["passed"] == summary["total"]
