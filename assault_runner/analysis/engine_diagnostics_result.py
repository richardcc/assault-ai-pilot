from dataclasses import dataclass
from typing import List, Dict


@dataclass
class EngineDiagnosticsResult:
    total_steps: int

    assaults_taken: int
    ranged_attacks_taken: int
    moves_taken: int

    assault_rate: float
    ranged_attack_rate: float
    move_rate: float

    @classmethod
    def from_steps(cls, steps: List[Dict]) -> "EngineDiagnosticsResult":
        """
        Build diagnostics strictly from OBSERVED actions.
        No inference, no assumed opportunities.
        """

        total_steps = len(steps)

        assaults_taken = sum(s.get("assaults_taken", 0) for s in steps)
        ranged_taken = sum(s.get("ranged_attacks_taken", 0) for s in steps)
        moves_taken = sum(s.get("moves_taken", 0) for s in steps)

        denom = max(1, total_steps)

        return cls(
            total_steps=total_steps,
            assaults_taken=assaults_taken,
            ranged_attacks_taken=ranged_taken,
            moves_taken=moves_taken,
            assault_rate=assaults_taken / denom,
            ranged_attack_rate=ranged_taken / denom,
            move_rate=moves_taken / denom,
        )

    def to_dict(self) -> Dict:
        return {
            "total_steps": self.total_steps,
            "assaults_taken": self.assaults_taken,
            "ranged_attacks_taken": self.ranged_attacks_taken,
            "moves_taken": self.moves_taken,
            "action_rates": {
                "assault": self.assault_rate,
                "ranged_fire": self.ranged_attack_rate,
                "move": self.move_rate,
            },
        }