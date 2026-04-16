---
rule_id: core.required_fields
title: Required fields before automated processing
decision: NEED_INFO
priority: 110
tags: [missing_info, required_fields, deterministic]
segments: [all]
scope_types: [all]
request_types: [all]
pending_order_types: [all]
---

# Required fields before automated processing

Automated validation must stop with `NEED_INFO` when essential identifiers are still unresolved after triage and integration.

Examples:
- missing customer ID
- missing scope when no pending order context can resolve it
- missing order reference when neither ticket nor customer context identifies a pending order

If authoritative integration context resolves a field flagged by the LLM, validation can continue with the resolved context.
