from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from assault_model.actions.action_catalog import ActionCatalog
from assault_model.actions.status import WaitAction
from assault_model.core.scenario_loader import load_scenario
from assault_model.map.terrain_config import terrain_config
from assault_model.runtime.execution_context import ExecutionContext
from assault_model.runtime.game_state_runtime import RuntimeGameState
from assault_model.state.game_state import GameState

from voec_sim.assets_bridge.importers import AssetPaths, _resolve_repo_path, load_catalogs
from voec_sim.contracts.types import StateSnapshot, TransitionRecord, UnitSnapshot

REACTION_USE_PREFIX = "OPPORTUNITY_FIRE"
REACTION_SKIP_PREFIX = "OPPORTUNITY_SKIP"


@dataclass
class EpisodeHandle:
    scenario_id: str
    seed: int


class VOECSimulator:
    """
    Clean simulator facade that reuses existing assets while exposing
    a stable, algorithm-agnostic contract.
    """

    def __init__(self, assets: Optional[AssetPaths] = None):
        self.assets = assets or AssetPaths()
        self._runtime: Optional[RuntimeGameState] = None
        self._state: Optional[GameState] = None
        self._scenario_id: Optional[str] = None
        self._seed: int = 0
        self._max_turns: Optional[int] = None
        self._legal_actions_cache_key: Optional[tuple] = None
        self._legal_actions_cache_value: List[str] = []

    def new_episode(self, scenario_id: str, seed: int = 0) -> EpisodeHandle:
        self._seed = int(seed)
        unit_catalog, map_piece_catalog = load_catalogs(self.assets)
        scenario_path = _resolve_repo_path(
            self.assets.scenarios_path / f"{scenario_id}.json"
        )
        scenario = load_scenario(
            scenario_path=scenario_path,
            unit_catalog=unit_catalog,
            map_piece_catalog=map_piece_catalog,
        )
        state = GameState.from_scenario(scenario)
        # Keep parity with the stable simulation path used in assault_sim.
        state.game_map.terrain_config = terrain_config
        runtime = RuntimeGameState(state, scenario)
        # In VOEC/MuZero we expose reaction windows as explicit decisions.
        runtime.side_controller_map = {str(side): "human" for side in list(state.turn_order or [])}
        runtime.start_turn()

        self._runtime = runtime
        self._state = runtime.base_state
        self._scenario_id = scenario_id
        self._max_turns = int(scenario.max_turns) if scenario.max_turns is not None else None
        self._legal_actions_cache_key = None
        self._legal_actions_cache_value = []
        return EpisodeHandle(scenario_id=scenario_id, seed=self._seed)

    def clone_state(self) -> GameState:
        self._require_state()
        return deepcopy(self._state)

    def legal_actions(self) -> List[str]:
        state = self._require_state()
        runtime = self._require_runtime()
        if bool(getattr(state, "done", False)):
            return []
        active_side = getattr(runtime, "active_side", None)
        cache_key = (
            int(getattr(state, "_cache_version", 0)),
            int(getattr(state, "turn", 0)),
            str(active_side) if active_side is not None else "",
            bool(getattr(state, "done", False)),
        )
        if self._legal_actions_cache_key == cache_key:
            return list(self._legal_actions_cache_value)
        pending = dict(getattr(runtime, "pending_reaction", {}) or {})
        if pending:
            reaction_actions = self._reaction_window_actions(pending)
            self._legal_actions_cache_key = cache_key
            self._legal_actions_cache_value = list(reaction_actions)
            return reaction_actions
        all_action_ids: List[str] = []
        if active_side is None:
            # Explicit pass to let runtime recover activation order deterministically.
            self._legal_actions_cache_key = cache_key
            self._legal_actions_cache_value = ["WAIT:SYSTEM"]
            return ["WAIT:SYSTEM"]
        candidate_units = runtime.get_available_units(active_side)
        if not candidate_units:
            self._legal_actions_cache_key = cache_key
            self._legal_actions_cache_value = ["WAIT:SYSTEM"]
            return ["WAIT:SYSTEM"]
        for unit in candidate_units:
            catalog = ActionCatalog(
                state,
                unit,
                terrain_config=state.game_map.terrain_config,
            )
            for action in catalog.actions():
                action_id = getattr(action, "action_id", None)
                if action_id is None and isinstance(action, WaitAction):
                    action_id = f"WAIT:{getattr(action, 'unit_id', unit.unit_id)}"
                if action_id:
                    all_action_ids.append(str(action_id))
        self._legal_actions_cache_key = cache_key
        self._legal_actions_cache_value = list(all_action_ids)
        return all_action_ids

    def step(self, action_id: str) -> TransitionRecord:
        runtime = self._require_runtime()
        state = self._require_state()
        class _StepEventBus:
            def __init__(self):
                self.events = []

            def emit(self, event):
                self.events.append(dict(event or {}))

        step_bus = _StepEventBus()
        context = ExecutionContext(event_bus=step_bus, game_map=state.game_map)
        reaction_choice = self._parse_reaction_choice(action_id)
        if reaction_choice is not None:
            out = runtime.resolve_pending_reaction(use_reaction=bool(reaction_choice), context=context)
            if not bool(out.get("resolved", False)):
                raise ValueError(f"Reaction action id not legal: {action_id}")
        else:
            action = self._resolve_action_by_id(action_id)
            runtime.apply_action(action, context=context)
        self._state = runtime.base_state
        self._legal_actions_cache_key = None
        self._legal_actions_cache_value = []

        done = bool(self._state.done)
        reward = self._terminal_reward(self._state)
        return TransitionRecord(
            action_id=action_id,
            reward=reward,
            done=done,
            info={
                "scenario_id": self._scenario_id,
                "runtime_events": list(step_bus.events),
            },
            state=self.snapshot(),
        )

    def is_terminal(self) -> bool:
        return bool(self._require_state().done)

    def resolve_timeout(
        self,
        action_id: str = "TIMEOUT",
        end_reason: str = "timeout_resolution",
    ) -> TransitionRecord:
        state = self._require_state()
        if not state.done:
            winner = self._compute_timeout_winner(state)
            state.done = True
            state.winner = winner
            state.end_reason = end_reason
        self._legal_actions_cache_key = None
        self._legal_actions_cache_value = []
        reward = self._terminal_reward(state)
        return TransitionRecord(
            action_id=action_id,
            reward=reward,
            done=bool(state.done),
            info={"scenario_id": self._scenario_id, "timeout_resolution": True},
            state=self.snapshot(),
        )

    def snapshot(self) -> StateSnapshot:
        state = self._require_state()
        runtime = self._require_runtime()
        units = [
            UnitSnapshot(
                unit_id=u.unit_id,
                unit_key=u.unit_type.code,
                unit_label=u.unit_type.code,
                art_ref=u.unit_type.code,
                side=str(u.side),
                q=u.position.q if u.position else None,
                r=u.position.r if u.position else None,
                hp=getattr(u, "hp", None),
                alive=bool(getattr(u, "alive", True)),
            )
            for u in state.units
        ]
        pending = dict(getattr(runtime, "pending_reaction", {}) or {})
        pending_reactor_id = str(pending.get("reactor_id", "")).strip()
        pending_reactor = next(
            (u for u in state.units if str(getattr(u, "unit_id", "")) == pending_reactor_id),
            None,
        )
        pending_to_play = str(getattr(pending_reactor, "side", "")) if pending_reactor is not None else None
        return StateSnapshot(
            turn=state.turn,
            to_play=(
                pending_to_play
                if pending_to_play
                else (
                    str(getattr(runtime, "active_side", None))
                    if getattr(runtime, "active_side", None) is not None
                    else None
                )
            ),
            done=bool(state.done),
            winner=str(state.winner) if state.winner is not None else None,
            end_reason=str(state.end_reason) if state.end_reason is not None else None,
            units=units,
        )

    def spatial_features(self) -> Dict[str, Any]:
        state = self._require_state()

        def _as_int(value: Any) -> Optional[int]:
            try:
                if value is None:
                    return None
                return int(value)
            except Exception:
                return None

        def _coord_to_qr(coord: Any) -> tuple[Optional[int], Optional[int]]:
            if isinstance(coord, (tuple, list)) and len(coord) >= 2:
                q = _as_int(coord[0])
                r = _as_int(coord[1])
                if q is not None and r is not None:
                    return q, r
            if isinstance(coord, dict):
                q = _as_int(coord.get("q"))
                r = _as_int(coord.get("r"))
                if q is not None and r is not None:
                    return q, r
                hc = coord.get("hex_coords")
                if isinstance(hc, (tuple, list)) and len(hc) >= 2:
                    q = _as_int(hc[0])
                    r = _as_int(hc[1])
                    if q is not None and r is not None:
                        return q, r
                if isinstance(hc, dict):
                    q = _as_int(hc.get("q"))
                    r = _as_int(hc.get("r"))
                    if q is not None and r is not None:
                        return q, r
            q = getattr(coord, "q", None)
            r = getattr(coord, "r", None)
            q = _as_int(q)
            r = _as_int(r)
            if q is not None and r is not None:
                return q, r
            return None, None

        playable_hexes: List[Dict[str, int]] = []
        terrain_move_cost_by_hex: Dict[str, float] = {}
        terrain_cover_by_hex: Dict[str, float] = {}
        terrain_los_block_by_hex: Dict[str, int] = {}
        for coord in list(getattr(state, "hex_states", {}).keys()):
            q, r = _coord_to_qr(coord)
            if q is None or r is None:
                continue
            playable_hexes.append({"q": int(q), "r": int(r)})
            key = f"{int(q)},{int(r)}"
            terrain_name = "clear"
            hex_obj = None
            try:
                hex_obj = state.game_map.get_hex(int(q), int(r))
            except Exception:
                hex_obj = None
            if hex_obj is not None:
                try:
                    terrain_name = str(hex_obj.get_terrain())
                except Exception:
                    terrain_name = "clear"
            move_cost = terrain_config.get_move_cost(terrain_name, "foot", default=1)
            if move_cost is None:
                terrain_move_cost_by_hex[key] = 0.0
            else:
                terrain_move_cost_by_hex[key] = float(max(0, int(move_cost))) / 4.0
            cover_dice = terrain_config.get_defense_dice(terrain_name, "INFANTRY")
            terrain_cover_by_hex[key] = float(len(cover_dice)) / 3.0
            los_type = str(terrain_config.get_los(terrain_name)).upper()
            terrain_los_block_by_hex[key] = 1 if los_type == "BLOCKED" else 0

        ownership_to_side = {v: str(k) for k, v in getattr(state, "side_to_ownership", {}).items()}
        hex_state_by_key: Dict[str, Any] = {}
        for coord_key, hex_state in list(getattr(state, "hex_states", {}).items()):
            q, r = _coord_to_qr(coord_key)
            if q is None or r is None:
                continue
            hex_state_by_key[f"{int(q)},{int(r)}"] = hex_state
        vp_hexes: List[Dict[str, int]] = []
        vp_owner_by_hex: Dict[str, str] = {}
        victory = getattr(state, "victory", None)
        points = list(getattr(victory, "points", [])) if victory is not None else []
        for vp in points:
            q, r = _coord_to_qr(getattr(vp, "hex_coords", None))
            if q is None or r is None:
                continue
            vp_hexes.append({"q": int(q), "r": int(r)})
            key = f"{int(q)},{int(r)}"
            hex_state = hex_state_by_key.get(key)
            owner = getattr(hex_state, "ownership", None) if hex_state is not None else None
            side_owner = ownership_to_side.get(owner, "")
            vp_owner_by_hex[key] = str(side_owner)

        return {
            "playable_hexes": playable_hexes,
            "vp_hexes": vp_hexes,
            "vp_owner_by_hex": vp_owner_by_hex,
            "terrain_move_cost_by_hex": terrain_move_cost_by_hex,
            "terrain_cover_by_hex": terrain_cover_by_hex,
            "terrain_los_block_by_hex": terrain_los_block_by_hex,
        }

    def _resolve_action_by_id(self, action_id: str) -> Any:
        state = self._require_state()
        runtime = self._require_runtime()
        if str(action_id) == "WAIT:SYSTEM":
            return WaitAction("SYSTEM")
        active_side = getattr(runtime, "active_side", None)
        if active_side is None:
            raise ValueError("No active side available to resolve action.")
        for unit in runtime.get_available_units(active_side):
            catalog = ActionCatalog(
                state,
                unit,
                terrain_config=state.game_map.terrain_config,
            )
            for action in catalog.actions():
                current_id = getattr(action, "action_id", None)
                if current_id is None and isinstance(action, WaitAction):
                    current_id = f"WAIT:{getattr(action, 'unit_id', unit.unit_id)}"
                    action.action_id = current_id
                if current_id == action_id:
                    return action
        raise ValueError(f"Action id not legal: {action_id}")

    @staticmethod
    def _terminal_reward(state: GameState) -> float:
        if not state.done:
            return 0.0
        if state.winner is None:
            return 0.0
        return 1.0

    @staticmethod
    def _compute_timeout_winner(state: GameState) -> Optional[str]:
        # Priority 1: scenario VP control score at timeout.
        vp_score: Dict[str, float] = {}
        if state.victory:
            for side in state.turn_order:
                vp_score[side] = 0.0
            for vp in state.victory.points:
                hex_state = state.hex_states.get(vp.hex_coords)
                if hex_state is None:
                    continue
                owner = hex_state.ownership
                for side, side_owner in state.side_to_ownership.items():
                    if owner == side_owner:
                        vp_score[side] += float(vp.per_turn)
                        break
            ranked_vp = sorted(vp_score.items(), key=lambda kv: kv[1], reverse=True)
            if ranked_vp:
                if len(ranked_vp) == 1:
                    return ranked_vp[0][0]
                if abs(ranked_vp[0][1] - ranked_vp[1][1]) > 1e-9:
                    return ranked_vp[0][0]

        # Priority 2: material advantage (alive units, then HP).
        score: Dict[str, float] = {}
        for unit in state.units:
            side = str(getattr(unit, "side", ""))
            if not side:
                continue
            if side not in score:
                score[side] = 0.0
            if bool(getattr(unit, "alive", True)):
                score[side] += 10.0
            hp = getattr(unit, "hp", 0)
            if isinstance(hp, (int, float)):
                score[side] += float(hp)
        if not score:
            return None
        ranked = sorted(score.items(), key=lambda kv: kv[1], reverse=True)
        if len(ranked) > 1 and abs(ranked[0][1] - ranked[1][1]) < 1e-9:
            return None
        return ranked[0][0]

    def _require_runtime(self) -> RuntimeGameState:
        if self._runtime is None:
            raise RuntimeError("Episode not initialized. Call new_episode() first.")
        return self._runtime

    def _require_state(self) -> GameState:
        if self._state is None:
            raise RuntimeError("Episode not initialized. Call new_episode() first.")
        return self._state

    @staticmethod
    def _reaction_window_actions(pending: Dict[str, Any]) -> List[str]:
        reactor_id = str(pending.get("reactor_id", "")).strip()
        target_id = str(pending.get("target_id", "")).strip()
        if not reactor_id or not target_id:
            return []
        return [
            f"{REACTION_USE_PREFIX}:{reactor_id}:{target_id}",
            f"{REACTION_SKIP_PREFIX}:{reactor_id}:{target_id}",
        ]

    @staticmethod
    def _parse_reaction_choice(action_id: str) -> bool | None:
        s = str(action_id or "").strip()
        if s.startswith(f"{REACTION_USE_PREFIX}:"):
            return True
        if s.startswith(f"{REACTION_SKIP_PREFIX}:"):
            return False
        return None

    def reached_turn_limit(self) -> bool:
        state = self._require_state()
        if self._max_turns is None:
            return False
        # Keep parity with RuntimeGameState._check_match_end:
        # terminal-by-turn-limit triggers when current turn exceeds max_turns.
        return int(state.turn) > int(self._max_turns)

    def scenario_max_turns(self) -> Optional[int]:
        return int(self._max_turns) if self._max_turns is not None else None
