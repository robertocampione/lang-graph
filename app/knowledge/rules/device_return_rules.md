---
rule_id: device_return.follow_on_allowed
title: Device return only allows follow-on
decision: ALLOW
priority: 96
tags: [device_return, cease, follow_on, deterministic]
segments: [CBU, EBU, PMIT_FIX, PMIT_MOBILE, all]
scope_types: [device, mobile, fiber, all]
request_types: [device_return, return_device, follow_on, all]
pending_order_types: [cease, cancellation, all]
---

# Device Return Only Allows Follow-On

For cease orders, when execution is done and only device return remains pending, follow-on orders can proceed.

Simulation assumption:
- The PoC uses `device_return_pending`, `device_return_days`, and the `device_return_only` marker to represent the SALTO state.
- After 21 days, the follow-on can still be planned, but the recommendation must expose the amend/penalty path.
