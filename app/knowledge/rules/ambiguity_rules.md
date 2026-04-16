---
rule_id: core.ambiguous_ticket
title: Ambiguous ticket requires clarification
decision: NEED_INFO
priority: 105
tags: [ambiguity, missing_info, request_scope, deterministic]
segments: [all]
scope_types: [all]
request_types: [all]
pending_order_types: [all]
---

# Ambiguous ticket requires clarification

If triage identifies contradictory scopes, unclear requested actions, or uncertainty about which pending order the request applies to, automated processing must stop and ask for clarification.

Examples:
- ticket mentions both fiber and mobile but does not identify the target order
- customer asks to change multiple services with one pending order open
- action wording is too vague to map to a deterministic follow-on

The LLM may detect ambiguity, but deterministic validation decides whether the graph can continue.
