import { Dict, TrainRow } from "./types";
import { calculateDurationSeconds } from "./dateUtils";

export interface CurriculumStepMetric {
  runId: string;
  phaseName: string;
  stepIndex: number;
  cycleInPhase: number;
  totalCyclesInPhase: number;
  phaseGroupIndex: number;
  isPhaseSelected: boolean;
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
  trainDurationSeconds?: number | null;
  benchDurationSeconds?: number | null;
  selfplayDurationSeconds?: number | null;
  optDurationSeconds?: number | null;
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
    // In mirror selfplay between the same model, the nominal symmetric score is 0.50 (1400 anchor).
    // Clamp within [0.15, 0.85] to prevent one-sided mirror draw/side artifacts from collapsing ELO.
    const s = Math.max(0.15, Math.min(0.85, scoreVsSelfplay));
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
  let scA: number | null = null;
  let scB: number | null = null;
  let scSelf: number | null = null;

  for (const [k, v] of Object.entries(prof)) {
    if (typeof v !== "number" || isNaN(v)) continue;
    const lk = k.toLowerCase();
    if (lk.includes("side_a") && scA === null) {
      scA = v;
    } else if (lk.includes("side_b") && scB === null) {
      scB = v;
    } else if ((lk.includes("selfplay") || lk.includes("self_play")) && scSelf === null) {
      scSelf = v;
    }
  }

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

  // Prefer resolved_non_timeout_win_rate if positive; fall back to aggregate phase score if resolved is 0 but score > 0
  const winRate =
    typeof gm.resolved_non_timeout_win_rate === "number" && gm.resolved_non_timeout_win_rate > 0
      ? gm.resolved_non_timeout_win_rate
      : typeof gm.score === "number"
      ? gm.score
      : typeof gm.resolved_non_timeout_win_rate === "number"
      ? gm.resolved_non_timeout_win_rate
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
 * Computes step-by-step curriculum progression metrics with delta tracking
 * and marks the chosen (best/promoted) cycle within each contiguous curriculum phase.
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

    const trainDur = typeof trace?.train_duration_seconds === "number" ? trace.train_duration_seconds : null;
    const benchDur = typeof trace?.bench_duration_seconds === "number" ? trace.bench_duration_seconds : null;
    const selfplayDur = typeof trace?.selfplay_duration_seconds === "number" ? trace.selfplay_duration_seconds : null;
    const optDur = typeof trace?.opt_duration_seconds === "number" ? trace.opt_duration_seconds : null;

    steps.push({
      runId: tid,
      phaseName: String(trace?.phase_name || t.curriculum_phase || `Fase ${index + 1}`),
      stepIndex: index + 1,
      cycleInPhase: 1,
      totalCyclesInPhase: 1,
      phaseGroupIndex: 0,
      isPhaseSelected: false,
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
      trainDurationSeconds: trainDur,
      benchDurationSeconds: benchDur,
      selfplayDurationSeconds: selfplayDur,
      optDurationSeconds: optDur,
      createdAt: String(t.created_at_utc || ""),
      checkpoint: String(t.latest_checkpoint || "-"),
    });
  });

  // 2. Group contiguous steps with the same phaseName and select the winning cycle per phase
  const groups: CurriculumStepMetric[][] = [];
  for (const step of steps) {
    const lastGroup = groups[groups.length - 1];
    if (!lastGroup || lastGroup[0].phaseName !== step.phaseName) {
      groups.push([step]);
    } else {
      lastGroup.push(step);
    }
  }

  groups.forEach((group, gIdx) => {
    const total = group.length;
    group.forEach((s, idx) => {
      s.cycleInPhase = idx + 1;
      s.totalCyclesInPhase = total;
      s.phaseGroupIndex = gIdx;
    });

    // Pick the best cycle in this phase group:
    // Priority 1: Explicit Gate PASS or promotionDecision === "promote" / "promoted"
    // Priority 2: Highest ELO (with winRate & score as tie-breakers)
    const evaluated = group.filter((s) => s.elo !== null || s.winRate !== null || s.gateStatus !== null);
    const pool = evaluated.length > 0 ? evaluated : group;

    let best = pool[0];
    for (const cand of pool.slice(1)) {
      const bestPassed =
        best.gateStatus === "PASS" ||
        best.gateStatus === "PASSED" ||
        best.promotionDecision === "promote" ||
        best.promotionDecision === "promoted";
      const candPassed =
        cand.gateStatus === "PASS" ||
        cand.gateStatus === "PASSED" ||
        cand.promotionDecision === "promote" ||
        cand.promotionDecision === "promoted";

      if (candPassed && !bestPassed) {
        best = cand;
        continue;
      }
      if (bestPassed && !candPassed) {
        continue;
      }

      const bestElo = best.elo ?? -Infinity;
      const candElo = cand.elo ?? -Infinity;
      if (candElo > bestElo) {
        best = cand;
      } else if (candElo === bestElo) {
        const bestWr = best.winRate ?? -Infinity;
        const candWr = cand.winRate ?? -Infinity;
        if (candWr > bestWr) {
          best = cand;
        }
      }
    }

    if (best) {
      best.isPhaseSelected = true;
    }
  });

  return steps;
}
