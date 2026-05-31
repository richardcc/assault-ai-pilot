from collections import defaultdict


def aggregate_units(results):
    """
    L1: Aggregate all unit-level statistics
    """

    units = defaultdict(lambda: {
        "attacks": 0,
        "damage": 0,
        "kills": 0,
        "side": None,
        "category": None,
        "classification": None,
    })

    for r in results:
        unit_data = r.get("units", {})

        for side, side_units in unit_data.items():
            for uid, stats in side_units.items():

                u = units[uid]

                u["attacks"] += stats.get("attacks", 0)
                u["damage"] += stats.get("damage", 0)
                u["kills"] += stats.get("kills", 0)

                if u["side"] is None:
                    u["side"] = side
                    u["category"] = stats.get("category")
                    u["classification"] = stats.get("classification")

    return units