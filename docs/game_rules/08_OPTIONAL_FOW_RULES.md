# 08 - OPTIONAL FOW RULES (Detailed Implementation Spec)

Primary source: `2025_09_10_FoW_v01.pdf`

## 1. Module Status

Fog of War is an optional module and must be feature-flagged:

- disabled by default in baseline scenarios,
- enabled only by scenario/ruleset declaration.

## 2. Contact Model

Unknown enemy information is represented via contact markers:

- unknown contact,
- identified contact,
- dummy/deception contact.

Each marker has its own reveal conditions and behavioral constraints.

## 3. Reveal Triggers

Marker reveal should occur on explicit triggers, such as:

- adjacency/visual confirmation,
- recon action success,
- attack interaction constraints defined by module.

## 4. Recon Action Contract

Recon must have:

- eligibility constraints,
- target scope,
- resolution roll/check (if applicable),
- reveal/update side effects.

## 5. Fire Interactions Under FoW

### Direct Fire

- can be restricted by unknown-contact status unless reveal criteria are met.

### Indirect Fire / OAS

- may target probable areas under module-specific limitations.
- final effect and reveal consequences must be explicit.

## 6. State Transition Requirements

Contacts must move through valid states only:

- hidden -> unknown contact -> identified or removed,
- hidden -> dummy reveal -> removed or persisted per module table.

## 7. Recommended Tests

- reveal trigger correctness,
- recon success/failure transitions,
- dummy marker behavior,
- direct-fire legal filtering under uncertain contacts,
- OAS behavior against contact-marked zones.

## 8. Validation Checklist

- [ ] FoW module is fully gated by scenario flag.
- [ ] Contact state transitions are finite-state and deterministic.
- [ ] Reveal logic is explicit and test-covered.
- [ ] Fire legality under FoW is not bypassed by generic action generators.
- [ ] Telemetry captures reveal events for replay analysis.
