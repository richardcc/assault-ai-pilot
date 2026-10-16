import type { Dict, TrainRow } from "../../types";

const OBJECTIVE_REWARD_DEFAULTS: Record<string, unknown> = {
  objective_loss_weight: 0.12,
  objective_target_mode: "progress",
  objective_pos_weight: 6.8,
  objective_opportunity_max_dist: 3.0,
  mcts_q_clip_abs: 20.0,
  mcts_q_root_normalization_mode: "adaptive_minmax",
  mcts_q_root_normalization_strength: 0.40,
  mcts_q_flat_spread_epsilon: 1.0e-6,
  mcts_vp_flat_q_score_epsilon: 0.02,
  mcts_vp_flat_q_min_progress: 0.0,
  aux_objective_enabled: false,
  aux_objective_loss_weight: 0.0,
  aux_intent_loss_weight: 0.5,
  aux_multi_vp_loss_weight: 0.5,
  aux_multi_vp_feature_dim: 4,
  aux_intent_classes: 8,
  objective_progress_positive_threshold: 0.0,
  objective_opportunity_near_vp_max_dist: 3.0,
  assault_advantage_prob_threshold: 0.55,
  assault_advantage_margin_threshold: 0.20,
  assault_advantage_legal_count_threshold: 6,
  assault_advantage_cover_max: 0.35,
  assault_advantage_min_score: 2,
  high_confidence_prob_threshold: 0.60,
  high_confidence_margin_threshold: 0.25,
  near_vp_max_dist: 2.0,
  strong_progress_delta_threshold: 2.0,
  conversion_window_steps_after_progress: 2,
  decision_flip_legal_count_tolerance: 2,
  mcts_vp_tiebreak_epsilon: 0.015,
  capture_bonus: 0.70,
  vp_capture_bonus_per_hex: 1.20,
  objective_progress_bonus_per_hex: 0.95,
  objective_no_progress_penalty: 0.46,
  objective_no_progress_attack_penalty: 0.40,
  reaction_fire_soft_signal_enabled: true,
  reaction_fire_soft_signal_weight: 0.04,
  reaction_fire_soft_signal_expected_damage_scale: 4.0,
  global_strategy_soft_enabled: true,
  global_strategy_vp_control_net_gain_weight: 0.08,
  global_strategy_units_in_vp_ring_weight: 0.04,
  global_strategy_enemy_vp_threat_reduced_weight: 0.05,
  global_strategy_sustained_vp_advantage_weight: 0.02,
  global_strategy_role_consistency_weight: 0.03,
  global_strategy_setup_convert_weight: 0.03,
  global_strategy_vp_ring_radius: 2,
  global_strategy_enemy_threat_radius: 3,
  global_strategy_sustained_advantage_min_turns: 2,
  global_strategy_total_cap_abs: 0.15,
  vp_horizon_soft_enabled: true,
  vp_horizon_soft_weight: 0.02,
  vp_horizon_soft_cap_steps: 8.0,
};

export function ObjectiveRewardConfigTab({ trainRow }: { trainRow: TrainRow | null }) {
  if (!trainRow) return <div className="muted">Select a train run from the left panel.</div>;

  const orc = (trainRow.objective_reward_config || {}) as Dict;
  const rawWarnings = Array.isArray(orc.preflight_warnings) ? (orc.preflight_warnings as string[]) : [];

  // Collect all active parameters
  const activeParams: Record<string, unknown> = {};

  const scanObject = (obj: unknown) => {
    if (!obj || typeof obj !== "object") return;
    for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
      if (v !== null && typeof v === "object" && !Array.isArray(v)) {
        scanObject(v);
      } else {
        activeParams[k] = v;
      }
    }
  };

  scanObject(trainRow.config);
  scanObject(orc);

  // Filter out false-positive warnings if the corresponding block is present in config
  const warnings = rawWarnings.filter((w) => {
    const hasSignal = Boolean(activeParams.objective_signal || orc.objective_signal || (trainRow.config as Dict)?.objective_signal);
    const hasHead = Boolean(activeParams.objective_head || orc.objective_head || (trainRow.config as Dict)?.objective_head);
    const hasReporting = Boolean(activeParams.objective_reporting || orc.objective_reporting || (trainRow.config as Dict)?.objective_reporting);
    const hasRewardShaping = Boolean(activeParams.reward_shaping || orc.reward_shaping || ((trainRow.config as Dict)?.selfplay as Dict)?.reward_shaping);

    if (w === "missing.train.objective_signal" && hasSignal) return false;
    if (w === "missing.train.objective_head" && hasHead) return false;
    if (w === "missing.train.objective_reporting" && hasReporting) return false;
    if (w === "missing.selfplay.reward_shaping" && hasRewardShaping) return false;
    return true;
  });

  const keys = Array.from(new Set([...Object.keys(OBJECTIVE_REWARD_DEFAULTS), ...Object.keys(activeParams)])).sort();

  return (
    <div>
      <h3 style={{ margin: "0 0 8px 0" }}>Objective & Reward Configuration</h3>
      <div className="muted" style={{ marginBottom: 12 }}>
        Canonical objective and reward shaping parameters for <b>{trainRow.run_id}</b> compared against canonical defaults.
      </div>

      {warnings.length > 0 && (
        <div style={{ background: "#7f1d1d", border: "1px solid #ef4444", borderRadius: 6, padding: 8, marginBottom: 12 }}>
          <h4 style={{ margin: "0 0 4px 0", color: "#fca5a5" }}>⚠️ Preflight Warnings</h4>
          <ul style={{ margin: 0, paddingLeft: 20 }}>
            {warnings.map((w, i) => <li key={i}>{w}</li>)}
          </ul>
        </div>
      )}

      <table>
        <thead>
          <tr>
            <th>parameter</th>
            <th>configured value</th>
            <th>canonical default</th>
            <th>status</th>
          </tr>
        </thead>
        <tbody>
          {keys.map((k) => {
            const configured = activeParams[k];
            const canonical = OBJECTIVE_REWARD_DEFAULTS[k];
            const hasConfigured = k in activeParams;
            const isDiff = hasConfigured && canonical !== undefined && String(configured) !== String(canonical);

            return (
              <tr key={k} style={isDiff ? { background: "rgba(56, 189, 248, 0.08)" } : undefined}>
                <td><b>{k}</b></td>
                <td>
                  {hasConfigured ? (
                    <span style={isDiff ? { color: "#38bdf8", fontWeight: "bold" } : undefined}>
                      {String(configured)}
                    </span>
                  ) : (
                    <span className="muted">(default)</span>
                  )}
                </td>
                <td className="muted">{canonical !== undefined ? String(canonical) : "N/A"}</td>
                <td>
                  {isDiff ? (
                    <span style={{ color: "#38bdf8", fontSize: 11, fontWeight: "bold" }}>MODIFIED</span>
                  ) : hasConfigured ? (
                    <span style={{ color: "#22c55e", fontSize: 11 }}>EXPLICIT</span>
                  ) : (
                    <span className="muted" style={{ fontSize: 11 }}>DEFAULT</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
