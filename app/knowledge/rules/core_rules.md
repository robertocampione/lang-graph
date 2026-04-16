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

In the BCI + SALTO PoC simulation, pending orders are scope-based rather than customer-wide. A follow-on order is blocked when it targets the same resolved SALTO scope as an active pending order.

Different addresses or different explicit product instances can be independent. If BCI does not provide enough address or scope evidence to disambiguate, the validator stays conservative.

Examples:
- fiber request while a fiber order is pending
- mobile request while a mobile provisioning order is pending
- TV cancellation while a TV order is already in progress

The validator must apply this as deterministic business logic, not as an LLM judgment.

Simulation assumption:
- The current PoC uses simple scope fields (`scope_type`, `scope_id`, `address_id`) instead of the full SALTO internal order model.
