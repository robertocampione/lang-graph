---
rule_id: core.future_dated_pending_order
title: Future-dated pending order restriction
decision: BLOCK
priority: 85
tags: [future_dated, pending_order, scheduling, deterministic]
segments: [all]
scope_types: [fiber, mobile, tv, all]
request_types: [modification, cancellation, follow_on, all]
pending_order_types: [all]
---

# Future-dated pending order restriction

Future-dated pending orders must not be automatically modified or followed by dependent actions before their planned execution window.

Examples:
- order planned for a future activation date
- cancellation requested before the pending order reaches execution
- follow-on action that depends on a not-yet-active service

The initial data backbone represents this using the `future_dated` marker in `exception_markers`.
