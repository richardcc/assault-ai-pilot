from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from assault_sim.config.ppo_config import PPOConfig


@dataclass(frozen=True)
class ScenarioScheduleEntry:
    id: str
    episodes: int


@dataclass(frozen=True)
class TrainConfig:
    rl_sides: tuple[str, ...]
    scenario_schedule: tuple[ScenarioScheduleEntry, ...]
    seed: int

    total_updates: int
    rollout_steps: int
    num_envs: int
    batch_rollouts: int
    lr: float

    eval_interval: int
    eval_episodes: int
    eval_min_improvement: float

    # SB3 official training config
    sb3_total_timesteps: int
    sb3_num_envs: int
    sb3_n_steps: int
    sb3_batch_size: int
    sb3_n_epochs: int
    sb3_gamma: float
    sb3_gae_lambda: float
    sb3_ent_coef: float
    sb3_clip_range: float
    sb3_learning_rate: float
    sb3_device: str
    sb3_eval_freq: int
    sb3_eval_episodes: int
    sb3_net_arch: tuple[int, ...]
    sb3_max_decisions: int
    sb3_zero_damage_penalty: float
    sb3_extra_good_trade_bonus: float

    @property
    def scenario(self) -> str:
        # Primary scenario reference (first phase).
        return self.scenario_schedule[0].id

    @property
    def rl_side(self) -> str:
        # Compatibility alias: first configured RL side.
        return self.rl_sides[0]

    @staticmethod
    def from_defaults() -> "TrainConfig":
        return TrainConfig(
            rl_sides=(PPOConfig.RL_SIDE,),
            scenario_schedule=(ScenarioScheduleEntry(id=PPOConfig.SCENARIO, episodes=1000),),
            seed=PPOConfig.SEED,
            total_updates=PPOConfig.TOTAL_UPDATES,
            rollout_steps=PPOConfig.ROLLOUT_STEPS,
            num_envs=PPOConfig.NUM_ENVS,
            batch_rollouts=PPOConfig.BATCH_ROLLOUTS,
            lr=PPOConfig.LR,
            eval_interval=PPOConfig.EVAL_INTERVAL,
            eval_episodes=PPOConfig.EVAL_EPISODES,
            eval_min_improvement=PPOConfig.EVAL_MIN_IMPROVEMENT,
            sb3_total_timesteps=1_000_000,
            sb3_num_envs=8,
            sb3_n_steps=2048,
            sb3_batch_size=1024,
            sb3_n_epochs=10,
            sb3_gamma=0.995,
            sb3_gae_lambda=0.97,
            sb3_ent_coef=0.01,
            sb3_clip_range=0.15,
            sb3_learning_rate=1e-4,
            sb3_device="cpu",
            sb3_eval_freq=25_000,
            sb3_eval_episodes=20,
            sb3_net_arch=(256, 256),
            sb3_max_decisions=400,
            sb3_zero_damage_penalty=0.8,
            sb3_extra_good_trade_bonus=0.3,
        )

    @staticmethod
    def from_dict(payload: dict[str, Any]) -> "TrainConfig":
        base = TrainConfig.from_defaults()
        merged = {**asdict(base), **payload}
        raw_rl_sides = merged.get("rl_sides")
        if isinstance(raw_rl_sides, list) and raw_rl_sides:
            rl_sides = tuple(str(s).upper() for s in raw_rl_sides)
        else:
            # Compatibility/fallback path
            rl_sides = (str(merged.get("rl_side", PPOConfig.RL_SIDE)).upper(),)

        raw_schedule = merged.get("scenario_schedule")
        if not isinstance(raw_schedule, list) or not raw_schedule:
            raise ValueError(
                "train_config.json requires non-empty 'scenario_schedule' list, "
                "e.g. [{\"id\":\"scenario_name\",\"episodes\":1000}]"
            )
        schedule = tuple(
            ScenarioScheduleEntry(
                id=str(item["id"]),
                episodes=int(item["episodes"]),
            )
            for item in raw_schedule
        )
        for entry in schedule:
            if entry.episodes <= 0:
                raise ValueError(
                    f"scenario_schedule entry '{entry.id}' must have episodes > 0"
                )
        return TrainConfig(
            rl_sides=rl_sides,
            scenario_schedule=schedule,
            seed=int(merged["seed"]),
            total_updates=int(merged["total_updates"]),
            rollout_steps=int(merged["rollout_steps"]),
            num_envs=int(merged["num_envs"]),
            batch_rollouts=int(merged["batch_rollouts"]),
            lr=float(merged["lr"]),
            eval_interval=int(merged["eval_interval"]),
            eval_episodes=int(merged["eval_episodes"]),
            eval_min_improvement=float(merged["eval_min_improvement"]),
            sb3_total_timesteps=int(merged["sb3_total_timesteps"]),
            sb3_num_envs=int(merged["sb3_num_envs"]),
            sb3_n_steps=int(merged["sb3_n_steps"]),
            sb3_batch_size=int(merged["sb3_batch_size"]),
            sb3_n_epochs=int(merged["sb3_n_epochs"]),
            sb3_gamma=float(merged["sb3_gamma"]),
            sb3_gae_lambda=float(merged["sb3_gae_lambda"]),
            sb3_ent_coef=float(merged["sb3_ent_coef"]),
            sb3_clip_range=float(merged["sb3_clip_range"]),
            sb3_learning_rate=float(merged["sb3_learning_rate"]),
            sb3_device=str(merged["sb3_device"]),
            sb3_eval_freq=int(merged["sb3_eval_freq"]),
            sb3_eval_episodes=int(merged["sb3_eval_episodes"]),
            sb3_net_arch=tuple(int(x) for x in merged["sb3_net_arch"]),
            sb3_max_decisions=int(merged["sb3_max_decisions"]),
            sb3_zero_damage_penalty=float(merged["sb3_zero_damage_penalty"]),
            sb3_extra_good_trade_bonus=float(merged["sb3_extra_good_trade_bonus"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_train_config(path: Path | None) -> TrainConfig:
    if path is None or not path.exists():
        return TrainConfig.from_defaults()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return TrainConfig.from_dict(data)

