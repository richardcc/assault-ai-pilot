from collections import deque


def bfs_hex_path(start, goal, state):
    """
    BFS pathfinding over a hex grid.

    - Considers ONLY fixed obstacles (terrain, map bounds)
    - Ignores ALL units (dynamic objects)
    - Returns a full path to the goal if it exists
    - Returns None if no route exists due to fixed blockers
    """

    if start == goal:
        return []

    visited = {start}
    queue = deque([(start, [])])

    game_map = state.game_map

    while queue:
        (q, r), path = queue.popleft()

        hex_obj = game_map.get_hex(q, r)
        if hex_obj is None:
            continue

        for neigh in hex_obj.neighbors():
            nxt = (neigh.q, neigh.r)

            if nxt in visited:
                continue

            hex_nxt = game_map.get_hex(*nxt)
            if hex_nxt is None:
                continue

            # ✅ SOLO BLOQUEOS FIJOS DEL MAPA
            if hex_nxt.terrain.value == "water":
                continue

            # (si tienes más terrenos impasables, añádelos aquí)
            # if hex_nxt.terrain.value in {"water", "lava", "mountain"}:
            #     continue

            new_path = path + [nxt]

            if nxt == goal:
                return new_path

            visited.add(nxt)
            queue.append((nxt, new_path))

    # ❌ No existe ruta debido a bloqueos fijos
    return None