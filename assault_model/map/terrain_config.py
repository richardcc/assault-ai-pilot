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
    # MOVEMENT COST (reglamento 9.4 / 9.10)
    # -----------------------------
    def get_move_cost(self, terrain_name, movement_type, default=1):
        """
        Puntos de movimiento para ENTRAR en el hex con ese tipo de movimiento.

        Devuelve:
        - int >= 1  -> coste de entrada
        - None      -> impasable / 'Blocked' para ese tipo de movimiento

        Convenciones de datos (terrain_modifiers.json):
        - terreno con flag "impassable": true -> impasable para todos
        - move_cost[movement_type] entero >= 1 -> coste
        - move_cost[movement_type] == 0 / negativo / "blocked" -> impasable
        - ausente o null -> aun sin rellenar, se usa `default` para no
          bloquear el juego mientras se completa la tabla
        """
        entry = self.get(terrain_name)

        if entry.get("impassable"):
            return None

        move_cost = entry.get("move_cost") or {}
        val = move_cost.get(movement_type, None)

        if val is None:
            return default

        if isinstance(val, str):
            return None

        if val <= 0:
            return None

        return int(val)

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
