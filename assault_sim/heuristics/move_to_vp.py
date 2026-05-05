from assault_model.actions.action_catalog import ActionCatalog
from assault_model.actions.action_category import ActionCategory
from assault_model.actions.assault import AssaultAction
from assault_model.map.hex_utils import hex_distance


class MoveToVictoryPointHeuristic:
    """
    Moves units towards Victory Points defined by vp_tracker.conditions.

    Key architectural assumptions:
    - MovementRules allow ONLY 1-hex movement per action.
    - ActionCatalog already generates all legal 1-step MoveActions.
    - This heuristic DOES NOT compute paths itself.
      Instead, it picks the best existing movement action.

    Priority:
    1. Close combat (AssaultAction)
    2. Movement action that reduces distance to nearest VP
    3. Wait action as fallback
    """

    def choose_action(self, state):
        unit = state.active_unit
        actions = ActionCatalog(state).actions()

        print(
            f"[TRACE][HEURISTIC] active_unit="
            f"{unit.unit_id if unit else None}"
        )

        if unit is None or not actions:
            print("[TRACE][HEURISTIC] no unit or no actions -> WAIT")
            return None

        print("[TRACE][HEURISTIC] available actions:")
        for a in actions:
            path = getattr(a, "path", None)
            if path:
                dest = path[-1]
                print(
                    f"  - {a.action_type.name} "
                    f"-> ({dest.q},{dest.r})"
                )
            else:
                print(f"  - {a.action_type.name}")

        # -------------------------------------------------
        # ✅ PRIORITY: CLOSE COMBAT
        # -------------------------------------------------
        for action in actions:
            if isinstance(action, AssaultAction):
                print("[TRACE][HEURISTIC] chose ASSAULT")
                return action

        vp_tracker = getattr(state, "vp_tracker", None)
        if not vp_tracker or not vp_tracker.conditions:
            print("[TRACE][HEURISTIC] no VP info -> WAIT")
            return self._wait(actions)

        vp_positions = vp_tracker.conditions.get_positions()
        if not vp_positions:
            print("[TRACE][HEURISTIC] VP list empty -> WAIT")
            return self._wait(actions)

        current_pos = unit.position
        target_vp = min(
            vp_positions,
            key=lambda p: hex_distance(current_pos, p)
        )

        best_dist = hex_distance(current_pos, target_vp)
        best_action = None

        print(
            f"[TRACE][HEURISTIC] target_vp="
            f"({target_vp.q},{target_vp.r}) "
            f"current_dist={best_dist}"
        )

        # -------------------------------------------------
        # ✅ Choose movement action that improves distance
        # -------------------------------------------------
        for action in actions:
            if action.action_type.category != ActionCategory.MOVEMENT:
                continue

            path = getattr(action, "path", None)
            if not path:
                continue

            dest = path[-1]
            d = hex_distance(dest, target_vp)

            print(
                f"[TRACE][HEURISTIC] check MOVE -> "
                f"({dest.q},{dest.r}) "
                f"dist={d}"
            )

            if d < best_dist:
                best_dist = d
                best_action = action

        if best_action:
            dest = best_action.path[-1]
            print(
                f"[TRACE][HEURISTIC] CHOSE MOVE -> "
                f"({dest.q},{dest.r})"
            )
            return best_action

        print("[TRACE][HEURISTIC] no improving move -> WAIT")
        return self._wait(actions)

    def _wait(self, actions):
        for a in actions:
            if a.action_type.category == ActionCategory.STATUS:
                return a
        return actions[0]
