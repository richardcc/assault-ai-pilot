from .data_model import DecisionRow, EpisodeRow, OutcomeRow


class EvaluationLogger:

    def __init__(self, experiment_id: str):
        self.experiment_id = experiment_id

        self.episodes = []
        self.decisions = []
        self.outcomes = []

    # -------------------------------------------------
    # DECISION LOG (L3 + L2 + CONTEXT)
    # -------------------------------------------------
    def log_decision(self, episode_id, turn, unit_id, hrl_payload, context):

        if hrl_payload is None:
            return

        context = context or {}

        self.decisions.append(
            DecisionRow(
                experiment_id=self.experiment_id,
                episode_id=episode_id,
                turn=turn,
                unit_id=unit_id,

                # HRL levels
                l3_strategy=hrl_payload.get("formation"),
                l2_option=hrl_payload.get("option"),
                attack_mode=hrl_payload.get("attack_mode"),

                # Model outputs
                confidence=hrl_payload.get("policy_info", {}).get("confidence", 0.0),
                value_estimate=hrl_payload.get("policy_info", {}).get("value_estimate", 0.0),

                # Context
                enemy_distance=context.get("enemy_distance"),
                terrain=context.get("terrain"),
                hp=context.get("hp", 0),
            )
        )

    # -------------------------------------------------
    # OUTCOME LOG (SAFE VERSION)
    # -------------------------------------------------
    def log_outcome(self, episode_id, turn, unit_id, action, result):

        # ✅ result is NOT a dict (it's reward)
        # so we DO NOT interpret it

        self.outcomes.append(
            OutcomeRow(
                experiment_id=self.experiment_id,
                episode_id=episode_id,
                turn=turn,
                unit_id=unit_id,

                action=action,

                # ⚠️ TEMPORAL (safe)
                result=None,
                damage=0,
                kills=0,
                unit_alive_after=True,
            )
        )

    # -------------------------------------------------
    # EPISODE (MACRO)
    # -------------------------------------------------
    def log_episode(self, episode_id, summary):

        summary = summary or {}

        self.episodes.append(
            EpisodeRow(
                experiment_id=self.experiment_id,
                episode_id=episode_id,

                winner=summary.get("winner"),
                final_vp=summary.get("vp"),
                steps=summary.get("steps"),

                rl_damage=summary.get("rl_damage", 0),
                enemy_damage=summary.get("enemy_damage", 0),
            )
        )