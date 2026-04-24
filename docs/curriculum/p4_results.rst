P4 – Symmetric Engagement (2 vs 2)
=================================

This document reports the results of **P4**, the first fully symmetric
scenario in the assault‑env curriculum.

P4 represents the transition from tactical optimization to
strategic interaction, where no trivial or universally safe policy
dominates.

---

Scenario Description
--------------------

P4 introduces a **2 vs 2 symmetric engagement** under the same rules,
terrain and reward structure used in previous stages.

Key properties:

- Two friendly units vs two enemy units
- Identical unit types and strength
- Identical movement and combat rules
- No reward shaping
- No hyperparameter changes

All complexity arises purely from **symmetry and interaction**.

---

Training Configuration
----------------------

- Algorithm: Proximal Policy Optimization (PPO)
- Policy: ``MultiInputPolicy``
- Observation space: P3 (global force awareness)
- Total training steps: ~200,000
- Environment: deterministic dynamics

The PPO configuration is unchanged from P1–P3 to preserve
comparability across curriculum stages.

---

Training Dynamics
-----------------

During the early phase (0–40k steps), the agent exhibits:

- High exploration (entropy remains high)
- Large variability in episode outcomes
- No immediate aggressive greedy policy

This behavior is expected due to the absence of dominant actions
in symmetric environments.

In the mid phase (40k–120k steps):

- PPO remains stable
- Policy gradients remain significant
- The value function becomes partially predictive

In the final phase (~200k steps):

- Policy and value stabilize
- Explained variance converges to a positive range
- Exploration remains present but controlled

---

Final Training Metrics
----------------------

At convergence, representative metrics include:

- Explained variance: ~0.35–0.40
- Entropy loss: moderately high (no policy collapse)
- Stable KL divergence and clipping behavior
- Non‑zero policy gradient

These signals indicate **functional convergence** rather than overfitting.

---

Behavioral Evaluation
---------------------

Evaluation reveals distinct behavior between deterministic and
stochastic policy execution:

Deterministic (greedy) evaluation:
- Conservative but consistent behavior
- No suicidal aggression
- Emphasis on safety in ambiguous situations

Stochastic (non‑greedy) evaluation:
- Selective assaults
- Intermittent pressure on victory points
- Reduced average distance to enemies
- Diverse trajectories across episodes

This divergence is expected and indicates that
aggressive strategies exist within the policy distribution
without being forced as dominant actions.

---

Interpretation
--------------

In symmetric strategic environments, a single optimal greedy policy
often does not exist.

P4 demonstrates that the agent learns to:

- Balance risk versus safety
- Maintain adaptability rather than rigid patterns
- Avoid degenerate solutions such as permanent evasion

The coexistence of conservative greedy behavior and stochastic
aggression is interpreted as **strategic maturity**, not indecision.

---

Curriculum Conclusion
---------------------

P4 successfully achieves its design objectives:

- Eliminates trivial safe policies
- Preserves learning stability
- Enables strategic interaction
- Establishes a non‑degenerate multi‑unit setting

P4 is therefore **frozen** as a completed curriculum stage.

---

Extension: Implicit Roles (P4‑B)
--------------------------------

Following P4 convergence, an optional extension (P4‑B) explores the
emergence of **implicit coordination roles** without introducing
explicit role labels or reward shaping.

P4‑B retains the P4 scenario unchanged, adding only minimal
ally‑centric observations (e.g., distance to ally, relative strength).

This extension investigates whether role‑like behavior (e.g.,
pressure vs support) can emerge naturally from relational information
in symmetric environments.

Results from P4‑B are documented separately as an exploratory analysis
and do not alter the frozen status of P4.