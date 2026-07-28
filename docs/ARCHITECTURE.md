# Architecture

Full detail lives in the design doc (`card_servicing_agent_design.pdf`,
§3). This is a short index into the actual code implementing each piece.

| Design doc component (§3.1) | Code |
|---|---|
| Conversational Orchestrator | `app/orchestration/graph.py` + `nodes/` |
| NLU Pipeline | `app/nlu/pipeline.py` (Stage 0/1/2 in `rule_classifier.py`, `embedding_classifier.py`, `llm_classifier.py`) |
| Policy and Risk Decision Engine | `app/policy/engine.py` + `rules/` |
| Integration Adapter Layer | `app/integrations/base_adapter.py` (Protocols) + `mocks/` |
| Audit Trail Service | `app/audit/writer.py`, `verifier.py` |
| Escalation Service | `app/escalation/handoff_builder.py`, `ticketing_adapter.py` |
| AuthN/AuthZ Service | `app/core/security.py` (dev stub only, see its docstring) |

## The one architectural principle everything else follows

Principle 1 (design doc §2): the LLM never has write access to core
banking. In this codebase, that's not just a comment — it's structural:

- `app/policy/` has zero imports from `app/nlu/` or `app/orchestration/`.
- The only thing `app/orchestration/nodes/route_node.py` (the
  policy_check node) can act on is `PolicyEngine`'s return value, which
  is a `Decision` built entirely from `AccountSnapshot`/`FeeRecord`/
  `RiskScore` objects fetched from the (mock) core banking / fraud
  adapters — never from anything the NLU pipeline produced, except as
  routing hints (which intent, which fee_type) that determine *which*
  policy function runs, not *what it decides*.
- `tests/unit/test_*_rules.py` exercises the policy engine with zero
  dependency on the NLU layer at all, proving the decision logic doesn't
  need conversation text to function.

## Data flow for one turn (fee reversal, auto-approved case)

```
customer message
  -> redact_pii()                                  [app/core/pii_redaction.py]
  -> NLUPipeline.classify()                         [app/nlu/pipeline.py]
       -> intent="fee_reversal", entities={fee_type: "late_fee"}
  -> containment_node                               [no-op for this intent]
  -> policy_check_node
       -> core_banking.get_account_summary()        [real system-of-record read]
       -> core_banking.list_fees() -> match fee_type
       -> PolicyEngine.evaluate_fee_reversal()       [deterministic, versioned]
       -> Decision(outcome="approved", ...)
  -> confirm_with_user_node -> interrupt()           [pauses for the UI click]
  -> [customer clicks Confirm]
  -> execute_action_node
       -> core_banking.reverse_fee(idempotency_key=...)
  -> audit_log_node
```

Every arrow that crosses a module boundary above is covered by a test in
`tests/integration/test_orchestration_graph.py`.
