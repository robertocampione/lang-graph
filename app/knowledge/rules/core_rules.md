---
rule_id: core.same_scope_pending
title: Same scope pending order conflict
decision: BLOCK
priority: 90
tags: [pending_order, same_scope, conflict, deterministic]
segments: [all]
scope_types: [all]
request_types: [modification, cancellation, follow_on, status_update, all]
pending_order_types: [all]
---

# Same scope pending order conflict

If a customer already has an active pending order on the same scope type as the requested follow-on action, the follow-on action must be blocked until the pending order is resolved or manually overridden.

Examples:
- fiber request while a fiber order is pending
- mobile request while a mobile provisioning order is pending
- TV cancellation while a TV order is already in progress

The validator must apply this as deterministic business logic, not as an LLM judgment.
