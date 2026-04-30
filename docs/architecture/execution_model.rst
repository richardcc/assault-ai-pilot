Execution Model
===============

This document defines **how the engine runs at runtime**.

Entry Point
-----------

Execution begins with a scenario.

From the scenario, the engine constructs the initial game state.

Execution Loop
--------------

The engine operates as a **state transition loop**:

1. current game state
2. incoming action
3. rule evaluation
4. next game state

This loop continues until termination conditions are met.

Runtime Flow
------------

.. graphviz::

   digraph ExecutionLoop {
       rankdir=TB;

       GameState -> Action;
       Action -> Engine;
       Engine -> GameState;
   }

The engine is the only component allowed to modify the game state.
``