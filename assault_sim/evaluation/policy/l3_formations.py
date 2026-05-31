from collections import defaultdict


def compute_formation_performance(results):
    """
    L3 analysis: performance per strategy / formation
    """

    data = defaultdict(lambda: {
        "usage": 0,
        "damage": 0,
        "attacks": 0,
        "kills": 0
    })

    for r in results:

        formation_counts = r.get("formation_counts", {})
        side = r.get("side", {}).get("RL", {})

        dmg = side.get("damage", 0)
        atk = side.get("attacks", 0)
        kills = side.get("kills", 0)

        total_forms = sum(formation_counts.values()) or 1

        for f, count in formation_counts.items():

            ratio = count / total_forms

            data[f]["usage"] += count
            data[f]["damage"] += dmg * ratio
            data[f]["attacks"] += atk * ratio
            data[f]["kills"] += kills * ratio

    # normalize
    result = {}

    for f, v in data.items():

        attacks = v["attacks"]

        result[f] = {
            "usage": v["usage"],
            "damage_per_attack": v["damage"] / attacks if attacks else 0,
            "kills_per_attack": v["kills"] / attacks if attacks else 0
        }

    return result