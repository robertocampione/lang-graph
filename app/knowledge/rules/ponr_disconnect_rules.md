---
rule_id: ponr.final_disconnect
title: Final disconnect and PONR restriction
decision: BLOCK
priority: 93
tags: [ponr, final_disconnect, port_out, deterministic]
segments: [CBU, EBU, PMIT_FIX, all]
scope_types: [fiber, tv, all]
request_types: [modification, follow_on, cancellation, all]
pending_order_types: [port_out, disconnect, cancellation, all]
---

# Final Disconnect And PONR Restriction

During final disconnect or port-out, SALTO can cancel orders still before PONR. The PoC blocks follow-on automation before PONR to avoid contradictory downstream actions.

Simulation assumption:
- The PoC models this through `final_disconnect=true` and `ponr_reached=false`.
