from __future__ import annotations

from types import SimpleNamespace

import torch

from agents.efficientzero_v2.core.mcts import MCTSOutput
import agents.efficientzero_v2.core.selfplay as selfplay_module
from agents.efficientzero_v2.core.selfplay import (
    _NativeEZV2SelfplayBackend,
    _best_enemy_vp_qr_for_side,
    _objective_progress_soft_signal,
    resolve_effective_step_budget,
)


class _DummyAdapter:
    def __init__(self) -> None:
        self._done = False

    def initial_state(self, scenario_id: str, seed: int = 0):
        return SimpleNamespace(
            turn=1,
            to_play="A",
            done=False,
            units=[{"unit_id": "u1", "side": "A", "q": 0, "r": 0, "hp": 10, "alive": True}],
            vp_hexes=[{"q": 1, "r": 0, "vp_id": "vp1"}],
            vp_owner_by_hex={"1,0": "B"},
        )

    def legal_actions(self):
        return ["CAPTURE:u1:1:0"] if not self._done else []

    def apply(self, action_id: str):
        self._done = True
        return SimpleNamespace(
            done=True,
            info={"damage_dealt": 0.0, "kills_dealt": 0},
            state=SimpleNamespace(end_reason="scenario_end", winner="A"),
        )

    def observation(self):
        return SimpleNamespace(
            turn=2,
            to_play="B",
            done=True,
            units=[{"unit_id": "u1", "side": "A", "q": 1, "r": 0, "hp": 10, "alive": True}],
            vp_hexes=[{"q": 1, "r": 0, "vp_id": "vp1"}],
            vp_owner_by_hex={"1,0": "A"},
        )

    def terminal(self):
        return self._done


class _FallbackActionAdapter:
    def __init__(self) -> None:
        self._done = False

    def initial_state(self, scenario_id: str, seed: int = 0):
        return SimpleNamespace(
            turn=1,
            to_play="A",
            done=False,
            units=[{"unit_id": "u1", "side": "A", "q": 0, "r": 0, "hp": 10, "alive": True}],
            vp_hexes=[{"q": 2, "r": 0, "vp_id": "vp1"}],
            vp_owner_by_hex={"2,0": "B"},
        )

    def legal_actions(self):
        return ["WAIT:u1", "ATTACK:u1:x:y"] if not self._done else []

    def apply(self, action_id: str):
        self._done = True
        return SimpleNamespace(
            done=True,
            info={"damage_dealt": 0.0, "kills_dealt": 0},
            state=SimpleNamespace(end_reason="scenario_end", winner="A"),
        )

    def observation(self):
        return SimpleNamespace(
            turn=2,
            to_play="B",
            done=True,
            units=[{"unit_id": "u1", "side": "A", "q": 1, "r": 0, "hp": 10, "alive": True}],
            vp_hexes=[{"q": 2, "r": 0, "vp_id": "vp1"}],
            vp_owner_by_hex={"2,0": "B"},
        )

    def terminal(self):
        return self._done


class _LoopingAdapter:
    def __init__(self, *, unit_count: int = 2, scenario_turn_limit: int = 4) -> None:
        self._step = 0
        self._unit_count = int(unit_count)
        self._scenario_turn_limit = int(scenario_turn_limit)

    def initial_state(self, scenario_id: str, seed: int = 0):
        self._step = 0
        return self.observation()

    def scenario_max_turns(self) -> int:
        return int(self._scenario_turn_limit)

    def legal_actions(self):
        return ["MOVE:u1:0:0"]

    def apply(self, action_id: str):
        self._step += 1
        return SimpleNamespace(
            done=False,
            info={"damage_dealt": 0.0, "kills_dealt": 0},
            state=SimpleNamespace(end_reason="", winner=""),
        )

    def observation(self):
        units = [
            {"unit_id": f"u{i}", "side": "A", "q": i, "r": 0, "hp": 10, "alive": True}
            for i in range(1, max(1, self._unit_count) + 1)
        ]
        return SimpleNamespace(
            turn=int(self._step + 1),
            to_play="A",
            done=False,
            units=units,
            vp_hexes=[],
            vp_owner_by_hex={},
        )

    def terminal(self):
        return False


class _VpTieAdapter:
    def __init__(self) -> None:
        self._done = False

    def initial_state(self, scenario_id: str, seed: int = 0):
        return SimpleNamespace(
            turn=1,
            to_play="A",
            done=False,
            units=[{"unit_id": "u1", "side": "A", "q": 0, "r": 0, "hp": 10, "alive": True}],
            vp_hexes=[{"q": 2, "r": 0, "vp_id": "vp1"}],
            vp_owner_by_hex={"2,0": "B"},
        )

    def legal_actions(self):
        return ["MOVE:u1:0:1", "MOVE:u1:1:0"] if not self._done else []

    def apply(self, action_id: str):
        self._done = True
        return SimpleNamespace(
            done=True,
            info={"damage_dealt": 0.0, "kills_dealt": 0},
            state=SimpleNamespace(end_reason="scenario_end", winner="A"),
        )

    def observation(self):
        return SimpleNamespace(
            turn=2,
            to_play="B",
            done=True,
            units=[{"unit_id": "u1", "side": "A", "q": 1, "r": 0, "hp": 10, "alive": True}],
            vp_hexes=[{"q": 2, "r": 0, "vp_id": "vp1"}],
            vp_owner_by_hex={"2,0": "B"},
        )

    def terminal(self):
        return self._done


class _HpDeltaFallbackAdapter:
    def __init__(self) -> None:
        self._done = False

    def initial_state(self, scenario_id: str, seed: int = 0):
        self._done = False
        return SimpleNamespace(
            turn=1,
            to_play="A",
            done=False,
            units=[
                {"unit_id": "a1", "side": "A", "q": 0, "r": 0, "hp": 10, "alive": True},
                {"unit_id": "b1", "side": "B", "q": 1, "r": 0, "hp": 6, "alive": True},
            ],
            vp_hexes=[],
            vp_owner_by_hex={},
        )

    def legal_actions(self):
        return ["ASSAULT_MELEE:a1:b1:1:0"] if not self._done else []

    def apply(self, action_id: str):
        self._done = True
        # VOEC can omit actor-relative damage fields for this path.
        return SimpleNamespace(
            done=True,
            info={"scenario_id": "s1", "runtime_events": []},
            state=SimpleNamespace(end_reason="scenario_end", winner="A"),
        )

    def observation(self):
        return SimpleNamespace(
            turn=2,
            to_play="B",
            done=True,
            units=[
                {"unit_id": "a1", "side": "A", "q": 0, "r": 0, "hp": 10, "alive": True},
                {"unit_id": "b1", "side": "B", "q": 1, "r": 0, "hp": 0, "alive": False},
            ],
            vp_hexes=[],
            vp_owner_by_hex={},
        )

    def terminal(self):
        return self._done


class _OwnedVpDistractionAdapter:
    def __init__(self) -> None:
        self._done = False

    def initial_state(self, scenario_id: str, seed: int = 0):
        self._done = False
        return SimpleNamespace(
            turn=1,
            to_play="A",
            done=False,
            units=[{"unit_id": "u1", "side": "A", "q": 0, "r": 0, "hp": 10, "alive": True}],
            vp_hexes=[
                {"q": 2, "r": 0, "vp_id": "vp_owned"},
                {"q": 8, "r": 0, "vp_id": "vp_enemy"},
            ],
            # Mixed key formats must still be resolved correctly.
            vp_owner_by_hex={"(2,0)": "A", "8:0": "B"},
        )

    def legal_actions(self):
        return ["MOVE:u1:1:0"] if not self._done else []

    def apply(self, action_id: str):
        self._done = True
        return SimpleNamespace(
            done=True,
            info={"damage_dealt": 0.0, "kills_dealt": 0},
            state=SimpleNamespace(end_reason="scenario_end", winner="A"),
        )

    def observation(self):
        return SimpleNamespace(
            turn=2,
            to_play="B",
            done=True,
            units=[{"unit_id": "u1", "side": "A", "q": 1, "r": 0, "hp": 10, "alive": True}],
            vp_hexes=[
                {"q": 2, "r": 0, "vp_id": "vp_owned"},
                {"q": 8, "r": 0, "vp_id": "vp_enemy"},
            ],
            vp_owner_by_hex={"2,0": "A", "8,0": "B"},
        )

    def terminal(self):
        return self._done


class _DiceTelemetryAdapter:
    def __init__(self) -> None:
        self._done = False

    def initial_state(self, scenario_id: str, seed: int = 0):
        self._done = False
        return SimpleNamespace(
            turn=1,
            to_play="A",
            done=False,
            units=[
                {"unit_id": "a1", "side": "A", "q": 0, "r": 0, "hp": 10, "alive": True},
                {"unit_id": "b1", "side": "B", "q": 1, "r": 0, "hp": 6, "alive": True},
            ],
            vp_hexes=[],
            vp_owner_by_hex={},
        )

    def legal_actions(self):
        return ["ASSAULT_MELEE:a1:b1:1:0"] if not self._done else []

    def apply(self, action_id: str):
        self._done = True
        return SimpleNamespace(
            done=True,
            info={
                "runtime_events": [
                    {
                        "type": "ACTION_EFFECT",
                        "payload": {
                            "attacker": "a1",
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
            state=SimpleNamespace(end_reason="scenario_end", winner="A"),
        )

    def observation(self):
        return SimpleNamespace(
            turn=2,
            to_play="B",
            done=True,
            units=[
                {"unit_id": "a1", "side": "A", "q": 0, "r": 0, "hp": 10, "alive": True},
                {"unit_id": "b1", "side": "B", "q": 1, "r": 0, "hp": 0, "alive": False},
            ],
            vp_hexes=[],
            vp_owner_by_hex={},
        )

    def terminal(self):
        return self._done


class _ReactionFireTelemetryAdapter:
    def __init__(self) -> None:
        self._done = False

    def initial_state(self, scenario_id: str, seed: int = 0):
        self._done = False
        return SimpleNamespace(
            turn=1,
            to_play="A",
            done=False,
            units=[
                {"unit_id": "a1", "side": "A", "unit_key": "US_RIFLE_SQUAD", "q": 0, "r": 0, "hp": 10, "alive": True},
                {"unit_id": "b1", "side": "B", "unit_key": "GE_RIFLE_SQUAD", "q": 1, "r": 0, "hp": 6, "alive": True},
            ],
            vp_hexes=[],
            vp_owner_by_hex={},
            terrain_cover_by_hex={"1,0": 0.2},
            terrain_los_block_by_hex={"1,0": 0.1},
        )

    def legal_actions(self):
        return ["OPPORTUNITY_FIRE:a1:b1:1:0"] if not self._done else []

    def apply(self, action_id: str):
        self._done = True
        return SimpleNamespace(
            done=True,
            info={
                "runtime_events": [
                    {
                        "type": "ACTION_EFFECT",
                        "payload": {
                            "attacker": "a1",
                            "attacker_attack_dice": [
                                {"color": "red", "faces": ["hit", "hit"]},
                            ],
                            "defender_defense_dice": [
                                {"color": "blue", "faces": ["block"]},
                            ],
                        },
                    }
                ]
            },
            state=SimpleNamespace(end_reason="scenario_end", winner="A"),
        )

    def observation(self):
        return SimpleNamespace(
            turn=2,
            to_play="B",
            done=True,
            units=[
                {"unit_id": "a1", "side": "A", "unit_key": "US_RIFLE_SQUAD", "q": 0, "r": 0, "hp": 10, "alive": True},
                {"unit_id": "b1", "side": "B", "unit_key": "GE_RIFLE_SQUAD", "q": 1, "r": 0, "hp": 4, "alive": True},
            ],
            vp_hexes=[],
            vp_owner_by_hex={},
            terrain_cover_by_hex={"1,0": 0.2},
            terrain_los_block_by_hex={"1,0": 0.1},
        )

    def terminal(self):
        return self._done


class _AttackVsWaitAdapter:
    def __init__(self) -> None:
        self._done = False

    def initial_state(self, scenario_id: str, seed: int = 0):
        self._done = False
        return SimpleNamespace(
            turn=1,
            to_play="A",
            done=False,
            units=[
                {"unit_id": "a1", "side": "A", "unit_key": "US_RIFLE_SQUAD", "q": 0, "r": 0, "hp": 10, "alive": True},
                {"unit_id": "b1", "side": "B", "unit_key": "GE_RIFLE_SQUAD", "q": 1, "r": 0, "hp": 6, "alive": True},
            ],
            vp_hexes=[],
            vp_owner_by_hex={},
            terrain_cover_by_hex={"1,0": 0.0},
            terrain_los_block_by_hex={"1,0": 0.0},
        )

    def legal_actions(self):
        return ["WAIT:a1", "ATTACK:a1:b1:1:0"] if not self._done else []

    def apply(self, action_id: str):
        self._done = True
        return SimpleNamespace(
            done=True,
            info={"damage_dealt": 0.0, "kills_dealt": 0},
            state=SimpleNamespace(end_reason="scenario_end", winner="A"),
        )

    def observation(self):
        return SimpleNamespace(
            turn=2,
            to_play="B",
            done=True,
            units=[
                {"unit_id": "a1", "side": "A", "unit_key": "US_RIFLE_SQUAD", "q": 0, "r": 0, "hp": 10, "alive": True},
                {"unit_id": "b1", "side": "B", "unit_key": "GE_RIFLE_SQUAD", "q": 1, "r": 0, "hp": 6, "alive": True},
            ],
            vp_hexes=[],
            vp_owner_by_hex={},
            terrain_cover_by_hex={"1,0": 0.0},
            terrain_los_block_by_hex={"1,0": 0.0},
        )

    def terminal(self):
        return self._done


class _EnemyThreatAdapter:
    def __init__(self) -> None:
        self._done = False

    def initial_state(self, scenario_id: str, seed: int = 0):
        self._done = False
        return SimpleNamespace(
            turn=1,
            to_play="A",
            done=False,
            units=[
                {"unit_id": "a1", "side": "A", "q": 0, "r": 0, "hp": 10, "alive": True},
                {"unit_id": "b1", "side": "B", "q": 2, "r": 0, "hp": 10, "alive": True},
            ],
            vp_hexes=[{"q": 3, "r": 0, "vp_id": "vp1"}],
            vp_owner_by_hex={"3,0": "A"},
        )

    def legal_actions(self):
        return ["MOVE:a1:1:0"] if not self._done else []

    def apply(self, action_id: str):
        self._done = True
        return SimpleNamespace(
            done=True,
            info={"damage_dealt": 0.0, "kills_dealt": 0},
            state=SimpleNamespace(end_reason="scenario_end", winner="A"),
        )

    def observation(self):
        return SimpleNamespace(
            turn=2,
            to_play="B",
            done=True,
            units=[
                {"unit_id": "a1", "side": "A", "q": 1, "r": 0, "hp": 10, "alive": True},
                {"unit_id": "b1", "side": "B", "q": 2, "r": 0, "hp": 10, "alive": True},
            ],
            vp_hexes=[{"q": 3, "r": 0, "vp_id": "vp1"}],
            vp_owner_by_hex={"3,0": "A"},
        )

    def terminal(self):
        return self._done


class _DummyInferenceModel(torch.nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.encoder_type = "mlp"
        self.anchor = torch.nn.Parameter(torch.tensor(0.0))

    def initial_inference(self, obs_tensor):
        _ = obs_tensor
        # latent, policy_logits, value_root, reward_logits
        return (
            torch.zeros((1, 2), dtype=torch.float32, device=self.anchor.device),
            torch.tensor([[2.0] * 32], dtype=torch.float32, device=self.anchor.device),
            torch.tensor([[0.75]], dtype=torch.float32, device=self.anchor.device),
            torch.zeros((1, 1), dtype=torch.float32, device=self.anchor.device),
        )


def test_native_selfplay_emits_contract_fields() -> None:
    backend = _NativeEZV2SelfplayBackend()
    samples = backend.play_episode(
        adapter=_DummyAdapter(),
        scenario_id="s1",
        seed=7,
        max_steps=5,
        action_dim=32,
        model=None,
    )
    assert samples
    info = dict(samples[0].info or {})
    required = (
        "legal_action_count",
        "chosen_action_prob",
        "real_decision_score",
        "decision_win_basis",
        "mcts_margin",
        "objective_converted",
        "objective_progress_delta",
        "legal_reaction_options",
        "legal_capture_options",
        "action_kind",
        "terminal_reason",
        "vp_horizon_steps",
        "vp_horizon_signal",
        "vp_horizon_decision_component",
        "vp_horizon_source",
    )
    for key in required:
        assert key in info


def test_native_selfplay_contract_uses_canonical_decision_telemetry_fields() -> None:
    backend = _NativeEZV2SelfplayBackend()
    samples = backend.play_episode(
        adapter=_DummyAdapter(),
        scenario_id="s1",
        seed=17,
        max_steps=4,
        action_dim=32,
        model=None,
    )
    assert samples
    info = dict(samples[0].info or {})
    assert "mcts_action_candidates" in info
    assert "why_action_vs_vp" in info
    assert "why_action_vs_vp_text" in info
    # Canonical ownership signal now relies on explicit override telemetry,
    # not legacy execution-mismatch aliases.
    assert "execution_mismatch_by_side" not in info
    assert "legacy_fallback_rows" not in info


def test_resolve_effective_step_budget_precedence() -> None:
    assert resolve_effective_step_budget(
        max_steps=100,
        max_steps_override=90,
        max_turns_override=3,
        unit_count=4,
        scenario_turn_limit=8,
    ) == (12, "max_turns_override*unit_count")
    assert resolve_effective_step_budget(
        max_steps=100,
        max_steps_override=90,
        max_turns_override=0,
        unit_count=4,
        scenario_turn_limit=8,
    ) == (90, "max_steps_override")
    assert resolve_effective_step_budget(
        max_steps=100,
        max_steps_override=0,
        max_turns_override=0,
        unit_count=4,
        scenario_turn_limit=8,
    ) == (32, "scenario_turn_limit*unit_count")
    assert resolve_effective_step_budget(
        max_steps=100,
        max_steps_override=0,
        max_turns_override=0,
        unit_count=0,
        scenario_turn_limit=8,
    ) == (100, "max_steps_fallback")


def test_native_selfplay_vp_candidate_fallbacks_are_present() -> None:
    backend = _NativeEZV2SelfplayBackend()
    samples = backend.play_episode(
        adapter=_FallbackActionAdapter(),
        scenario_id="s1",
        seed=11,
        max_steps=3,
        action_dim=32,
        model=None,
    )
    assert samples
    info = dict(samples[0].info or {})
    cands = list(info.get("mcts_action_candidates", []) or [])
    assert cands
    assert "why_action_vs_vp" in info
    assert "why_action_vs_vp_text" in info
    for c in cands:
        assert "real_decision_score" in c
        assert "visit_count" in c
        assert "decision_rank" in c
        assert "decision_components" in c
        assert "selected_by" in c
        assert "mcts_q_value" in c
        assert "mcts_u_value" in c
        assert "mcts_success_prob_proxy" in c
        assert "mcts_success_component" in c
        assert "mcts_puct_score" in c
        assert "vp_progress_delta" in c
        assert "vp_progress_source" in c
        assert "expected_damage_proxy" in c
        assert "vp_horizon_steps" in c
        assert "vp_horizon_signal" in c
        assert "vp_horizon_component" in c
        assert "vp_horizon_source" in c
        assert isinstance(c.get("vp_progress_delta", None), float)
        assert isinstance(c.get("expected_damage_proxy", None), float)
        assert isinstance(c.get("vp_horizon_steps", None), float)
        assert isinstance(c.get("vp_horizon_signal", None), float)
        assert isinstance(c.get("vp_horizon_component", None), float)
        assert str(c.get("vp_progress_source", "")).strip()
        assert isinstance(c.get("visit_count", None), int)
        assert isinstance(c.get("decision_rank", None), int)
        assert isinstance(c.get("decision_components", None), dict)


def test_best_enemy_vp_qr_for_side_supports_fallback_vp_id_format() -> None:
    vp_hexes = [
        {"q": 2, "r": 3},
        {"q": 7, "r": -1},
    ]
    vp_owner_by_hex = {"2,3": "B", "7,-1": "B"}

    q, r = _best_enemy_vp_qr_for_side(
        side="A",
        vp_hexes=vp_hexes,
        vp_owner_by_hex=vp_owner_by_hex,
        best_vp_id="VP_1_7,-1",
    )

    assert (q, r) == (7, -1)


def test_action_target_qr_supports_compact_hex_formats() -> None:
    assert selfplay_module._action_target_qr("MOVE:US_1:2:3") == (2, 3)
    assert selfplay_module._action_target_qr("MOVE:US_1:2,3") == (2, 3)
    assert selfplay_module._action_target_qr("MOVE:US_1:(2,3)") == (2, 3)


def test_observation_tensor_populates_declared_spatial_channels() -> None:
    obs = SimpleNamespace(
        turn=3,
        to_play="A",
        done=False,
        units=[
            {"unit_id": "u1", "unit_key": "US_RIFLE_SQUAD", "side": "A", "q": 0, "r": 0, "hp": 10, "alive": True},
            {"unit_id": "u2", "unit_key": "GE_RIFLE_SQUAD", "side": "B", "q": 1, "r": 0, "hp": 8, "alive": True},
        ],
        playable_hexes=[{"q": 0, "r": 0}, {"q": 1, "r": 0}, {"q": 2, "r": 1}],
        vp_hexes=[{"q": 2, "r": 1, "vp_id": "vp1"}],
        vp_owner_by_hex={"2,1": "B"},
        terrain_move_cost_by_hex={"0,0": 1.0, "1,0": 1.0, "2,1": 1.0},
        terrain_cover_by_hex={"2,1": 0.4},
        terrain_los_block_by_hex={"2,1": 0.2},
        terrain_type_by_hex={"2,1": "urban"},
        fortification_type_by_hex={},
        fortification_edge_by_hex={},
    )
    ten = selfplay_module._observation_to_tensor(obs, channels=32, height=16, width=16)
    assert isinstance(ten, torch.Tensor)
    assert tuple(ten.shape) == (32, 16, 16)
    # VP/terrain/coord and tactical channels should be populated for declared 32-channel contract.
    assert float(ten[7].abs().sum().item()) > 0.0   # reaction_fire_threat
    assert float(ten[13].abs().sum().item()) > 0.0  # vp_mask
    assert float(ten[14].abs().sum().item()) > 0.0  # vp_owner_relative
    assert float(ten[15].abs().sum().item()) > 0.0  # terrain_move_cost_norm
    assert float(ten[16].abs().sum().item()) > 0.0  # terrain_cover_norm
    assert float(ten[18].abs().sum().item()) > 0.0  # vp_distance_inv
    assert float(ten[19].abs().sum().item()) > 0.0  # q_coord_norm
    assert float(ten[20].abs().sum().item()) > 0.0  # r_coord_norm
    assert float(ten[21].abs().sum().item()) > 0.0  # frontline_control


def test_native_selfplay_applies_derived_scenario_budget_when_no_overrides() -> None:
    backend = _NativeEZV2SelfplayBackend()
    samples = backend.play_episode(
        adapter=_LoopingAdapter(unit_count=3, scenario_turn_limit=4),
        scenario_id="s1",
        seed=42,
        max_steps=5,
        max_steps_override=0,
        max_turns_override=0,
        action_dim=32,
        model=None,
    )
    assert len(samples) == 12
    info = dict(samples[-1].info or {})
    assert int(info.get("effective_max_steps", -1)) == 12
    assert str(info.get("step_budget_source", "")) == "scenario_turn_limit*unit_count"
    assert bool(info.get("timeout", False)) is True
    assert str(info.get("terminal_reason", "")) == "turn_unit_budget"


def test_native_selfplay_uses_vp_tiebreak_for_near_equal_scores(monkeypatch) -> None:
    backend = _NativeEZV2SelfplayBackend()

    def _fake_mcts(**_kwargs):
        return MCTSOutput(
            actions=["MOVE:u1:0:1", "MOVE:u1:1:0"],
            visits=[10, 10],
            probs=[0.505, 0.500],
            chosen_action="MOVE:u1:0:1",
            q_guardrail_clipped_count=0,
            q_guardrail_clip_limit=10.0,
            q_root_score_spread=0.0,
            q_root_normalization_applied=False,
        )

    monkeypatch.setattr(selfplay_module, "run_mcts_puct", _fake_mcts)
    samples = backend.play_episode(
        adapter=_VpTieAdapter(),
        scenario_id="s1",
        seed=31,
        max_steps=3,
        action_dim=32,
        model=None,
        mcts_vp_tiebreak_epsilon=0.01,
    )
    assert samples
    info = dict(samples[0].info or {})
    assert str(info.get("action_id", "")) == "MOVE:u1:1:0"
    assert str(info.get("mcts_tiebreak_path", "")) == "vp_progress_tiebreak"
    assert str((dict(info.get("why_action_vs_vp", {}) or {})).get("tie_break_path", "")) == "vp_progress_tiebreak"


def test_native_selfplay_prefers_vp_progress_when_q_is_flat(monkeypatch) -> None:
    backend = _NativeEZV2SelfplayBackend()

    def _fake_mcts(**_kwargs):
        return MCTSOutput(
            actions=["MOVE:u1:0:1", "MOVE:u1:1:0"],
            visits=[11, 9],
            probs=[0.515, 0.500],
            chosen_action="MOVE:u1:0:1",
            q_guardrail_clipped_count=8,
            q_guardrail_clip_limit=0.01,
            q_root_score_spread=0.0,
            q_root_normalization_applied=True,
        )

    monkeypatch.setattr(selfplay_module, "run_mcts_puct", _fake_mcts)
    samples = backend.play_episode(
        adapter=_VpTieAdapter(),
        scenario_id="s1",
        seed=41,
        max_steps=3,
        action_dim=32,
        model=None,
        mcts_vp_tiebreak_epsilon=0.005,
        mcts_q_flat_spread_epsilon=1.0e-6,
        mcts_vp_flat_q_score_epsilon=0.02,
        mcts_vp_flat_q_min_progress=0.0,
    )
    assert samples
    info = dict(samples[0].info or {})
    assert str(info.get("action_id", "")) == "MOVE:u1:1:0"
    assert str(info.get("mcts_tiebreak_path", "")) == "vp_progress_flat_q_override"
    why = dict(info.get("why_action_vs_vp", {}) or {})
    assert str(why.get("tie_break_path", "")) == "vp_progress_flat_q_override"


def test_native_selfplay_backfills_damage_from_hp_delta_when_info_missing() -> None:
    backend = _NativeEZV2SelfplayBackend()
    samples = backend.play_episode(
        adapter=_HpDeltaFallbackAdapter(),
        scenario_id="s1",
        seed=77,
        max_steps=2,
        action_dim=32,
        model=None,
    )
    assert samples
    info = dict(samples[0].info or {})
    assert str(info.get("action_kind", "")) == "ASSAULT_MELEE"
    assert float(info.get("damage_dealt", 0.0)) == 6.0
    assert int(info.get("kills_dealt", 0)) == 1


def test_native_selfplay_ignores_owned_vp_in_objective_progress_diagnostics(monkeypatch) -> None:
    backend = _NativeEZV2SelfplayBackend()

    def _fake_mcts(**_kwargs):
        return MCTSOutput(
            actions=["MOVE:u1:1:0"],
            visits=[10],
            probs=[1.0],
            chosen_action="MOVE:u1:1:0",
            q_guardrail_clipped_count=0,
            q_guardrail_clip_limit=10.0,
            q_root_score_spread=0.0,
            q_root_normalization_applied=False,
        )

    monkeypatch.setattr(selfplay_module, "run_mcts_puct", _fake_mcts)
    samples = backend.play_episode(
        adapter=_OwnedVpDistractionAdapter(),
        scenario_id="s1",
        seed=12,
        max_steps=2,
        action_dim=32,
        model=None,
    )
    assert samples
    info = dict(samples[0].info or {})
    assert str(info.get("objective_best_vp_id", "")) == "vp_enemy"
    # Moving toward owned VP should not be counted as objective progress.
    assert float(info.get("objective_progress_delta", 0.0)) == 0.0
    # Own-VP shuffling does not receive positive objective soft shaping.
    assert float(info.get("objective_soft_reward_component", 0.0)) <= 0.0
    why = dict(info.get("why_action_vs_vp", {}) or {})
    assert str(why.get("vp_best_action_id", "")) == "MOVE:u1:1:0"


def test_objective_soft_signal_rewards_progress_over_stall_in_opportunity_windows() -> None:
    progress_component, _ = _objective_progress_soft_signal(
        reward_shaping={
            "objective_progress_bonus_per_hex": 1.65,
            "objective_team_progress_bonus_per_hex": 0.72,
            "objective_progress_cap_abs": 1.0,
            "objective_team_progress_cap_abs": 1.5,
            "objective_no_progress_penalty": 1.20,
            "objective_no_progress_attack_penalty": 0.82,
        },
        objective_had_opportunity=1,
        objective_converted=0,
        objective_progress_delta=1.0,
        team_progress_delta=0.75,
        legal_capture_options=1,
        action_kind="MOVE",
    )
    stall_component, stall_meta = _objective_progress_soft_signal(
        reward_shaping={
            "objective_progress_bonus_per_hex": 1.65,
            "objective_team_progress_bonus_per_hex": 0.72,
            "objective_progress_cap_abs": 1.0,
            "objective_team_progress_cap_abs": 1.5,
            "objective_no_progress_penalty": 1.20,
            "objective_no_progress_attack_penalty": 0.82,
        },
        objective_had_opportunity=1,
        objective_converted=0,
        objective_progress_delta=0.0,
        team_progress_delta=0.0,
        legal_capture_options=1,
        action_kind="ATTACK",
    )
    assert float(progress_component) > float(stall_component)
    assert bool(stall_meta.get("objective_soft_no_progress_triggered", False)) is True


def test_objective_soft_signal_is_neutral_outside_opportunity_windows() -> None:
    component, meta = _objective_progress_soft_signal(
        reward_shaping={
            "objective_progress_bonus_per_hex": 1.65,
            "objective_no_progress_penalty": 1.20,
        },
        objective_had_opportunity=0,
        objective_converted=0,
        objective_progress_delta=1.0,
        team_progress_delta=1.0,
        legal_capture_options=0,
        action_kind="MOVE",
    )
    assert float(component) == 0.0
    assert int(meta.get("objective_soft_had_opportunity", 1)) == 0


def test_objective_soft_signal_masks_progress_when_converted() -> None:
    component, meta = _objective_progress_soft_signal(
        reward_shaping={
            "objective_progress_bonus_per_hex": 1.65,
            "objective_no_progress_penalty": 1.20,
        },
        objective_had_opportunity=1,
        objective_converted=1,
        objective_progress_delta=-3.0,
        team_progress_delta=0.0,
        legal_capture_options=1,
        action_kind="MOVE",
    )
    assert float(component) == 0.0
    assert bool(meta.get("objective_soft_progress_masked_on_convert", False)) is True


def test_native_selfplay_keeps_per_die_attack_defense_components() -> None:
    backend = _NativeEZV2SelfplayBackend()
    samples = backend.play_episode(
        adapter=_DiceTelemetryAdapter(),
        scenario_id="s1",
        seed=99,
        max_steps=2,
        action_dim=32,
        model=None,
    )
    assert samples
    info = dict(samples[0].info or {})
    assert len(list(info.get("attack_dice_rolls", []) or [])) == 2
    assert len(list(info.get("defense_dice_rolls", []) or [])) == 1
    assert dict(info.get("attack_components_by_die", {}) or {}).get("HIT", 0) == 2
    assert dict(info.get("defense_components_by_die", {}) or {}).get("BLOCK", 0) == 1
    score_priority = list((dict(info.get("why_action_vs_vp", {}) or {})).get("score_components_priority", []) or [])
    assert "attack_die_components" in score_priority
    assert "defense_die_components" in score_priority


def test_native_selfplay_computes_soft_reaction_fire_signal() -> None:
    backend = _NativeEZV2SelfplayBackend()
    samples = backend.play_episode(
        adapter=_ReactionFireTelemetryAdapter(),
        scenario_id="s1",
        seed=120,
        max_steps=2,
        action_dim=32,
        model=None,
        reward_shaping={
            "reaction_fire_soft_signal_enabled": True,
            "reaction_fire_soft_signal_weight": 0.04,
            "reaction_fire_soft_signal_expected_damage_scale": 4.0,
        },
    )
    assert samples
    info = dict(samples[0].info or {})
    assert str(info.get("action_kind", "")) == "OPPORTUNITY_FIRE"
    assert float(info.get("reaction_fire_success_proxy", 0.0)) > 0.0
    assert float(info.get("reaction_fire_soft_reward_component", 0.0)) != 0.0


def test_native_selfplay_non_reaction_actions_keep_soft_signal_zero() -> None:
    backend = _NativeEZV2SelfplayBackend()
    samples = backend.play_episode(
        adapter=_DiceTelemetryAdapter(),
        scenario_id="s1",
        seed=121,
        max_steps=2,
        action_dim=32,
        model=None,
        reward_shaping={
            "reaction_fire_soft_signal_enabled": True,
            "reaction_fire_soft_signal_weight": 0.04,
        },
    )
    assert samples
    info = dict(samples[0].info or {})
    assert str(info.get("action_kind", "")) == "ASSAULT_MELEE"
    assert float(info.get("reaction_fire_success_proxy", 0.0)) == 0.0
    assert float(info.get("reaction_fire_soft_reward_component", 0.0)) == 0.0
    assert str(info.get("reaction_fire_proxy_source", "")) == "non_reaction_action"


def test_native_selfplay_reaction_fire_signal_respects_toggle_and_weight() -> None:
    backend = _NativeEZV2SelfplayBackend()
    disabled = backend.play_episode(
        adapter=_ReactionFireTelemetryAdapter(),
        scenario_id="s1",
        seed=122,
        max_steps=2,
        action_dim=32,
        model=None,
        reward_shaping={
            "reaction_fire_soft_signal_enabled": False,
            "reaction_fire_soft_signal_weight": 0.04,
        },
    )
    enabled_low = backend.play_episode(
        adapter=_ReactionFireTelemetryAdapter(),
        scenario_id="s1",
        seed=123,
        max_steps=2,
        action_dim=32,
        model=None,
        reward_shaping={
            "reaction_fire_soft_signal_enabled": True,
            "reaction_fire_soft_signal_weight": 0.04,
            "reaction_fire_soft_signal_expected_damage_scale": 4.0,
        },
    )
    weighted = backend.play_episode(
        adapter=_ReactionFireTelemetryAdapter(),
        scenario_id="s1",
        seed=123,
        max_steps=2,
        action_dim=32,
        model=None,
        reward_shaping={
            "reaction_fire_soft_signal_enabled": True,
            "reaction_fire_soft_signal_weight": 0.08,
            "reaction_fire_soft_signal_expected_damage_scale": 4.0,
        },
    )
    assert disabled and enabled_low and weighted
    info_disabled = dict(disabled[0].info or {})
    info_enabled_low = dict(enabled_low[0].info or {})
    info_weighted = dict(weighted[0].info or {})
    component_disabled = float(info_disabled.get("reaction_fire_soft_reward_component", 0.0))
    component_low = float(info_enabled_low.get("reaction_fire_soft_reward_component", 0.0))
    component_weighted = float(info_weighted.get("reaction_fire_soft_reward_component", 0.0))
    proxy_disabled = float(info_disabled.get("reaction_fire_success_proxy", 0.0))
    proxy_low = float(info_enabled_low.get("reaction_fire_success_proxy", 0.0))
    proxy_weighted = float(info_weighted.get("reaction_fire_success_proxy", 0.0))
    source_disabled = str(info_disabled.get("reaction_fire_proxy_source", ""))
    source_low = str(info_enabled_low.get("reaction_fire_proxy_source", ""))
    source_weighted = str(info_weighted.get("reaction_fire_proxy_source", ""))

    # Disabled toggle always neutralizes the shaping component.
    assert component_disabled == 0.0

    # Proxy/signal diagnostics are always emitted and stay bounded.
    assert source_disabled
    assert source_low
    assert source_weighted
    assert 0.0 <= proxy_disabled <= 1.0
    assert 0.0 <= proxy_low <= 1.0
    assert 0.0 <= proxy_weighted <= 1.0
    assert abs(component_low) <= 0.04 + 1e-9
    assert abs(component_weighted) <= 0.08 + 1e-9

    # Enabled shaping uses centered soft signal, so sign may be + or -.
    assert component_low != 0.0
    # Magnitude scales with weight for identical telemetry.
    assert abs(component_weighted) > abs(component_low)


def test_native_selfplay_emits_global_strategy_soft_signals_when_applicable() -> None:
    backend = _NativeEZV2SelfplayBackend()
    samples = backend.play_episode(
        adapter=_DummyAdapter(),
        scenario_id="s1",
        seed=130,
        max_steps=2,
        action_dim=32,
        model=None,
        reward_shaping={
            "global_strategy_soft_enabled": True,
            "global_strategy_vp_control_net_gain_weight": 0.10,
            "global_strategy_units_in_vp_ring_weight": 0.05,
            "global_strategy_enemy_vp_threat_reduced_weight": 0.05,
            "global_strategy_role_consistency_weight": 0.04,
            "global_strategy_setup_convert_weight": 0.03,
        },
    )
    assert samples
    info = dict(samples[0].info or {})
    assert bool(info.get("global_strategy_soft_enabled", False)) is True
    assert float(info.get("vp_control_net_gain_signal", 0.0)) > 0.0
    assert str(info.get("soft_role_kind", "")) == "capture"
    assert float(info.get("global_strategy_soft_reward_component", 0.0)) != 0.0


def test_native_selfplay_global_strategy_non_applicable_states_stay_neutral() -> None:
    backend = _NativeEZV2SelfplayBackend()
    samples = backend.play_episode(
        adapter=_DiceTelemetryAdapter(),
        scenario_id="s1",
        seed=131,
        max_steps=2,
        action_dim=32,
        model=None,
        reward_shaping={
            "global_strategy_soft_enabled": True,
        },
    )
    assert samples
    info = dict(samples[0].info or {})
    assert float(info.get("vp_control_net_gain_signal", 0.0)) == 0.0
    assert float(info.get("units_in_vp_ring_signal", 0.0)) == 0.0
    assert float(info.get("enemy_vp_threat_reduced_signal", 0.0)) == 0.0
    assert float(info.get("global_strategy_soft_reward_component", 0.0)) == 0.0


def test_native_selfplay_global_strategy_toggle_zeroes_effect() -> None:
    backend = _NativeEZV2SelfplayBackend()
    samples = backend.play_episode(
        adapter=_DummyAdapter(),
        scenario_id="s1",
        seed=132,
        max_steps=2,
        action_dim=32,
        model=None,
        reward_shaping={
            "global_strategy_soft_enabled": False,
            "global_strategy_vp_control_net_gain_weight": 1.0,
            "global_strategy_units_in_vp_ring_weight": 1.0,
            "global_strategy_enemy_vp_threat_reduced_weight": 1.0,
            "global_strategy_sustained_vp_advantage_weight": 1.0,
            "global_strategy_role_consistency_weight": 1.0,
            "global_strategy_setup_convert_weight": 1.0,
        },
    )
    assert samples
    info = dict(samples[0].info or {})
    assert bool(info.get("global_strategy_soft_enabled", True)) is False
    assert float(info.get("global_strategy_soft_reward_component", 0.0)) == 0.0


def test_native_selfplay_global_strategy_never_hard_overrides_action_choice(monkeypatch) -> None:
    backend = _NativeEZV2SelfplayBackend()

    def _fake_mcts(**_kwargs):
        return MCTSOutput(
            actions=["WAIT:u1", "ATTACK:u1:x:y"],
            visits=[12, 8],
            probs=[0.70, 0.30],
            chosen_action="WAIT:u1",
            q_guardrail_clipped_count=0,
            q_guardrail_clip_limit=10.0,
            q_root_score_spread=1.0,
            q_root_normalization_applied=False,
        )

    monkeypatch.setattr(selfplay_module, "run_mcts_puct", _fake_mcts)
    base = backend.play_episode(
        adapter=_FallbackActionAdapter(),
        scenario_id="s1",
        seed=133,
        max_steps=2,
        action_dim=32,
        model=None,
        mcts_vp_tiebreak_epsilon=0.0,
        reward_shaping={"global_strategy_soft_enabled": False},
    )
    nudged = backend.play_episode(
        adapter=_FallbackActionAdapter(),
        scenario_id="s1",
        seed=133,
        max_steps=2,
        action_dim=32,
        model=None,
        mcts_vp_tiebreak_epsilon=0.0,
        reward_shaping={
            "global_strategy_soft_enabled": True,
            "global_strategy_vp_control_net_gain_weight": 1.0,
            "global_strategy_units_in_vp_ring_weight": 1.0,
            "global_strategy_enemy_vp_threat_reduced_weight": 1.0,
            "global_strategy_role_consistency_weight": 1.0,
            "global_strategy_setup_convert_weight": 1.0,
        },
    )
    assert base and nudged
    assert str(base[0].info.get("action_id", "")) == "WAIT:u1"
    assert str(nudged[0].info.get("action_id", "")) == "WAIT:u1"


def test_native_selfplay_success_prob_term_prefers_attack_in_tie_like_conditions(monkeypatch) -> None:
    backend = _NativeEZV2SelfplayBackend()

    def _fake_priors_values(_model, _obs_encoded, legal_actions, _action_dim):
        priors = {str(a): 0.5 for a in list(legal_actions or [])}
        values = {str(a): 0.0 for a in list(legal_actions or [])}
        return priors, values, {}

    def _fake_expected_damage(**kwargs):
        action_id = str(kwargs.get("action_id", ""))
        return 4.0 if action_id.startswith("ATTACK:") else 0.0

    monkeypatch.setattr(selfplay_module, "_priors_and_values", _fake_priors_values)
    monkeypatch.setattr(selfplay_module, "_candidate_expected_damage", _fake_expected_damage)
    samples = backend.play_episode(
        adapter=_AttackVsWaitAdapter(),
        scenario_id="s1",
        seed=140,
        max_steps=2,
        action_dim=32,
        model=SimpleNamespace(),
        mcts_simulations=1,
        mcts_c_puct=0.0,
        mcts_success_prob_enabled=True,
        mcts_success_prob_alpha=0.30,
        mcts_success_prob_center=0.5,
        mcts_success_prob_scale=0.5,
    )
    assert samples
    info = dict(samples[0].info or {})
    assert str(info.get("action_id", "")) == "ATTACK:a1:b1:1:0"
    candidates = {
        str(c.get("action_id", "")): dict(c)
        for c in list(info.get("mcts_action_candidates", []) or [])
    }
    assert float(candidates["WAIT:a1"].get("mcts_success_prob_proxy", 0.0)) == 0.5
    assert float(candidates["ATTACK:a1:b1:1:0"].get("mcts_success_prob_proxy", 0.0)) > 0.5


def test_native_selfplay_success_prob_disabled_restores_old_choice(monkeypatch) -> None:
    backend = _NativeEZV2SelfplayBackend()

    def _fake_priors_values(_model, _obs_encoded, legal_actions, _action_dim):
        priors = {str(a): 0.5 for a in list(legal_actions or [])}
        values = {str(a): 0.0 for a in list(legal_actions or [])}
        return priors, values, {}

    def _fake_expected_damage(**kwargs):
        action_id = str(kwargs.get("action_id", ""))
        return 4.0 if action_id.startswith("ATTACK:") else 0.0

    monkeypatch.setattr(selfplay_module, "_priors_and_values", _fake_priors_values)
    monkeypatch.setattr(selfplay_module, "_candidate_expected_damage", _fake_expected_damage)
    samples = backend.play_episode(
        adapter=_AttackVsWaitAdapter(),
        scenario_id="s1",
        seed=141,
        max_steps=2,
        action_dim=32,
        model=SimpleNamespace(),
        mcts_simulations=1,
        mcts_c_puct=0.0,
        mcts_success_prob_enabled=False,
        mcts_success_prob_alpha=0.30,
        mcts_success_prob_center=0.5,
        mcts_success_prob_scale=0.5,
    )
    assert samples
    info = dict(samples[0].info or {})
    assert str(info.get("action_id", "")) == "WAIT:a1"


def test_priors_and_values_do_not_broadcast_root_value_across_actions() -> None:
    model = _DummyInferenceModel()
    legal_actions = ["WAIT:a1", "ATTACK:a1:b1:1:0"]
    priors, values, xai = selfplay_module._priors_and_values(
        model=model,
        obs_encoded=[0.0, 0.0, 0.0, 0.0],
        legal_actions=legal_actions,
        action_dim=32,
    )
    assert priors is not None
    assert set(priors.keys()) == set(legal_actions)
    assert values is None
    assert str(xai.get("mcts_action_value_source", "")) == "root_only_no_broadcast"
    assert bool(xai.get("mcts_action_value_fallback_expected", False)) is True


def test_native_selfplay_reports_mcts_action_value_fallback_usage(monkeypatch) -> None:
    backend = _NativeEZV2SelfplayBackend()
    captured = {}

    def _spy_run_mcts(**kwargs):
        captured["values_by_action"] = kwargs.get("values_by_action")
        return MCTSOutput(
            actions=["WAIT:u1", "ATTACK:u1:x:y"],
            visits=[6, 4],
            probs=[0.6, 0.4],
            chosen_action="WAIT:u1",
        )

    monkeypatch.setattr(selfplay_module, "run_mcts_puct", _spy_run_mcts)
    samples = backend.play_episode(
        adapter=_FallbackActionAdapter(),
        scenario_id="s1",
        seed=201,
        max_steps=2,
        action_dim=32,
        model=_DummyInferenceModel(),
    )
    assert samples
    assert captured.get("values_by_action", "missing") is None
    info = dict(samples[0].info or {})
    assert str(info.get("mcts_action_value_source", "")) == "root_only_no_broadcast"
    assert bool(info.get("mcts_action_value_fallback_used", False)) is True


def test_native_selfplay_vp_horizon_soft_term_can_break_near_ties(monkeypatch) -> None:
    backend = _NativeEZV2SelfplayBackend()

    def _fake_mcts(**_kwargs):
        return MCTSOutput(
            actions=["MOVE:u1:0:1", "MOVE:u1:1:0"],
            visits=[10, 10],
            probs=[0.51, 0.50],
            chosen_action="MOVE:u1:0:1",
            q_guardrail_clipped_count=0,
            q_guardrail_clip_limit=10.0,
            q_root_score_spread=1.0,
            q_root_normalization_applied=False,
            root_candidate_breakdown=[],
        )

    monkeypatch.setattr(selfplay_module, "run_mcts_puct", _fake_mcts)
    samples = backend.play_episode(
        adapter=_VpTieAdapter(),
        scenario_id="s1",
        seed=211,
        max_steps=2,
        action_dim=32,
        model=None,
        mcts_vp_tiebreak_epsilon=0.0,
        reward_shaping={
            "vp_horizon_soft_enabled": True,
            "vp_horizon_soft_weight": 0.10,
            "vp_horizon_soft_cap_steps": 8.0,
        },
    )
    assert samples
    info = dict(samples[0].info or {})
    assert str(info.get("action_id", "")) == "MOVE:u1:1:0"
    assert float(info.get("vp_horizon_decision_component", 0.0)) != 0.0


def test_native_selfplay_emits_enemy_threat_fields_and_candidate_component() -> None:
    backend = _NativeEZV2SelfplayBackend()
    samples = backend.play_episode(
        adapter=_EnemyThreatAdapter(),
        scenario_id="s1",
        seed=220,
        max_steps=2,
        action_dim=32,
        model=None,
        reward_shaping={
            "enemy_threat_component_enabled": True,
            "enemy_threat_component_weight": 0.01,
            "enemy_threat_component_horizon_steps": 6.0,
            "enemy_threat_component_cap_abs": 0.03,
            "enemy_threat_component_immediate_capture_bonus": 0.40,
        },
    )
    assert samples
    info = dict(samples[0].info or {})
    assert "enemy_can_capture_vp_next" in info
    assert "enemy_min_steps_to_vp" in info
    assert "enemy_threat_component" in info
    assert int(info.get("enemy_can_capture_vp_next", 0)) == 1
    assert float(info.get("enemy_min_steps_to_vp", 99.0)) <= 1.0
    assert float(info.get("enemy_threat_component", 0.0)) <= 0.0
    candidates = list(info.get("mcts_action_candidates", []) or [])
    assert candidates
    first = dict(candidates[0] or {})
    assert "enemy_can_capture_vp_next" in first
    assert "enemy_min_steps_to_vp" in first
    assert "enemy_threat_component" in first
    assert "vp_target_id" in first
    assert "vp_target_source" in first
    assert "vp_distance_after" in first
    assert "vp_distance_source" in first


class _UnitPrefilterConstrainedAdapter:
    def __init__(self) -> None:
        self._done = False

    def initial_state(self, scenario_id: str, seed: int = 0):
        self._done = False
        return SimpleNamespace(
            turn=1,
            to_play="A",
            done=False,
            units=[
                {"unit_id": "u1", "side": "A", "q": 0, "r": 0, "hp": 10, "alive": True},
                {"unit_id": "u2", "side": "A", "q": 1, "r": 0, "hp": 10, "alive": True},
            ],
            vp_hexes=[{"q": 2, "r": 0, "vp_id": "vp1"}],
            vp_owner_by_hex={"2,0": "B"},
        )

    def legal_actions(self):
        return ["MOVE:u1:0:1", "CAPTURE:u2:2:0", "MOVE:u2:1:1"] if not self._done else []

    def apply(self, action_id: str):
        self._done = True
        return SimpleNamespace(
            done=True,
            info={"damage_dealt": 0.0, "kills_dealt": 0},
            state=SimpleNamespace(end_reason="scenario_end", winner="A"),
        )

    def observation(self):
        return SimpleNamespace(
            turn=2,
            to_play="B",
            done=True,
            units=[
                {"unit_id": "u1", "side": "A", "q": 0, "r": 1, "hp": 10, "alive": True},
                {"unit_id": "u2", "side": "A", "q": 2, "r": 0, "hp": 10, "alive": True},
            ],
            vp_hexes=[{"q": 2, "r": 0, "vp_id": "vp1"}],
            vp_owner_by_hex={"2,0": "A"},
        )

    def terminal(self):
        return self._done


class _UnitPrefilterFallbackAdapter:
    def __init__(self) -> None:
        self._done = False

    def initial_state(self, scenario_id: str, seed: int = 0):
        self._done = False
        return SimpleNamespace(
            turn=1,
            to_play="A",
            done=False,
            units=[{"unit_id": "u1", "side": "A", "q": 0, "r": 0, "hp": 10, "alive": True}],
            vp_hexes=[],
            vp_owner_by_hex={},
        )

    def legal_actions(self):
        return ["WAIT", "END_TURN"] if not self._done else []

    def apply(self, action_id: str):
        self._done = True
        return SimpleNamespace(
            done=True,
            info={"damage_dealt": 0.0, "kills_dealt": 0},
            state=SimpleNamespace(end_reason="scenario_end", winner="A"),
        )

    def observation(self):
        return SimpleNamespace(
            turn=2,
            to_play="B",
            done=True,
            units=[{"unit_id": "u1", "side": "A", "q": 0, "r": 0, "hp": 10, "alive": True}],
            vp_hexes=[],
            vp_owner_by_hex={},
        )

    def terminal(self):
        return self._done


def test_unit_prefilter_constrains_candidates_to_selected_unit(monkeypatch) -> None:
    backend = _NativeEZV2SelfplayBackend()
    captured = {}

    def _spy_mcts(**kwargs):
        captured["legal_actions"] = list(kwargs.get("legal_actions", []) or [])
        return MCTSOutput(
            actions=list(captured["legal_actions"]),
            visits=[1 for _ in captured["legal_actions"]],
            probs=[1.0 / max(1, len(captured["legal_actions"])) for _ in captured["legal_actions"]],
            chosen_action=str(captured["legal_actions"][0]),
        )

    monkeypatch.setattr(selfplay_module, "run_mcts_puct", _spy_mcts)
    samples = backend.play_episode(
        adapter=_UnitPrefilterConstrainedAdapter(),
        scenario_id="s1",
        seed=301,
        max_steps=2,
        action_dim=32,
        model=None,
        unit_prefilter_enabled=True,
    )
    assert samples
    constrained = list(captured.get("legal_actions", []) or [])
    assert constrained
    assert all(str(a).split(":")[1] == "u2" for a in constrained)
    info = dict(samples[0].info or {})
    assert bool(info.get("unit_prefilter_enabled", False)) is True
    assert str(info.get("unit_prefilter_selected_unit_id", "")) == "u2"
    assert int(info.get("unit_prefilter_constrained_count", -1)) == len(constrained)
    assert int(info.get("unit_prefilter_global_count", -1)) == 3


def test_unit_prefilter_falls_back_to_global_actions_when_constrained_empty(monkeypatch) -> None:
    backend = _NativeEZV2SelfplayBackend()
    captured = {}

    def _spy_mcts(**kwargs):
        captured["legal_actions"] = list(kwargs.get("legal_actions", []) or [])
        return MCTSOutput(
            actions=list(captured["legal_actions"]),
            visits=[1 for _ in captured["legal_actions"]],
            probs=[1.0 / max(1, len(captured["legal_actions"])) for _ in captured["legal_actions"]],
            chosen_action=str(captured["legal_actions"][0]),
        )

    monkeypatch.setattr(selfplay_module, "run_mcts_puct", _spy_mcts)
    samples = backend.play_episode(
        adapter=_UnitPrefilterFallbackAdapter(),
        scenario_id="s1",
        seed=302,
        max_steps=2,
        action_dim=32,
        model=None,
        unit_prefilter_enabled=True,
    )
    assert samples
    assert list(captured.get("legal_actions", []) or []) == ["WAIT", "END_TURN"]
    info = dict(samples[0].info or {})
    assert bool(info.get("unit_prefilter_enabled", False)) is True
    assert str(info.get("unit_prefilter_selected_unit_id", "")) == ""
    assert int(info.get("unit_prefilter_constrained_count", -1)) == 2
    assert int(info.get("unit_prefilter_global_count", -1)) == 2


class _CombatRewardAdapter:
    def __init__(self) -> None:
        self._done = False

    def initial_state(self, scenario_id: str, seed: int = 0):
        return SimpleNamespace(
            turn=1,
            to_play="A",
            done=False,
            units=[
                {"unit_id": "u1", "side": "A", "q": 0, "r": 0, "hp": 10, "alive": True},
                {"unit_id": "e1", "side": "B", "q": 1, "r": 0, "hp": 5, "alive": True},
            ],
            vp_hexes=[{"q": 1, "r": 0, "vp_id": "vp1"}],
            vp_owner_by_hex={"1,0": "B"},
        )

    def legal_actions(self):
        return ["ATTACK:u1:1:0"] if not self._done else []

    def apply(self, action_id: str):
        self._done = True
        return SimpleNamespace(
            done=True,
            info={"damage_dealt": 5.0, "kills_dealt": 1, "vp_captures": 1},
            state=SimpleNamespace(end_reason="annihilation", winner="A"),
        )

    def observation(self):
        return SimpleNamespace(
            turn=2,
            to_play="A",
            done=True,
            units=[
                {"unit_id": "u1", "side": "A", "q": 1, "r": 0, "hp": 10, "alive": True},
                {"unit_id": "e1", "side": "B", "q": 1, "r": 0, "hp": 0, "alive": False},
            ],
            vp_hexes=[{"q": 1, "r": 0, "vp_id": "vp1"}],
            vp_owner_by_hex={"1,0": "A"},
        )

    def terminal(self):
        return self._done


def test_native_selfplay_combat_and_capture_reward_shaping() -> None:
    backend = _NativeEZV2SelfplayBackend()
    samples = backend.play_episode(
        adapter=_CombatRewardAdapter(),
        scenario_id="s1",
        seed=401,
        max_steps=2,
        action_dim=32,
        model=None,
        reward_shaping={
            "damage_weight": 0.10,
            "kill_weight": 0.50,
            "vp_capture_bonus_per_hex": 1.20,
            "terminal_win_bonus": 0.20,
        },
    )
    assert samples
    info = dict(samples[0].info or {})
    # damage: 5 * 0.10 = 0.50, kill: 1 * 0.50 = 0.50 => combat_reward = 1.00
    assert abs(float(info.get("combat_reward", 0.0)) - 1.00) < 1e-4
    # capture: 1 * 1.20 = 1.20
    assert abs(float(info.get("capture_reward", 0.0)) - 1.20) < 1e-4
    # terminal win: 1.0 + 0.20 = 1.20 => total base >= 3.40
    assert float(samples[0].reward_target) >= 3.20
