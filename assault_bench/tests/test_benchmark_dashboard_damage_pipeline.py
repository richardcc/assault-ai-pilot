from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from assault_bench.runner import (
    _backfill_why_action_vs_vp_from_observed_transition,
    _build_eval_decision_summary,
    _build_eval_decision_steps_top,
    _resolve_vp_horizon_selected_fields,
    _select_action_with_probability_tie_break,
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
        self._done = False
        self.sim = SimpleNamespace(
            _state=SimpleNamespace(
                side_to_ownership={},
                victory=SimpleNamespace(points=[]),
                hex_states={},
            ),
            _runtime=SimpleNamespace(
                scenario=SimpleNamespace(victory_outcomes={}),
            ),
            reached_turn_limit=lambda: False,
            scenario_max_turns=lambda: 0,
        )

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
        self._done = False
        return self._obs

    def initial_state(self, scenario_id: str, seed: int):
        # Runner contract now expects initial_state().
        return self.reset(scenario_id=scenario_id, seed=seed)

    def observation(self):
        return self._obs

    def legal_actions(self):
        return ["ATTACK:US_1:GE_1:1:0"]

    def apply(self, action: str):
        self._obs = self._after
        self._done = True
        return _Transition(state=self._after, reward=0.0, done=True)

    def terminal(self):
        return bool(self._done)


class _AdapterInfoMetricsStub(_AdapterStub):
    def apply(self, action: str):
        self._obs = self._after
        return _Transition(
            state=self._after,
            reward=0.0,
            done=True,
            info={"enemy_damage": 7.0, "enemy_kills": 1.0},
        )


class _AdapterDiceInfoStub(_AdapterStub):
    def __init__(self):
        super().__init__()
        self._before = self._mk_obs_dict(us_hp=3, ge_hp=2, ge_alive=True)
        self._after = self._mk_obs_dict(us_hp=3, ge_hp=0, ge_alive=False)
        self._obs = self._before
        self._done = False

    @staticmethod
    def _mk_obs_dict(*, us_hp: int, ge_hp: int, ge_alive: bool):
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
            vp_hexes=[],
            vp_owner_by_hex={},
        )

    def apply(self, action: str):
        self._obs = self._after
        self._done = True
        return _Transition(
            state=self._after,
            reward=0.0,
            done=True,
            info={
                "runtime_events": [
                    {
                        "type": "ACTION_EFFECT",
                        "payload": {
                            "attacker": "US_1",
                            "attacker_attack_dice": [
                                {"color": "red", "faces": ["hit", "suppression"]},
                                {"color": "black", "faces": ["hit"]},
                            ],
                            "defender_defense_dice": [
                                {"color": "blue", "faces": ["block"]},
                            ],
                        },
                    }
                ]
            },
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


class _AdapterUnitPrefilterInfoStub(_AdapterDictUnitsStub):
    def apply(self, action: str):
        self._obs = self._after
        return _Transition(
            state=self._after,
            reward=0.0,
            done=True,
            info={
                "unit_prefilter_enabled": True,
                "unit_prefilter_selected_unit_id": "US_1",
                "unit_prefilter_constrained_count": 2,
                "unit_prefilter_global_count": 5,
            },
        )


class _AdapterReactionComponentsInfoStub(_AdapterDictUnitsStub):
    def __init__(self, *, include_reaction_exposure: bool):
        super().__init__()
        self._include_reaction_exposure = bool(include_reaction_exposure)

    def apply(self, action: str):
        self._obs = self._after
        info = {
            "reward_components": {
                "reaction_fire_miss": -0.05,
                "opportunity_fire_no_progress": 0.02,
                "opportunity_skip_capture_preserve": 0.01,
            }
        }
        if self._include_reaction_exposure:
            info["reaction_exposure_component"] = -0.12
        return _Transition(
            state=self._after,
            reward=0.0,
            done=True,
            info=info,
        )


class _AdapterHiddenEnemyRuntimeEventStub(_AdapterStub):
    @staticmethod
    def _mk_obs(*, us_hp: int, ge_hp: int, ge_alive: bool):
        del ge_hp, ge_alive
        units = [
            {"unit_id": "US_1", "side": "US", "hp": float(us_hp), "alive": True, "q": 0, "r": 0},
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

    def apply(self, action: str):
        self._obs = self._after
        self._done = True
        return _Transition(
            state=self._after,
            reward=0.0,
            done=True,
            info={
                "damage_dealt": 0.0,
                "kills_dealt": 0,
                "runtime_events": [
                    {
                        "type": "ACTION_EFFECT",
                        "payload": {
                            "attacker": "US_1",
                            "defender": "GE_1",
                            "attacker_effects": {"damage": 3},
                            "defender_killed": True,
                        },
                    }
                ],
            },
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


def test_run_episode_preserves_per_die_attack_defense_components():
    adapter = _AdapterDiceInfoStub()
    (*_, trace_rows) = _run_episode_with_policy(
        adapter=adapter,
        scenario_id="stub_scenario",
        seed=10,
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
    assert len(list(row.get("attack_dice_rolls", []) or [])) == 2
    assert len(list(row.get("defense_dice_rolls", []) or [])) == 1
    assert dict(row.get("attack_components_by_die", {}) or {}).get("HIT", 0) == 2
    assert dict(row.get("defense_components_by_die", {}) or {}).get("BLOCK", 0) == 1
    assert len(list(row.get("dice_rolls", []) or [])) == 3
    assert len(list(row.get("runtime_events", []) or [])) == 1


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


def test_run_episode_prefers_runtime_events_when_obs_enemy_hidden_and_info_zero():
    adapter = _AdapterHiddenEnemyRuntimeEventStub()
    (*_, trace_rows) = _run_episode_with_policy(
        adapter=adapter,
        scenario_id="stub_scenario",
        seed=13,
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
    assert row["damage_dealt"] == 3.0
    assert row["kills_dealt"] == 1


def test_run_episode_seed_start_populates_legal_actions_for_backfill_path():
    adapter = _AdapterStub()
    (*_, trace_rows) = _run_episode_with_policy(
        adapter=adapter,
        scenario_id="stub_scenario",
        seed=1,
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
    assert isinstance(row.get("why_action_vs_vp"), dict)
    assert row.get("legal_actions") == ["ATTACK:US_1:GE_1:1:0"]


def test_run_episode_emits_canonical_decision_fields_without_model() -> None:
    adapter = _AdapterDictUnitsStub()
    (*_, trace_rows) = _run_episode_with_policy(
        adapter=adapter,
        scenario_id="stub_scenario",
        seed=21,
        policy_name="muzero_stub",
        policy_by_side={"US": "muzero_stub", "GE": "muzero_stub"},
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
    candidates = list(row.get("mcts_action_candidates", []) or [])
    assert candidates
    chosen = next(
        (c for c in candidates if str(c.get("action_id", "")) == str(row.get("action_id", ""))),
        {},
    )
    for key in (
        "real_decision_score",
        "decision_rank",
        "visit_count",
        "selected_by",
        "mcts_q_value",
        "mcts_u_value",
        "mcts_success_prob_proxy",
        "mcts_success_component",
        "mcts_puct_score",
        "decision_components",
    ):
        assert key in chosen
    assert row.get("real_decision_score", None) is not None


def test_run_episode_emits_vp_horizon_fields_for_selected_candidate() -> None:
    adapter = _AdapterDictUnitsStub()
    (*_, trace_rows) = _run_episode_with_policy(
        adapter=adapter,
        scenario_id="stub_scenario",
        seed=22,
        policy_name="muzero_stub",
        policy_by_side={"US": "muzero_stub", "GE": "muzero_stub"},
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
    assert "vp_horizon_steps" in row
    assert "vp_horizon_signal" in row
    assert "vp_horizon_decision_component" in row
    candidates = list(row.get("mcts_action_candidates", []) or [])
    chosen = next(
        (c for c in candidates if str(c.get("action_id", "")) == str(row.get("action_id", ""))),
        {},
    )
    dc = dict(chosen.get("decision_components", {}) or {})
    assert isinstance(dc, dict)
    assert "vp_horizon_steps" in dc
    assert "vp_horizon_signal" in dc
    assert "vp_horizon_component" in dc


def test_run_episode_fills_obs_enemy_reaction_fire_risk_from_proximity_fallback() -> None:
    adapter = _AdapterDictUnitsStub()
    (*_, trace_rows) = _run_episode_with_policy(
        adapter=adapter,
        scenario_id="stub_scenario",
        seed=25,
        policy_name="muzero_stub",
        policy_by_side={"US": "muzero_stub", "GE": "muzero_stub"},
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
    risk = float(row.get("obs_enemy_reaction_fire_risk", 0.0) or 0.0)
    assert risk > 0.0
    assert risk <= 1.0


def test_run_episode_computes_vp_horizon_when_producer_fields_missing() -> None:
    adapter = _AdapterDictUnitsStub()
    (*_, trace_rows) = _run_episode_with_policy(
        adapter=adapter,
        scenario_id="stub_scenario",
        seed=26,
        policy_name="muzero_stub",
        policy_by_side={"US": "muzero_stub", "GE": "muzero_stub"},
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
    assert row.get("vp_horizon_available", None) is True
    assert str(row.get("vp_horizon_source", "")).startswith("computed_")
    assert row.get("vp_horizon_steps", None) is not None
    assert row.get("vp_horizon_signal", None) is not None
    assert row.get("vp_horizon_component", None) is not None


def test_run_episode_computes_reaction_components_when_producer_fields_missing() -> None:
    adapter = _AdapterDictUnitsStub()
    (*_, trace_rows) = _run_episode_with_policy(
        adapter=adapter,
        scenario_id="stub_scenario",
        seed=27,
        policy_name="muzero_stub",
        policy_by_side={"US": "muzero_stub", "GE": "muzero_stub"},
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
    assert row.get("reaction_fire_soft_reward_component_available", None) is True
    assert str(row.get("reaction_fire_soft_reward_component_source", "")).startswith("computed_")
    assert row.get("reaction_exposure_component_available", None) is True
    assert str(row.get("reaction_exposure_component_source", "")).startswith("computed_")


def test_run_episode_computes_reaction_exposure_when_producer_field_missing() -> None:
    adapter = _AdapterReactionComponentsInfoStub(include_reaction_exposure=False)
    (*_, trace_rows) = _run_episode_with_policy(
        adapter=adapter,
        scenario_id="stub_scenario",
        seed=23,
        policy_name="muzero_stub",
        policy_by_side={"US": "muzero_stub", "GE": "muzero_stub"},
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
    assert row.get("reaction_exposure_component", None) is not None
    assert row.get("reaction_exposure_component_available", None) is True
    assert str(row.get("reaction_exposure_component_source", "")).startswith("computed_")


def test_run_episode_derives_reaction_fire_soft_component_from_reward_components() -> None:
    adapter = _AdapterReactionComponentsInfoStub(include_reaction_exposure=True)
    (*_, trace_rows) = _run_episode_with_policy(
        adapter=adapter,
        scenario_id="stub_scenario",
        seed=24,
        policy_name="muzero_stub",
        policy_by_side={"US": "muzero_stub", "GE": "muzero_stub"},
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
    assert row.get("reaction_fire_soft_reward_component_available", None) is True
    assert str(row.get("reaction_fire_soft_reward_component_source", "")) == (
        "transition_info.reward_components.reaction_sum"
    )
    # -0.05 + 0.02 + 0.01
    assert abs(float(row.get("reaction_fire_soft_reward_component", 0.0)) - (-0.02)) <= 1e-12


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
    assert us["unknown_override_rows"] == 0


def test_decision_ownership_marks_unknown_when_override_signal_missing():
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
    assert ge["policy_kept"] == 0
    assert ge["overwritten"] == 0
    assert ge["override_signal_rows"] == 0
    assert ge["unknown_override_rows"] == 2
    source = dict(summary.get("decision_ownership_source", {}) or {})
    assert source["primary_signal"] == "policy_overridden_by_mcts"
    assert source["unknown_override_rows"] == 2
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


def test_eval_decision_summary_builds_attack_effectiveness_calibration_metrics():
    trace_rows = [
        {
            "action_kind": "ATTACK",
            "unit_side": "US",
            "unit_label": "US_INF",
            "action_id": "ATTACK:US_1:GE_1:2:2",
            "damage_dealt": 3.0,
            "kills_dealt": 1.0,
            "chosen_action_prob": 0.80,
            "attack_distance_mean": 2.0,
            "attack_target_cover_mean": 0.20,
        },
        {
            "action_kind": "ATTACK",
            "unit_side": "US",
            "unit_label": "US_INF",
            "action_id": "ATTACK:US_1:GE_2:4:4",
            "damage_dealt": 0.0,
            "kills_dealt": 0.0,
            "chosen_action_prob": 0.60,
            "attack_distance_mean": 4.0,
            "attack_target_cover_mean": 0.70,
        },
    ]
    summary, _top = _build_eval_decision_summary(trace_rows)
    eff = dict(summary.get("attack_effectiveness", {}) or {})
    global_eff = dict(eff.get("global", {}) or {})
    assert global_eff.get("count", 0) == 2
    assert float(global_eff.get("empirical_expected_damage", 0.0)) == 1.5
    assert float(global_eff.get("damage_variance", 0.0)) >= 0.0
    assert 0.0 <= float(global_eff.get("exchange_win_rate", 0.0)) <= 1.0
    assert "by_action_kind" in eff
    assert "calibration_bins" in eff


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


def test_build_why_action_vs_vp_emits_canonical_decision_fields_per_candidate() -> None:
    out = _build_why_action_vs_vp(
        legal_actions=["MOVE:US_1:2:2", "WAIT:US_1"],
        chosen_action="MOVE:US_1:2:2",
        priors_by_action={"MOVE:US_1:2:2": 0.7, "WAIT:US_1": 0.3},
        values_by_action={"MOVE:US_1:2:2": 0.2, "WAIT:US_1": 0.1},
        value_sign_by_action={},
        visits_by_action={"MOVE:US_1:2:2": 3, "WAIT:US_1": 2},
        c_puct=1.5,
        dynamics_pred_reward=None,
        acting_unit_q=3,
        acting_unit_r=3,
        vp_hexes=[{"q": 2, "r": 2, "vp_id": "VP_A"}],
        top_k=2,
    )
    candidates = list(out.get("candidate_actions", []) or [])
    assert candidates
    for c in candidates:
        row = dict(c or {})
        for key in (
            "real_decision_score",
            "visit_count",
            "mcts_q_value",
            "mcts_u_value",
            "selected_by",
            "decision_criterion",
            "decision_components",
        ):
            assert key in row
        assert isinstance(row.get("decision_components", None), dict)
        assert "visits" not in row


def test_build_why_action_vs_vp_stationary_actions_report_zero_delta():
    out = _build_why_action_vs_vp(
        legal_actions=["WAIT:US_1", "PASS:US_1"],
        chosen_action="WAIT:US_1",
        priors_by_action={"WAIT:US_1": 0.7, "PASS:US_1": 0.3},
        values_by_action={"WAIT:US_1": 0.2, "PASS:US_1": 0.1},
        value_sign_by_action={},
        visits_by_action={"WAIT:US_1": 3, "PASS:US_1": 2},
        c_puct=1.5,
        dynamics_pred_reward=None,
        acting_unit_q=3,
        acting_unit_r=3,
        vp_hexes=[{"q": 2, "r": 2, "vp_id": "VP_A"}],
        top_k=2,
    )
    by_action = {str(c.get("action_id", "")): c for c in list(out.get("candidate_actions", []) or [])}
    assert float(by_action["WAIT:US_1"]["vp_progress_delta"]) == 0.0
    assert float(by_action["PASS:US_1"]["vp_progress_delta"]) == 0.0


def test_build_why_action_vs_vp_marks_no_vp_context_explicitly():
    out = _build_why_action_vs_vp(
        legal_actions=["MOVE:US_1:2:2", "WAIT:US_1"],
        chosen_action="MOVE:US_1:2:2",
        priors_by_action={"MOVE:US_1:2:2": 0.7, "WAIT:US_1": 0.3},
        values_by_action={"MOVE:US_1:2:2": 0.2, "WAIT:US_1": 0.1},
        value_sign_by_action={},
        visits_by_action={"MOVE:US_1:2:2": 3, "WAIT:US_1": 2},
        c_puct=1.5,
        dynamics_pred_reward=None,
        acting_unit_q=3,
        acting_unit_r=3,
        vp_hexes=[],
        top_k=2,
    )
    by_action = {str(c.get("action_id", "")): c for c in list(out.get("candidate_actions", []) or [])}
    assert str(by_action["MOVE:US_1:2:2"].get("vp_progress_source", "")) == "unavailable_no_vp_context"
    assert str(by_action["WAIT:US_1"].get("vp_progress_source", "")) == "unavailable_no_vp_context"


def test_backfill_why_action_vs_vp_uses_observed_progress_when_unparseable():
    base = _build_why_action_vs_vp(
        legal_actions=["MOVE:US_1:abc:def", "WAIT:US_1"],
        chosen_action="MOVE:US_1:abc:def",
        priors_by_action={"MOVE:US_1:abc:def": 0.8, "WAIT:US_1": 0.2},
        values_by_action={"MOVE:US_1:abc:def": 0.6, "WAIT:US_1": 0.1},
        value_sign_by_action={},
        visits_by_action={"MOVE:US_1:abc:def": 3, "WAIT:US_1": 1},
        c_puct=1.5,
        dynamics_pred_reward=None,
        acting_unit_q=3,
        acting_unit_r=3,
        vp_hexes=[{"q": 2, "r": 2, "vp_id": "VP_A"}],
        top_k=2,
    )
    out = _backfill_why_action_vs_vp_from_observed_transition(
        why_action_vs_vp=base,
        chosen_action="MOVE:US_1:abc:def",
        objective_progress_delta=1.0,
    )
    by_action = {str(c.get("action_id", "")): c for c in list(out.get("candidate_actions", []) or [])}
    assert float(by_action["MOVE:US_1:abc:def"]["vp_progress_delta"]) == 1.0
    assert str(by_action["MOVE:US_1:abc:def"].get("vp_progress_source", "")).strip()
    assert str(out.get("explanation", "")).strip() != "N/A (missing VP candidate telemetry)"


def test_backfill_why_action_vs_vp_move_never_null_with_mixed_missing_fields():
    out = _backfill_why_action_vs_vp_from_observed_transition(
        why_action_vs_vp={
            "top_k": 5,
            "chosen_action_id": "MOVE:US_1:bad:q",
            "vp_best_action_id": "",
            "delta_score": None,
            "score_components_priority": [],
            "explanation": "N/A (legacy telemetry)",
            "candidate_actions": [],
        },
        chosen_action="MOVE:US_1:bad:q",
        objective_progress_delta=None,
        objective_best_vp_id="",
        legal_actions=[
            "MOVE:US_2:2:2",  # mixed-unit candidate must be ignored
            "MOVE:US_1:bad:q",  # unparseable move id should still be accepted deterministically
            "MOVE:US_1:5:6",
            "WAIT:US_1",
        ],
    )
    assert str(out.get("vp_best_action_id", "")).strip() == "MOVE:US_1:bad:q"
    cand_ids = [str(c.get("action_id", "")) for c in list(out.get("candidate_actions", []) or [])]
    assert "MOVE:US_1:bad:q" in cand_ids
    assert "MOVE:US_1:5:6" in cand_ids
    assert "MOVE:US_2:2:2" not in cand_ids
    assert str(out.get("explanation", "")).strip()


def test_build_why_action_vs_vp_emits_vp_source_for_all_candidates():
    out = _build_why_action_vs_vp(
        legal_actions=["MOVE:US_1:2:2", "WAIT:US_1", "MOVE:US_1:abc:def"],
        chosen_action="WAIT:US_1",
        priors_by_action={"MOVE:US_1:2:2": 0.4, "WAIT:US_1": 0.4, "MOVE:US_1:abc:def": 0.2},
        values_by_action={"MOVE:US_1:2:2": 0.1, "WAIT:US_1": 0.2, "MOVE:US_1:abc:def": 0.0},
        value_sign_by_action={},
        visits_by_action={"MOVE:US_1:2:2": 4, "WAIT:US_1": 2, "MOVE:US_1:abc:def": 1},
        c_puct=1.5,
        dynamics_pred_reward=None,
        acting_unit_q=3,
        acting_unit_r=3,
        vp_hexes=[{"q": 2, "r": 2, "vp_id": "VP_A"}],
        top_k=3,
    )
    candidates = list(out.get("candidate_actions", []) or [])
    assert candidates
    for c in candidates:
        assert "vp_progress_delta" in c
        assert "vp_progress_source" in c
        assert isinstance(c.get("vp_progress_delta", None), float)
        assert str(c.get("vp_progress_source", "")).strip()


def test_build_why_action_vs_vp_move_unparseable_uses_state_fallback_when_state_available():
    out = _build_why_action_vs_vp(
        legal_actions=["MOVE:US_1:abc:def", "WAIT:US_1"],
        chosen_action="MOVE:US_1:abc:def",
        priors_by_action={"MOVE:US_1:abc:def": 0.6, "WAIT:US_1": 0.4},
        values_by_action={"MOVE:US_1:abc:def": 0.2, "WAIT:US_1": 0.1},
        value_sign_by_action={},
        visits_by_action={"MOVE:US_1:abc:def": 3, "WAIT:US_1": 2},
        c_puct=1.5,
        dynamics_pred_reward=None,
        acting_unit_q=3,
        acting_unit_r=3,
        vp_hexes=[{"q": 2, "r": 2, "vp_id": "VP_A"}],
        top_k=2,
    )
    by_action = {str(c.get("action_id", "")): c for c in list(out.get("candidate_actions", []) or [])}
    move_row = dict(by_action["MOVE:US_1:abc:def"] or {})
    assert str(move_row.get("vp_progress_source", "")) == "state_fallback"
    assert float(move_row.get("vp_progress_delta", 0.0)) == 0.0


def test_build_why_action_vs_vp_reconstructs_actor_from_step_snapshot_units():
    out = _build_why_action_vs_vp(
        legal_actions=["MOVE:US_1:2:2", "WAIT:US_1"],
        chosen_action="MOVE:US_1:2:2",
        priors_by_action={"MOVE:US_1:2:2": 0.6, "WAIT:US_1": 0.4},
        values_by_action={"MOVE:US_1:2:2": 0.2, "WAIT:US_1": 0.1},
        value_sign_by_action={},
        visits_by_action={"MOVE:US_1:2:2": 3, "WAIT:US_1": 2},
        c_puct=1.5,
        dynamics_pred_reward=None,
        acting_unit_q=None,
        acting_unit_r=None,
        step_units_snapshot=[
            {"unitId": "US_1", "position": {"hexQ": 3, "hexR": 3}},
        ],
        vp_hexes=[{"q": 0, "r": 0, "vp_id": "VP_A"}],
        top_k=2,
    )
    by_action = {str(c.get("action_id", "")): c for c in list(out.get("candidate_actions", []) or [])}
    move_row = dict(by_action["MOVE:US_1:2:2"] or {})
    assert str(move_row.get("vp_progress_source", "")) == "target_hex_parse"
    assert float(move_row.get("vp_progress_delta", 0.0)) > 0.0


def test_build_why_action_vs_vp_keeps_chosen_visible_when_outside_topk():
    out = _build_why_action_vs_vp(
        legal_actions=["MOVE:US_3:13:7", "MOVE:US_3:15:7", "MOVE:US_4:14:7"],
        chosen_action="MOVE:US_3:13:7",
        priors_by_action={
            "MOVE:US_3:13:7": 0.05,
            "MOVE:US_3:15:7": 0.45,
            "MOVE:US_4:14:7": 0.50,
        },
        values_by_action={
            "MOVE:US_3:13:7": 0.0,
            "MOVE:US_3:15:7": 0.0,
            "MOVE:US_4:14:7": 0.0,
        },
        value_sign_by_action={},
        visits_by_action={
            "MOVE:US_3:13:7": 20,
            "MOVE:US_3:15:7": 1,
            "MOVE:US_4:14:7": 1,
        },
        c_puct=1.5,
        dynamics_pred_reward=None,
        acting_unit_q=14,
        acting_unit_r=8,
        vp_hexes=[{"q": 2, "r": 6, "vp_id": "VP_2_2,6"}],
        top_k=2,
    )
    cand_ids = [str(c.get("action_id", "")) for c in list(out.get("candidate_actions", []) or [])]
    assert len(cand_ids) == 2
    assert "MOVE:US_3:13:7" in cand_ids


def test_build_why_action_vs_vp_selects_vp_best_from_acting_unit_move_candidates_only():
    out = _build_why_action_vs_vp(
        legal_actions=[
            "MOVE:US_1:2:2",
            "MOVE:US_1:4:4",
            "MOVE:US_2:2:2",
            "WAIT:US_1",
        ],
        chosen_action="MOVE:US_1:4:4",
        priors_by_action={
            "MOVE:US_1:2:2": 0.20,
            "MOVE:US_1:4:4": 0.30,
            "MOVE:US_2:2:2": 0.99,
            "WAIT:US_1": 0.01,
        },
        values_by_action={
            "MOVE:US_1:2:2": 0.05,
            "MOVE:US_1:4:4": 0.15,
            "MOVE:US_2:2:2": 1.00,
            "WAIT:US_1": 0.00,
        },
        value_sign_by_action={},
        visits_by_action={
            "MOVE:US_1:2:2": 5,
            "MOVE:US_1:4:4": 6,
            "MOVE:US_2:2:2": 1,
            "WAIT:US_1": 1,
        },
        c_puct=1.5,
        dynamics_pred_reward=None,
        acting_unit_q=3,
        acting_unit_r=3,
        vp_hexes=[{"q": 2, "r": 2, "vp_id": "VP_A"}],
        top_k=4,
    )
    assert out["vp_best_action_id"] == "MOVE:US_1:2:2"
    assert out["vp_best_action_id"] != "MOVE:US_2:2:2"
    assert out["delta_score"] is not None
    assert str(out["explanation"]).strip() != "N/A (missing VP candidate telemetry)"


def test_build_why_action_vs_vp_deterministic_fallback_uses_chosen_when_move_scoring_missing():
    out = _build_why_action_vs_vp(
        legal_actions=[
            "MOVE:US_1:abc:def",
            "MOVE:US_1:ghi:jkl",
            "WAIT:US_1",
        ],
        chosen_action="MOVE:US_1:abc:def",
        priors_by_action={
            "MOVE:US_1:abc:def": 0.4,
            "MOVE:US_1:ghi:jkl": 0.4,
            "WAIT:US_1": 0.2,
        },
        values_by_action={
            "MOVE:US_1:abc:def": 0.1,
            "MOVE:US_1:ghi:jkl": 0.1,
            "WAIT:US_1": 0.0,
        },
        value_sign_by_action={},
        visits_by_action={
            "MOVE:US_1:abc:def": 2,
            "MOVE:US_1:ghi:jkl": 2,
            "WAIT:US_1": 1,
        },
        c_puct=1.5,
        dynamics_pred_reward=None,
        acting_unit_q=None,
        acting_unit_r=None,
        vp_hexes=[{"q": 2, "r": 2, "vp_id": "VP_A"}],
        top_k=3,
    )
    assert out["vp_best_action_id"] == "MOVE:US_1:abc:def"
    assert out["delta_score"] == 0.0
    assert out["explanation"] == "selected action is also best toward VP"


def test_build_why_action_vs_vp_rescales_large_q_values_for_diagnostics():
    out = _build_why_action_vs_vp(
        legal_actions=["MOVE:US_1:2:2", "WAIT:US_1"],
        chosen_action="MOVE:US_1:2:2",
        priors_by_action={"MOVE:US_1:2:2": 0.6, "WAIT:US_1": 0.4},
        values_by_action={"MOVE:US_1:2:2": 1_000_000.0, "WAIT:US_1": -1_000_000.0},
        value_sign_by_action={},
        visits_by_action={"MOVE:US_1:2:2": 1, "WAIT:US_1": 1},
        c_puct=1.5,
        dynamics_pred_reward=None,
        acting_unit_q=3,
        acting_unit_r=3,
        vp_hexes=[{"q": 2, "r": 2, "vp_id": "VP_A"}],
        top_k=2,
        q_clip_abs=25.0,
        value_rescale_mode="tanh",
        value_rescale_temperature=1.5,
    )
    by_action = {str(c.get("action_id", "")): dict(c or {}) for c in list(out.get("candidate_actions", []) or [])}
    q_move = float(by_action["MOVE:US_1:2:2"]["mcts_q_value"])
    q_wait = float(by_action["WAIT:US_1"]["mcts_q_value"])
    assert 0.99 <= q_move <= 1.0
    assert -1.0 <= q_wait <= -0.99


def test_resolve_vp_horizon_marks_available_when_signal_exists_without_steps() -> None:
    steps, signal, comp, source, available = _resolve_vp_horizon_selected_fields(
        selected_candidate={
            "vp_horizon_steps": None,
            "vp_horizon_signal": 0.25,
            "vp_horizon_component": 0.10,
            "vp_horizon_source": "selected_candidate",
        },
        transition_info=None,
    )
    assert steps is None
    assert signal == 0.25
    assert comp == 0.10
    assert source == "selected_candidate"
    assert available is True


def test_resolve_vp_horizon_uses_transition_info_when_candidate_missing() -> None:
    steps, signal, comp, source, available = _resolve_vp_horizon_selected_fields(
        selected_candidate={},
        transition_info={
            "vp_horizon_steps": None,
            "vp_horizon_signal": 0.4,
            "vp_horizon_component": 0.08,
        },
    )
    assert steps is None
    assert signal == 0.4
    assert comp == 0.08
    assert source == "transition_info"
    assert available is True


def test_probability_tie_break_prefers_capture_then_visits_then_score() -> None:
    chosen, source = _select_action_with_probability_tie_break(
        sampled_action="WAIT:US_1",
        actions=["WAIT:US_1", "MOVE:US_1:2:6", "MOVE:US_1:1:6"],
        probs=[0.333333, 0.333333, 0.333333],
        visits=[5, 5, 5],
        breakdown_by_action={
            "WAIT:US_1": {"puct_score": 0.9, "q_value": 0.2},
            "MOVE:US_1:2:6": {"puct_score": 0.2, "q_value": 0.1},
            "MOVE:US_1:1:6": {"puct_score": 0.8, "q_value": 0.3},
        },
        side="US",
        vp_hexes=[{"q": 2, "r": 6, "vp_id": "VP_A"}],
        vp_owner_by_hex={"2,6": "GE"},
    )
    assert chosen == "MOVE:US_1:2:6"
    assert source == "mcts_prob_tie_break_capture_visits_score"


def test_eval_decision_top_preserves_vp_candidate_fields_when_present():
    trace_rows = [
        {
            "step": 0,
            "game_turn": 1,
            "action_id": "MOVE:US_1:2:2",
            "action_kind": "MOVE",
            "unit_side": "US",
            "chosen_action_prob": 0.55,
            "mcts_margin": 0.21,
            "objective_progress_delta": 1.0,
            "why_action_vs_vp_text": "selected action is also best toward VP",
            "mcts_action_candidates": [
                {
                    "action_id": "MOVE:US_1:2:2",
                    "policy_prior": 0.55,
                    "final_score": 0.63,
                    "vp_progress_delta": 1.0,
                    "vp_progress_source": "target_hex_parse",
                }
            ],
            "why_action_vs_vp": {
                "top_k": 1,
                "chosen_action_id": "MOVE:US_1:2:2",
                "vp_best_action_id": "MOVE:US_1:2:2",
                "candidate_actions": [
                    {
                        "action_id": "MOVE:US_1:2:2",
                        "vp_progress_delta": 1.0,
                        "vp_progress_source": "target_hex_parse",
                    }
                ],
            },
            "damage_dealt": 0.0,
            "kills_dealt": 0.0,
        }
    ]
    _summary, _top = _build_eval_decision_summary(trace_rows)
    steps_top = _build_eval_decision_steps_top(trace_rows, limit=10)
    assert len(steps_top) == 1
    row = dict(steps_top[0] or {})
    assert isinstance(row.get("mcts_action_candidates", None), list)
    assert isinstance(row.get("why_action_vs_vp", None), dict)
    cand = list(row.get("mcts_action_candidates", []) or [])[0]
    assert float(cand.get("vp_progress_delta", 0.0)) == 1.0
    assert str(cand.get("vp_progress_source", "")).strip() == "target_hex_parse"
    why_cand = list(dict(row.get("why_action_vs_vp", {}) or {}).get("candidate_actions", []) or [])[0]
    assert float(why_cand.get("vp_progress_delta", 0.0)) == 1.0
    assert str(why_cand.get("vp_progress_source", "")).strip() == "target_hex_parse"


def test_eval_trace_propagates_unit_prefilter_telemetry_into_decision_steps_top() -> None:
    adapter = _AdapterUnitPrefilterInfoStub()
    (*_, trace_rows) = _run_episode_with_policy(
        adapter=adapter,
        scenario_id="stub_scenario",
        seed=23,
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
    assert trace_rows
    row = dict(trace_rows[0] or {})
    assert bool(row.get("unit_prefilter_enabled", False)) is True
    assert str(row.get("unit_prefilter_selected_unit_id", "")) == "US_1"
    assert int(row.get("unit_prefilter_constrained_count", -1)) == 2
    assert int(row.get("unit_prefilter_global_count", -1)) == 5
    steps_top = _build_eval_decision_steps_top(trace_rows, limit=10)
    assert steps_top
    top = dict(steps_top[0] or {})
    assert bool(top.get("unit_prefilter_enabled", False)) is True
    assert str(top.get("unit_prefilter_selected_unit_id", "")) == "US_1"
    assert int(top.get("unit_prefilter_constrained_count", -1)) == 2
    assert int(top.get("unit_prefilter_global_count", -1)) == 5


def test_eval_steps_top_uses_selected_tie_break_for_vp_progress_when_observed_missing() -> None:
    trace_rows = [
        {
            "step": 0,
            "action_id": "MOVE:US_1:2:2",
            "unit_side": "US",
            "objective_progress_delta": None,
            "tie_break_term": 1.5,
            "vp_progress_estimated_selected": 1.5,
            "vp_progress_source": "selected_candidate.tie_break_term",
            "vp_progress_available": True,
            "mcts_action_candidates": [
                {
                    "action_id": "MOVE:US_1:2:2",
                    "selected_action": True,
                    "decision_components": {"tie_break_term": 1.5},
                }
            ],
            "why_action_vs_vp": {"chosen_action_id": "MOVE:US_1:2:2"},
        }
    ]
    steps_top = _build_eval_decision_steps_top(trace_rows, limit=10)
    top = dict(steps_top[0] or {})
    assert top["vp_progress"] == 1.5
    assert top["vp_progress_source"] == "selected_candidate.tie_break_term"
    assert top["vp_progress_available"] is True


def test_eval_steps_top_keeps_missing_mcts_success_channels_as_none() -> None:
    trace_rows = [
        {
            "step": 0,
            "action_id": "MOVE:US_1:2:2",
            "unit_side": "US",
            "mcts_success_prob_proxy": None,
            "mcts_success_component": None,
            "mcts_success_prob_proxy_source": "missing",
            "mcts_success_component_source": "missing",
            "mcts_success_prob_proxy_available": False,
            "mcts_success_component_available": False,
            "mcts_action_candidates": [
                {
                    "action_id": "MOVE:US_1:2:2",
                    "selected_action": True,
                    "decision_components": {
                        "success_prob_proxy": None,
                        "success_component": None,
                    },
                }
            ],
            "why_action_vs_vp": {"chosen_action_id": "MOVE:US_1:2:2"},
        }
    ]
    steps_top = _build_eval_decision_steps_top(trace_rows, limit=10)
    top = dict(steps_top[0] or {})
    assert top["mcts_success_prob_proxy"] is None
    assert top["mcts_success_component"] is None


def test_eval_steps_top_preserves_health_diagnostics_denominator_fields() -> None:
    trace_rows = [
        {
            "step": 0,
            "action_id": "MOVE:US_1:2:2",
            "unit_side": "US",
            "mcts_total_visits": 128,
            "mcts_active_actions": 31,
            "mcts_q_guardrail_clipped_count": 4,
            "mcts_q_clipped_count": 4,
            "mcts_q_clip_denominator_count": 128,
            "telemetry_coverage_status": "partial",
            "telemetry_coverage_reason": "some_heads_missing_or_not_applicable",
            "mcts_action_candidates": [
                {"action_id": "MOVE:US_1:2:2", "visit_count": 9, "selected_action": True},
                {"action_id": "WAIT:US_1", "visit_count": 3},
            ],
            "why_action_vs_vp": {"chosen_action_id": "MOVE:US_1:2:2"},
        }
    ]
    steps_top = _build_eval_decision_steps_top(trace_rows, limit=10)
    top = dict(steps_top[0] or {})
    assert int(top.get("mcts_total_visits", -1)) == 128
    assert int(top.get("mcts_active_actions", -1)) == 31
    assert int(top.get("mcts_q_guardrail_clipped_count", -1)) == 4
    assert int(top.get("mcts_q_clipped_count", -1)) == 4
    assert int(top.get("mcts_q_clip_denominator_count", -1)) == 128
    assert str(top.get("telemetry_coverage_status", "")) == "partial"
    assert str(top.get("telemetry_coverage_reason", "")) == "some_heads_missing_or_not_applicable"
