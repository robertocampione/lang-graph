---
rule_id: segment.cbu_vs_ebu_handling
title: Segment-specific pending order handling
decision: REVIEW
priority: 60
tags: [segment, cbu, ebu, pmit_mobile, review]
segments: [CBU, EBU, PMIT, all]
scope_types: [mobile, fiber, tv, all]
request_types: [modification, cancellation, follow_on, all]
pending_order_types: [all]
---

# Segment-specific pending order handling

Consumer, PMIT Fix, EBU, and PMIT Mobile cases can require different operational handling even when the technical order shape is similar.

Guidance:
- CBU cases follow the restrictive bundle, fixed, TV, and installation rules.
- PMIT Fix follows the same restrictive logic as CBU.
- EBU fixed-line cases still respect same-scope blockers; SLA/tier can affect escalation, not the deterministic blocker itself.
- PMIT Mobile standalone cases use a cross-order matrix where rows are pending order types, columns are follow-on actions, and values are Accept or Block.

This rule must not override core deterministic blockers except where PMIT Mobile matrix behavior is explicitly implemented.
