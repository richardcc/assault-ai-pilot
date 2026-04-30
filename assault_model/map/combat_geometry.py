from assault_model.combat.attack_sector import AttackSector
import os

# DEBUG TRACE (configurable por entorno)
DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


def _trace(tag: str, **data):
    if not DEBUG_TRACE:
        return
    payload = " ".join(f"{k}={v}" for k, v in data.items())
    print(f"[TRACE][{tag}] {payload}")


def determine_attack_sector(
    attacker_pos: tuple[int, int],
    defender_pos: tuple[int, int],
    defender_facing: str,
) -> AttackSector:
    ax, ay = attacker_pos
    dx, dy = defender_pos

    vx = ax - dx
    vy = ay - dy

    facing_vectors = {
        "N": (0, -1),
        "S": (0, 1),
        "E": (1, 0),
        "W": (-1, 0),
    }

    fx, fy = facing_vectors[defender_facing]

    dot = vx * fx + vy * fy

    if dot > 0:
        sector = AttackSector.FRONT
    elif dot < 0:
        sector = AttackSector.REAR
    else:
        cross = fx * vy - fy * vx
        if cross > 0:
            sector = AttackSector.FLANK_LEFT
        else:
            sector = AttackSector.FLANK_RIGHT

    _trace(
        "ATTACK_SECTOR",
        attacker_pos=attacker_pos,
        defender_pos=defender_pos,
        defender_facing=defender_facing,
        sector=sector.name,
    )

    return sector