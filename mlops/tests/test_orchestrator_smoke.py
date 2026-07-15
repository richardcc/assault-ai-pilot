from pathlib import Path

from mlops.orchestrator.run import run_experiment
from mlops.registry.base import TrainResult


def test_orchestrator_smoke(monkeypatch, tmp_path: Path) -> None:
    curriculum = tmp_path / "curriculum.yaml"
    curriculum.write_text(
        """
stages:
  - name: smoke
    scenario_id: s1
    seeds: [42]
    train_iterations: 1
    eval_episodes: 1
    train_agents: [muzero, baseline_random]
""".strip(),
        encoding="utf-8",
    )
    bench_cfg = tmp_path / "bench.yaml"
    bench_cfg.write_text("paths: {}\nbenchmark: {}\n", encoding="utf-8")
    muzero_cfg = tmp_path / "muzero.yaml"
    muzero_cfg.write_text("paths: {}\nscenario: {}\nmodel: {}\nselfplay: {}\ntrain: {}\n", encoding="utf-8")
    exp_cfg = tmp_path / "experiment.yaml"
    exp_cfg.write_text(
        f"""
experiment_name: smoke_exp
agents: [muzero, baseline_random]
paths:
  run_root: {tmp_path.as_posix()}
  curriculum_config: {curriculum.as_posix()}
  benchmark_config: {bench_cfg.as_posix()}
  muzero_config: {muzero_cfg.as_posix()}
""".strip(),
        encoding="utf-8",
    )

    class _Adapter:
        def __init__(self, name: str) -> None:
            self.name = name

        def train(self, *, config_path: str, stage_name: str, scenario_id: str):
            return TrainResult(
                agent_name=self.name,
                run_id=f"{self.name}_run",
                checkpoint_path="runs/muzero_stub/checkpoints/iter_1.pt" if self.name == "muzero" else "",
                metadata={"stage_name": stage_name, "scenario_id": scenario_id},
            )

    monkeypatch.setattr(
        "mlops.orchestrator.run.build_default_registry",
        lambda run_root: {"muzero": _Adapter("muzero"), "baseline_random": _Adapter("baseline_random")},
    )
    monkeypatch.setattr(
        "mlops.orchestrator.run.run_benchmark",
        lambda **kwargs: {
            "scenario_id": "s1",
            "run_id": "muzero_stub",
            "results": [
                {"agent_name": "muzero_stub", "win_rate": 0.6},
                {"agent_name": "baseline_random", "win_rate": 0.4},
            ],
            "phase_2_9_promotion_gate": {"status": "PASS", "checks": {"reaction_contract_pass": True}},
        },
    )
    out = run_experiment(config_path=str(exp_cfg))
    assert out["decision_report"]["decision"] == "PROMOTE"
