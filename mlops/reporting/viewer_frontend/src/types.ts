export type Dict = Record<string, unknown>;

export interface TrainRow extends Dict {
  run_id?: string;
  scenario_id?: string;
  scenario_ids?: string[];
  scenario_mix_ids?: string[];
  scenario_mix_weights?: number[];
  created_at_utc?: string;
  git_commit?: string;
  is_retrain?: boolean;
  parent_run_id?: string;
  latest_checkpoint?: string;
  config?: Dict;
  objective_reward_config?: {
    objective_signal?: Dict;
    objective_head?: Dict;
    objective_reporting?: Dict;
    reward_shaping?: Dict;
    preflight_warnings?: string[];
  };
}

export interface TrainSummaryPayload extends Dict {
  summary?: Dict;
  metrics?: Dict;
  losses?: Dict;
  hyperparameters?: Dict;
  observation_channels?: {
    spatial_channels?: string[];
    global_features?: string[];
    shapes?: Dict;
    [key: string]: unknown;
  };
  total_steps?: number;
  total_episodes?: number;
  wall_time_seconds?: number;
}

export interface EvalResultRow extends Dict {
  agent_name?: string;
  matchup_profile?: string;
  matchup_group?: string;
  measurement_goal?: string;
  policy_name?: string;
  policy_by_side?: Record<string, string>;
  controller_by_side?: Record<string, string>;
  episodes?: number;
  avg_return?: number;
  avg_steps?: number;
  terminal_rate?: number;
  timeout_rate?: number;
  non_timeout_resolution_rate?: number;
  win_rate?: number;
  resolved_non_timeout_win_rate?: number;
  score?: number;
  gate_ok?: boolean;
  terminal_reasons?: Record<string, number>;
  vp_initial_avg_by_side?: Record<string, number>;
  vp_final_avg_by_side?: Record<string, number>;
  vp_net_avg_by_side?: Record<string, number>;
  vp_gained_avg_by_side?: Record<string, number>;
  vp_lost_avg_by_side?: Record<string, number>;
  vp_final_distribution_by_side?: Record<string, Dict>;
  winner_side_counts?: Record<string, number>;
  winner_side_rates?: Record<string, number>;
  tracked_side?: string;
  tracked_metric?: string;
  tracked_captured_avg?: number;
  tracked_to_engage_ratio_avg?: number;
  scenario_outcome_counts?: Record<string, number>;
  scenario_outcome_rates?: Record<string, number>;
  scenario_outcome_class_counts?: Record<string, number>;
  scenario_outcome_class_rates?: Record<string, number>;
  scenario_outcome_class_counts_by_side?: Record<string, Record<string, number>>;
  scenario_outcome_class_rates_by_side?: Record<string, Record<string, number>>;
  tracked_outcome_bucket_counts?: Record<string, number>;
  tracked_outcome_bucket_rates?: Record<string, number>;
  opponent_outcome_bucket_counts?: Record<string, number>;
  opponent_outcome_bucket_rates?: Record<string, number>;
  phase_2_9_eval_kpis?: Dict;
  phase_2_9_eval_kpis_by_side?: Record<string, Dict>;
  eval_decision_summary?: {
    by_action_kind_and_side?: Record<string, Dict>;
    decision_ownership_by_side?: Record<string, Dict>;
    decision_ownership_source?: Record<string, number>;
  };
  eval_decisions_top?: Dict[];
  eval_decision_steps_top?: Dict[];
  seed_games?: Dict[];
  profile_wall_s?: number;
  episode_wall_s_mean?: number;
  episodes_per_second?: number;
}

export interface EvalRow extends Dict {
  eval_id?: string;
  created_at_utc?: string;
  scenario_id?: string;
  scenario_ids?: string[];
  train_run_id?: string;
  engine?: string;
  model_id?: string;
  source_path?: string;
  gate_status?: string;
  gate_score?: number;
  head_diagnostics_eval?: Record<string, Dict>;
  phase_2_9_train_eval?: Dict;
  phase_2_9_promotion_gate?: Dict;
  diagnostics_summary_eval?: Dict;
  benchmark_timing?: Dict;
  results?: EvalResultRow[];
}

export interface ModelPayload extends Dict {
  schema_version?: string;
  engine?: string;
  model_id?: string;
  algorithm?: string;
  config_fingerprint?: string;
  latest_train_run_id?: string;
  latest_eval_created_at_utc?: string;
  train_history?: TrainRow[];
  eval_history?: EvalRow[];
  train_history_total_count?: number;
  eval_history_total_count?: number;
  scenarios_seen?: string[];
  scenario_train_counts?: Record<string, number>;
  scenario_eval_counts?: Record<string, number>;
}

export interface ReplayMetaEpisode extends Dict {
  episode_id?: string;
  episode_index?: number;
  episode_path?: string;
  rows?: number;
  steps_count?: number;
}

export interface ReplayMetaPayload extends Dict {
  episodes_meta?: ReplayMetaEpisode[];
  eval_id?: string;
  run_id?: string;
  bench_id?: string;
}

export interface ReplayUnitSnapshot extends Dict {
  unit_id?: string;
  unit_label?: string;
  unit_key?: string;
  side?: string;
  q?: number;
  r?: number;
  hp?: number;
  alive?: boolean;
  suppressed?: boolean;
  is_suppressed?: boolean;
}

export interface ReplayStepRow extends Dict {
  step_index?: number;
  to_play?: string;
  action_id?: string;
  unit_id?: string;
  target_q?: number;
  target_r?: number;
  target_vp?: string;
  target_vp_why?: string;
  reward?: number;
  damage_dealt?: number;
  kills_dealt?: number;
  mcts_total_visits?: number;
  mcts_root_actions_count?: number;
  mcts_active_actions?: number;
  mcts_q_clipped_count?: number;
  telemetry_coverage_status?: string;
  telemetry_coverage_reason?: string;
  units?: ReplayUnitSnapshot[];
  unit_suppressed_map?: Record<string, boolean | number | string>;
  legal_actions?: unknown[];
  mcts_action_candidates?: Dict[];
  controller_by_side?: Record<string, string>;
  side_controller_map?: Record<string, string>;
  policy_top_action?: string;
  policy_overridden_by_mcts?: boolean | number;
  why_action_vs_vp_text?: string;
}

export interface ScenarioObjectiveRow {
  captured?: { min?: number; max?: number };
  result?: string;
  outcome_class?: string;
  canonical_class?: string;
  canonical_score?: number;
  dual_class?: string;
  dual_score?: number;
  next_scenario?: string | null;
  next_page?: number | null;
  outcome_score?: number;
  note?: string;
}

export interface ScenarioDetailPayload {
  ok: boolean;
  scenario_id?: string;
  filename?: string;
  max_turns?: number;
  shape?: [number, number];
  sides?: string[];
  tracked_side?: string;
  opponent_side?: string;
  initial_objectives_by_side?: Record<string, number>;
  vp?: {
    value_per_hex?: number;
    hexes?: Array<{ q: number; r: number; initial_owner?: string; value?: number }>;
    total_objectives?: number;
  };
  victory_outcomes?: {
    tracked_side?: string;
    metric?: string;
    timing?: string;
    table?: ScenarioObjectiveRow[];
  };
  error?: string;
}

