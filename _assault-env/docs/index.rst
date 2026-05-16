Assault Environment Documentation
=================================

This documentation describes the **assault-env** project: a deterministic,
Gymnasium-compatible reinforcement learning environment built on top of the
``assault-engine`` tactical core.

The environment is explicitly designed to support:

- Reinforcement learning via self-play and adversarial setups
- Curriculum-based tactical training
- Deterministic simulation and reproducible evaluation
- Integration with symbolic or perception-based agents

The environment deliberately **does not implement game rules or mechanics**.
All movement validation, combat resolution, and tactical constraints are fully
delegated to the underlying **assault-engine** core.

This separation ensures:

- Clear responsibility boundaries
- Engine reusability outside reinforcement learning
- Stable and interpretable learning signals
- Deterministic debugging via replay

---

Contents
--------

.. toctree::
   :maxdepth: 2
   :caption: Documentation

   overview
   environment
   scenarios
   curriculum
   reward_design
   evaluation
   integration