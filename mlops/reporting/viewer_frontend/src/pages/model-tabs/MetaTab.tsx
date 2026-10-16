import type { EvalRow, ModelPayload, TrainRow } from "../../types";
import { formatLocalDate } from "../../dateUtils";

export function MetaTab({
  model,
  evalHistory,
}: {
  model: ModelPayload | null;
  evalHistory: EvalRow[];
}) {
  const m = model || {};
  const trains = Array.isArray(m.train_history) ? (m.train_history as TrainRow[]) : [];
  const latestTrain = trains[0];
  const trainCounts = (m.scenario_train_counts || {}) as Record<string, number>;
  const evalCounts = (m.scenario_eval_counts || {}) as Record<string, number>;
  const scenarios = Array.from(new Set([...(m.scenarios_seen || []), ...Object.keys(trainCounts), ...Object.keys(evalCounts)])).sort();

  const kpis: Array<{ k: string; v: string }> = [
    { k: "model_id", v: String(m.model_id || "-") },
    { k: "engine", v: String(m.engine || "-") },
    { k: "algorithm", v: String((m as Record<string, unknown>).algorithm || "-") },
    { k: "config_fingerprint", v: String(m.config_fingerprint || "-") },
    { k: "latest_train_run_id", v: String(m.latest_train_run_id || (latestTrain || {}).run_id || "-") },
    { k: "latest_eval_created_at", v: formatLocalDate(m.latest_eval_created_at_utc) },
    { k: "train_runs_count", v: String(m.train_history_total_count ?? trains.length) },
    { k: "eval_history_total_count", v: String(m.eval_history_total_count ?? evalHistory.length) },
  ];

  return (
    <div>
      <h3 style={{ margin: "0 0 8px 0" }}>Model Identity & Specification</h3>
      <div className="kpi-grid" style={{ marginBottom: 14 }}>
        {kpis.map(({ k, v }) => (
          <div key={k} className="kpi">
            <div className="k">{k}</div>
            <div className="v" style={{ wordBreak: "break-all", fontSize: 11 }}>{v}</div>
          </div>
        ))}
      </div>

      {scenarios.length > 0 && (
        <>
          <h3 style={{ margin: "14px 0 8px 0" }}>Scenarios Seen ({scenarios.length})</h3>
          <table style={{ marginBottom: 16 }}>
            <thead>
              <tr>
                <th>scenario_id</th>
                <th>train_count</th>
                <th>eval_count</th>
              </tr>
            </thead>
            <tbody>
              {scenarios.map((s) => (
                <tr key={s}>
                  <td><b>{s}</b></td>
                  <td>{trainCounts[s] ?? 0}</td>
                  <td>{evalCounts[s] ?? 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {evalHistory.length > 0 && (
        <>
          <h3 style={{ margin: "14px 0 8px 0" }}>Evaluations Index ({evalHistory.length})</h3>
          <table>
            <thead>
              <tr>
                <th>eval_id</th>
                <th>created_at</th>
                <th>scenario_id</th>
                <th>train_run_id</th>
                <th>profiles_count</th>
              </tr>
            </thead>
            <tbody>
              {evalHistory.slice(0, 50).map((ev) => (
                <tr key={String(ev.eval_id || Math.random())}>
                  <td><b>{String(ev.eval_id || "-")}</b></td>
                  <td>{formatLocalDate(ev.created_at_utc)}</td>
                  <td>{String(ev.scenario_id || "-")}</td>
                  <td><code>{String(ev.train_run_id || "-")}</code></td>
                  <td>{Array.isArray(ev.results) ? ev.results.length : 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
