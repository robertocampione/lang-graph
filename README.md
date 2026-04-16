# Pending Orders LangGraph

A stateful LangGraph orchestrator for pending order management.

## Architecture Overview

The codebase has been refactored into a scalable modular architecture ready for real business logic.

```
pending-orders-langgraph/
  app/
    main.py                       # Graph export entrypoint
    config/
      settings.py                 # Environment variables and config
    state/
      schema.py                   # GraphState comprehensive TypedDict
    nodes/
      triage.py                   # Triage evaluation node
      integration.py              # Context integration node
      recommendation.py           # Business rules and recommendation node
    graphs/
      pending_orders.py           # Construct the physical StateGraph flow
    tools/
      mock_db.py                  # Mock services & stubs (CRM etc.)
    prompts/                      # Prompt templates (future)
    memory/                       # Short & long-term memory (future)
  tests/                          # Test suite
  ...
```

## Setup

### 1. Create environment file

```bash
cp .env.example .env
# Fill in your API keys
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

### 5. Run LangGraph dev server

```bash
langgraph dev
```

The LangGraph Studio UI will be available at the URL printed in the terminal.
