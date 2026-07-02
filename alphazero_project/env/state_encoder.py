import numpy as np


def encode_state(state, config):
    """
    Convierte GameState → tensor [C, H, W] con padding fijo

    Canales:
    0: unidades propias
    1: unidades enemigas
    2: hp propias
    3: hp enemigas
    4: terreno
    5: objetivos
    """

    game_map = state.game_map
    hexes = getattr(game_map, "hexes", [])

    if not hexes:
        raise ValueError("Map has no hexes")

    # -------------------------
    # MAP SIZE REAL
    # -------------------------
    max_q = max(h.q for h in hexes)
    max_r = max(h.r for h in hexes)

    H_real = max_q + 1
    W_real = max_r + 1

    # -------------------------
    # CONFIG (TAMAÑO MODELO)
    # -------------------------
    model_cfg = config["model"]
    C = model_cfg["in_channels"]
    MAX_SIZE = model_cfg["max_board_size"]

    # -------------------------
    # TENSOR BASE
    # -------------------------
    tensor = np.zeros((C, H_real, W_real), dtype=np.float32)

    # -------------------------
    # TERRAIN
    # -------------------------
    for h in hexes:
        q, r = h.q, h.r
        terrain = h.get_terrain()

        terrain_id = hash(terrain) % 10 / 10.0
        tensor[4, q, r] = terrain_id

    # -------------------------
    # UNITS
    # -------------------------
    for u in state.units:
        if not getattr(u, "alive", True):
            continue

        if u.position is None:
            continue

        q = u.position.q
        r = u.position.r

        is_friendly = (u.side == state.active_side)

        hp = getattr(u, "hp", 0.0)
        max_hp = getattr(u, "max_hp", hp if hp > 0 else 1.0)
        hp_norm = hp / max_hp if max_hp > 0 else 0.0

        if is_friendly:
            tensor[0, q, r] = 1.0
            tensor[2, q, r] = hp_norm
        else:
            tensor[1, q, r] = 1.0
            tensor[3, q, r] = hp_norm

    # -------------------------
    # OBJECTIVES
    # -------------------------
    vp_tracker = getattr(state, "vp_tracker", None)

    if vp_tracker and getattr(vp_tracker, "conditions", None):
        for vp in getattr(vp_tracker.conditions, "points", []):
            q, r = vp.hex_coords
            if 0 <= q < H_real and 0 <= r < W_real:
                tensor[5, q, r] = 1.0

    # -------------------------
    # ✅ PADDING A TAMAÑO FIJO
    # -------------------------
    padded = np.zeros((C, MAX_SIZE, MAX_SIZE), dtype=np.float32)

    h = min(H_real, MAX_SIZE)
    w = min(W_real, MAX_SIZE)

    padded[:, :h, :w] = tensor[:, :h, :w]

    return padded
``