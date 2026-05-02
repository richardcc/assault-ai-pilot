# assault_sim/sim_env.py
#
# Simulation environment.
#
# RESPONSABILIDADES:
# - Cargar catálogos y escenario
# - Crear GameState y RuntimeGameState
# - Emitir EVENTOS DE OBSERVABILIDAD mediante EventBus
# - Decidir TURN_END y MATCH_END
#
# NO HACE:
# - No imprime gameplay directamente
# - No renderiza
# - No mezcla observabilidad con trazas
#
# NOTAS IMPORTANTES:
# - Observabilidad = EventBus + Observers
# - Trazas de desarrollo = _trace() + ASSAULT_DEBUG_TRACE
# - Son DOS SALIDAS distintas y no se mezclan

import json
import os

from assault_sim.config.config_loader import SimConfig
from assault_model.units.catalog_loader import load_unit_catalog
from assault_model.map.map_piece_loader import load_map_piece_catalog
from assault_model.core.scenario_loader import load_scenario
from assault_model.state.game_state import GameState
from assault_model.runtime.game_state_runtime import RuntimeGameState
from assault_model.actions.action_catalog import ActionCatalog
from assault_model.actions.status import WaitAction
from assault_sim.debug.debug_config import DebugConfig
from assault_sim.debug.event_bus import EventBus


# -------------------------------------------------
# DESARROLLO / DEBUG (NO OBSERVABILIDAD)
# -------------------------------------------------
# Esta variable SOLO controla trazas internas para desarrollador.
# NO controla EventBus.
# NO afecta a observers.
# NO afecta al gameplay.
DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


def _trace(tag: str, **data):
    """
    Trazas de desarrollo.
    - Se imprimen SOLO si ASSAULT_DEBUG_TRACE=1
    - NO usan EventBus
    - NO forman parte de la observabilidad
    """
    if not DEBUG_TRACE:
        return
    payload = " ".join(f"{k}={v}" for k, v in data.items())
    print(f"[TRACE][{tag}] {payload}")


class SimEnv:
    """
    High-level simulation environment.

    ESTA CLASE ES PURO CONTROL.

    - Coordina runtime
    - Emite eventos de observabilidad
    - NO imprime gameplay
    - NO renderiza mapas
    - NO decide acciones
    """

    def __init__(self, config: SimConfig, debug_config: DebugConfig | None = None):
        self.config = config
        self.debug_config = debug_config or DebugConfig(enabled=False)

        # ------------------------------
        # EVENT BUS (OBSERVABILIDAD)
        # ------------------------------
        # El EventBus EXISTE o NO existe únicamente según debug_config.enabled,
        # exactamente como estaba antes.
        #
        # Importante:
        # - Si no hay EventBus, NO hay observabilidad.
        # - Esto NO tiene relación con ASSAULT_DEBUG_TRACE.
        self.event_bus = EventBus() if self.debug_config.enabled else None

        self.scenario = None
        self.game_state = None
        self.runtime = None
        self.player_config: dict[str, dict] = {}

    # -------------------------------------------------
    # RESET
    # -------------------------------------------------
    def reset(self):
        """
        Reinicia completamente la simulación:
        - Carga catálogos
        - Carga escenario
        - Crea GameState y Runtime
        - Emite eventos RESET / UNIT_LOADED / MAP_STATE
        """

        root = self.config.data_root

        unit_catalog = load_unit_catalog(root / self.config.unit_catalog)
        map_catalog = load_map_piece_catalog(root / self.config.map_piece_catalog)

        scenario_path = (
            root
            / self.config.scenario_folder
            / f"{self.config.scenario_name}.json"
        )

        self.scenario = load_scenario(scenario_path, unit_catalog, map_catalog)
        self.game_state = GameState.from_scenario(self.scenario)
        self.runtime = RuntimeGameState(self.game_state)

        # Configuración de controladores (si existe)
        env_config_path = root / "env_config.json"
        if env_config_path.exists():
            with open(env_config_path, "r", encoding="utf-8") as f:
                env_config = json.load(f)
                self.player_config = env_config.get("players", {})
        else:
            self.player_config = {}

        # ---------------- OBSERVABILIDAD ----------------
        # Aquí EMPEZAMOS a emitir eventos de juego
        if self.event_bus:
            self.game_state.event_bus = self.event_bus

            # Evento RESET
            self.event_bus.emit(
                {
                    "type": "RESET",
                    "payload": {
                        "scenario": self.scenario.name,
                        "turn": self.game_state.turn,
                        "game_map": self.game_state.game_map,
                    },
                }
            )

            # Evento UNIT_LOADED por cada unidad
            for unit in self.game_state.units:
                side_cfg = self.player_config.get(unit.side, {})
                self.event_bus.emit(
                    {
                        "type": "UNIT_LOADED",
                        "payload": {
                            "unit_id": unit.unit_id,
                            "side": unit.side,
                            "position": unit.position,
                            "controller": side_cfg.get("controller", "heuristic"),
                            "heuristic": side_cfg.get("heuristic", "HeuristicBase"),
                        },
                    }
                )

        # Iniciar el primer turno
        self.runtime.start_turn()
        self.game_state = self.runtime.base_state

        # Estado inicial del mapa
        if self.event_bus:
            self.event_bus.emit(
                {
                    "type": "MAP_STATE",
                    "payload": {
                        "turn": self.game_state.turn,
                        "game_map": self.game_state.game_map,
                        "units": self.game_state.units,
                        "vp_tracker": self.game_state.vp_tracker,
                        "game_state": self.game_state,
                    },
                }
            )

        return self.game_state

    # -------------------------------------------------
    # STEP
    # -------------------------------------------------
    def step(self, action):
        """
        Aplica UNA acción externa (intención del agente).

        Regla clave:
        - ACTION se emite SOLO cuando hay una acción explícita.
        """

        # ---------------- ACTION (INTENCIÓN) ----------------
        # Esto es OBSERVABILIDAD (no debug)
        if self.event_bus and action is not None:
            self.event_bus.emit(
                {
                    "type": "ACTION",
                    "payload": {
                        "turn": self.game_state.turn,
                        "action": action.__class__.__name__,
                        "active_unit": (
                            self.game_state.active_unit.unit_id
                            if self.game_state.active_unit
                            else None
                        ),
                    },
                }
            )

        # ---------------- EJECUCIÓN REAL ----------------
        self.runtime.apply_action(action)
        self.game_state = self.runtime.base_state

        # ---------------- TRAZA DE DESARROLLO ----------------
        # Esto NO es observabilidad
        _trace(
            "ACTIVE_UNIT",
            unit=self.game_state.active_unit.unit_id
            if self.game_state.active_unit
            else None,
        )

        # ---------------- FIN DE PARTIDA ----------------
        alive_units = [u for u in self.game_state.units if u.alive]
        alive_sides = {u.side for u in alive_units}

        if len(alive_sides) == 1:
            winner = next(iter(alive_sides))
            if self.event_bus:
                self.event_bus.emit(
                    {
                        "type": "MATCH_END",
                        "payload": {
                            "winner": winner,
                            "reason": "last_side_standing",
                        },
                    }
                )

            reward = (
                self.game_state.vp_tracker.total_points
                if self.game_state.vp_tracker
                else 0
            )
            return self.game_state, reward, True, {}

        # ---------------- FIN DE TURNO ----------------
        if self._turn_has_ended():
            if self.event_bus:
                self.event_bus.emit(
                    {
                        "type": "TURN_END",
                        "payload": {
                            "turn": self.game_state.turn,
                            "reason": "no_activable_units",
                        },
                    }
                )

                self.event_bus.emit(
                    {
                        "type": "MAP_STATE",
                        "payload": {
                            "turn": self.game_state.turn,
                            "game_map": self.game_state.game_map,
                            "units": self.game_state.units,
                            "vp_tracker": self.game_state.vp_tracker,
                            "game_state": self.game_state,
                        },
                    }
                )

            self.runtime.end_turn()
            self.runtime.start_turn()
            self.game_state = self.runtime.base_state

        done = (
            self.scenario.max_turns is not None
            and self.game_state.turn > self.scenario.max_turns
        )

        reward = (
            self.game_state.vp_tracker.total_points
            if self.game_state.vp_tracker
            else 0
        )

        return self.game_state, reward, done, {}

    # =================================================
    # TURN-END CRITERION
    # =================================================
    def _turn_has_ended(self) -> bool:
        return len(self._activable_units()) == 0

    def _activable_units(self):
        gs = self.game_state
        catalog = ActionCatalog(gs)

        return [
            u
            for u in gs.units
            if self._is_unit_activable(u, gs, catalog)
        ]

    def _is_unit_activable(self, unit, gs, catalog) -> bool:
        # Todo esto son REGLAS INTERNAS (con traza opcional)
        if not unit.alive:
            _trace("INACTIVABLE", unit=unit.unit_id, reason="dead")
            return False

        if unit in gs.activation_state.activated:
            _trace("INACTIVABLE", unit=unit.unit_id, reason="already_activated")
            return False

        if getattr(unit, "suppressed", False):
            _trace("INACTIVABLE", unit=unit.unit_id, reason="suppressed")
            return False

        if getattr(unit, "fallback", False):
            _trace("INACTIVABLE", unit=unit.unit_id, reason="fallback")
            return False

        prev_active = gs.activation_state.active_unit
        gs.activation_state.active_unit = unit
        try:
            actions = catalog.actions()
        finally:
            gs.activation_state.active_unit = prev_active

        real_actions = [a for a in actions if not isinstance(a, WaitAction)]

        _trace("ACTIONS", unit=unit.unit_id, real=len(real_actions))

        return len(real_actions) > 0