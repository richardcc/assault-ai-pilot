Assault Environment Documentation
=================================

This documentation describes the **assault-env** project: a deterministic,
Gymnasium-compatible training environment built on top of the
``assault-engine`` tactical core.

The environment is designed for:

- Reinforcement learning via self-play
- Curriculum-based tactical training
- Deterministic simulation and evaluation
- Integration with perception-based agents

The environment does **not** implement game rules or mechanics.
All combat resolution is delegated to the underlying engine.

---

Contents
--------

.. toctree::
   :maxdepth: 2

   overview
   environment
   scenarios
   curriculum
   reward_design
   evaluation
   integration
