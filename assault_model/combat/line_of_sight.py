import math
from enum import Enum

from assault_model.map.hex_coord import HexCoord


# -------------------------------------------------
# LOS RESULT
# -------------------------------------------------

class LineOfSight(Enum):
    CLEAR = 0
    HINDERED = 1
    BLOCKED = 2


# -------------------------------------------------
# CACHE GLOBAL
# -------------------------------------------------

_los_cache = {}


def _make_key(a: HexCoord, b: HexCoord):
    return (a.q, a.r, b.q, b.r)


# -------------------------------------------------
# ✅ TRANSFORMACIONES DE ESPACIO (FLAT-TOP HEX)
# -------------------------------------------------

def _hex_to_pixel(q: int, r: int, size: float = 1.0):
    """Convierte una coordenada axial a una posición (X, Y) cartesiana real."""
    x = size * (3.0 / 2.0 * q)
    y = size * (math.sqrt(3.0) * (r + q / 2.0))
    return x, y


def _pixel_to_hex(x: float, y: float, size: float = 1.0):
    """Convierte una posición (X, Y) continua al hexágono correspondiente."""
    q = (2.0 / 3.0 * x) / size
    r = (-1.0 / 3.0 * x + math.sqrt(3.0) / 3.0 * y) / size
    return _cube_round(q, r)


# -------------------------------------------------
# ✅ CUBE ROUND INDISPENSABLE
# -------------------------------------------------

def _cube_round(q, r):
    x = q
    z = r
    y = -x - z

    rx = math.floor(x + 0.5)
    ry = math.floor(y + 0.5)
    rz = math.floor(z + 0.5)

    dx = abs(rx - x)
    dy = abs(ry - y)
    dz = abs(rz - z)

    if dx > dy and dx > dz:
        rx = -ry - rz
    elif dy > dz:
        ry = -rx - rz
    else:
        rz = -rx - ry

    return HexCoord(int(rx), int(rz))


# -------------------------------------------------
# 🔥 NUEVO TRAZADO DE LÍNEA POR INTERPOLACIÓN DE CUBO (ALTA PRECISIÓN)
# -------------------------------------------------

def _hex_path_strict(a: HexCoord, b: HexCoord):
    """
    Calcula la trayectoria exacta mediante interpolación lineal directa en espacio cúbico.
    Aplica un ligero desfase (nudge) infinitesimal para resolver limpiamente empates visuales.
    Garantiza 0 errores de continuidad (distancia siempre igual a 1 entre hexágonos vecinos).
    """
    if a.q == b.q and a.r == b.r:
        return [HexCoord(a.q, a.r)]

    # 1. Calcular distancia de pasos en la cuadrícula hexagonal discreta
    dq = b.q - a.q
    dr = b.r - a.r
    steps = max(abs(dq), abs(dr), abs(dq + dr))

    # 2. Convertir puntos de origen y destino a coordenadas tridimensionales de cubo
    ax, az = a.q, a.r
    ay = -ax - az

    bx, bz = b.q, b.r
    by = -bx - bz

    # 3. Aplicar "nudge" infinitesimal para romper simetrías problemáticas en bordes/vértices
    ax += 1e-6
    ay += 1e-6
    az -= 2e-6

    path = []
    
    # 4. Muestreo exacto paso a paso coordinado con la distancia real
    for i in range(steps + 1):
        t = i / steps
        lx = ax + (bx - ax) * t
        ly = ay + (by - ay) * t
        lz = az + (bz - az) * t
        
        # Redondeo tridimensional de cubo ultra preciso
        rx = int(round(lx))
        ry = int(round(ly))
        rz = int(round(lz))
        
        x_diff = abs(rx - lx)
        y_diff = abs(ry - ly)
        z_diff = abs(rz - lz)
        
        if x_diff > y_diff and x_diff > z_diff:
            rx = -ry - rz
        elif y_diff > z_diff:
            ry = -rx - rz
        else:
            rz = -rx - ry
            
        path.append(HexCoord(int(rx), int(rz)))

    return path


# -------------------------------------------------
# LOS CORE
# -------------------------------------------------

def check_line_of_sight(attacker, target, game_map, terrain_config):
    start = getattr(attacker, "position", None)
    end = getattr(target, "position", None)

    if start is None or end is None:
        return LineOfSight.BLOCKED

    key = _make_key(start, end)

    if key in _los_cache:
        result, cached_debug = _los_cache[key]
        attacker._los_debug = cached_debug
        return result

    reverse_key = (end.q, end.r, start.q, start.r)
    if reverse_key in _los_cache:
        result, cached_debug = _los_cache[reverse_key]
        attacker._los_debug = {
            "blocking": cached_debug["blocking"],
            "hindrance": cached_debug["hindrance"],
            "path": list(reversed(cached_debug["path"]))
        }
        return result

    # Calculamos la trayectoria limpia usando el nuevo motor de cubo de alta precisión
    path = _hex_path_strict(start, end)

    if not path:
        return LineOfSight.BLOCKED

    inner_path = path[1:-1]

    hindrance = 0
    blocking_hexes = []
    hindrance_hexes = []
    is_blocked = False

    for coord in inner_path:
        hex_ = game_map.get_hex(coord.q, coord.r)
        if not hex_:
            continue

        terrain = hex_.get_terrain()
        config = terrain_config.get(terrain)
        los_type = config.get("los", "CLEAR") if config else "CLEAR"

        if los_type == "BLOCKED":
            is_blocked = True
            blocking_hexes.append((coord.q, coord.r))

        elif los_type == "HINDERED":
            hindrance += 1
            hindrance_hexes.append((coord.q, coord.r))
            
            if hindrance >= 3:
                is_blocked = True

    if hindrance >= 3:
        for h_coord in hindrance_hexes:
            if h_coord not in blocking_hexes:
                blocking_hexes.append(h_coord)

    if is_blocked:
        result = LineOfSight.BLOCKED
    elif hindrance >= 1:
        result = LineOfSight.HINDERED
    else:
        result = LineOfSight.CLEAR

    # Datos limpios y ordenados secuencialmente para pintar las flechas en el Frontend
    debug_data = {
        "blocking": blocking_hexes,
        "hindrance": hindrance_hexes,
        "path": [(c.q, c.r) for c in path]
    }
    attacker._los_debug = debug_data

    _los_cache[key] = (result, debug_data)
    return result


# -------------------------------------------------
# PUBLIC API
# -------------------------------------------------

def has_line_of_sight(attacker, target, game_map, terrain_config):
    return check_line_of_sight(
        attacker,
        target,
        game_map,
        terrain_config
    ) != LineOfSight.BLOCKED