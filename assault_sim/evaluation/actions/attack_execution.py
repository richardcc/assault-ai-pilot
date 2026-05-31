from collections import defaultdict


def compute_action_execution(results):
    """
    Real action-level execution analysis (per side)
    """

    data = defaultdict(lambda: {
        "count": 0,
        "damage": 0
    })

    for r in results:

        side_data = r.get("side", {})
        events = r.get("events", [])

        for e in events:

            if e.get("type") != "attack":
                continue

            atk_type = e.get("attack_type", "UNKNOWN")

            # --------------------------
            # NORMALIZE TYPES
            # --------------------------
            if atk_type is None:
                atk_type = "UNKNOWN"

            elif "INDIRECT" in atk_type.upper():
                atk_type = "INDIRECT"

            elif "DIRECT" in atk_type.upper():
                atk_type = "DIRECT"

            else:
                atk_type = "OTHER"

            data[atk_type]["count"] += 1
            data[atk_type]["damage"] += e.get("damage", 0)

        # --------------------------
        # OPCIONAL → moves / waits
        # --------------------------
        # esto depende de si lo logueas en info
        move_count = r.get("move_count", 0)
        wait_count = r.get("wait_count", 0)

        data["MOVE"]["count"] += move_count
        data["WAIT"]["count"] += wait_count

    # ---------------------------------
    # NORMALIZE
    # ---------------------------------
    result = {}

    for k, v in data.items():

        c = v["count"]

        result[k] = {
            "count": c,
            "damage_per_action": v["damage"] / c if c else 0
        }

    return result