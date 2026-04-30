ASSAULT – Game Model (Living Document)
=====================================

8. Game Flow: Rounds, Turns, and Initiative
--------------------------------------------

8.1 Temporal Structure
~~~~~~~~~~~~~~~~~~~~~~

The game progresses in a strict, deterministic hierarchy::

    Game
        Rounds
            Turns
                Phases
                    Actions and Reactions

Only one side is active at any time.

----

8.2 Initiative
~~~~~~~~~~~~~~

ASSAULT uses an **initiative-driven flow** to determine the active side.

Initiative defines:

- which side becomes active
- the order of turns within a round

At any given moment, exactly one side holds initiative.

----

8.3 Active Side
~~~~~~~~~~~~~~~

The **active side** may voluntarily declare actions during its turn.

Non-active sides may only respond via automatic reactions governed by rules.

Initiative passes according to scenario-defined turn order.

----

9. Action Model and Turn Constraints
------------------------------------

9.1 Action Types
~~~~~~~~~~~~~~~~

During a turn, units may perform different **types of actions** defined by the ruleset.

Action categories:

- Movement actions
- Combat actions
- Combined actions
- Passive actions (wait / pass)

Actions express player intent; outcomes are determined by rules.

----

9.2 Per-Turn Action Availability
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Action availability depends on:

- unit type and status
- current phase
- actions already taken by the unit during the turn
- current game state (terrain, visibility, adjacency)

Not all actions are always available.

----

9.3 Action Legality Rules
~~~~~~~~~~~~~~~~~~~~~~~~~

Rules determine whether an action is legal.

Legality may depend on:

- remaining action capacity for the turn
- incompatible action combinations
- terrain and position
- visibility and line of sight

Illegal actions cannot be executed.

----

9.4 Reactions
~~~~~~~~~~~~~

Reactions are automatic responses triggered by rules.

Characteristics:

- not player-declared
- may interrupt or respond to actions
- resolved deterministically

Examples include reaction fire and opportunity attacks.

----

9.5 Line of Sight (LOS)
~~~~~~~~~~~~~~~~~~~~~~~

**Line of Sight (LOS)** is a core spatial constraint that affects action legality
and reaction triggering.

LOS:

- is evaluated against the current hex map
- depends on terrain, elevation, and blocking elements
- may change dynamically due to movement actions

Action interaction:

- Combat actions typically require LOS to the target
- Some movement actions may deliberately break or expose LOS
- Combined actions are constrained by LOS before and after movement

Reaction interaction:

- Certain reactions (e.g., reaction fire) require valid LOS at trigger time
- LOS is evaluated at the moment of the triggering event, not retroactively

LOS evaluation is handled by dedicated spatial/visibility rules and is not
embedded in action definitions.

----

10. Activation-Based Game Model
-------------------------------

ASSAULT uses an **activation-based game flow** rather than a pure side-based
turn model.

10.1 Activation Principle
~~~~~~~~~~~~~~~~~~~~~~~~~

- The initiative system selects the **next unit to activate**
- Only one unit is active at a time
- An activated unit may perform **exactly one voluntary action** (or pass)
- After resolution, the unit becomes exhausted for the current round

This model applies equally to human and AI-controlled play.

----

10.2 Activation Cycle
~~~~~~~~~~~~~~~~~~~~~

The engine executes the following activation cycle:

#. Initiative selects next unit
#. Active unit declares one action
#. Engine validates legality (LOS, ZOC, terrain, state)
#. Engine executes the action
#. Automatic reactions may occur
#. GameState is updated
#. Unit is marked as activated

When no units remain available, the round ends.

----

11. Action–Activation Contract
------------------------------

An **Action** is always executed in the context of a unit activation.

Key constraints:

- Actions are atomic
- One action per activation
- Action availability depends on the current GameState
- Action legality is determined exclusively by rules

The engine exposes the action space implicitly through legality checks.

----

12. Conceptual Diagrams
----------------------

12.1 High-Level Game Flow
~~~~~~~~~~~~~~~~~~~~~~~~

.. mermaid::

    graph TD
        Game --> Round
        Round --> ActivationCycle
        ActivationCycle --> UnitActivation
        UnitActivation --> Action
        Action --> Engine
        Engine --> GameState
        GameState --> ActivationCycle

----

12.2 Action and Constraint Model
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. mermaid::

    graph TD
        UnitActivation --> Action
        Action --> MovementAction
        Action --> CombatAction
        Action --> CombinedAction
        Action --> PassiveAction
        MovementAction -->|triggers| Reaction
        CombatAction -->|requires| LOS
        CombinedAction -->|split| MovementAction
        Action -->|validated by| Rules
        Rules --> LOS
        Rules --> ZoneOfControl
        Rules --> Terrain

----

12.3 System Responsibility Boundary
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. mermaid::

    graph TD
        Agent -->|selects| Action
        Action --> Engine
        Engine -->|resolves| GameState
        GameState --> Agent
        Engine --> Rules
        Rules --> LOS
        Rules --> Reactions

----

13. Document Status
-------------------

- **Version:** 1.2
- **Scope:** Activation-based model, actions, LOS, diagrams
- **Stability:** Stable (conceptual)
- **Next planned extension:** CampaignState and Scenario Outcomes