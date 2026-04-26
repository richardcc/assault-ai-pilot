Rationale Flow
==============

This document describes how **rationales** flow through the system,
from neural computation to persistent replay data and offline analysis.

The key design goal is to ensure **causal alignment** between:

- the acting unit
- the executed action
- the learned rationale

High-Level Flow
---------------

The rationale flow for every decision step is:

::

   observation
        ↓
   policy.forward(observation)
        ↓
   rationale logits (tensor)
        ↓
   argmax → rationale_id (int)
        ↓
   env.step(action)
        ↓
   info["unit_id"]  (acting unit)
        ↓
   snapshot(state, decision)
        ↓
   Replay (json)
        ↓
   Offline Analysis

Key Properties
--------------

- Rationale logits exist **only during policy.forward()**
- Stable-Baselines3 does NOT expose them via ``model.predict()``
- Rationales are extracted **at decision time**
- Rationales are never inferred post-hoc
- The environment is the only component that knows which unit acted

Design Choice
-------------

Rationales are captured during **manual step-by-step execution**.
The system deliberately avoids using ``model.learn()`` or callbacks.

Reason:

- Training loops do not expose per-step decisions
- Callbacks do not provide reliable actor–action alignment
- Manual execution guarantees full control over decision capture

Layer Responsibilities
----------------------

Policy
~~~~~~
- computes rationale logits during ``forward()``
- does not store or serialize them
- remains stateless with respect to explanation

RL Runner
~~~~~~~~~
- executes the policy step by step
- calls ``policy.forward()`` for rationale logits
- calls ``policy.predict()`` for actions
- reads ``info["unit_id"]`` from the environment
- assembles decision records

Environment
~~~~~~~~~~~
- decides which unit acts each turn
- applies the chosen action
- emits the acting unit via ``info["unit_id"]``

Replay System
~~~~~~~~~~~~~
- stores decisions exactly as recorded
- does not interpret actions or rationales
- represents ground truth for analysis

Offline Analysis
~~~~~~~~~~~~~~~~
- reads stored rationale identifiers
