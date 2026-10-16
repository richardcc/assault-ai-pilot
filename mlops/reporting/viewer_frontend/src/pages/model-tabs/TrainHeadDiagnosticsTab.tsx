import type { Dict, TrainRow } from "../../types";

export function TrainHeadDiagnosticsTab({
  trainRow,
  trainSummary,
}: {
  trainRow: TrainRow | null;
  trainSummary: Dict | null;
}) {
  if (!trainRow) return <div className="muted">Select a train run from the left panel.</div>;

  const summary = (trainSummary?.summary || trainSummary || {}) as Dict;
  const losses = (trainSummary?.losses || {}) as Dict;

  const heads = [
    {
      head: "Policy Head",
      key: "policy",
      metrics: [
        { label: "train_policy_loss", val: summary.loss_policy ?? losses.policy ?? summary.train_policy_loss },
        { label: "policy_entropy", val: summary.policy_entropy ?? losses.entropy },
        { label: "policy_grad_norm", val: summary.policy_grad_norm ?? losses.policy_grad_norm },
      ],
    },
    {
      head: "Value Head",
      key: "value",
      metrics: [
        { label: "train_value_loss", val: summary.loss_value ?? losses.value ?? summary.train_value_loss },
        { label: "value_grad_norm", val: summary.value_grad_norm ?? losses.value_grad_norm },
        { label: "value_explained_variance", val: summary.value_explained_variance ?? losses.explained_variance },
      ],
    },
    {
      head: "Reward Head",
      key: "reward",
      metrics: [
        { label: "train_reward_loss", val: summary.loss_reward ?? losses.reward ?? summary.train_reward_loss },
        { label: "reward_grad_norm", val: summary.reward_grad_norm ?? losses.reward_grad_norm },
      ],
    },
    {
      head: "Objective Head",
      key: "objective",
      metrics: [
        { label: "train_objective_loss", val: summary.loss_objective ?? losses.objective ?? summary.train_objective_loss },
        { label: "objective_pos_weight", val: summary.objective_pos_weight },
        { label: "objective_loss_weight", val: summary.objective_loss_weight },
      ],
    },
    {
      head: "Consistency Head",
      key: "consistency",
      metrics: [
        { label: "train_consistency_loss", val: summary.loss_consistency ?? losses.consistency ?? summary.train_consistency_loss },
        { label: "train_reanalysis_coverage", val: summary.reanalysis_coverage ?? summary.train_reanalysis_coverage },
        { label: "train_consistency_pairs", val: summary.consistency_pairs ?? summary.train_consistency_pairs },
      ],
    },
  ];

  return (
    <div>
      <h3 style={{ margin: "0 0 8px 0" }}>Train Head Diagnostics</h3>
      <div className="muted" style={{ marginBottom: 12 }}>
        Losses, stability, and gradients per model head during training for <b>{trainRow.run_id}</b>.
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 10 }}>
        {heads.map(({ head, metrics }) => (
          <div key={head} style={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 8, padding: 10 }}>
            <h4 style={{ margin: "0 0 8px 0", color: "#38bdf8" }}>{head}</h4>
            <table>
              <thead>
                <tr><th>metric</th><th>value</th></tr>
              </thead>
              <tbody>
                {metrics.map(({ label, val }) => {
                  const num = Number(val);
                  const display = val === null || val === undefined
                    ? "N/A"
                    : Number.isFinite(num)
                    ? (num < 0.001 && num > 0 ? num.toExponential(3) : num.toFixed(6))
                    : String(val);
                  return (
                    <tr key={label}>
                      <td>{label}</td>
                      <td><b>{display}</b></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ))}
      </div>
    </div>
  );
}
