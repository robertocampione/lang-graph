# Pending Orders LangGraph

An enterprise-grade LangGraph orchestrator for telecom pending order management.
The current PoC simulation is aligned to a Proximus-style BCI + SALTO workflow: BCI is the unstructured case intake system, SALTO is the simulated customer, order, installed-base, milestone, and dry-run execution system.

## Architecture Overview

```
pending-orders-langgraph/
  app/
    main.py                       # Graph export entrypoint
    config/
      settings.py                 # Environment variables and config
      llm.py                      # LLM initialization (Gemini 2.5 Flash)
    state/
      schema.py                   # Pydantic domain models + GraphState TypedDict
    db/
      connection.py               # psycopg PostgreSQL connection helpers
    knowledge/
      rules/                      # Local Markdown business rule corpus
    nodes/
      triage.py                   # LLM-based ticket parsing
      integration.py              # Load BCI case + SALTO customer/order/asset context from DB
      policy_retrieval.py         # Metadata/keyword retrieval over local business rules
      validation.py               # Deterministic business rule engine (no LLM)
      recommendation.py           # Produce operator recommendation + ActionPlan
      auto_execute.py             # Persist guarded dry-run SALTO actions
      human_review.py             # Persist escalated cases for review
    graphs/
      pending_orders.py           # StateGraph construction + conditional routing
    tools/
      db_services.py              # Explicit BCI/SALTO PostgreSQL query helpers
      rule_loader.py              # Markdown rule corpus loader
      rule_retriever.py           # Deterministic rule matching by metadata/keywords
      policy_retriever.py         # Optional vector policy retriever retained for later phases
      audit.py                    # Audit event logger to DB
      case_history.py             # Lightweight memory helpers over audit/review/execution records
  scripts/
    seed_db.py                    # DB schema creation + seed data
    run_demo_cases.py             # Curated demo scenarios with optional offline mode
    evaluate_golden_cases.py      # Offline golden dataset evaluator
  tests/                          # Offline test suite (mocked DB + LLM)
    fixtures/golden_cases.json    # Stable deterministic evaluation cases
```

### Graph Flow

```
BCI triage → BCI/SALTO integration → policy_retrieval → deterministic validation
    → recommendation + action_plan → [conditional]
                                  ├── auto_execute dry-run → END
                                  └── human_review → END (interrupt_before)
```

Phase 1 is the operator-assist path: the graph explains what the back-office agent should do in BCI/SALTO.
Phase 2 is represented as guarded dry-run autonomy: eligible second-order actions can route to `auto_execute`, but only after deterministic validation and action-plan guardrails pass.

## Setup

### 1. Create environment file

```bash
cp .env.example .env
# Fill in your GOOGLE_API_KEY and verify POSTGRES_URL
```

### 2. Create and activate virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Start infrastructure

```bash
docker compose up -d
```

### 5. Initialize and seed the database

```bash
PYTHONPATH=. python scripts/seed_db.py
```

This creates BCI/SALTO simulation tables, including `bci_cases`, `bci_case_events`, `customers`, `customer_addresses`, `salto_orders`, `pending_orders`, `order_milestones`, `installed_base_assets`, `bundle_memberships`, `compatibility_matrix`, `action_catalog`, `audit_events`, `execution_log`, and `human_reviews`.

Seed data is synthetic and covers CBU, EBU, PMIT Fix, PMIT Mobile, bundles, future-dated orders, device return, SIM exceptions, and PONR/final disconnect.

To **reset** the database, simply re-run the seed script — it drops and recreates all tables.

### 6. Run LangGraph dev server

```bash
langgraph dev
```

The LangGraph Studio UI will be available at the URL printed in the terminal.

### 7. Run tests

```bash
PYTHONPATH=. pytest tests/ -v
```

Tests run fully offline using mocked DB and LLM layers.

### 8. Run demo scenarios

```bash
PYTHONPATH=. python scripts/run_demo_cases.py --continuous
```

The demo runner uses curated BCI/SALTO stories, real DB reads by default, and dry-run action handling by default. It demonstrates both Phase 1 HITL recommendations and Phase 2 dry-run action plans. 

### Core Demo Scenarios
The demo runs 5 key business scenarios representing standard handling:
- **Same Scope Block**: Evaluates Fiber + Fiber request on the same customer, resulting in `BLOCKED` (Phase 1).
- **Explicit Exception**: Evaluates a SIM Swap request on an explicitly marked Mobile order, resulting in `ALLOWED` (Phase 2 Auto-eligible).
- **Missing Info**: Evaluates an intake request lacking a Customer ID, resulting in `NEEDS_INFO` (Phase 1).
- **Valid Follow-on**: Evaluates a TV request while a Fiber order is pending, resulting in `ALLOWED` (Phase 2 Auto-eligible).
- **Human Override**: Evaluates a scenario where guardrails force human review via low confidence or missing information, resulting in `NEEDS_INFO` or `BLOCKED`.

For a fully offline smoke demo:

```bash
PYTHONPATH=. python scripts/run_demo_cases.py --source offline --continuous
```

To persist `auto_execute` / `human_review` records during a demo, pass:

```bash
PYTHONPATH=. python scripts/run_demo_cases.py --persist-actions
```

### 9. Run golden evaluation

```bash
PYTHONPATH=. python scripts/evaluate_golden_cases.py --source offline
```

The golden evaluator uses `tests/fixtures/golden_cases.json` and curated structured state. It does not call live LLMs or require a database, so it is suitable for local regression checks and CI-style validation. The current fixture has 34 BCI/SALTO scenarios and compares validation status, reason codes, recommendation, action-plan type, auto eligibility, guardrails, and HITL routing. Add `--json` for machine-readable output.

## Rule Knowledge Base

Business rules live in `app/knowledge/rules/` as Markdown files with small front matter blocks. The graph retrieves matching rules in `policy_retrieval.py` using deterministic metadata and keyword scoring, then `validation.py` applies explicit Python checks.

Current rule IDs include:

- `core.ambiguous_ticket`
- `core.same_scope_pending`
- `core.required_fields`
- `installation.one_active_installation`
- `core.future_dated_pending_order`
- `exceptions.explicit_non_conflicting_exception`
- `exceptions.salto_explicit_exception`
- `scope.different_scope_allowed`
- `bundle.bundle_member_pending`
- `segment.cbu_vs_ebu_handling`
- `segment.pmit_mobile_matrix`
- `device_return.follow_on_allowed`
- `activation.delivery_milestone`
- `ponr.final_disconnect`

## LLM Model Roles

The project uses LLMs only for extraction and optional future operator-facing language tasks. Business validation and routing remain deterministic.

Environment-driven model roles:

- `TRIAGE_MODEL`: extracts `TicketStructured` from raw ticket text in `triage.py`
- `REASONING_MODEL`: reserved for future explanation drafting; it must not decide validation outcomes
- `UTILITY_MODEL`: reserved for low-risk formatting or summarization helpers
- `TRIAGE_TEMPERATURE`: defaults to `0` for repeatable extraction
- `LLM_TIMEOUT_SECONDS`: request timeout for role-based LLM helpers
- `ENABLE_LLM_TRACE`: enables lightweight trace metadata in graph state

The triage node extracts BCI-oriented fields such as `bci_case_id`, `intake_channel`, `ticket_type_raw`, `creator_role`, `customer_identifier`, `address_identifier`, `salto_order_reference`, `requested_action`, and evidence text. It still records `llm_trace`, `confidence_summary`, and structured `errors` when extraction fails. If the LLM returns malformed output or times out, the graph receives a safe low-confidence `TicketStructured` object instead of crashing.

## Human Review And Execution Guardrails

Automatic execution is protected by deterministic guardrails in `app/tools/execution_guardrails.py`. The graph routes to `auto_execute` only when all of these are true:

- `ENABLE_AUTO_EXECUTE=true`
- recommendation decision is `ALLOWED`
- `requires_human=false`
- `action_plan.auto_eligible=true`
- `action_plan.action_type` is a supported dry-run action (`INTRODUCE_SECOND_ORDER_DRY_RUN` or `AMEND_ORDER_DRY_RUN`)
- `action_plan.target_system=SALTO`
- validation status is `ALLOW`
- no validation missing info or blocking conditions exist
- recommendation and validation confidence meet `AUTO_EXECUTE_MIN_CONFIDENCE`
- no upstream state errors are present

The `auto_execute` node re-checks the same guardrails defensively before writing execution records. It records simulated dry-run actions rather than calling real SALTO APIs. Any failed guardrail routes to `human_review`, where `human_review_payload` includes validation status, reason codes, action-plan fields, missing fields, and guardrail reasons for the operator.

## Auditability And Memory

Graph state carries trace fields for `correlation_id`, `case_id`, optional `thread_id`, accumulated `audit_log`, and non-authoritative `memory_context`. Audit writes include node name, actor type, trace identifiers, BCI/SALTO identifiers, action metadata, payload summary, and timestamp. The audit writer still tolerates older call sites and falls back to the legacy DB insert shape if the local database has not been reseeded yet.

`app/tools/case_history.py` reads existing `audit_events`, `human_reviews`, and `execution_log` style data to expose prior cases, prior human review decisions, and recurring missing-info patterns. This memory is shown to recommendation/HITL payloads for operator context only; validation, recommendation decisions, guardrails, and routing remain deterministic.

## Key Design Decisions

- **LLM is used only for extraction** (triage) — all business decisions are deterministic Python rules in `validation.py`
- **Rules are retrieved, not delegated**: the local knowledge base improves traceability and rationale, but validation code owns final decisions
- **Action planning separates Phase 1 and Phase 2**: recommendation tells the operator what to do; `ActionPlan` states whether guarded dry-run autonomy is possible
- **Auto-execution is guarded twice**: routing can choose the auto path, but `auto_execute.py` still re-checks deterministic guardrails and only dry-runs eligible SALTO actions
- **Audit trail and memory**: core nodes write enriched audit events and can surface lightweight historical context
- **Golden evaluation**: stable offline fixtures exercise known allow/block/need-info scenarios without live LLMs
- **Human-in-the-Loop**: `interrupt_before=["human_review"]` pauses the graph for operator approval
- **Conditional routing**: only `ALLOWED` with an eligible dry-run action plan triggers auto-execution; everything else requires human review
