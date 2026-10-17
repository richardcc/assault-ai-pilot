import { Dict, TrainRow } from "./types";
import { calculateDurationSeconds } from "./dateUtils";

export interface CurriculumStepMetric {
  runId: string;
  phaseName: string;
  stepIndex: number;
  elo: number | null;
  deltaElo: number | null; // vs previous chronological step
  winRate: number | null;
  score: number | null;
  gateStatus: string | null;
  promotionDecision: string | null;
  gateFailReasons: string[];
  vpNet: number | null;
  capturedAvg: number | null;
  durationSeconds: number | null;
  createdAt: string;
  checkpoint: string;
}

/**
 * Bradley-Terry Anchor ELO calibrated against reference baselines.
 * Uses Random (800) and Selfplay/MCTS (1400) anchors.
 */
export function computeStepAnchorElo(
  mirrorScoreVsRandom: number | null,
  scoreVsSelfplay: number | null
): number | null {
  if (mirrorScoreVsRandom === null && scoreVsSelfplay === null) return null;

  const estimates: [number, number][] = [];

  if (mirrorScoreVsRandom !== null && !isNaN(mirrorScoreVsRandom)) {
    const s = Math.max(0.02, Math.min(0.98, mirrorScoreVsRandom));
    const implied = 800.0 + 400.0 * Math.log10(s / (1.0 - s));
    estimates.push([implied, 1.0]);
  }

  if (scoreVsSelfplay !== null && !isNaN(scoreVsSelfplay)) {
    const s = Math.max(0.02, Math.min(0.98, scoreVsSelfplay));
    const implied = 1400.0 + 400.0 * Math.log10(s / (1.0 - s));
    estimates.push([implied, 1.5]);
  }

  if (!estimates.length) return 1200;

  const totalW = estimates.reduce((acc, [, w]) => acc + w, 0);
  const weighted = estimates.reduce((acc, [r, w]) => acc + r * w, 0) / totalW;
  return Math.round(weighted);
}

/**
 * Extracts tactical metrics and calibrated ELO from a curriculum traceability record.
 */
export function extractStepTraceMetrics(trace?: Dict | null): {
  elo: number | null;
  winRate: number | null;
  score: number | null;
  gateStatus: string | null;
  promotionDecision: string | null;
  gateFailReasons: string[];
  vpNet: number | null;
  capturedAvg: number | null;
} {
  if (!trace) {
    return {
      elo: null,
      winRate: null,
      score: null,
      gateStatus: null,
      promotionDecision: null,
      gateFailReasons: [],
      vpNet: null,
      capturedAvg: null,
    };
  }

  const gm = (trace.gate_metrics || {}) as Dict;
  const prof = (gm.profile_scores || {}) as Record<string, number>;
  const scA = typeof prof.muzero_vs_random_side_a === "number" ? prof.muzero_vs_random_side_a : null;
  const scB = typeof prof.muzero_vs_random_side_b === "number" ? prof.muzero_vs_random_side_b : null;
  const scSelf = typeof prof.muzero_selfplay === "number" ? prof.muzero_selfplay : null;

  let mirrorRand: number | null = null;
  if (scA !== null && scB !== null) {
    mirrorRand = (scA + scB) / 2;
  } else if (scA !== null) {
    mirrorRand = scA;
  } else if (scB !== null) {
    mirrorRand = scB;
  } else if (typeof gm.score === "number") {
    mirrorRand = gm.score;
  }

  const elo = computeStepAnchorElo(mirrorRand, scSelf);

  const winRate =
    typeof gm.resolved_non_timeout_win_rate === "number"
      ? gm.resolved_non_timeout_win_rate
      : typeof gm.score === "number"
      ? gm.score
      : null;

  const score = typeof gm.score === "number" ? gm.score : null;
  const gateStatus = trace.gate_result_status ? String(trace.gate_result_status).toUpperCase() : null;
  const promotionDecision = trace.promotion_decision ? String(trace.promotion_decision).toLowerCase() : null;
  const gateFailReasons = Array.isArray(trace.gate_fail_reasons) ? (trace.gate_fail_reasons as string[]) : [];
  const vpNet = typeof gm.vp_net_avg_tracked_side === "number" ? gm.vp_net_avg_tracked_side : null;
  const capturedAvg = typeof gm.tracked_captured_avg === "number" ? gm.tracked_captured_avg : null;

  return {
    elo,
    winRate,
    score,
    gateStatus,
    promotionDecision,
    gateFailReasons,
    vpNet,
    capturedAvg,
  };
}

/**
 * Computes step-by-step curriculum progression metrics with delta tracking.
 * Returns steps sorted chronologically (oldest to newest) or formatted for display.
 */
export function buildCurriculumProgression(
  trains: TrainRow[],
  traceByTrainRun: Map<string, Dict>
): CurriculumStepMetric[] {
  // 1. Sort trains chronologically (oldest first)
  const sorted = [...trains].sort((a, b) => {
    const da = a.created_at_utc ? new Date(a.created_at_utc).getTime() : 0;
    const db = b.created_at_utc ? new Date(b.created_at_utc).getTime() : 0;
    return da - db;
  });

  const steps: CurriculumStepMetric[] = [];
  let prevElo: number | null = null;

  sorted.forEach((t, index) => {
    const tid = String(t.run_id || "").trim();
    const trace = traceByTrainRun.get(tid);
    const m = extractStepTraceMetrics(trace);

    let dur = typeof t.duration_seconds === "number" ? t.duration_seconds : null;
    if (dur === null || dur === undefined) {
      dur = calculateDurationSeconds(
        (trace?.phase_started_at || t.phase_started_at) as string | undefined,
        (trace?.phase_finished_at || t.phase_finished_at) as string | undefined
      );
    }

    const deltaElo = (m.elo !== null && prevElo !== null) ? m.elo - prevElo : null;
    if (m.elo !== null) {
      prevElo = m.elo;
    }

    steps.push({
      runId: tid,
      phaseName: String(trace?.phase_name || t.curriculum_phase || `Fase ${index + 1}`),
      stepIndex: index + 1,
      elo: m.elo,
      deltaElo,
      winRate: m.winRate,
      score: m.score,
      gateStatus: m.gateStatus,
      promotionDecision: m.promotionDecision,
      gateFailReasons: m.gateFailReasons,
      vpNet: m.vpNet,
      capturedAvg: m.capturedAvg,
      durationSeconds: dur,
      createdAt: String(t.created_at_utc || ""),
      checkpoint: String(t.latest_checkpoint || "-"),
    });
  });

  return steps;
}
