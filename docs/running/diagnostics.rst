Engine Diagnostics
==================

The engine diagnostics system provides a **structured, policy‑agnostic
observation layer** over the tactical engine.

Its purpose is to characterize **what the engine makes possible** in
each situation, and **how those possibilities are used or avoided** by
agents, without interfering with gameplay.

Diagnostics are central to the study of **emergent coordination** and
**soft role allocation**, as they allow behavior to be analyzed without
imposing explicit role definitions or reward shaping.

Design principles
-----------------

The diagnostics system is designed according to the following principles:

- **Passive observation**  
  Diagnostics never influence engine state or agent decisions.

- **Engine‑centric focus**  
  Observations describe engine opportunities and risks, not agent internals.

- **Policy agnosticism**  
  The same diagnostics apply to RL and heuristic controllers.

- **Step‑level granularity**  
  Observations are collected at each engine activation step.

These principles ensure that diagnostics remain valid
across algorithms, curricula and experimental conditions.

Observed engine context
-----------------------

At each activation step, the diagnostics layer observes a structured
representation of the engine state.

This context encodes information such as:

- Availability of assault opportunities
- Availability of ranged attack opportunities
- Possibility of capturing victory points
- Availability of safe or risky movement options
- Presence of zone‑of‑control pressure
- Exposure to reaction fire risk

The diagnostic context describes **what the engine permits**, not what
the agent will choose to do.

Engine observation model
^^^^^^^^^^^^^^^^^^^^^^^^

.. graphviz::

   digraph diagnostics_context {
       rankdir=TB;
       node [shape=box, style="rounded,filled", fillcolor="#F0F7FF"];

       EngineState [label="Engine State"];
       StepContext [label="Step Engine Context"];
       Opportunities [label="Opportunities"];
       Risk [label="Risk Signals"];
       Decisions [label="Actions Taken / Avoided"];
       Aggregated [label="Aggregated Diagnostics"];

       EngineState -> StepContext;
       StepContext -> Opportunities;
       StepContext -> Risk;
       StepContext -> Decisions;
       Opportunities -> Aggregated;
       Risk -> Aggregated;
       Decisions -> Aggregated;
   }

This diagram highlights that diagnostics derive exclusively from
**engine state**, and that both opportunities and risks are observed
*prior* to any agent decision.

Opportunities versus decisions
-------------------------------

A central design feature of the diagnostics system is the distinction
between **opportunities** and **decisions**.

For example:

- An assault opportunity exists, regardless of whether the agent attacks
- A movement option exists, regardless of whether it is taken
- A risk is present, regardless of whether it is avoided

This separation allows analysis of questions such as:

- Is an agent aggressive or cautious?
- Are attacks avoided due to risk or lack of opportunity?
- Is stagnation caused by engine structure or policy behavior?

Such questions cannot be answered using outcome metrics alone.

Opportunity–decision separation
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. graphviz::

   digraph opportunity_decision {
       rankdir=LR;
       node [shape=box, style="rounded,filled", fillcolor="#FFF7E6"];

       Engine [label="Engine State"];
       Opportunity [label="Tactical Opportunity"];
       Risk [label="Associated Risk"];
       Decision [label="Agent Decision"];
       Outcome [label="Observed Action"];

       Engine -> Opportunity;
       Engine -> Risk;
       Opportunity -> Decision;
       Risk -> Decision;
       Decision -> Outcome;
   }

The diagram emphasizes that **absence of action does not imply absence
of opportunity**, a critical distinction for interpreting emergent
behavior.

Risk characterization
---------------------

The diagnostics system explicitly captures **risk signals** imposed by
the tactical engine.

Examples include:

- Average zone‑of‑control exposure
- Average reaction fire threat
- Frequency of high‑risk movement options

Risk is measured as a property of the **environmental configuration**,
not as a subjective agent perception.

This allows behavioral patterns to be interpreted relative to the
objective tactical landscape.

Derived diagnostic metrics
--------------------------

From step‑level observations, per‑game diagnostic summaries are derived.

These summaries include:

- Counts of available opportunities
- Counts of actions taken versus avoided
- Average and cumulative risk measures
- Ratios expressing opportunity utilization

Derived ratios are preferred over absolute counts, as they support
comparison across:

- Games of different length
- Different scenarios
- Different curriculum stages

Stalemate indicators
--------------------

A subset of derived metrics is used to characterize **tactical
stagnation**.

These include indicators such as:

- Low action‑to‑opportunity ratios
- High avoidance rates under persistent opportunity
- Sustained high risk with low decision throughput

Stalemate indicators are **diagnostic signals**, not failure criteria.

They allow the experimenter to determine whether stagnation arises from:

- Engine configuration
- Scenario geometry
- Emergent risk‑averse behavior
- Soft stabilization of agent roles

Relation to emergent behavior
-----------------------------

The diagnostics system is deliberately **role‑free**.

It does not label units as attackers, defenders or supports.
Instead, such roles are inferred indirectly from consistent patterns in:

- Opportunity usage
- Risk exposure
- Decision frequency

This makes diagnostics suitable for studying **soft role allocation**
as an emergent phenomenon rather than a predefined abstraction.

Output and persistence
----------------------

Diagnostics are aggregated and persisted per game as structured JSON.

Each diagnostic artifact is:

- Immutable once written
- Independent of training state
- Inspectable without running code

These artifacts form the empirical basis for
offline analysis, visualization and reporting.

Summary
-------

Engine diagnostics provide a principled, non‑intrusive way to observe
the tactical structure experienced by agents.

By focusing on opportunities, risks and utilization patterns,
the diagnostics layer enables the analysis of emergent coordination
and role behavior without embedding any role assumptions into
the engine or the learning process.
