# 02 - TURN SEQUENCE AND ACTIONS (Execution Contract)

Primary source: Rulebook v2.0 (chapters 6 to 11).

## 1. Phase Order (Hard Constraint)

The engine must process phases in this exact order:

1. Initiative Phase
2. Planning Phase
3. Support Phase
4. Action Phase
5. Organization Phase
6. Victory Check Phase
7. Reinforcements Phase

## 2. Phase Responsibilities

### Initiative

- Determine initiative holder.
- Apply initiative-linked scenario hooks.

### Planning

- Assign command resources/cards (if enabled).
- Register deferred support requests (TAS/OAS optional flow).

### Support

- Execute support actions (indirect fire, smoke, support abilities).
- Apply support-side state updates before action phase.

### Action

- Resolve activations and tactical actions:
  - movement,
  - ranged fire,
  - close combat,
  - special actions.

### Organization

- Resolve status maintenance/cleanup.
- Apply end-of-turn marker transitions.

### Victory Check

- Evaluate scenario victory conditions.
- Set terminal state if conditions are satisfied.

### Reinforcements

- Deploy scenario/campaign reinforcements.

## 3. Action Domain Taxonomy

### Movement

- normal/fast movement,
- move-and-fire variants when legal,
- hide/ambush movement interactions,
- objective-entry and capture effects.

### Ranged Fire

- direct and indirect modes,
- LOS/spotting validation,
- dice resolution and critical routing.

### Close Combat

- initiation conditions,
- round-level attack/defense modifiers,
- fallback/elimination closure behavior.

### Special Actions

- pass,
- reaction fire,
- command card play.

## 4. Activation Eligibility

A unit may be ineligible if:

- suppressed or fallback state forbids action,
- already activated in current activation cycle,
- action-specific legality fails,
- terrain/LOS/arc constraints block execution.

## 5. Validation Checklist

- [ ] Phase order is immutable and auditable.
- [ ] Legal-action generation is phase-aware.
- [ ] State updates are committed immediately after action resolution.
- [ ] Victory check timing matches rule semantics.
- [ ] Reinforcements are handled only in reinforcement timing.
