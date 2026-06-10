# Critical Method-Level Contracts

This page keeps detailed method contracts for high-impact classes.

Detailed blocks are maintained in:

- [Flat Full View - Class Contracts](../CLASS_CONTRACTS.md#method-level-contracts-critical-classes)

## Covered Critical Classes

- `RuntimeGameState`
- `MovementRules`
- `ActionCatalog`
- `OptionExecutor`
- `TrainingEnv`
- `Evaluator`

## Validation Rule

Any behavioral change in these classes requires updating:

1. this critical contract index,
2. the detailed method blocks in `CLASS_CONTRACTS.md`,
3. linked rule/test traceability docs.
