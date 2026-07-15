from __future__ import annotations

import os
from typing import Any, Protocol

import torch

from agents.efficientzero_v2.core.mcts import run_mcts_puct
from agents.efficientzero_v2.core.objective_signals import objective_step_signal
from agents.efficientzero_v2.core.targets import build_sample

DEFAULT_ACTION_DIM = 32
DEFAULT_OBS_CHANNELS = 32
DEFAULT_OBS_HEIGHT = 16
DEFAULT_OBS_WIDTH = 16


def _observation_to_vector(obs) -> list[float]:
    alive = sum(1 for u in obs.units if u.get("alive", True))
    mean_hp = 0.0
    hp_values = [float(u.get("hp", 0.0)) for u in obs.units if isinstance(u.get("hp"), (int, float))]
    if hp_values:
        mean_hp = float(sum(hp_values) / max(1, len(hp_values)))
    return [float(obs.turn), float(alive), float(mean_hp), float(obs.done)]


def _observation_to_tensor(obs, channels: int = DEFAULT_OBS_CHANNELS, height: int = DEFAULT_OBS_HEIGHT, width: int = DEFAULT_OBS_WIDTH):
    out = torch.zeros(int(channels), int(height), int(width), dtype=torch.float32)
    for unit in list(getattr(obs, "units", []) or []):
        q = unit.get("q")
        r = unit.get("r")
        if not isinstance(q, int) or not isinstance(r, int):
            continue
        x = int(q) % max(1, int(width))
        y = int(r) % max(1, int(height))
        ally = str(unit.get("side", "")) == str(getattr(obs, "to_play", ""))
        hp = float(unit.get("hp", 0.0) or 0.0) / 10.0
        out[0 if ally else 1, y, x] = 1.0
        out[2 if ally else 3, y, x] = max(0.0, min(1.0, hp))
    return out


def _action_id_to_index(action_id: str, action_dim: int) -> int:
    return sum(str(action_id).encode("utf-8")) % int(action_dim)


def _parse_action_id(action_id: str) -> tuple[str, str]:
    parts = str(action_id).split(":")
    return (parts[0] if parts else "", parts[1] if len(parts) > 1 else "")


def _count_capture_options(legal_actions: list[str], vp_owner_by_hex: dict[str, str], to_play: str) -> int:
    side = str(to_play or "").strip().upper()
    count = 0
    for action_id in list(legal_actions or []):
        kind = str(_parse_action_id(action_id)[0]).upper()
        if "CAPTURE" in kind:
            count += 1
            continue
        parts = str(action_id).split(":")
        if len(parts) < 2:
            continue
        try:
            q = int(parts[-2])
            r = int(parts[-1])
        except Exception:
            continue
        owner = str((vp_owner_by_hex or {}).get(f"{q},{r}", "")).strip().upper()
        if owner and owner != side:
            count += 1
    return count


def _priors_and_values(model, obs_encoded, legal_actions: list[str], action_dim: int):
    if model is None or not legal_actions:
        return None, None, {}
    model_device = next(model.parameters()).device
    with torch.inference_mode():
        if str(getattr(model, "encoder_type", "mlp")) == "cnn":
            obs_tensor = obs_encoded.unsqueeze(0).to(model_device)
        else:
            obs_tensor = torch.tensor([obs_encoded], dtype=torch.float32, device=model_device)
        _, policy_logits, value_root, _ = model.initial_inference(obs_tensor)
        logits = policy_logits[0]
        idx = [_action_id_to_index(a, action_dim) for a in legal_actions]
        idx_t = torch.tensor(idx, dtype=torch.long, device=model_device)
        legal_logits = torch.index_select(logits, dim=0, index=idx_t).to(torch.float32)
        probs = torch.softmax(legal_logits, dim=0).detach().cpu().tolist()
        priors = {a: float(p) for a, p in zip(legal_actions, probs)}
        values = {a: float(value_root[0, 0].item()) for a in legal_actions}
        return priors, values, {
            "latent_top_indices": [],
            "latent_top_values": [],
            "predicted_value_root": float(value_root[0, 0].item()),
        }


class SelfplayBackend(Protocol):
    def play_episode(self, **kwargs: Any) -> list:
        ...


class _NativeEZV2SelfplayBackend:
    def play_episode(self, **kwargs: Any) -> list:
        return list(self._play_episode(**kwargs))

    def _play_episode(
        self,
        adapter,
        scenario_id: str,
        seed: int,
        max_steps: int = 100,
        max_steps_override: int = 0,
        max_turns_override: int = 0,
        action_dim: int = DEFAULT_ACTION_DIM,
        model=None,
        mcts_simulations: int = 32,
        mcts_c_puct: float = 1.5,
        mcts_temperature: float = 1.0,
        mcts_dirichlet_alpha: float = 0.3,
        mcts_dirichlet_epsilon: float = 0.0,
        timeout_penalty: float = -0.1,
        objective_opportunity_near_vp_max_dist: float = 2.0,
        **_: Any,
    ) -> list:
        samples = []
        obs = adapter.initial_state(scenario_id=str(scenario_id), seed=int(seed))
        unit_count = len(getattr(obs, "units", []) or [])
        effective_max_steps = int(max_steps)
        if int(max_turns_override) > 0 and unit_count > 0:
            effective_max_steps = int(max_turns_override) * int(unit_count)
        elif int(max_steps_override) > 0:
            effective_max_steps = int(max_steps_override)

        for step_idx in range(max(1, effective_max_steps)):
            legal = list(adapter.legal_actions() or [])
            if not legal:
                break
            legal_reaction_options = sum(1 for a in legal if str(a).upper().startswith("OPPORTUNITY_"))
            legal_capture_options = _count_capture_options(legal, dict(getattr(obs, "vp_owner_by_hex", {}) or {}), str(getattr(obs, "to_play", "") or ""))
            if str(getattr(model, "encoder_type", "mlp")) == "cnn":
                obs_encoded = _observation_to_tensor(
                    obs,
                    channels=int(getattr(model, "observation_channels", DEFAULT_OBS_CHANNELS)) if model is not None else DEFAULT_OBS_CHANNELS,
                    height=int(getattr(model, "observation_height", DEFAULT_OBS_HEIGHT)) if model is not None else DEFAULT_OBS_HEIGHT,
                    width=int(getattr(model, "observation_width", DEFAULT_OBS_WIDTH)) if model is not None else DEFAULT_OBS_WIDTH,
                )
            else:
                obs_encoded = _observation_to_vector(obs)
            priors, values, xai = _priors_and_values(model, obs_encoded, legal, int(action_dim))
            mcts = run_mcts_puct(
                legal_actions=legal,
                num_simulations=int(mcts_simulations),
                c_puct=float(mcts_c_puct),
                priors_by_action=priors,
                values_by_action=values,
                temperature=float(mcts_temperature),
                dirichlet_alpha=float(mcts_dirichlet_alpha),
                dirichlet_epsilon=float(mcts_dirichlet_epsilon),
            )
            chosen = str(mcts.chosen_action)
            chosen_prob = 0.0
            for action_id, prob in zip(list(mcts.actions or []), list(mcts.probs or [])):
                if str(action_id) == chosen:
                    chosen_prob = float(prob)
                    break
            sorted_probs = sorted([float(p) for p in list(mcts.probs or [])], reverse=True)
            mcts_margin = float((sorted_probs[0] if sorted_probs else 0.0) - (sorted_probs[1] if len(sorted_probs) > 1 else 0.0))
            transition = adapter.apply(chosen)
            post_obs = adapter.observation()
            action_kind, unit_id = _parse_action_id(chosen)
            side = ""
            for u in list(getattr(obs, "units", []) or []):
                if str(u.get("unit_id", "")) == str(unit_id):
                    side = str(u.get("side", "") or "")
                    break
            before_vp = dict(getattr(obs, "vp_owner_by_hex", {}) or {})
            after_vp = dict(getattr(post_obs, "vp_owner_by_hex", {}) or {})
            vp_captures = sum(1 for k, v in after_vp.items() if before_vp.get(k) != v and str(v) == str(side))
            objective = objective_step_signal(
                side=str(side),
                vp_hexes=list(getattr(obs, "vp_hexes", []) or []),
                legal_actions=legal,
                before_units=list(getattr(obs, "units", []) or []),
                before_vp_owner_by_hex=before_vp,
                after_units=list(getattr(post_obs, "units", []) or []),
                after_vp_owner_by_hex=after_vp,
                legal_capture_options=int(legal_capture_options),
                capture_taken=("CAPTURE" in str(action_kind).upper()),
                vp_captures=int(vp_captures),
                vp_gain_for_side=int(vp_captures),
                opportunity_near_vp_max_dist=float(objective_opportunity_near_vp_max_dist),
            )
            info = dict(getattr(transition, "info", {}) or {})
            damage_dealt = float(info.get("damage_dealt", 0.0) or 0.0)
            kills_dealt = int(info.get("kills_dealt", 0) or 0)
            done = bool(getattr(transition, "done", False))
            terminal_reason = str(getattr(getattr(transition, "state", None), "end_reason", "") or "")
            reward = 0.0 if not done else (1.0 if str(getattr(getattr(transition, "state", None), "winner", "") or "") == str(getattr(obs, "to_play", "") or "") else -1.0)
            samples.append(
                build_sample(
                    observation=obs_encoded,
                    action_index=_action_id_to_index(chosen, int(action_dim)),
                    action_dim=int(action_dim),
                    reward=float(reward),
                    done=done,
                    info={
                        "step": int(step_idx),
                        "action_id": chosen,
                        "action_kind": str(action_kind),
                        "unit_id": str(unit_id),
                        "unit_side": str(side),
                        "game_turn": int(getattr(obs, "turn", 0) or 0),
                        "to_play": str(getattr(obs, "to_play", "") or ""),
                        "damage_dealt": float(damage_dealt),
                        "kills_dealt": int(kills_dealt),
                        "legal_action_count": int(len(legal)),
                        "legal_reaction_options": int(legal_reaction_options),
                        "legal_capture_options": int(legal_capture_options),
                        "vp_captures": int(vp_captures),
                        "objective_had_opportunity": int(objective.objective_had_opportunity),
                        "objective_progress_delta": float(objective.objective_progress_delta),
                        "objective_converted": int(objective.objective_converted),
                        "objective_min_dist_before": float(objective.objective_min_dist_before),
                        "objective_min_dist_after": float(objective.objective_min_dist_after),
                        "objective_outcome_bucket_actor": "unknown",
                        "chosen_action_prob": float(chosen_prob),
                        "mcts_margin": float(mcts_margin),
                        "latent_top_indices": list(xai.get("latent_top_indices", []) or []),
                        "latent_top_values": list(xai.get("latent_top_values", []) or []),
                        "predicted_value_root": float(xai.get("predicted_value_root", 0.0)),
                        "timeout": False,
                        "terminal_reason": str(terminal_reason),
                    },
                )
            )
            obs = post_obs
            if done:
                break

        if samples and not adapter.terminal():
            samples[-1].reward_target = float(timeout_penalty)
            samples[-1].value_target = float(timeout_penalty)
            samples[-1].info["timeout"] = True
            samples[-1].info["terminal_reason"] = "turn_unit_budget"
        return samples


class _LegacyMuZeroSelfplayBackend:
    def play_episode(self, **kwargs: Any) -> list:
        from agents.muzero.core.selfplay import play_episode as muzero_play_episode

        return list(muzero_play_episode(**kwargs))


def _default_backend() -> SelfplayBackend:
    backend_env = str(os.getenv("ASSAULT_EZV2_SELFPLAY_BACKEND", "ezv2")).strip().lower()
    if backend_env == "legacy_muzero":
        return _LegacyMuZeroSelfplayBackend()
    return _NativeEZV2SelfplayBackend()


_BACKEND: SelfplayBackend = _default_backend()


def current_backend_name() -> str:
    return _BACKEND.__class__.__name__


def set_selfplay_backend(backend: SelfplayBackend) -> None:
    global _BACKEND
    _BACKEND = backend


def play_episode(**kwargs: Any) -> list:
    return _BACKEND.play_episode(**kwargs)


__all__ = ["play_episode", "set_selfplay_backend", "current_backend_name", "SelfplayBackend"]
