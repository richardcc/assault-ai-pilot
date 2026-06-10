# 07 - GELA CAMPAIGN (Detailed Implementation Spec)

Primary source: `ITA_Assault_Libro_Campagna_v1.0.pdf`

## 1. Campaign Scope

Campaign mode defines a persistent multi-scenario operation with:

- one-time campaign initialization,
- scenario-by-scenario battle execution,
- post-battle persistence updates,
- branching progression and final campaign outcome.

## 2. Campaign Lifecycle

1. Campaign Setup (one-time)
2. Scenario Setup
3. Battle Phase
4. Scenario Resolution
5. End-of-Campaign Evaluation

## 3. Persistent Data Model

Minimum campaign state should include:

- selected factions/sides,
- main-unit roster,
- troop register values,
- experience per relevant unit,
- campaign branch pointer (next scenario logic),
- cumulative loss/status thresholds.

## 4. Scenario Resolution Contract

After each scenario:

1. determine scenario result,
2. update troop register/morale thresholds,
3. apply experience adjustments,
4. apply reinforcement/replacement rules,
5. resolve next scenario selection.

## 5. Campaign Precedence Rule

When campaign rules and base rulebook differ:

- campaign-book explicit rule takes precedence for campaign context.

## 6. Final Campaign Outcome

End-of-campaign logic must map final state to campaign outcome tables.

Implementation should keep this table-driven (not hardcoded by assumption).

## 7. Recommended Tests

- campaign setup invariants,
- scenario result -> troop register update mapping,
- experience adjustment edge cases,
- branch transition correctness,
- final outcome table mapping.

## 8. Validation Checklist

- [ ] Campaign setup runs once and seeds persistent state.
- [ ] Post-scenario updates are applied in deterministic order.
- [ ] Branching decisions are table-driven and traceable.
- [ ] Campaign precedence over base rules is explicit.
- [ ] Final campaign result matches campaign-book mapping.
