from collections import defaultdict


def compute_option_performance(results):
    """
    L2 analysis: performance per tactical option
    """

    data = defaultdict(lambda: {
        "usage": 0,
        "damage": 0,
        "attacks": 0,
        "kills": 0
    })

    for r in results:

        option_counts = r.get("option_counts", {})
        side = r.get("side", {}).get("RL", {})

        dmg = side.get("damage", 0)
        atk = side.get("attacks", 0)
        kills = side.get("kills", 0)

        total_opts = sum(option_counts.values()) or 1

        for opt, count in option_counts.items():

            ratio = count / total_opts

            data[opt]["usage"] += count
            data[opt]["damage"] += dmg * ratio
            data[opt]["attacks"] += atk * ratio
            data[opt]["kills"] += kills * ratio

    # normalize
    result = {}

    for opt, v in data.items():

        attacks = v["attacks"]

        result[opt] = {
            "usage": v["usage"],
            "damage_per_attack": v["damage"] / attacks if attacks else 0,
            "kills_per_attack": v["kills"] / attacks if attacks else 0
        }

    return result
