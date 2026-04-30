from dataclasses import dataclass


@dataclass
class Target:
    q: int
    r: int
    score: float


class VictoryPointBrick:
    def score_targets(self, state, unit) -> list:
        targets = []

        vp_tracker = getattr(state, "vp_tracker", None)
        if not vp_tracker or not vp_tracker.conditions:
            return targets

        # API pública ya validada por tu código existente
        for q, r in vp_tracker.conditions.get_positions():
            targets.append(Target(q=q, r=r, score=100.0))

        return targets