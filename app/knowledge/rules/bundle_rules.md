---
rule_id: bundle.bundle_member_pending
title: Bundle member pending order restriction
decision: BLOCK
priority: 75
tags: [bundle, multi_product, pending_order, deterministic]
segments: [CBU, EBU, all]
scope_types: [fiber, tv, mobile, all]
request_types: [modification, cancellation, follow_on, all]
pending_order_types: [bundle, provision, move, all]
---

# Bundle member pending order restriction

When the pending order belongs to a bundle or shared installation flow, dependent bundle members should not be modified independently until the parent order reaches a final state.

Examples:
- internet and TV installation created as one bundle order
- mobile SIM added as part of a converged package
- cancellation request on one bundle member while the bundle order is still open

The initial implementation treats this as knowledge for retrieval and audit. A future deterministic rule can use explicit bundle identifiers once the data model contains them.
