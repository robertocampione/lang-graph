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

Consumer, enterprise, and PMIT Mobile-style cases can require different operational handling even when the technical order shape is similar.

Guidance:
- CBU cases should remain conservative when customer identity or scope is incomplete.
- EBU cases may require SLA-aware escalation when the customer tier is high.
- PMIT Mobile placeholder cases should be reviewed when source markers are incomplete or contradictory.

This rule is currently retrieval and explanation knowledge. It must not override core deterministic blockers without explicit implementation.
