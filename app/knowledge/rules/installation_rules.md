---
rule_id: installation.one_active_installation
title: One active installation order at a time
decision: BLOCK
priority: 100
tags: [installation, physical_work, pending_order, deterministic]
segments: [all]
scope_types: [fiber, tv, all]
request_types: [modification, cancellation, follow_on, all]
pending_order_types: [provision, move, all]
---

# One active installation order at a time

If a pending order still requires physical installation work, the case must be blocked from automated follow-on execution.

Examples:
- technician appointment not completed
- installation marker still active
- order is waiting for customer premises work

This is a high priority deterministic rule because it protects downstream provisioning and field-service systems from contradictory actions.
