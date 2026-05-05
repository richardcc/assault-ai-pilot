from collections import deque
from assault_model.map.hex_coord import HexCoord


def bfs_hex_path(start: HexCoord, goal: HexCoord, state):
    if start == goal:
        return []

    visited = {(start.q, start.r)}
    queue = deque([(start, [])])

    game_map = state.game_map

    while queue:
        pos, path = queue.popleft()
        key = (pos.q, pos.r)

        hex_obj = game_map.get_hex(pos.q, pos.r)
        if hex_obj is None:
            continue

        for neigh in hex_obj.neighbors():
            nxt = neigh
            nxt_key = (nxt.q, nxt.r)

            if nxt_key in visited:
                continue

            hex_nxt = game_map.get_hex(nxt.q, nxt.r)
            if hex_nxt is None:
                continue

            if hex_nxt.terrain.value == "water":
                continue

            new_path = path + [nxt]

            if nxt == goal:
                return new_path

            visited.add(nxt_key)
            queue.append((nxt, new_path))

    return None