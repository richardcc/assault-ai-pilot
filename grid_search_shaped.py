import subprocess
import json
from datetime import datetime
from pathlib import Path

from assault_sim.config.ppo_config import PPOConfig
from assault_sim.rewards.shaped_reward import ShapedReward
from assault_sim.train import train_ppo

def main():
    # quick grid
    zero_penalties = [0.3, 0.6, 0.9]
    extra_bonuses = [0.0, 0.2, 0.4]

    # short-training overrides
    PPOConfig.TOTAL_UPDATES = 120
    PPOConfig.NUM_ENVS = 2
    PPOConfig.ROLLOUT_STEPS = 16
    PPOConfig.BATCH_ROLLOUTS = 2

    MODEL_DIR = Path("C:/repos/python/assault/models")
    RESULTS = []

    for zp in zero_penalties:
        for eb in extra_bonuses:
            tag = f"zp{zp:.2f}_eb{eb:.2f}_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}"
            print(f"\n=== RUN {tag} ===")

            reward_fn = ShapedReward(rl_side=PPOConfig.RL_SIDE, zero_damage_penalty=zp, extra_good_trade_bonus=eb)

            # train (short)
            train_ppo.main(reward_fn=reward_fn)

            # evaluate (calls external module)
            ev = subprocess.run(["python", "-m", "assault_sim.evaluation.evaluate_model"], capture_output=True, text=True)

            # save raw stdout
            out_path = MODEL_DIR / f"grid_{tag}.log"
            out_path.write_text(ev.stdout)

            # collect metrics file created by evaluate_model (most recent metrics_report_*.json)
            metrics_files = sorted(MODEL_DIR.parent.glob("metrics_report_*.json"), key=lambda p: p.stat().st_mtime)
            metrics = None
            if metrics_files:
                metrics = json.loads(metrics_files[-1].read_text())

            RESULTS.append({"tag": tag, "zp": zp, "eb": eb, "metrics": metrics})

    # save summary
    summary_path = MODEL_DIR / f"grid_search_summary_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.json"
    summary_path.write_text(json.dumps(RESULTS, indent=2))
    print(f"Grid search finished. Summary: {summary_path}")


if __name__ == '__main__':
    main()
