# Pending Orders LangGraph

An enterprise-grade LangGraph orchestrator for telecom pending order management.
Built with deterministic validation, PostgreSQL persistence, local business-rule retrieval, and Human-in-the-Loop controls.

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
      integration.py              # Load customer/order/asset context from DB
      policy_retrieval.py         # Metadata/keyword retrieval over local business rules
      validation.py               # Deterministic business rule engine (no LLM)
      recommendation.py           # Format validation output for humans
      auto_execute.py             # Persist auto-approved actions
      human_review.py             # Persist escalated cases for review
    graphs/
      pending_orders.py           # StateGraph construction + conditional routing
    tools/
      db_services.py              # PostgreSQL query layer for domain data
      rule_loader.py              # Markdown rule corpus loader
      rule_retriever.py           # Deterministic rule matching by metadata/keywords
      policy_retriever.py         # Optional vector policy retriever retained for later phases
      audit.py                    # Audit event logger to DB
  scripts/
    seed_db.py                    # DB schema creation + seed data
  tests/                          # Offline test suite (mocked DB + LLM)
```

### Graph Flow

```
triage → integration → policy_retrieval → validation → recommendation → [conditional]
                                                                            ├── auto_execute → END
                                                                            └── human_review → END (interrupt_before)
```

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

This creates all tables (`customers`, `pending_orders`, `installed_base_assets`, `audit_events`, `execution_log`, `human_reviews`) and populates them with 8 customers and realistic pending order scenarios.

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

The demo runner uses curated structured tickets, real DB reads by default, and dry-run action handling by default. For a fully offline smoke demo:

```bash
PYTHONPATH=. python scripts/run_demo_cases.py --source offline --continuous
```

To persist `auto_execute` / `human_review` records during a demo, pass:

```bash
PYTHONPATH=. python scripts/run_demo_cases.py --write --persist-actions
```

## Rule Knowledge Base

Business rules live in `app/knowledge/rules/` as Markdown files with small front matter blocks. The graph retrieves matching rules in `policy_retrieval.py` using deterministic metadata and keyword scoring, then `validation.py` applies explicit Python checks.

Current rule IDs include:

- `core.same_scope_pending`
- `core.required_fields`
- `installation.one_active_installation`
- `core.future_dated_pending_order`
- `exceptions.explicit_non_conflicting_exception`
- `scope.different_scope_allowed`
- `bundle.bundle_member_pending`
- `segment.cbu_vs_ebu_handling`

## Key Design Decisions

- **LLM is used only for extraction** (triage) — all business decisions are deterministic Python rules in `validation.py`
- **Rules are retrieved, not delegated**: the local knowledge base improves traceability and rationale, but validation code owns final decisions
- **Audit trail**: every node writes to `audit_events` for full traceability
- **Human-in-the-Loop**: `interrupt_before=["human_review"]` pauses the graph for operator approval
- **Conditional routing**: only `ALLOW_FOLLOW_ON` triggers auto-execution; everything else requires human review
