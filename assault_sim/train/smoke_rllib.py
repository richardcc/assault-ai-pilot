from __future__ import annotations

from pathlib import Path


def main() -> None:
    try:
        import ray
        from ray.rllib.algorithms.ppo import PPOConfig as RLlibPPOConfig
        from ray.tune.registry import register_env
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "RLlib is not installed. Install with: pip install \"ray[rllib]\""
        ) from exc

    from assault_sim.envs.gym_assault_env import GymAssaultEnv

    repo_root = Path(__file__).resolve().parents[2]
    env_name = "assault_gym_smoke_v1"

    def env_creator(env_config):
        return GymAssaultEnv(
            scenario=env_config.get("scenario", "phase01_seq001_initial_contact"),
            rl_side=env_config.get("rl_side", "US"),
            seed=int(env_config.get("seed", 42)),
            sim_config_path=repo_root / "assault_sim" / "config" / "sim_config.yaml",
            env_config_path=repo_root / "assault_sim" / "config" / "env_config.json",
            max_decisions=int(env_config.get("max_decisions", 120)),
        )

    register_env(env_name, env_creator)

    ray.init(ignore_reinit_error=True, include_dashboard=False)
    algo = None
    try:
        cfg = (
            RLlibPPOConfig()
            .environment(
                env=env_name,
                env_config={
                    "scenario": "phase01_seq001_initial_contact",
                    "rl_side": "US",
                    "seed": 42,
                    "max_decisions": 120,
                },
            )
            .framework("torch")
            .resources(num_gpus=0)
            .rollouts(num_rollout_workers=0)
            .training(
                train_batch_size=128,
                sgd_minibatch_size=64,
                num_sgd_iter=1,
            )
        )

        algo = cfg.build()
        result = algo.train()
        env_steps = result.get("num_env_steps_sampled") or result.get("timesteps_total")
        reward_mean = result.get("episode_reward_mean")
        print(f"RLLIB_SMOKE_OK env_steps={env_steps} reward_mean={reward_mean}")
    finally:
        if algo is not None:
            algo.stop()
        ray.shutdown()


if __name__ == "__main__":
    main()

