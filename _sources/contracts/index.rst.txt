System Contracts
================

This section defines **explicit contracts** between system components.

A contract specifies:
- what a component is responsible for
- what information it is allowed to produce
- what information it must never infer or reconstruct

Contracts exist to prevent:

- responsibility leakage between layers
- post-hoc inference bugs
- duplicated or ambiguous logic
- violations of causal alignment

All contracts in this section are normative.
Implementations are expected to follow them exactly.

.. toctree::
   :maxdepth: 1

   rationale