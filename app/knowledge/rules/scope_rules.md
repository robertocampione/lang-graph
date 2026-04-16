---
rule_id: scope.different_scope_allowed
title: Different scope follow-on handling
decision: ALLOW
priority: 30
tags: [scope, follow_on, allow, deterministic]
segments: [all]
scope_types: [fiber, mobile, tv, billing, all]
request_types: [modification, follow_on, status_update, all]
pending_order_types: [all]
---

# Different scope follow-on handling

A follow-on action can proceed when the open pending order concerns a different scope type and no stronger blocking rule applies.

Examples:
- mobile data booster while a fiber order is pending
- billing clarification while a mobile provisioning order is pending
- TV package question while a fiber move order is pending

This rule is lower priority than installation, same-scope, future-dated, and segment restriction rules.
