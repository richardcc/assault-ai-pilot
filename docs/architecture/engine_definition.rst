Scenario and Map Canonical Model
================================

This document is generated automatically from the canonical model package
``assault_model``.

The content of this document is derived directly from the source code.
No manual duplication of structure is allowed.

---

Scenario model
--------------

.. automodule:: assault_model.core.scenario
   :members:
   :undoc-members:
   :show-inheritance:

---

Map model
---------

.. automodule:: assault_model.map.map
   :members:
   :undoc-members:
   :show-inheritance:

---

Map composition
---------------

.. automodule:: assault_model.map.map_piece
   :members:

.. automodule:: assault_model.map.hex
   :members:

.. automodule:: assault_model.map.terrain
   :members:

---

Structural relationships (derived)
----------------------------------

.. graphviz::

   digraph CanonicalModel {
       rankdir=TB;

       Scenario -> Map;
       Map -> MapPiece;
       MapPiece -> Hex;
       Hex -> Terrain;
   }