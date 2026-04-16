---
rule_id: activation.delivery_milestone
title: Delivery milestone keeps order pending
decision: BLOCK
priority: 88
tags: [delivery, activation, milestone, deterministic]
segments: [CBU, EBU, PMIT_FIX, all]
scope_types: [fiber, tv, mobile, all]
request_types: [modification, follow_on, cancellation, all]
pending_order_types: [provision, move, bundle, all]
---

# Delivery Milestone Keeps Order Pending

Orders remain pending until the delivery milestone is reached. A follow-on order that depends on that future state must wait or be handled manually.

Simulation assumption:
- The PoC models this through a simplified milestone name and boolean `delivery_reached`.
