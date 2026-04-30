from collections import deque


def bfs_hex_path(start, goal, state):
    if start == goal:
        return []

    visited = {start}
    queue = deque([(start, [])])

    game_map = state.game_map
    unit_side = state.active_unit.side

    occupied = {
        u.position
        for u in state.units
        if u.alive and u.side == unit_side and u.position != goal
    }

    while queue:
        (q, r), path = queue.popleft()

        # ✅ CONTRATO REAL DEL MAPA
        hex_obj = game_map.get_hex(q, r)
        if hex_obj is None:
            continue

        for neigh in hex_obj.neighbors():
            nq, nr = neigh.q, neigh.r
            nxt = (nq, nr)

            if nxt in visited:
                continue
            if nxt in occupied:
                continue

            new_path = path + [nxt]

            if nxt == goal:
                return new_path

            visited.add(nxt)
            queue.append((nxt, new_path))

    return None