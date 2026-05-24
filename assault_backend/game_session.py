from typing import Optional, Dict, Any
from pathlib import Path

from assault_sim.sim_env import SimEnv
from assault_sim.config.config_loader import load_sim_config


class GameSession:
    def __init__(self):
        self.env: Optional[SimEnv] = None

    # ---------------------------------------------
    def start(self, scenario_id: str):
        base_path = Path(__file__).resolve().parents[1]

        # ✅ ruta al YAML
        config_path = (
            base_path
            / "assault_sim"
            / "config"
            / "sim_config.yaml"
        )

        config = load_sim_config(str(config_path))

        # ✅ FIX CRÍTICO: data_root absoluto
        config.data_root = (
            base_path
            / "assault_sim"
            / "assets"
        )

        # ✅ override dinámico del escenario
        config.scenario_name = scenario_id

        self.env = SimEnv(config)
        self.env.reset()

    # ---------------------------------------------
    def get_state(self) -> Dict[str, Any]:
        if self.env is None:
            return {"units": []}

        state = self.env.game_state

        units = []
        for u in state.units:
            if not getattr(u, "alive", True):
                continue

            units.append({
                "id": u.unit_id,
                "unit_key": str(u.unit_type.code),
                "q": u.position.q,
                "r": u.position.r,
                "side": u.side,
                "hp": getattr(u, "hp", None),
            })

        return {
            "units": units
        }