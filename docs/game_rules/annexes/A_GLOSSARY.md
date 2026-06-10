si, tiene que llegar al nivel por jeemplo de rsolcuion ed combates ocn dados y sus colores asi ocmo las tabals de modificaciones 
# Annex A - Glossary (Implementation-Oriented)

## Core Terms

- **LOS (Line of Sight)**: geometric visibility relation between attacker and target.
- **Hindrance**: LOS degradation element that can reduce or block effective fire.
- **Spotting**: detection mechanism determining whether effective targeting is possible.
- **AoI (Area of Impact)**: impacted hex set for blasts/indirect/support effects.

## Unit-State Terms

- **Suppressed**: degraded action/defense condition affecting legality and modifiers.
- **Fallback**: forced retreat state with activation/combat constraints.
- **Half-Strength**: reduced combat capability state.
- **Activated**: unit already consumed activation opportunity in current cycle.

## Fire-Support Terms

- **TAS**: Tactical Air Support, resolved through request/AA/strike sequence.
- **OAS**: Off-board Artillery Support with planning and delayed execution flow.
- **FFE**: Fire For Effect mode in OAS.

## Objective and Campaign Terms

- **VP Hex / Objective Hex**: scenario victory-related location.
- **Objective Control**: side ownership state of objective hex.
- **Troop Register**: campaign persistent manpower/force accounting.

## Optional Module Terms

- **FoW**: Fog of War optional system.
- **Contact Marker**: marker representing uncertain enemy information.
- **Dummy Contact**: deceptive marker without real unit backing.

## Engine Terms

- **Legal Action Set**: all actions valid for unit/state/phase context.
- **Rule Precedence**: deterministic order of conflicting rule families.
- **Resolution Contract**: explicit step-by-step rule execution path.
