from .turn_buffer import TurnBuffer
from .movement_renderer import MovementRenderer
from .combat_renderer import CombatRenderer
from .map_renderer import MapRenderer
from .deployment_renderer import DeploymentRenderer
from .unit_formatter import UnitFormatter


class ConsoleObserver:
    """
    EventBus observer.

    Responsibilities:
    - React to domain events emitted by the engine.
    - Delegate presentation to specialized renderers.
    - Maintain a coherent, human-readable console output.

    Presentation ONLY:
    - No game logic
    - No training logic
    - No interpretation of combat mechanics
    """

    def __init__(self, rl_side: str | None = None):
        self.rl_side = rl_side

        self.unit_formatter = UnitFormatter()
        self.turns = TurnBuffer(self.unit_formatter)

        self.move = MovementRenderer(self.turns)
        self.combat = CombatRenderer(self.turns, self.unit_formatter)

        self.map = MapRenderer()
        self.deploy = DeploymentRenderer()

        self._map_rendered_once = False

    def __call__(self, event: dict):
        event_type = event.get("type")
        payload = event.get("payload", {})

        # ---------------- RESET ----------------
        if event_type == "RESET":
            self.turns.reset()
            self.deploy.reset(payload)
            self._map_rendered_once = False

        # ---------------- UNIT LOADED ----------------
        elif event_type == "UNIT_LOADED":
            self.deploy.on_unit_loaded(payload)

        # ---------------- MAP STATE ----------------
        elif event_type == "MAP_STATE":
            self.map.update_state(payload)
            self.unit_formatter.update_units(payload.get("units", []))

            if not self._map_rendered_once:
                self.deploy.maybe_print()
                self._map_rendered_once = True

        # ---------------- ACTION ----------------
        elif event_type == "ACTION":
            self.turns.on_action(payload)

        # ---------------- UNIT MOVED ----------------
        elif event_type == "UNIT_MOVED":
            self.move.on_unit_moved(payload)

        # ---------------- ACTION EFFECT ----------------
        elif event_type == "ACTION_EFFECT":
            self.combat.on_action_effect(payload)

        # ---------------- TURN END ----------------
        elif event_type == "TURN_END":
            self.turns.close_turn()
            self.map.render(payload.get("turn"))

        # ---------------- MATCH END ----------------
        elif event_type == "MATCH_END":
            result = payload.get("result")
            winner = payload.get("winner")
            reason = payload.get("reason", "scenario_end")
            turn = payload.get("turn")

            self.turns.add_line("")

            # -------- DRAW --------
            if result != "victory" or not winner:
                self.turns.add_line("🤝 MATCH FINISHED — DRAW")
                self.turns.add_line(f"    Ended at turn: {turn}")

            # -------- VICTORY --------
            else:
                is_hrl = self.rl_side is not None and winner == self.rl_side
                winner_type = "HRL" if is_hrl else "HEURISTIC"

                self.turns.add_line(
                    f"🏆 MATCH FINISHED — {winner_type} VICTORY ({winner})"
                )

                self.turns.add_line(
                    f"    Winner: {winner} ({winner_type.lower()}-controlled)"
                )

                if self.rl_side:
                    loser = "GE" if winner == "US" else "US"
                    loser_type = "heuristic" if is_hrl else "hrl-controlled"
                    self.turns.add_line(
                        f"    Loser:  {loser} ({loser_type})"
                    )

                self.turns.add_line(f"    Ended at turn: {turn}")

            # -------- REASON --------
            if reason:
                pretty_reason = reason.replace("_", " ").capitalize()
                self.turns.add_line(f"    Reason: {pretty_reason}")

            # Force final print
            self.turns.close_turn()