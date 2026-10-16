import type { Dict, EvalRow } from "../../types";

function n(v: unknown): number | null {
  const x = Number(v);
  return Number.isFinite(x) ? x : null;
}

function pct(v: number | null): string {
  return v === null ? "N/A" : `${(v * 100).toFixed(1)}%`;
}

function num(v: number | null, digits = 4): string {
  return v === null ? "N/A" : v.toFixed(digits);
}

function avg(xs: number[]): number | null {
  if (!xs.length) return null;
  return xs.reduce((a, b) => a + b, 0) / xs.length;
}

const METRIC_ALIASES: Record<string, Record<string, string[]>> = {
  mcts: {
    eval_decision_steps: ["xai_decision_steps"],
    eval_policy_confidence_mean: ["xai_policy_confidence_mean"],
    eval_policy_margin_mean: ["xai_policy_margin_mean"],
    eval_latent_signal_coverage: ["xai_latent_signal_coverage"],
    eval_reaction_window_count: ["reaction_window_count"],
    eval_melee_attempts: ["melee_attempts"],
  },
  objective: {
    eval_vp_capture_opportunity_steps: ["xai_vp_capture_opportunity_steps"],
    eval_vp_capture_taken_steps: ["xai_vp_capture_taken_steps"],
    eval_vp_immediate_capture_opportunity_steps: ["xai_vp_immediate_capture_opportunity_steps"],
    eval_vp_immediate_capture_taken_steps: ["xai_vp_immediate_capture_taken_steps"],
    eval_vp_capture_take_rate: ["xai_vp_capture_take_rate"],
    eval_vp_immediate_capture_take_rate: ["xai_vp_immediate_capture_take_rate"],
    eval_vp_conversion_efficiency: ["vp_conversion_efficiency"],
    eval_vp_immediate_conversion_efficiency: ["vp_immediate_conversion_efficiency"],
  },
};

function readMetricFromEvalRow(row: EvalRow, head: string, key: string): number | null {
  const aliases = [key, ...(METRIC_ALIASES[head]?.[key] || [])];
  const hd = ((row.head_diagnostics_eval || {})[head] || {}) as Record<string, unknown>;

  for (const a of aliases) {
    if (a in hd && n(hd[a]) !== null) return n(hd[a]);
  }

  const results = Array.isArray(row.results) ? row.results : [];
  const vals: number[] = [];
  for (const rr of results) {
    const kpi = (rr.phase_2_9_eval_kpis || {}) as Record<string, unknown>;
    for (const a of aliases) {
      if (a in kpi && n(kpi[a]) !== null) {
        vals.push(n(kpi[a])!);
        break;
      }
    }
  }
  return avg(vals);
}

function getHeadMetric(rows: EvalRow[], head: string, key: string): number | null {
  const vals: number[] = [];
  for (const r of rows) {
    const v = readMetricFromEvalRow(r, head, key);
    if (v !== null) vals.push(v);
  }
  return avg(vals);
}

function computeModelHealth(rows: EvalRow[]) {
  let qSatNum = 0;
  let qSatDen = 0;
  let activeActionsSum = 0;
  let totalVisitsSum = 0;
  let completeCov = 0;
  let covRows = 0;
  let usefulVisitNum = 0;
  let usefulVisitDen = 0;

  for (const er of rows) {
    const results = Array.isArray(er?.results) ? (er.results as Dict[]) : [];
    for (const rr of results) {
      const steps = ((rr.eval_decision_steps_top || rr.eval_decisions_top || []) as Dict[]);
      for (const step of steps) {
        const qClipped = Number(step.mcts_q_clipped_count ?? step.mcts_q_guardrail_clipped_count ?? 0);
        const qDen = Number(step.mcts_q_clip_denominator_count ?? step.mcts_total_visits ?? 0);
        if (Number.isFinite(qClipped) && Number.isFinite(qDen) && qDen > 0) {
          qSatNum += qClipped;
          qSatDen += qDen;
        }

        const active = Number(step.mcts_active_actions);
        const visits = Number(step.mcts_total_visits);
        if (Number.isFinite(active) && Number.isFinite(visits) && visits > 0) {
          activeActionsSum += active;
          totalVisitsSum += visits;
        }

        const cov = String(step.telemetry_coverage_status || "").trim().toLowerCase();
        if (cov) {
          covRows += 1;
          if (cov === "complete") completeCov += 1;
        }

        const cands = Array.isArray(step.mcts_action_candidates) ? (step.mcts_action_candidates as Dict[]) : [];
        for (const c of cands) {
          const v = Number(c.visit_count);
          if (Number.isFinite(v)) {
            usefulVisitDen += 1;
            if (v >= 2) usefulVisitNum += 1;
          }
        }
      }
    }
  }

  return {
    qSatRate: qSatDen > 0 ? qSatNum / qSatDen : null,
    exploreRate: totalVisitsSum > 0 ? activeActionsSum / totalVisitsSum : null,
    covRate: covRows > 0 ? completeCov / covRows : null,
    usefulRate: usefulVisitDen > 0 ? usefulVisitNum / usefulVisitDen : null,
  };
}

export function HeadDiagnosticsTab({ evalRows }: { evalRows: EvalRow[] }) {
  if (!evalRows.length) return <div className="muted">No evaluation data available for head diagnostics.</div>;

  // Model Health Checks (aggregating step telemetry following computeModelHealth)
  const healthFromSteps = computeModelHealth(evalRows);
  const qSat = healthFromSteps.qSatRate ?? getHeadMetric(evalRows, "mcts", "mcts_q_saturation_rate");
  const exploreBreadth = healthFromSteps.exploreRate ?? getHeadMetric(evalRows, "mcts", "eval_exploration_breadth");
  const telemetryCov = healthFromSteps.covRate ?? getHeadMetric(evalRows, "mcts", "eval_latent_signal_coverage");
  const usefulVisits = healthFromSteps.usefulRate ?? getHeadMetric(evalRows, "mcts", "eval_useful_visits_rate");
  const consistencyLoss = getHeadMetric(evalRows, "consistency", "train_consistency_loss");

  const healthChecks: Array<{
    check: string;
    val: number | null;
    fmt: string;
    note: string;
    status: "green" | "yellow" | "red" | "na";
  }> = [
    {
      check: "Q Saturation",
      val: qSat,
      fmt: pct(qSat),
      note: "lower is better (clip guardrail rate)",
      status: qSat === null ? "na" : qSat <= 0.10 ? "green" : qSat <= 0.25 ? "yellow" : "red",
    },
    {
      check: "Exploration Breadth (actions/visits)",
      val: exploreBreadth,
      fmt: pct(exploreBreadth),
      note: "too high often means shallow search",
      status: exploreBreadth === null ? "na" : exploreBreadth <= 0.35 ? "green" : exploreBreadth <= 0.50 ? "yellow" : "red",
    },
    {
      check: "Telemetry Coverage",
      val: telemetryCov,
      fmt: pct(telemetryCov),
      note: "higher is better",
      status: telemetryCov === null ? "na" : telemetryCov >= 0.95 ? "green" : telemetryCov >= 0.80 ? "yellow" : "red",
    },
    {
      check: "Useful Visits (visit_count >= 2)",
      val: usefulVisits,
      fmt: pct(usefulVisits),
      note: "higher is better",
      status: usefulVisits === null ? "na" : usefulVisits >= 0.30 ? "green" : usefulVisits >= 0.15 ? "yellow" : "red",
    },
    {
      check: "Train Consistency Loss",
      val: consistencyLoss,
      fmt: num(consistencyLoss, 6),
      note: "lower is better",
      status: consistencyLoss === null ? "na" : consistencyLoss <= 0.05 ? "green" : consistencyLoss <= 0.20 ? "yellow" : "red",
    },
  ];

  const headSpecs: Array<{ head: string; key: string; metrics: string[] }> = [
    {
      head: "Policy Head",
      key: "policy",
      metrics: ["eval_decision_steps", "eval_confidence_mean", "eval_margin_mean", "eval_latent_signal_coverage", "train_policy_loss"],
    },
    {
      head: "Value Head",
      key: "value",
      metrics: ["train_value_loss", "eval_win_rate_proxy", "eval_avg_return_proxy"],
    },
    {
      head: "Reward Head",
      key: "reward",
      metrics: ["train_reward_loss", "eval_avg_return_proxy", "eval_avg_steps_proxy"],
    },
    {
      head: "Objective Head",
      key: "objective",
      metrics: [
        "train_objective_loss",
        "eval_vp_capture_opportunity_steps",
        "eval_vp_capture_taken_steps",
        "eval_vp_immediate_capture_opportunity_steps",
        "eval_vp_immediate_capture_taken_steps",
        "eval_vp_capture_take_rate",
        "eval_vp_immediate_capture_take_rate",
        "eval_vp_conversion_efficiency",
        "eval_vp_immediate_conversion_efficiency",
      ],
    },
    {
      head: "Consistency Head",
      key: "consistency",
      metrics: [
        "train_consistency_loss",
        "train_consistency_pairs",
        "train_reanalysis_coverage",
        "train_reanalysis_target_drift",
        "train_reanalysis_policy_drift",
      ],
    },
    {
      head: "MCTS Search & Signals",
      key: "mcts",
      metrics: [
        "eval_decision_steps",
        "eval_policy_confidence_mean",
        "eval_policy_margin_mean",
        "eval_latent_signal_coverage",
        "eval_reaction_window_count",
        "eval_melee_attempts",
      ],
    },
  ];

  const badgeColors: Record<string, string> = {
    green: "#22c55e",
    yellow: "#f59e0b",
    red: "#ef4444",
    na: "#94a3b8",
  };

  return (
    <div>
      <h3 style={{ margin: "0 0 8px 0" }}>Model Health Board</h3>
      <div className="muted" style={{ marginBottom: 10 }}>
        Sanity board for EfficientZero v2 telemetry across selected evaluations.
      </div>

      <table style={{ marginBottom: 16 }}>
        <thead>
          <tr>
            <th>check</th>
            <th>status</th>
            <th>value</th>
            <th>note</th>
          </tr>
        </thead>
        <tbody>
          {healthChecks.map(({ check, fmt, note, status }) => (
            <tr key={check}>
              <td><b>{check}</b></td>
              <td>
                <span
                  style={{
                    display: "inline-block",
                    padding: "2px 8px",
                    borderRadius: 999,
                    border: `1px solid ${badgeColors[status]}`,
                    color: badgeColors[status],
                    fontSize: 11,
                    fontWeight: 700,
                  }}
                >
                  {status.toUpperCase()}
                </span>
              </td>
              <td><b>{fmt}</b></td>
              <td className="muted">{note}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3 style={{ margin: "14px 0 8px 0" }}>Head Metrics Breakdown</h3>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 10 }}>
        {headSpecs.map(({ head, key, metrics }) => {
          const rows = metrics.map((m) => {
            const v = getHeadMetric(evalRows, key, m);
            return {
              m,
              val: v,
              fmt: v === null ? "N/A" : m.includes("rate") || m.includes("coverage") || m.includes("efficiency") ? pct(v) : num(v),
            };
          });
          const available = rows.filter((r) => r.val !== null).length;
          const status = available === metrics.length ? "complete" : available > 0 ? "partial" : "none";

          return (
            <div key={head} style={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 8, padding: 10 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                <h4 style={{ margin: 0, color: "#38bdf8" }}>{head}</h4>
                <span
                  style={{
                    fontSize: 11,
                    padding: "1px 6px",
                    borderRadius: 999,
                    border: `1px solid ${badgeColors[status === "complete" ? "green" : status === "partial" ? "yellow" : "red"]}`,
                    color: badgeColors[status === "complete" ? "green" : status === "partial" ? "yellow" : "red"],
                  }}
                >
                  {status} ({available}/{metrics.length})
                </span>
              </div>
              <table>
                <thead>
                  <tr><th>metric</th><th>value</th></tr>
                </thead>
                <tbody>
                  {rows.map(({ m, fmt, val }) => (
                    <tr key={m}>
                      <td>{m}</td>
                      <td>
                        <span style={val !== null ? { color: "#e2e8f0", fontWeight: 600 } : { color: "#64748b" }}>
                          {fmt}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        })}
      </div>
    </div>
  );
}
