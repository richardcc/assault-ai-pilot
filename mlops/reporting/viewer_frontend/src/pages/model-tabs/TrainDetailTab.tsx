import type { Dict, TrainRow } from "../../types";
import { calculateDurationSeconds, formatDuration, formatDurationDetailed, formatLocalDate } from "../../dateUtils";

export function TrainDetailTab({
  trainRow,
  trainSummary,
}: {
  trainRow: TrainRow | null;
  trainSummary: Dict | null;
}) {
  if (!trainRow) {
    return <div className="muted">Select a train run from the left panel.</div>;
  }

  const summary = (trainSummary?.summary || trainSummary || {}) as Dict;
  const obs = (trainSummary?.observation_channels || {}) as Dict;
  const spatialChannels = Array.isArray(obs.spatial_channels)
    ? (obs.spatial_channels as string[])
    : Array.isArray(obs.channels)
    ? (obs.channels as Array<Dict | string>).map((c) => (typeof c === "string" ? c : String(c.name || "")))
    : [];
  const globalFeatures = Array.isArray(obs.global_features) ? (obs.global_features as string[]) : [];
  const config = (trainRow.config || {}) as Dict;
  const modelCfg = (config.model || {}) as Dict;
  const optCfg = (config.optimization || {}) as Dict;
  const selfplayCfg = (config.selfplay || {}) as Dict;

  let dur = typeof trainRow.duration_seconds === "number" ? trainRow.duration_seconds : null;
  if (dur === null || dur === undefined) {
    dur = calculateDurationSeconds(
      trainRow.phase_started_at as string | undefined,
      trainRow.phase_finished_at as string | undefined
    );
  }

  const kpis: Array<{ k: string; v: string; highlight?: boolean }> = [
    { k: "run_id", v: String(trainRow.run_id || "-") },
    { k: "curriculum_phase", v: String(trainRow.curriculum_phase || "-"), highlight: Boolean(trainRow.curriculum_phase) },
    {
      k: "⏱️ phase_duration",
      v: dur !== null && dur >= 0 ? formatDurationDetailed(dur) : "-",
      highlight: dur !== null && dur >= 0,
    },
    { k: "scenario_id", v: String(trainRow.scenario_id || "-") },
    { k: "created_at", v: formatLocalDate(trainRow.created_at_utc) },
    { k: "git_commit", v: String(trainRow.git_commit || "-").slice(0, 10) },
    { k: "parent_run_id", v: String(trainRow.parent_run_id || "-") },
    { k: "is_retrain", v: String(trainRow.is_retrain ?? false) },
    { k: "latest_checkpoint", v: String(trainRow.latest_checkpoint || "-") },
    {
      k: "scenario_mix",
      v: Array.isArray(trainRow.scenario_mix_ids) && trainRow.scenario_mix_ids.length
        ? trainRow.scenario_mix_ids.join(", ")
        : String(trainRow.scenario_id || "-"),
    },
  ];

  // Métricas del summary si existen
  const metricCards: Array<{ k: string; v: string }> = [];
  const lossKeys = ["loss_policy", "loss_value", "loss_reward", "loss_objective", "loss_consistency", "loss_total", "total_loss", "loss"];
  for (const lk of lossKeys) {
    if (lk in summary && summary[lk] !== undefined && summary[lk] !== null) {
      const num = Number(summary[lk]);
      metricCards.push({ k: lk, v: Number.isFinite(num) ? num.toFixed(6) : String(summary[lk]) });
    }
  }

  const statKeys = ["total_steps", "steps", "total_episodes", "episodes", "learning_rate", "lr", "wall_time_seconds", "elapsed_s", "throughput", "steps_per_second", "mcts_simulations", "mcts_iterations"];
  for (const sk of statKeys) {
    if (sk in summary && summary[sk] !== undefined && summary[sk] !== null) {
      const num = Number(summary[sk]);
      let displayVal = Number.isFinite(num) ? (num < 0.01 && num > 0 ? num.toExponential(3) : num.toFixed(2)) : String(summary[sk]);
      if ((sk === "wall_time_seconds" || sk === "elapsed_s") && Number.isFinite(num)) {
        displayVal = `${formatDuration(num)} (${num.toFixed(1)}s)`;
      }
      metricCards.push({ k: sk, v: displayVal });
    }
  }

  return (
    <div>
      <h3 style={{ margin: "0 0 8px 0" }}>Train Metadata</h3>
      <div className="kpi-grid" style={{ marginBottom: 12 }}>
        {kpis.map(({ k, v }) => (
          <div key={k} className="kpi">
            <div className="k">{k}</div>
            <div className="v" style={{ wordBreak: "break-all", fontSize: 11 }}>{v}</div>
          </div>
        ))}
      </div>

      {metricCards.length > 0 && (
        <>
          <h3 style={{ margin: "12px 0 8px 0" }}>Training Metrics Summary</h3>
          <div className="kpi-grid" style={{ marginBottom: 12 }}>
            {metricCards.map(({ k, v }) => (
              <div key={k} className="kpi">
                <div className="k">{k}</div>
                <div className="v" style={{ color: "#22d3ee" }}>{v}</div>
              </div>
            ))}
          </div>
        </>
      )}

      {(spatialChannels.length > 0 || globalFeatures.length > 0) && (
        <>
          <h3 style={{ margin: "12px 0 8px 0" }}>Observation Channels Architecture</h3>
          <table>
            <thead>
              <tr>
                <th style={{ width: "25%" }}>type</th>
                <th style={{ width: "15%" }}>count</th>
                <th>features / channels</th>
              </tr>
            </thead>
            <tbody>
              {spatialChannels.length > 0 && (
                <tr>
                  <td><b>Spatial Channels</b></td>
                  <td>{spatialChannels.length}</td>
                  <td>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                      {spatialChannels.map((c, i) => (
                        <span key={i} style={{ background: "#1e293b", padding: "2px 6px", borderRadius: 4, fontSize: 11 }}>
                          {c}
                        </span>
                      ))}
                    </div>
                  </td>
                </tr>
              )}
              {globalFeatures.length > 0 && (
                <tr>
                  <td><b>Global Features</b></td>
                  <td>{globalFeatures.length}</td>
                  <td>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                      {globalFeatures.map((f, i) => (
                        <span key={i} style={{ background: "#1e293b", padding: "2px 6px", borderRadius: 4, fontSize: 11 }}>
                          {f}
                        </span>
                      ))}
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </>
      )}

      {Object.keys(config).length > 0 && (
        <>
          <h3 style={{ margin: "12px 0 8px 0" }}>Hyperparameters / Configuration</h3>
          <table>
            <thead>
              <tr><th>group</th><th>parameter</th><th>value</th></tr>
            </thead>
            <tbody>
              {Object.entries(modelCfg).map(([k, v]) => (
                <tr key={`model-${k}`}><td>model</td><td>{k}</td><td>{typeof v === "object" ? JSON.stringify(v) : String(v)}</td></tr>
              ))}
              {Object.entries(optCfg).map(([k, v]) => (
                <tr key={`opt-${k}`}><td>optimization</td><td>{k}</td><td>{typeof v === "object" ? JSON.stringify(v) : String(v)}</td></tr>
              ))}
              {Object.entries(selfplayCfg).map(([k, v]) => (
                <tr key={`selfplay-${k}`}><td>selfplay</td><td>{k}</td><td>{typeof v === "object" ? JSON.stringify(v) : String(v)}</td></tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
