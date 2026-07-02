from pathlib import Path

from assault_model.core.scenario_loader import load_scenario
from assault_model.units.catalog_loader import load_unit_catalog
from assault_model.map.map_piece_loader import load_map_piece_catalog

from assault_model.state.game_state import GameState
from assault_model.runtime.game_state_runtime import RuntimeGameState
from assault_model.runtime.execution_context import ExecutionContext

from assault_model.map.terrain_config import terrain_config
from assault_model.actions.action_catalog import ActionCatalog


class AssaultSimulation:

    def __init__(self, config):
        # -------------------------
        # CONFIG (inyectada desde main)
        # -------------------------
        cfg = config

        # ✅ escenario
        self.scenario_name = cfg["scenario_schedule"][0]["id"]

        # ✅ rutas robustas
        repo_root = Path(__file__).resolve().parents[2]
        self.assets_root = repo_root / "assault_sim" / "assets"

        # -------------------------
        # CARGA DE DATOS
        # -------------------------
        self.unit_catalog = load_unit_catalog(
            self.assets_root / "catalogs" / "unit_catalog.json"
        )

        self.map_catalog = load_map_piece_catalog(
            self.assets_root / "catalogs" / "map_piece_catalog.json"
        )

        scenario_path = self.assets_root / "scenarios" / f"{self.scenario_name}.json"

        self.scenario = load_scenario(
            scenario_path,
            self.unit_catalog,
            self.map_catalog
        )

        # -------------------------
        # ESTADO
        # -------------------------
        self.game_state = None
        self.runtime = None
        self.done = False

    # -------------------------
    # INITIAL STATE
    # -------------------------
    def get_initial_state(self):
        self.game_state = GameState.from_scenario(self.scenario)

        self.game_state.game_map.terrain_config = terrain_config

        self.runtime = RuntimeGameState(self.game_state, self.scenario)
        self.runtime.start_turn()

        self.game_state = self.runtime.base_state
        self.done = False

        return self.game_state

    # -------------------------
    # LEGAL ACTIONS
    # -------------------------
    def get_legal_actions(self, state):
        actions = []

        terrain_cfg = state.game_map.terrain_config

        for unit in state.units:
            if not getattr(unit, "alive", True):
                continue

            catalog = ActionCatalog(
                state,
                unit,
                terrain_config=terrain_cfg
            )

            actions.extend(catalog.actions())

        return actions

    # -------------------------
    # STEP
    # -------------------------
    def step(self, state, action):
        if self.runtime is None:
            raise RuntimeError("Simulation not initialized. Call get_initial_state() first.")

        context = ExecutionContext(
            game_map=self.game_state.game_map
        )

        prev_turn = self.game_state.turn

        # ✅ aplicar acción
        self.runtime.apply_action(action, context=context)
        self.game_state = self.runtime.base_state

        # ✅ fin partida
        if self.game_state.done:
            self.done = True
            return self.game_state

        # ✅ cambio de turno
        if self.game_state.turn != prev_turn:
            self.runtime.start_turn()
            self.game_state = self.runtime.base_state

        return self.game_state

    # -------------------------
    # TERMINAL
    # -------------------------
    def is_done(self, state):
        return self.done