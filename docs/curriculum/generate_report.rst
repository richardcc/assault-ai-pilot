Analysis Report Generation
==========================

The report generation module aggregates analysis outputs
into **human‑readable summaries**.

Purpose
-------

It produces structured reports that integrate:

- behavioral statistics
- rationale distributions
- qualitative interpretations

These reports are the **primary artefacts** used for evaluation,
discussion, and presentation.

---

Inputs
------

- outputs from behavior_stats
- outputs from rationale_stats
- evaluation metadata (episodes, scenario, policy name)

---

Outputs
-------

- textual reports
- tables of aggregated metrics
- structured summaries suitable for documentation

Reports are written to:
- analysis_outputs/

---

Role in the System
------------------

Report generation:

- occurs after training
- does not affect policies
- does not modify data
- does not execute environments

It is the final step in the analysis pipeline.

---

Interpretation Boundary
-----------------------

The report interprets results but MUST:

- clearly separate observation from explanation
- avoid normative claims of optimality
- remain scenario‑specific