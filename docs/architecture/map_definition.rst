Map Definition
==============

This document defines the **map model used by the Assault game engine**.

The map is a **static semantic structure** that describes space, terrain,
and connectivity. It contains no execution logic and no presentation data.

---

1. Role of the Map in the Engine
--------------------------------

The map defines **where the simulation takes place**.

It provides:

- spatial structure
- movement topology
- terrain semantics

The map is consumed by the engine to evaluate:

- movement legality
- combat modifiers
- line-of-sight
- positional relationships

The map itself never changes during execution.

---

2. Map Composition Model
------------------------

The Assault map is **not defined as a monolithic grid**.

Instead, it is composed from **predefined map pieces**.

Each map piece is reusable and can be combined with others
to form different battlefields.

This composition-based approach enables:

- reuse
- modular scenario design
- consistent terrain semantics

---

3. Map Pieces
-------------

A map piece is a **static spatial template**.

Each map piece:

- contains a fixed arrangement of hexes
- defines terrain type per hex
- defines adjacency and local topology

Map pieces contain **no unit information** and no scenario-specific logic.

---

4. Hex Model
------------

The hex is the **atomic spatial element** of the map.

Each hex defines:

- a unique coordinate within the map
- a terrain type
- adjacency to neighboring hexes

Hexes are immutable during execution.

---

5. Terrain Semantics
--------------------

Each hex carries exactly **one terrain type**.

Terrain defines **semantic properties**, not visuals.

Typical terrain semantics include:

- movement cost
- combat modifiers
- cover effects
- line-of-sight blocking or attenuation

Terrain semantics are evaluated exclusively by engine rules.

---

6. Map Assembly into a Scenario
-------------------------------

A scenario selects and assembles map pieces to construct
the complete battlefield.

During scenario initialization:

- map pieces are selected
- hexes are placed into a global coordinate system
- terrain information is preserved verbatim

Once assembly is complete, the scenario produces a **final immutable map**
that is used for the entire execution.

---

7. Determinism and Reusability
------------------------------

Map definitions are:

- deterministic
- immutable
- reusable across scenarios

The same sequence of map pieces assembled in the same way
will always produce the same map.

This guarantees reproducibility and consistent rule evaluation.

---

8. Conceptual Model
-------------------

The relationship between map pieces, hexes, and terrain
can be summarized as follows:

.. graphviz::

   digraph MapModel {
       rankdir=LR;

       MapPiece [shape=box];
       Hex [shape=box];
       Terrain [shape=box];
       Map [shape=box];
       Scenario [shape=box];

       MapPiece -> Hex [label="contains"];
       Hex -> Terrain [label="defines"];
       MapPiece -> Map [label="assembled into"];
       Scenario -> Map [label="uses"];
   }
