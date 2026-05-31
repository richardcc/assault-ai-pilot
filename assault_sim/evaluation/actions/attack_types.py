from collections import defaultdict


def compute_attack_type_performance(results):
    """
    Analyze performance by attack type (direct vs indirect)
    """

    data = defaultdict(lambda: {
        "attacks": 0,
        "damage": 0,
        "kills": 0
    })

    for r in results:

        units = r.get("units", {}).get("RL", {})

        for uid, stats in units.items():

            classification = stats.get("classification", "UNKNOWN")

            attacks = stats.get("attacks", 0)
            damage = stats.get("damage", 0)
            kills = stats.get("kills", 0)

            key = classification  # INDIRECT_FIRE_UNIT, STANDARD, etc.

            data[key]["attacks"] += attacks
            data[key]["damage"] += damage
            data[key]["kills"] += kills

    # normalize
    result = {}

    for k, v in data.items():

        a = v["attacks"]

        result[k] = {
            "attacks": a,
            "damage_per_attack": v["damage"] / a if a else 0,
            "kills_per_attack": v["kills"] / a if a else 0
        }

    return result