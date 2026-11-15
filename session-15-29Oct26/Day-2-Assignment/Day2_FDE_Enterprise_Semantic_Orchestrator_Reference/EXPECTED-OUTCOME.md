# Expected Outcome — What Good Looks Like

There is no required exact trajectory.

A strong solution demonstrates:

```text
Semantic next-action reasoning
        +
Deterministic enforcement
        +
Explicit evidence provenance
        +
Bounded execution
        +
Grounded termination
```

## Example only

A payment-hold case may reasonably converge through:

```text
GET_ORDER
→ CHECK_PAYMENT_HOLD
→ SYNTHESIZE
```

An inventory case may reasonably converge through:

```text
GET_ORDER
→ CHECK_WAREHOUSE
→ CHECK_INVENTORY
→ SYNTHESIZE
```

A systemic-change case may reasonably require:

```text
GET_ORDER
→ CHECK_WAREHOUSE
→ CHECK_INVENTORY
→ GET_RECENT_CHANGES
→ SEARCH_OPERATIONS_KNOWLEDGE
→ SYNTHESIZE
```

These are examples, **not expected hard-coded sequences**.

What matters is whether each selected action is justified by the evidence available
at that point, and whether deterministic controls remain invariant.
