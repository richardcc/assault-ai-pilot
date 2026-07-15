from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from assault_bench.runner import (
    _build_eval_decision_summary,
    _build_why_action_vs_vp,
    _run_episode_with_policy,
)


class _SideToken:
    def __init__(self, value: str):
        self.value = value


@dataclass
class _Transition:
    state: object
    reward: float
    done: bool
    info: object = None


class _AdapterStub:
    def __init__(self):
        self._before = self._mk_obs(us_hp=3, ge_hp=2, ge_alive=True)
        self._after = self._mk_obs(us_hp=3, ge_hp=0, ge_alive=False)
        self._obs = self._before

    @staticmethod
    def _mk_obs(*, us_hp: int, ge_hp: int, ge_alive: bool):
        us_side = _SideToken("US")
        ge_side = _SideToken("GE")
        units = [
            SimpleNamespace(unit_id="US_1", side=us_side, hp=float(us_hp), alive=True, q=0, r=0),
            SimpleNamespace(unit_id="GE_1", side=ge_side, hp=float(ge_hp), alive=bool(ge_alive), q=1, r=0),
        ]
        return SimpleNamespace(
            to_play=_SideToken("US"),
            turn=1,
            units=units,
            end_reason="natural_terminal",
            winner=_SideToken("US"),
            side_to_ownership={},
            victory=SimpleNamespace(points=[]),
            terrain_cover_by_hex={},
            terrain_los_block_by_hex={},
        )

    def reset(self, scenario_id: str, seed: int):
        self._obs = self._before
        return self._obs

    def observation(self):
        return self._obs

    def legal_actions(self):
        return ["ATTACK:US_1:GE_1:1:0"]

    def apply(self, action: str):
        self._obs = self._after
        return _Transition(state=self._after, reward=0.0, done=True)


class _AdapterInfoMetricsStub(_AdapterStub):
    def apply(self, action: str):
        self._obs = self._after
        return _Transition(
            state=self._after,
            reward=0.0,
            done=True,
            info={"enemy_damage": 7.0, "enemy_kills": 1.0},
        )


class _AdapterDictUnitsStub(_AdapterStub):
    @staticmethod
    def _mk_obs(*, us_hp: int, ge_hp: int, ge_alive: bool):
        units = [
            {"unit_id": "US_1", "side": "US", "hp": float(us_hp), "alive": True, "q": 0, "r": 0},
            {"unit_id": "GE_1", "side": "GE", "hp": float(ge_hp), "alive": bool(ge_alive), "q": 1, "r": 0},
        ]
        return SimpleNamespace(
            to_play="US",
            turn=1,
            units=units,
            end_reason="natural_terminal",
            winner="US",
            side_to_ownership={},
            victory=SimpleNamespace(points=[]),
            terrain_cover_by_hex={},
            terrain_los_block_by_hex={},
        )


class _AdapterZeroLegacyInfoStub(_AdapterDictUnitsStub):
    def apply(self, action: str):
        self._obs = self._after
        return _Transition(
            state=self._after,
            reward=0.0,
            done=True,
            info={"enemy_damage": 0.0, "enemy_kills": 0.0},
        )


def test_benchmark_trace_keeps_nonzero_damage_kills_with_enum_like_sides():
    adapter = _AdapterStub()
    (
        _seed,
        _ret,
        _steps,
        _terminal,
        _timeout,
        _win,
        _terminal_reason,
        _initial_vp_by_side,
        _final_vp_by_side,
        _winner_side,
        _scenario_outcome,
        _phase29_summary,
        trace_rows,
    ) = _run_episode_with_policy(
        adapter=adapter,
        scenario_id="stub_scenario",
        seed=7,
        policy_name="random",
        policy_by_side={"US": "random", "GE": "random"},
        max_steps=2,
        max_steps_override=2,
        mcts_simulations=8,
        mcts_c_puct=1.5,
        mcts_temperature=1.0,
        model=None,
        action_dim=32,
        mcts_unroll_steps=1,
        mcts_discount=0.997,
        collect_flow_metrics=True,
    )

    assert len(trace_rows) == 1
    row = dict(trace_rows[0] or {})
    assert row["damage_dealt"] == 2.0
    assert row["kills_dealt"] == 1
    assert row["unit_side"] == "US"

    summary, _top = _build_eval_decision_summary(trace_rows)
    by_kind = dict(summary.get("by_action_kind", {}) or {})
    assert by_kind["ATTACK"]["damage_sum"] == 2.0
    assert by_kind["ATTACK"]["kills_sum"] == 1.0


def test_run_episode_reads_enemy_metrics_from_transition_info():
    adapter = _AdapterInfoMetricsStub()
    (
        _seed,
        _ret,
        _steps,
        _terminal,
        _timeout,
        _win,
        _terminal_reason,
        _initial_vp_by_side,
        _final_vp_by_side,
        _winner_side,
        _scenario_outcome,
        _phase29_summary,
        trace_rows,
    ) = _run_episode_with_policy(
        adapter=adapter,
        scenario_id="stub_scenario",
        seed=9,
        policy_name="random",
        policy_by_side={"US": "random", "GE": "random"},
        max_steps=2,
        max_steps_override=2,
        mcts_simulations=8,
        mcts_c_puct=1.5,
        mcts_temperature=1.0,
        model=None,
        action_dim=32,
        mcts_unroll_steps=1,
        mcts_discount=0.997,
        collect_flow_metrics=True,
    )

    assert len(trace_rows) == 1
    row = dict(trace_rows[0] or {})
    assert row["damage_dealt"] == 7.0
    assert row["kills_dealt"] == 1


def test_run_episode_derives_damage_from_dict_unit_snapshots():
    adapter = _AdapterDictUnitsStub()
    (*_, trace_rows) = _run_episode_with_policy(
        adapter=adapter,
        scenario_id="stub_scenario",
        seed=11,
        policy_name="random",
        policy_by_side={"US": "random", "GE": "random"},
        max_steps=2,
        max_steps_override=2,
        mcts_simulations=8,
        mcts_c_puct=1.5,
        mcts_temperature=1.0,
        model=None,
        action_dim=32,
        mcts_unroll_steps=1,
        mcts_discount=0.997,
        collect_flow_metrics=True,
    )
    row = dict(trace_rows[0] or {})
    assert row["damage_dealt"] == 2.0
    assert row["kills_dealt"] == 1


def test_run_episode_legacy_zero_info_does_not_clobber_real_damage():
    adapter = _AdapterZeroLegacyInfoStub()
    (*_, trace_rows) = _run_episode_with_policy(
        adapter=adapter,
        scenario_id="stub_scenario",
        seed=12,
        policy_name="random",
        policy_by_side={"US": "random", "GE": "random"},
        max_steps=2,
        max_steps_override=2,
        mcts_simulations=8,
        mcts_c_puct=1.5,
        mcts_temperature=1.0,
        model=None,
        action_dim=32,
        mcts_unroll_steps=1,
        mcts_discount=0.997,
        collect_flow_metrics=True,
    )
    row = dict(trace_rows[0] or {})
    assert row["damage_dealt"] == 2.0
    assert row["kills_dealt"] == 1


def test_decision_ownership_prefers_policy_override_signal_when_present():
    trace_rows = [
        {
            "action_kind": "MOVE",
            "unit_side": "US",
            "action_id": "MOVE:US_1:1:0",
            "requested_action_id": "MOVE:US_1:1:0",
            "action_mismatch": False,
            "policy_overridden_by_mcts": 1,
            "damage_dealt": 0.0,
            "kills_dealt": 0.0,
        },
        {
            "action_kind": "ATTACK",
            "unit_side": "US",
            "action_id": "ATTACK:US_1:GE_1:1:0",
            "requested_action_id": "ATTACK:US_1:GE_1:1:0",
            "action_mismatch": False,
            "policy_overridden_by_mcts": 0,
            "damage_dealt": 1.0,
            "kills_dealt": 0.0,
        },
    ]
    summary, _top = _build_eval_decision_summary(trace_rows)
    ownership = dict(summary.get("decision_ownership_by_side", {}) or {})
    us = dict(ownership.get("US", {}) or {})
    assert us["rows"] == 2
    assert us["overwritten"] == 1
    assert us["policy_kept"] == 1
    assert us["override_signal_rows"] == 2
    assert us["legacy_fallback_rows"] == 0


def test_decision_ownership_falls_back_to_execution_mismatch_for_legacy_rows():
    trace_rows = [
        {
            "action_kind": "MOVE",
            "unit_side": "GE",
            "action_id": "MOVE:GE_1:2:0",
            "requested_action_id": "MOVE:GE_1:2:0",
            "action_mismatch": False,
            "policy_overridden_by_mcts": None,
            "damage_dealt": 0.0,
            "kills_dealt": 0.0,
        },
        {
            "action_kind": "MOVE",
            "unit_side": "GE",
            "action_id": "MOVE:GE_1:2:1",
            "requested_action_id": "MOVE:GE_1:9:9",
            "action_mismatch": False,
            "policy_overridden_by_mcts": None,
            "damage_dealt": 0.0,
            "kills_dealt": 0.0,
        },
    ]
    summary, _top = _build_eval_decision_summary(trace_rows)
    ownership = dict(summary.get("decision_ownership_by_side", {}) or {})
    ge = dict(ownership.get("GE", {}) or {})
    assert ge["rows"] == 2
    assert ge["policy_kept"] == 1
    assert ge["overwritten"] == 1
    assert ge["override_signal_rows"] == 0
    assert ge["legacy_fallback_rows"] == 2
    source = dict(summary.get("decision_ownership_source", {}) or {})
    assert source["primary_signal"] == "policy_overridden_by_mcts"
    assert source["fallback_signal"] == "execution_mismatch"
    mismatch_total = dict(summary.get("execution_mismatch_total", {}) or {})
    assert mismatch_total["execution_mismatch"] == 1


def test_eval_decision_summary_accepts_legacy_damage_kills_keys():
    trace_rows = [
        {
            "action_kind": "ATTACK",
            "unit_side": "US",
            "action_id": "ATTACK:US_1:GE_1:1:0",
            "requested_action_id": "ATTACK:US_1:GE_1:1:0",
            "action_mismatch": False,
            "policy_overridden_by_mcts": 0,
            "damage": 3.0,
            "kills": 1.0,
        },
        {
            "action_kind": "ATTACK",
            "unit_side": "US",
            "action_id": "ATTACK:US_1:GE_1:1:0",
            "requested_action_id": "ATTACK:US_1:GE_1:1:0",
            "action_mismatch": False,
            "policy_overridden_by_mcts": 0,
            "damage_dealt": 2.0,
            "kills_dealt": 0.0,
        },
    ]
    summary, _top = _build_eval_decision_summary(trace_rows)
    by_kind = dict(summary.get("by_action_kind", {}) or {})
    assert by_kind["ATTACK"]["damage_sum"] == 5.0
    assert by_kind["ATTACK"]["kills_sum"] == 1.0
    by_kind_side = dict(summary.get("by_action_kind_and_side", {}) or {})
    us_attack = dict(by_kind_side.get("ATTACK|US", {}) or {})
    assert us_attack["damage_sum"] == 5.0
    assert us_attack["kills_sum"] == 1.0


def test_eval_decision_summary_accepts_enemy_damage_kills_keys():
    trace_rows = [
        {
            "action_kind": "ATTACK",
            "unit_side": "US",
            "action_id": "ATTACK:US_1:GE_1:1:0",
            "requested_action_id": "ATTACK:US_1:GE_1:1:0",
            "action_mismatch": False,
            "policy_overridden_by_mcts": 0,
            "enemy_damage": 4.0,
            "enemy_kills": 1.0,
        },
        {
            "action_kind": "ATTACK",
            "unit_side": "US",
            "action_id": "ATTACK:US_1:GE_2:1:1",
            "requested_action_id": "ATTACK:US_1:GE_2:1:1",
            "action_mismatch": False,
            "policy_overridden_by_mcts": 0,
            "enemy_damage": 2.0,
            "enemy_kills": 0.0,
        },
    ]
    summary, _top = _build_eval_decision_summary(trace_rows)
    by_kind = dict(summary.get("by_action_kind", {}) or {})
    assert by_kind["ATTACK"]["damage_sum"] == 6.0
    assert by_kind["ATTACK"]["kills_sum"] == 1.0
    by_kind_side = dict(summary.get("by_action_kind_and_side", {}) or {})
    us_attack = dict(by_kind_side.get("ATTACK|US", {}) or {})
    assert us_attack["damage_sum"] == 6.0
    assert us_attack["kills_sum"] == 1.0


def test_build_why_action_vs_vp_returns_topk_and_explanation():
    out = _build_why_action_vs_vp(
        legal_actions=[
            "MOVE:US_1:2:2",
            "MOVE:US_1:4:4",
            "WAIT:US_1",
        ],
        chosen_action="MOVE:US_1:4:4",
        priors_by_action={
            "MOVE:US_1:2:2": 0.55,
            "MOVE:US_1:4:4": 0.35,
            "WAIT:US_1": 0.10,
        },
        values_by_action={
            "MOVE:US_1:2:2": 0.10,
            "MOVE:US_1:4:4": 0.45,
            "WAIT:US_1": 0.02,
        },
        value_sign_by_action={},
        visits_by_action={
            "MOVE:US_1:2:2": 12,
            "MOVE:US_1:4:4": 4,
            "WAIT:US_1": 1,
        },
        c_puct=1.5,
        dynamics_pred_reward=0.15,
        acting_unit_q=3,
        acting_unit_r=3,
        vp_hexes=[{"q": 2, "r": 2, "vp_id": "VP_A"}],
        top_k=2,
    )
    assert out["top_k"] == 2
    assert out["chosen_action_id"] == "MOVE:US_1:4:4"
    assert out["vp_best_action_id"] == "MOVE:US_1:2:2"
    assert len(out["candidate_actions"]) == 2
    assert isinstance(out["delta_score"], float)
    assert isinstance(out["explanation"], str) and out["explanation"]
