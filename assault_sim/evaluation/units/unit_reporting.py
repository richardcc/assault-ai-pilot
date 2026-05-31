def print_all_units(units, rl_side):
    """
    Print all units grouped by side dynamically
    """

    print(f"\n=== ALL UNITS ({rl_side}) ===")

    for uid, u in sorted(units.items()):
        if u["side"] == "RL":
            print(
                f"{uid} | {u['category']} | {u['classification']} | "
                f"dmg={u['damage']} atk={u['attacks']} kills={u['kills']}"
            )

    print("\n=== ALL UNITS (OTHER SIDE) ===")

    for uid, u in sorted(units.items()):
        if u["side"] != "RL":
            print(
                f"{uid} | {u['category']} | {u['classification']} | "
                f"dmg={u['damage']} atk={u['attacks']} kills={u['kills']}"
            )