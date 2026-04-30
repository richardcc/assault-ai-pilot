Victory Points Rules
===================

This file defines the normative rules governing Victory Point occupation,
control, and scoring in Assault.

Each rule is uniquely identified and traceable to concrete runtime classes
and files.

VP-R01 — Scenario-Defined Objectives
------------------------------------

**Rule ID:** VP-R01

Victory Points are defined by the scenario.

- Each Victory Point is associated with one or more hex coordinates.
- Each Victory Point has a fixed value, defined per scenario.

**Code References:**

- ``assault_model.core.victory_conditions.VictoryConditions``
- ``assault_model.core.victory_point.VictoryPoint``


VP-R02 — End-of-Turn Evaluation
-------------------------------

**Rule ID:** VP-R02

Victory Points are evaluated **only at the end of a turn**.

- Entering a Victory Point hex never grants points immediately.
- All scoring is deferred until turn resolution.
- The canonical evaluation point is ``GameState.end_turn``.

**Code References:**

- ``assault_model.core.game_state.GameState.end_turn``
- ``assault_model.core.vp_tracker.VictoryPointTracker.apply_turn``


VP-R03 — Hex Control as Prerequisite
------------------------------------

**Rule ID:** VP-R03

Victory Points are awarded based on **resolved hex control**, not unit
movement.

- Hex control is resolved during turn finalization.
- Control resolution consolidates unit presence into a single ownership
  state.
- The Victory Points subsystem does not inspect units directly.

**Code References:**

- ``assault_model.core.game_state.GameState.end_turn``
- ``assault_model.map.hex_state.HexState``
- ``assault_model.map.hex_ownership.HexOwnership``


VP-R04 — Exclusive Occupation
-----------------------------

**Rule ID:** VP-R04

A Victory Point hex awards points only if controlled by **exactly one side**.

- If no units are present on the hex, no Victory Points are awarded.
- If units from multiple sides are present, the hex is considered contested
  and awards no points.

**Code References:**

- ``assault_model.map.hex_ownership.HexOwnership.NONE``
- ``HexOwnership.SIDE_A``
- ``HexOwnership.SIDE_B``


VP-R05 — Contested Hexes
------------------------

**Rule ID:** VP-R05

A contested hex never awards Victory Points.

- Contest status is resolved during turn finalization.
- Contest resolution does not persist beyond turn resolution.

**Code References:**

- ``assault_model.map.hex_state.HexState.contested``
- ``assault_model.core.game_state.GameState.end_turn``


VP-R06 — Victory Point Awarding
-------------------------------

**Rule ID:** VP-R06

If a Victory Point hex is controlled by a single side at end of turn:

- That side gains the Victory Point value defined by the scenario.
- Victory Points may be awarded repeatedly across multiple turns if control
  is maintained.
- Victory Point values are derived from the scenario definition.

**Code References:**

- ``assault_model.core.vp_tracker.VictoryPointTracker.apply_turn``
- ``assault_model.core.vp_tracker.VictoryPointTracker.score``
- ``assault_model.core.victory_point.VictoryPoint.per_turn``


VP-R07 — Campaign Consistency
-----------------------------

**Rule ID:** VP-R07

Victory Point mechanics are consistent across all campaigns.

- Scenarios may vary the number and value of Victory Points.
- Scenarios may define victory thresholds.
- The occupation and scoring mechanism remains unchanged.

**Code References:**

- ``VictoryConditions.from_json``
- Scenario JSON definitions


VP-R08 — Separation from Movement
---------------------------------

**Rule ID:** VP-R08

Victory Point scoring is independent from movement rules.

- Movement positions units on the map.
- Victory Point evaluation depends solely on resolved hex control.

**Code References:**

- ``assault_model.actions.movement.MoveAction``
- ``assault_model.core.game_state.GameState.end_turn``