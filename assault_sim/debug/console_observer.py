# assault_sim/debug/console_observer.py

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

    Design rules:
    - Presentation only (NO domain logic).
    - Listens to the real domain events.
    """

    def __init__(self):
        self.unit_formatter = UnitFormatter()
        self.turns = TurnBuffer(self.unit_formatter)

        self.move = MovementRenderer(self.turns)
        self.combat = CombatRenderer(self.turns)
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

            # Initial deployment printed once
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
            if payload.get("action") == "CloseCombat":
                self.combat.on_close_combat_effect(payload)

        # ---------------- TURN END ----------------
        elif event_type == "TURN_END":
            # ✅ Correct, encapsulated turn closure
            self.turns.close_turn()

            # Render map AFTER the turn is fully closed
            self.map.render(payload.get("turn"))