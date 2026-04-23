"""
Assault action orchestration.

This module implements the game rule for resolving a full assault
between two adjacent units, potentially consisting of multiple
close combat rounds, including post-assault consequences such as
retreat and advance.
"""

from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Tuple
import random

from assault.core.unit import Unit
from assault.core.combat.close_combat import (
    CloseCombatResolver,
    CombatResult,
)


class AssaultOutcome(Enum):
    """
    Final outcome of an assault action.
    """
    ATTACKER_ELIMINATED = auto()
    DEFENDER_ELIMINATED = auto()
    BOTH_ELIMINATED = auto()
    DEFENDER_RETREATS = auto()
    STALEMATE = auto()


@dataclass
class AssaultReport:
    """
    Report describing the full resolution of an assault.
    """
    rounds: List[CombatResult]
    outcome: AssaultOutcome
    defender_retreats: bool
    attacker_advances: bool


class AssaultAction:
    """
    Orchestrates a full assault between two units.

    The assault consists of one or more close combat rounds resolved
    by the CloseCombatResolver. This class applies higher-level rules
    such as retreat and advance, but does not directly move units
    on the map.
    """

    def __init__(
        self,
        attacker: Unit,
        defender: Unit,
        rng: random.Random | None = None,
        max_rounds: int = 3,
    ) -> None:
        self.attacker = attacker
        self.defender = defender
        self.rng = rng or random.Random()
        self.max_rounds = max_rounds
        self.resolver = CloseCombatResolver(self.rng)

    def can_continue(self) -> bool:
        """
        Returns True if both units are still alive.
        """
        return self.attacker.is_alive() and self.defender.is_alive()

    def resolve(self) -> AssaultReport:
        """
        Resolves the full assault action.
        """
        rounds: List[CombatResult] = []

        for _ in range(self.max_rounds):
            if not self.can_continue():
                break

            result = self.resolver.resolve(self.attacker, self.defender)
            rounds.append(result)

        outcome, retreat, advance = self.determine_post_assault_state(rounds)

        return AssaultReport(
            rounds=rounds,
            outcome=outcome,
            defender_retreats=retreat,
            attacker_advances=advance,
        )

    def determine_post_assault_state(
        self,
        rounds: List[CombatResult],
    ) -> Tuple[AssaultOutcome, bool, bool]:
        """
        Determines retreat and advance after the assault.

        Returns:
            (outcome, defender_retreats, attacker_advances)
        """
        attacker_alive = self.attacker.is_alive()
        defender_alive = self.defender.is_alive()

        any_hits = any(
            r.attacker_hits > 0 or r.defender_hits > 0
            for r in rounds
        )

        # --- Elimination cases ---
        if attacker_alive and not defender_alive:
            return (
                AssaultOutcome.DEFENDER_ELIMINATED,
                False,
                True,
            )

        if defender_alive and not attacker_alive:
            return (
                AssaultOutcome.ATTACKER_ELIMINATED,
                False,
                False,
            )

        if not attacker_alive and not defender_alive:
            return (
                AssaultOutcome.BOTH_ELIMINATED,
                False,
                False,
            )

        # --- No pressure at all: stalemate ---
        if not any_hits:
            return (
                AssaultOutcome.STALEMATE,
                False,
                False,
            )

        # --- Pressure without elimination: defender retreats ---
        return (
            AssaultOutcome.DEFENDER_RETREATS,
            True,
            True,
        )