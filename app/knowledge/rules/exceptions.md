---
rule_id: exceptions.explicit_non_conflicting_exception
title: Explicit non-conflicting exceptions
decision: ALLOW_OVERRIDE
priority: 95
tags: [exception, sim, device_return, override, deterministic]
segments: [all]
scope_types: [mobile, device, all]
request_types: [device_return, sim_swap, follow_on, all]
pending_order_types: [all]
---

# Explicit non-conflicting exceptions

Some requests can be allowed even when a pending order exists, but only when the ticket or source system provides an explicit exception marker.

Allowed exception examples:
- SIM-only administrative exception
- device return only, with no provisioning dependency
- explicitly approved backoffice exception marker

The validator may allow these cases only when the structured state contains a clear exception marker. The LLM may extract candidate wording, but the deterministic validator must decide.
