---
rule_id: segment.pmit_mobile_matrix
title: PMIT Mobile cross-order matrix
decision: MATRIX
priority: 94
tags: [pmit_mobile, matrix, accept_block, deterministic]
segments: [PMIT_MOBILE]
scope_types: [mobile, all]
request_types: [modification, add_roaming_option, add_barring_option, all]
pending_order_types: [provision, modification, all]
---

# PMIT Mobile Cross-Order Matrix

PMIT Mobile standalone orders do not simply inherit CBU same-scope behavior. Compatibility is driven by a cross-order matrix:

- row = pending order type
- column = requested follow-on action
- value = Accept or Block

Simulation assumption:
- The PoC stores selected matrix rows in `compatibility_matrix`.
- If no matrix row is available, validation falls back to conservative same-scope handling.
