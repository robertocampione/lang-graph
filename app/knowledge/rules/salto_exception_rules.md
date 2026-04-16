---
rule_id: exceptions.salto_explicit_exception
title: SALTO explicit exceptions and exclusions
decision: ALLOW_OR_BLOCK
priority: 97
tags: [exception, sim, iff, copper_outphasing, exclusion, deterministic]
segments: [CBU, EBU, PMIT_FIX, PMIT_MOBILE, all]
scope_types: [mobile, device, all]
request_types: [sim_swap, block_sim, unblock_sim, add_data_boost, all]
pending_order_types: [all]
---

# SALTO Explicit Exceptions And Exclusions

Some actions can proceed despite a pending order when SALTO or the BCI case clearly identifies them as non-conflicting exceptions:

- SIM block, unblock, or swap
- Instant Fulfilment data or volume boosts
- mobile asset action related to copper outphasing
- approved mobile "keep" actions inside a pack

Exclusions still block the exception:

- V1 / OMS customer
- import or export order
- change ownership
- DUO card

Simulation assumption:
- The PoC uses `exception_markers` and `exclusion_markers` rather than the full SALTO rule engine.
