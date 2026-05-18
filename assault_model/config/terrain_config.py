import json
from pathlib import Path


class TerrainConfig:

    def __init__(self, config_path=None):

        if config_path is None:
            config_path = Path(__file__).parent / "terrain_modifiers.json"

        with open(config_path, "r", encoding="utf-8") as f:
            self.data = json.load(f)

    # -----------------------------
    # Terrain entry
    # -----------------------------
    def get(self, terrain_name):
        return self.data["terrain"].get(
            terrain_name,
            self.data["terrain"]["clear"]
        )

    # -----------------------------
    # Defense dice
    # -----------------------------
    def get_defense_dice(self, terrain_name, unit_type):
        entry = self.get(terrain_name)
        return entry.get("defense", {}).get(unit_type, [])

    # -----------------------------
    # LOS
    # -----------------------------
    def get_los(self, terrain_name):
        entry = self.get(terrain_name)
        return entry.get("los", "CLEAR")

    # -----------------------------
    # Flags
    # -----------------------------
    def has_flag(self, terrain_name, flag):
        entry = self.get(terrain_name)
        return entry.get(flag, False)


# ✅ 💥 ESTA LÍNEA FALTABA
terrain_config = TerrainConfig()
