import { useEffect, useMemo, useState } from "react";
import type { Dict, EvalResultRow, EvalRow, ScenarioDetailPayload, ScenarioObjectiveRow } from "../../types";
import { fetchScenario } from "../../api";
import { formatLocalDate } from "../../dateUtils";
import { FunnelChart } from "../../components/FunnelChart";
import { SideCombatTable } from "../../components/SideCombatTable";

const OUTCOME_STYLES: Record<string, { label: string; bg: string; border: string; color: string }> = {
  total_victory: { label: "Vittoria Totale (+1)", bg: "#064e3b", border: "#059669", color: "#34d399" },
  victory: { label: "Vittoria (+1)", bg: "#14532d", border: "#16a34a", color: "#86efac" },
  draw: { label: "Pareggio (0)", bg: "#78350f", border: "#d97706", color: "#fde047" },
  defeat: { label: "Sconfitta (-1)", bg: "#7c2d12", border: "#ea580c", color: "#fdba74" },
  total_defeat: { label: "Sconfitta Totale (-1)", bg: "#7f1d1d", border: "#dc2626", color: "#fca5a5" },
  unknown: { label: "Desconocido", bg: "#1e293b", border: "#475569", color: "#94a3b8" },
};

function OutcomeBadge({ outcomeClass, customLabel }: { outcomeClass?: string; customLabel?: string }) {
  const norm = String(outcomeClass || "").toLowerCase();
  const style = OUTCOME_STYLES[norm] || OUTCOME_STYLES.unknown;
  return (
    <span
      style={{
        display: "inline-block",
        padding: "2px 8px",
        borderRadius: 4,
        fontSize: 11,
        fontWeight: 700,
        backgroundColor: style.bg,
        border: `1px solid ${style.border}`,
        color: style.color,
        letterSpacing: "0.02em",
      }}
    >
      {customLabel || style.label}
    </span>
  );
}

function sanitizeController(val: string): string {
  if (!val) return "-";
  let s = String(val).trim();
  const lower = s.toLowerCase();
  if (lower === "muzero" || lower === "efficientzero_v2" || lower === "efficientzero" || lower === "ezv2") {
    return "EfficientZeroV2";
  }
  if (lower === "mcts") return "MCTS";
  if (lower === "random") return "Random";
  return s.replace(/muzero/gi, "EfficientZeroV2");
}

function matchesEngine(controllerStr: string, filterStr: string): boolean {
  if (!filterStr || filterStr === "all") return true;
  const c = String(controllerStr || "").toLowerCase().replace(/[^a-z0-9]/g, "");
  const f = String(filterStr || "").toLowerCase().replace(/[^a-z0-9]/g, "");
  if (!c || !f) return false;

  const isEZFilter = f.includes("efficient") || f.includes("ezv2") || f.includes("zero") || f.includes("muzero");
  const isEZCtrl = c.includes("efficient") || c.includes("ezv2") || c.includes("zero") || c.includes("mcts");
  if (isEZFilter && isEZCtrl) return true;

  return c.includes(f) || f.includes(c);
}

function resolveController(
  side: string,
  ctrlsMap: Record<string, string>,
  policiesMap?: Record<string, string>,
  defaultFallback: string = "",
  matchupProfile: string = ""
): string {
  const norm = String(side || "").toUpperCase();
  const formatPolicy = (p: string) => {
    const pl = String(p || "").trim().toLowerCase();
    if (pl === "mcts") return "MCTS";
    if (pl === "random") return "Random";
    if (pl === "muzero") return "EfficientZeroV2";
    return sanitizeController(p);
  };

  const isUnknown = (val?: string) => !val || String(val).trim().toLowerCase() === "unknown";

  // 1. Direct match if known
  const direct = ctrlsMap[norm] || ctrlsMap[side];
  if (!isUnknown(direct)) return sanitizeController(direct);
  for (const [k, v] of Object.entries(ctrlsMap || {})) {
    if (k.toUpperCase() === norm && !isUnknown(v)) return sanitizeController(v);
  }

  // 2. Direct policy match if present
  if (policiesMap) {
    const pDirect = policiesMap[norm] || policiesMap[side];
    if (!isUnknown(pDirect)) return formatPolicy(pDirect);
    for (const [k, v] of Object.entries(policiesMap || {})) {
      if (k.toUpperCase() === norm && !isUnknown(v)) return formatPolicy(v);
    }
  }

  if (defaultFallback && !isUnknown(defaultFallback)) {
    return sanitizeController(defaultFallback);
  }

  return sanitizeController(direct) || sanitizeController(defaultFallback) || "-";
}

function getOpponentInfo(side: string, allSides: string[], main: EvalResultRow | null) {
  const normSide = String(side || "").toUpperCase();
  // Discover true participating sides in this specific row
  const rowSides = Array.from(
    new Set([
      ...Object.keys(main?.controller_by_side || {}),
      ...Object.keys(main?.policy_by_side || {}),
      ...Object.keys(main?.winner_side_rates || {}),
      ...Object.keys(main?.vp_net_avg_by_side || {}),
    ])
  ).map((s) => s.toUpperCase());

  const searchPool = rowSides.length > 1 ? rowSides : allSides;
  const candidates = searchPool.filter((x) => String(x || "").toUpperCase() !== normSide);
  const opp = candidates[0] || (normSide === "IT" ? "US" : normSide === "US" ? "IT" : normSide === "GE" ? "US" : "-");
  const oppNorm = opp.toUpperCase();
  const label = oppNorm === "US" ? "🇺🇸 US" : oppNorm === "IT" ? "🇮🇹 IT" : oppNorm === "GE" ? "🇩🇪 GE" : oppNorm;
  const color = oppNorm === "US" ? "#60a5fa" : oppNorm === "IT" ? "#34d399" : oppNorm === "GE" ? "#f87171" : "#e2e8f0";

  const ctrlMap = (main?.controller_by_side || {}) as Record<string, string>;
  const policyMap = (main?.policy_by_side || {}) as Record<string, string>;
  const ctrl = resolveController(oppNorm, ctrlMap, policyMap, "", main?.matchup_profile || "");
  return { side: oppNorm, label, color, controller: ctrl };
}

interface BilateralMatchupRow {
  key: string;
  scenarioId: string;
  matchupProfile: string;
  side: string;
  sideColor: string;
  ownController: string;
  oppSide: string;
  oppColor: string;
  oppController: string;
  episodes: number;
  total_victory: number;
  victory: number;
  draw: number;
  defeat: number;
  total_defeat: number;
  win_rate: number;
  loss_rate: number;
  outcome_score: number;
  vpInitial: string | number;
  vpFinal: string | number;
  vpNet: string | number;
  vpGained: string | number;
  vpGainedTotal: string | number;
  vpLost: string | number;
  vpLostTotal: string | number;
  avgLost: string;
  avgKills: string;
  avgDmg: string;
  isFirstInGroup?: boolean;
  groupSize?: number;
  isLastInGroup?: boolean;
  isFirstInSideGroup?: boolean;
  sideGroupSize?: number;
  isLastInSideGroup?: boolean;
}

export function VpSummaryTab({
  evalRows,
  selectedEval,
}: {
  evalRows: EvalRow[];
  selectedEval: EvalRow | null;
}) {
  const [selectedScenario, setSelectedScenario] = useState<string>("all");
  const [selectedEngine, setSelectedEngine] = useState<string>("all");
  const [selectedProfile, setSelectedProfile] = useState<string>("all");
  const [selectedSide, setSelectedSide] = useState<string>("all");
  const [selectedOpponent, setSelectedOpponent] = useState<string>("all");
  const [showScenarioRules, setShowScenarioRules] = useState<boolean>(true);

  const currentEval = selectedEval || evalRows[0] || null;
  const rawResults = useMemo(
    () => (Array.isArray(currentEval?.results) ? (currentEval!.results as EvalResultRow[]) : []),
    [currentEval]
  );

  // Dynamic scenario data fetching
  const scenarioId = currentEval?.scenario_id || "";
  const [scenarioData, setScenarioData] = useState<ScenarioDetailPayload | null>(null);
  const [scenarioLoading, setScenarioLoading] = useState<boolean>(false);

  useEffect(() => {
    if (!scenarioId) {
      setScenarioData(null);
      return;
    }
    let active = true;
    setScenarioLoading(true);
    fetchScenario(scenarioId)
      .then((data) => {
        if (active) {
          setScenarioData(data);
          setScenarioLoading(false);
        }
      })
      .catch((err) => {
        if (active) {
          console.warn("Could not fetch scenario details:", err);
          setScenarioData(null);
          setScenarioLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [scenarioId]);

  // Discover available filter options from current evaluation results
  const { availableEngines, availableProfiles, availableSides, availableOpponents, availableScenarios } = useMemo(() => {
    const engines = new Set<string>();
    const profiles = new Set<string>();
    const sides = new Set<string>();
    const opponents = new Set<string>();
    const scenarios = new Set<string>();

    if (currentEval?.engine) engines.add(sanitizeController(currentEval.engine));
    if (currentEval?.scenario_id) scenarios.add(currentEval.scenario_id);
    if (Array.isArray(currentEval?.scenario_ids)) {
      currentEval!.scenario_ids.forEach((s) => s && scenarios.add(s));
    }

    for (const r of rawResults) {
      if (r.scenario_id) scenarios.add(String(r.scenario_id));
      if (r.scenario) scenarios.add(String(r.scenario));
      if (Array.isArray(r.seed_games)) {
        for (const sg of r.seed_games) {
          if (sg?.scenario_id) scenarios.add(String(sg.scenario_id));
        }
      }
      if (r.matchup_profile) profiles.add(r.matchup_profile);
      if (r.matchup_group) profiles.add(r.matchup_group);
      if (r.tracked_side) sides.add(r.tracked_side);
      if (r.vp_net_avg_by_side) {
        for (const s of Object.keys(r.vp_net_avg_by_side)) sides.add(s);
      }
      if (r.winner_side_rates) {
        for (const s of Object.keys(r.winner_side_rates)) sides.add(s);
      }
      if (r.phase_2_9_eval_kpis_by_side) {
        for (const s of Object.keys(r.phase_2_9_eval_kpis_by_side)) sides.add(s);
      }
      if (r.policy_by_side) {
        for (const [s, p] of Object.entries(r.policy_by_side)) {
          sides.add(s);
          if (p) {
            const sc = sanitizeController(p);
            engines.add(sc);
            opponents.add(sc);
          }
        }
      }
      if (r.controller_by_side) {
        for (const [s, c] of Object.entries(r.controller_by_side)) {
          sides.add(s);
          if (c) {
            const sc = sanitizeController(c);
            engines.add(sc);
            opponents.add(sc);
          }
        }
      }
      if (r.opponent_side) {
        opponents.add(r.opponent_side);
      }
    }
    return {
      availableEngines: Array.from(engines).sort(),
      availableProfiles: Array.from(profiles).sort(),
      availableSides: Array.from(sides).sort(),
      availableOpponents: Array.from(opponents).sort(),
      availableScenarios: Array.from(scenarios).sort(),
    };
  }, [currentEval, rawResults]);

  // Filter matchup results
  const filteredResults = useMemo(() => {
    const rowEngine = String(currentEval?.engine || "").toLowerCase();
    return rawResults.filter((r) => {
      // 0. Scenario Filter
      if (selectedScenario !== "all") {
        const selScen = selectedScenario.toLowerCase();
        const rScen = String(
          r.scenario_id ||
          r.scenario ||
          (Array.isArray(r.seed_games) && r.seed_games[0]?.scenario_id) ||
          currentEval?.scenario_id ||
          ""
        ).toLowerCase();
        if (!rScen.includes(selScen)) {
          return false;
        }
      }

      // 1. Engine
      if (selectedEngine !== "all") {
        const matchesRow = matchesEngine(rowEngine, selectedEngine);
        const matchesPolicy = Object.values(r.policy_by_side || {}).some((p) =>
          matchesEngine(String(p || ""), selectedEngine)
        );
        const matchesController = Object.values(r.controller_by_side || {}).some((c) =>
          matchesEngine(String(c || ""), selectedEngine)
        );
        const matchesAgent = matchesEngine(String(r.agent_name || ""), selectedEngine);
        if (!matchesRow && !matchesPolicy && !matchesController && !matchesAgent) {
          return false;
        }
      }

      // 2. Profile / Simulation Type
      if (selectedProfile !== "all") {
        const prof = String(r.matchup_profile || "");
        const grp = String(r.matchup_group || "");
        if (prof !== selectedProfile && grp !== selectedProfile) {
          return false;
        }
      }

      // 3. Side / Bando
      if (selectedSide !== "all") {
        const side = selectedSide.toUpperCase();
        const matchesTracked = String(r.tracked_side || "").toUpperCase() === side;
        const inVp = Boolean(r.vp_net_avg_by_side && side in r.vp_net_avg_by_side);
        const inRates = Boolean(r.winner_side_rates && side in r.winner_side_rates);
        const inKpi = Boolean(r.phase_2_9_eval_kpis_by_side && side in r.phase_2_9_eval_kpis_by_side);
        const inPolicy = Boolean(r.policy_by_side && side in r.policy_by_side);
        if (!matchesTracked && !inVp && !inRates && !inKpi && !inPolicy) {
          return false;
        }
      }

      // 4. Opponent
      if (selectedOpponent !== "all") {
        const selOpp = selectedOpponent.toLowerCase();
        const ctrls = (r.controller_by_side || r.policy_by_side || {}) as Record<string, string>;
        const rSides = Array.from(
          new Set([...Object.keys(r.winner_side_rates || {}), ...Object.keys(r.vp_net_avg_by_side || {}), ...Object.keys(ctrls)])
        );
        if (selectedSide !== "all") {
          const s = selectedSide.toUpperCase();
          const oppSide = rSides.find((x) => x.toUpperCase() !== s) || "";
          const oppCtrl = String(ctrls[oppSide] || oppSide || "").toLowerCase();
          if (!oppCtrl.includes(selOpp)) {
            return false;
          }
        } else {
          const matchesAnyOpp =
            Object.values(ctrls).some((c) => String(c || "").toLowerCase().includes(selOpp)) ||
            (r.opponent_side && String(r.opponent_side).toLowerCase().includes(selOpp));
          if (!matchesAnyOpp) {
            return false;
          }
        }
      }

      return true;
    });
  }, [rawResults, currentEval, selectedEngine, selectedProfile, selectedSide, selectedOpponent]);

  if (!currentEval || !rawResults.length) {
    return <div className="muted">No evaluation results available for this train run.</div>;
  }

  // Pick main result for global KPI cards (from filtered if available, else first raw)
  const main = filteredResults[0] || rawResults[0];
  const kpis = (main.phase_2_9_eval_kpis || {}) as Dict;

  const topCards: Array<{ k: string; v: string; highlight?: boolean; color?: string }> = [
    {
      k: selectedSide !== "all" ? `Win Rate (${selectedSide})` : "Win Rate",
      v:
        selectedSide !== "all" && main.winner_side_rates?.[selectedSide] !== undefined
          ? `${(Number(main.winner_side_rates[selectedSide]) * 100).toFixed(1)}%`
          : main.win_rate !== undefined
          ? `${(Number(main.win_rate) * 100).toFixed(1)}%`
          : "-",
      highlight: true,
      color: "#22c55e",
    },
    {
      k: "Resolved Win Rate (No Timeout)",
      v: main.resolved_non_timeout_win_rate !== undefined ? `${(Number(main.resolved_non_timeout_win_rate) * 100).toFixed(1)}%` : "-",
    },
    {
      k: "Timeout Rate",
      v: main.timeout_rate !== undefined ? `${(Number(main.timeout_rate) * 100).toFixed(1)}%` : "-",
      color: Number(main.timeout_rate || 0) > 0.3 ? "#ef4444" : "#e2e8f0",
    },
    {
      k: "Gate Status",
      v: main.gate_ok ? "PASS" : "FAIL",
      highlight: true,
      color: main.gate_ok ? "#22c55e" : "#ef4444",
    },
    {
      k: "Gate Score",
      v: main.score !== undefined ? Number(main.score).toFixed(3) : "-",
    },
    {
      k: "Tracked Captured Avg",
      v: main.tracked_captured_avg !== undefined ? Number(main.tracked_captured_avg).toFixed(2) : "-",
    },
    {
      k: "VP Capture Take Rate",
      v: kpis.xai_vp_capture_take_rate !== undefined ? `${(Number(kpis.xai_vp_capture_take_rate) * 100).toFixed(1)}%` : "-",
    },
    {
      k: "Avg Steps / Return",
      v: `${Number(main.avg_steps || 0).toFixed(0)} / ${Number(main.avg_return || 0).toFixed(2)}`,
    },
  ];

  // Sides present in VP
  const vpNet = (main.vp_net_avg_by_side || {}) as Record<string, number>;
  const vpInitial = (main.vp_initial_avg_by_side || {}) as Record<string, number>;
  const vpFinal = (main.vp_final_avg_by_side || {}) as Record<string, number>;
  const vpGained = (main.vp_gained_avg_by_side || {}) as Record<string, number>;
  const vpLost = (main.vp_lost_avg_by_side || {}) as Record<string, number>;
  const winnerRates = (main.winner_side_rates || {}) as Record<string, number>;

  let allSides = Array.from(new Set([...Object.keys(vpNet), ...Object.keys(winnerRates), ...(scenarioData?.sides || [])])).sort();
  if (allSides.length === 0) {
    allSides = ["US", "IT"];
  }
  const displaySides = selectedSide !== "all" ? allSides.filter((s) => s.toUpperCase() === selectedSide.toUpperCase()) : allSides;

  // Aggregate tactical casualties across seed games
  const tacticalCasualtiesBySide: Record<string, { lost: number; kills: number; damage: number; games: number }> = {};
  for (const r of filteredResults) {
    const seedGames = (r.seed_games || []) as Dict[];
    for (const sg of seedGames) {
      const sm = (sg.side_metrics || {}) as Record<string, Dict>;
      for (const [sideKey, metrics] of Object.entries(sm)) {
        const s = sideKey.toUpperCase();
        if (!tacticalCasualtiesBySide[s]) {
          tacticalCasualtiesBySide[s] = { lost: 0, kills: 0, damage: 0, games: 0 };
        }
        tacticalCasualtiesBySide[s].lost += Number(metrics.units_lost || 0);
        tacticalCasualtiesBySide[s].kills += Number(metrics.enemy_units_eliminated || 0);
        tacticalCasualtiesBySide[s].damage += Number(metrics.damage_dealt || 0);
        tacticalCasualtiesBySide[s].games += 1;
      }
    }
  }

  // Disaggregated Matchup Rows (Outcome distributions & VP Gains/Losses per Matchup)
  const matchupRows: BilateralMatchupRow[] = useMemo(() => {
    const list: BilateralMatchupRow[] = [];

    filteredResults.forEach((r, rIdx) => {
      const prof = String(r.matchup_profile || `Profile ${rIdx}`);
      const eps = Number(r.episodes || 0);
      const ctrls = (r.controller_by_side || r.policy_by_side || {}) as Record<string, string>;
      const bySide = (r.scenario_outcome_class_rates_by_side || {}) as Record<string, Record<string, number>>;
      const rates = (r.winner_side_rates || {}) as Record<string, number>;
      const vpNetMap = (r.vp_net_avg_by_side || {}) as Record<string, number>;
      const vpInitMap = (r.vp_initial_avg_by_side || {}) as Record<string, number>;
      const vpFinMap = (r.vp_final_avg_by_side || {}) as Record<string, number>;
      const vpGainMap = (r.vp_gained_avg_by_side || {}) as Record<string, number>;
      const vpLostMap = (r.vp_lost_avg_by_side || {}) as Record<string, number>;

      // Determine the real 2 participating sides in this specific match result
      let matchSides = Array.from(
        new Set([
          ...Object.keys(rates),
          ...Object.keys(vpNetMap),
          ...Object.keys(bySide),
        ])
      )
        .map((s) => s.toUpperCase())
        .filter(Boolean);

      // If missing from rates/vp, check seed_games side_metrics
      if (!matchSides.length && r.seed_games && Array.isArray(r.seed_games)) {
        const sgSides = new Set<string>();
        for (const sg of r.seed_games as Dict[]) {
          if (sg.side_metrics) {
            for (const s of Object.keys(sg.side_metrics)) sgSides.add(s.toUpperCase());
          }
        }
        matchSides = Array.from(sgSides);
      }

      // If still missing, check tracked_side and opponent_side
      if (!matchSides.length) {
        if (r.tracked_side) matchSides.push(String(r.tracked_side).toUpperCase());
        if (r.opponent_side) matchSides.push(String(r.opponent_side).toUpperCase());
      }

      // Fallback only if completely empty
      if (!matchSides.length) {
        matchSides = ["IT", "US"];
      } else if (matchSides.length === 1) {
        const s0 = matchSides[0];
        matchSides.push(s0 === "IT" ? "US" : s0 === "US" ? "IT" : s0 === "GE" ? "US" : "US");
      }

      // Ensure we only have the distinct participating sides
      const resultSides = Array.from(new Set(matchSides)).sort();

      // Determine scenario for this result row:
      let rowScenario = String(
        r.scenario_id ||
        r.scenario ||
        (Array.isArray(r.seed_games) && r.seed_games[0]?.scenario_id) ||
        ""
      );
      if (!rowScenario) {
        if (resultSides.includes("IT")) {
          rowScenario = currentEval?.scenario_ids?.[0] || currentEval?.scenario_id || "battaglia_cittadina_2_1";
        } else if (resultSides.includes("GE")) {
          rowScenario = currentEval?.scenario_ids?.[1] || "colline_d_acciaio_2_2";
        } else {
          rowScenario = currentEval?.scenario_id || "-";
        }
      }

      // Casualties in this specific result
      const seedGames = (r.seed_games || []) as Dict[];
      const rTactical: Record<string, { lost: number; kills: number; damage: number; games: number }> = {};
      for (const sg of seedGames) {
        const sm = (sg.side_metrics || {}) as Record<string, Dict>;
        for (const [sideKey, metrics] of Object.entries(sm)) {
          const s = sideKey.toUpperCase();
          if (!rTactical[s]) rTactical[s] = { lost: 0, kills: 0, damage: 0, games: 0 };
          rTactical[s].lost += Number(metrics.units_lost || 0);
          rTactical[s].kills += Number(metrics.enemy_units_eliminated || 0);
          rTactical[s].damage += Number(metrics.damage_dealt || 0);
          rTactical[s].games += 1;
        }
      }

      resultSides.forEach((s) => {
        const sNorm = s.toUpperCase();
        if (selectedSide !== "all" && sNorm !== selectedSide.toUpperCase()) {
          return;
        }

        const opp = resultSides.find((x) => x.toUpperCase() !== sNorm) || (sNorm === "IT" ? "US" : sNorm === "US" ? "IT" : sNorm === "GE" ? "US" : "-");
        const oppNorm = opp.toUpperCase();

        const policies = (r.policy_by_side || {}) as Record<string, string>;
        const defaultEng = String(currentEval?.engine || "");
        const ownCtrl = resolveController(sNorm, ctrls, policies, defaultEng, prof);
        const oppCtrl = resolveController(oppNorm, ctrls, policies, defaultEng, prof);

        // Filter 1: Engine filter strictly targets the first column (the side being evaluated)
        if (selectedEngine !== "all") {
          const ownMatches = matchesEngine(ownCtrl, selectedEngine);
          if (!ownMatches) {
            return;
          }
        }

        // Filter 2: Opponent filter strictly targets the second column (the opponent side)
        if (selectedOpponent !== "all") {
          const oppMatches = matchesEngine(oppCtrl, selectedOpponent) || oppNorm.toLowerCase().includes(selectedOpponent.toLowerCase());
          if (!oppMatches) {
            return;
          }
        }

        // Side colors
        const sideColor = sNorm === "US" ? "#60a5fa" : sNorm === "IT" ? "#34d399" : sNorm === "GE" ? "#f87171" : "#e2e8f0";
        const oppColor = oppNorm === "US" ? "#60a5fa" : oppNorm === "IT" ? "#34d399" : oppNorm === "GE" ? "#f87171" : "#e2e8f0";

        // Outcome rates
        let tv = 0, v = 0, d = 0, def = 0, td = 0;
        if (eps > 0) {
          if (bySide[s] && Object.keys(bySide[s]).length > 0) {
            const sr = bySide[s];
            tv = Number(sr.total_victory || 0);
            v = Number(sr.victory || 0);
            d = Number(sr.draw || 0);
            def = Number(sr.defeat || 0);
            td = Number(sr.total_defeat || 0);
          } else if (bySide[sNorm] && Object.keys(bySide[sNorm]).length > 0) {
            const sr = bySide[sNorm];
            tv = Number(sr.total_victory || 0);
            v = Number(sr.victory || 0);
            d = Number(sr.draw || 0);
            def = Number(sr.defeat || 0);
            td = Number(sr.total_defeat || 0);
          } else if (rates[s] !== undefined || rates[sNorm] !== undefined) {
            const wr = Number(rates[s] ?? rates[sNorm] ?? 0);
            v = wr;
            def = Math.max(0, 1 - wr);
          }
        }

        const winRate = eps > 0 ? (tv + v > 0 ? (tv + v) : Number(rates[s] ?? rates[sNorm] ?? 0)) : 0;
        const lossRate = eps > 0 ? (td + def > 0 ? (td + def) : Math.max(0, 1 - winRate)) : 0;
        const score = eps > 0 ? ((tv + v) * 1 + (td + def) * -1) : 0;

        // Tactical averages
        const tact = rTactical[sNorm];
        const avgLost = tact && tact.games > 0 ? (tact.lost / tact.games).toFixed(1) : "-";
        const avgKills = tact && tact.games > 0 ? (tact.kills / tact.games).toFixed(1) : "-";
        const avgDmg = tact && tact.games > 0 ? (tact.damage / tact.games).toFixed(1) : "-";

        const totalGainedNum = vpGainMap[s] !== undefined && eps > 0 ? Math.round(Number(vpGainMap[s]) * eps) : null;
        const totalLostNum = vpLostMap[s] !== undefined && eps > 0 ? Math.round(Number(vpLostMap[s]) * eps) : null;

        const vpGainedTotal = totalGainedNum !== null ? (totalGainedNum > 0 ? `+${totalGainedNum}` : "0") : "-";
        const vpLostTotal = totalLostNum !== null ? (totalLostNum > 0 ? `-${totalLostNum}` : "0") : "-";

        list.push({
          key: `${rowScenario}-${prof}-${sNorm}-${oppNorm}-${rIdx}`,
          scenarioId: rowScenario,
          matchupProfile: prof,
          side: sNorm,
          sideColor,
          ownController: ownCtrl,
          oppSide: oppNorm,
          oppColor,
          oppController: oppCtrl,
          episodes: eps,
          total_victory: tv,
          victory: v,
          draw: d,
          defeat: def,
          total_defeat: td,
          win_rate: winRate,
          loss_rate: lossRate,
          outcome_score: score,
          vpInitial: vpInitMap[s] !== undefined ? Number(vpInitMap[s]).toFixed(1) : "-",
          vpFinal: vpFinMap[s] !== undefined ? Number(vpFinMap[s]).toFixed(1) : "-",
          vpNet: vpNetMap[s] !== undefined ? Number(vpNetMap[s]) : 0,
          vpGained: vpGainMap[s] !== undefined ? Number(vpGainMap[s]).toFixed(2) : "-",
          vpGainedTotal,
          vpLost: vpLostMap[s] !== undefined ? Number(vpLostMap[s]).toFixed(2) : "-",
          vpLostTotal,
          avgLost,
          avgKills,
          avgDmg,
        });
      });
    });

    // 1. Group all rows by scenarioId so identical scenarios are strictly contiguous
    const scenarioGroups = new Map<string, BilateralMatchupRow[]>();
    for (const item of list) {
      const scenKey = item.scenarioId || "-";
      if (!scenarioGroups.has(scenKey)) {
        scenarioGroups.set(scenKey, []);
      }
      scenarioGroups.get(scenKey)!.push(item);
    }

    const groupedList: BilateralMatchupRow[] = [];
    for (const [, scenItems] of scenarioGroups) {
      // 2. Within each scenario, group by sideKey (side + ownController) so identical sides are contiguous
      const sideGroups = new Map<string, BilateralMatchupRow[]>();
      for (const item of scenItems) {
        const sideKey = `${item.side}__${item.ownController || ""}`;
        if (!sideGroups.has(sideKey)) {
          sideGroups.set(sideKey, []);
        }
        sideGroups.get(sideKey)!.push(item);
      }

      // Collect all rows for this scenario with side grouping metadata
      const orderedScenRows: BilateralMatchupRow[] = [];
      for (const [, sItems] of sideGroups) {
        sItems.forEach((item, sIdx) => {
          orderedScenRows.push({
            ...item,
            isFirstInSideGroup: sIdx === 0,
            sideGroupSize: sItems.length,
            isLastInSideGroup: sIdx === sItems.length - 1,
          });
        });
      }

      // Add scenario grouping metadata
      orderedScenRows.forEach((item, scIdx) => {
        groupedList.push({
          ...item,
          isFirstInGroup: scIdx === 0,
          groupSize: orderedScenRows.length,
          isLastInGroup: scIdx === orderedScenRows.length - 1,
        });
      });
    }

    return groupedList;
  }, [filteredResults, selectedSide, selectedEngine, selectedOpponent, selectedScenario, currentEval]);

  const hasActiveFilters =
    selectedScenario !== "all" ||
    selectedEngine !== "all" ||
    selectedProfile !== "all" ||
    selectedSide !== "all" ||
    selectedOpponent !== "all";

  const resetFilters = () => {
    setSelectedScenario("all");
    setSelectedEngine("all");
    setSelectedProfile("all");
    setSelectedSide("all");
    setSelectedOpponent("all");
  };

  const scenarioTable: ScenarioObjectiveRow[] = scenarioData?.victory_outcomes?.table || [];

  return (
    <div>
      <h3 style={{ margin: "0 0 8px 0" }}>🏆 Resumen de Enfrentamientos & Puntos de Victoria</h3>
      <div className="muted" style={{ marginBottom: 12 }}>
        Evaluation: <b>{currentEval.eval_id}</b> | Engine: <b>{currentEval.engine || "efficientzero_v2"}</b> | Scenario: <b>{currentEval.scenario_id}</b> | Created: <b>{formatLocalDate(currentEval.created_at_utc)}</b>
      </div>

      {/* Filter Bar */}
      <div
        style={{
          background: "#0f172a",
          border: "1px solid #334155",
          borderRadius: 8,
          padding: "10px 14px",
          marginBottom: 14,
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          gap: 12,
        }}
      >
        <span style={{ fontSize: 13, fontWeight: 700, color: "#38bdf8", display: "flex", alignItems: "center", gap: 5 }}>
          <span>🔍</span> Filtros:
        </span>

        {/* Scenario Filter */}
        {availableScenarios.length > 0 && (
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <label htmlFor="vp-filter-scenario" style={{ fontSize: 12, color: "#94a3b8", fontWeight: 600 }}>
              Escenario:
            </label>
            <select
              id="vp-filter-scenario"
              value={selectedScenario}
              onChange={(e) => setSelectedScenario(e.target.value)}
              style={{
                padding: "4px 8px",
                background: "#1e293b",
                color: "#e2e8f0",
                border: selectedScenario !== "all" ? "1px solid #38bdf8" : "1px solid #475569",
                borderRadius: 5,
                fontSize: 12,
              }}
            >
              <option value="all">Todos los escenarios ({availableScenarios.length})</option>
              {availableScenarios.map((scen) => (
                <option key={scen} value={scen}>
                  {scen}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Side Filter */}
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <label htmlFor="vp-filter-side" style={{ fontSize: 12, color: "#94a3b8", fontWeight: 600 }}>
            Bando:
          </label>
          <select
            id="vp-filter-side"
            value={selectedSide}
            onChange={(e) => setSelectedSide(e.target.value)}
            style={{
              padding: "4px 8px",
              background: "#1e293b",
              color: "#e2e8f0",
              border: selectedSide !== "all" ? "1px solid #38bdf8" : "1px solid #475569",
              borderRadius: 5,
              fontSize: 12,
            }}
          >
            <option value="all">Todos los bandos ({availableSides.length})</option>
            {availableSides.map((s) => (
              <option key={s} value={s}>
                {s === "US" ? "🇺🇸 US" : s === "IT" ? "🇮🇹 IT" : s === "GE" ? "🇩🇪 GE" : s}
              </option>
            ))}
          </select>
        </div>

        {/* Engine Filter */}
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <label htmlFor="vp-filter-engine" style={{ fontSize: 12, color: "#94a3b8", fontWeight: 600 }}>
            Engine:
          </label>
          <select
            id="vp-filter-engine"
            value={selectedEngine}
            onChange={(e) => setSelectedEngine(e.target.value)}
            style={{
              padding: "4px 8px",
              background: "#1e293b",
              color: "#e2e8f0",
              border: selectedEngine !== "all" ? "1px solid #38bdf8" : "1px solid #475569",
              borderRadius: 5,
              fontSize: 12,
            }}
          >
            <option value="all">Todos los engines ({availableEngines.length || 1})</option>
            {availableEngines.map((e) => (
              <option key={e} value={e}>
                {e}
              </option>
            ))}
          </select>
        </div>

        {/* Simulation Type Filter */}
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <label htmlFor="vp-filter-profile" style={{ fontSize: 12, color: "#94a3b8", fontWeight: 600 }}>
            Tipo Simulación:
          </label>
          <select
            id="vp-filter-profile"
            value={selectedProfile}
            onChange={(e) => setSelectedProfile(e.target.value)}
            style={{
              padding: "4px 8px",
              background: "#1e293b",
              color: "#e2e8f0",
              border: selectedProfile !== "all" ? "1px solid #38bdf8" : "1px solid #475569",
              borderRadius: 5,
              fontSize: 12,
            }}
          >
            <option value="all">Todos los tipos ({availableProfiles.length})</option>
            {availableProfiles.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </div>

        {/* Opponent Filter */}
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <label htmlFor="vp-filter-opponent" style={{ fontSize: 12, color: "#94a3b8", fontWeight: 600 }}>
            Oponente:
          </label>
          <select
            id="vp-filter-opponent"
            value={selectedOpponent}
            onChange={(e) => setSelectedOpponent(e.target.value)}
            style={{
              padding: "4px 8px",
              background: "#1e293b",
              color: "#e2e8f0",
              border: selectedOpponent !== "all" ? "1px solid #38bdf8" : "1px solid #475569",
              borderRadius: 5,
              fontSize: 12,
            }}
          >
            <option value="all">Todos los oponentes ({availableOpponents.length})</option>
            {availableOpponents.map((op) => (
              <option key={op} value={op}>
                {op}
              </option>
            ))}
          </select>
        </div>

        {/* Reset button */}
        {hasActiveFilters && (
          <button
            onClick={resetFilters}
            style={{
              fontSize: 11,
              padding: "4px 10px",
              background: "#334155",
              color: "#f87171",
              border: "1px solid #64748b",
              borderRadius: 5,
              cursor: "pointer",
              fontWeight: 600,
            }}
          >
            ✕ Limpiar filtros
          </button>
        )}

        <div style={{ marginLeft: "auto", fontSize: 12, color: "#94a3b8" }}>
          Mostrando <b style={{ color: "#38bdf8" }}>{filteredResults.length}</b> de {rawResults.length} perfiles
        </div>
      </div>

      {/* Global KPI Strip - Fila única compacta de alta densidad */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(8, minmax(0, 1fr))",
          gap: 6,
          marginBottom: 12,
        }}
      >
        {topCards.map(({ k, v, highlight, color }) => (
          <div
            key={k}
            style={{
              background: "#1e293b",
              border: "1px solid #334155",
              borderRadius: 6,
              padding: "4px 8px",
              minWidth: 0,
              display: "flex",
              flexDirection: "column",
              justifyContent: "center",
            }}
            title={`${k}: ${v}`}
          >
            <div
              style={{
                color: "#94a3b8",
                fontSize: 10,
                fontWeight: 600,
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
                lineHeight: 1.2,
                marginBottom: 2,
              }}
            >
              {k}
            </div>
            <div
              style={{
                color: color || (highlight ? "#22c55e" : "#f1f5f9"),
                fontSize: 12,
                fontWeight: 700,
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
                lineHeight: 1.2,
              }}
            >
              {v}
            </div>
          </div>
        ))}
      </div>

      {/* 1. SCENARIO OBJECTIVE RULES & VICTORY CASUISTRY CARD */}
      <div
        style={{
          background: "#0f172a",
          border: "1px solid #334155",
          borderRadius: 8,
          padding: 16,
          marginBottom: 16,
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            cursor: "pointer",
            userSelect: "none",
          }}
          onClick={() => setShowScenarioRules(!showScenarioRules)}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 16 }}>🎯</span>
            <h3 style={{ margin: 0, fontSize: 15, color: "#f8fafc" }}>
              Casuística y Reglamento de Victoria del Escenario
            </h3>
            {scenarioData && (
              <span style={{ fontSize: 12, color: "#38bdf8", background: "#0369a122", padding: "2px 8px", borderRadius: 4, border: "1px solid #0284c744" }}>
                {scenarioData.scenario_id}
              </span>
            )}
            {scenarioLoading && <span style={{ fontSize: 12, color: "#94a3b8" }}>(Cargando reglas...)</span>}
          </div>
          <button
            style={{
              background: "transparent",
              border: "1px solid #475569",
              color: "#94a3b8",
              borderRadius: 4,
              fontSize: 11,
              padding: "3px 8px",
              cursor: "pointer",
            }}
          >
            {showScenarioRules ? "▲ Ocultar Reglamento" : "▼ Ver Reglamento"}
          </button>
        </div>

        {showScenarioRules && (
          <div style={{ marginTop: 12 }}>
            {scenarioData ? (
              <>
                {/* Scenario Metadata Strip */}
                <div
                  style={{
                    display: "flex",
                    flexWrap: "wrap",
                    gap: 16,
                    padding: "8px 12px",
                    background: "#1e293b",
                    borderRadius: 6,
                    fontSize: 12,
                    color: "#cbd5e1",
                    marginBottom: 12,
                    alignItems: "center",
                  }}
                >
                  <div>
                    Turnos Máximos: <b style={{ color: "#38bdf8" }}>{scenarioData.max_turns ?? "-"}</b>
                  </div>
                  <div>
                    Dimensiones: <b style={{ color: "#e2e8f0" }}>{scenarioData.shape ? `${scenarioData.shape[0]} × ${scenarioData.shape[1]}` : "-"}</b>
                  </div>
                  <div>
                    Total Objetivos VP: <b style={{ color: "#f59e0b" }}>{scenarioData.vp?.total_objectives ?? "-"} hexes</b> ({scenarioData.vp?.value_per_hex ?? 2} VP base)
                  </div>
                  <div>
                    Bando Rastreado: <b style={{ color: "#60a5fa" }}>{scenarioData.victory_outcomes?.tracked_side || "US"}</b>
                  </div>
                  <div>
                    Métrica: <b style={{ color: "#e2e8f0" }}>{scenarioData.victory_outcomes?.metric || "objectives_captured"}</b>
                  </div>
                  <div>
                    Momento Resolución: <b style={{ color: "#e2e8f0" }}>{scenarioData.victory_outcomes?.timing || "end_of_last_turn"}</b>
                  </div>
                  {scenarioData.initial_objectives_by_side && (
                    <div style={{ marginLeft: "auto", display: "flex", gap: 10 }}>
                      <span style={{ color: "#94a3b8" }}>Control inicial:</span>
                      {Object.entries(scenarioData.initial_objectives_by_side).map(([s, cnt]) => (
                        <span key={s} style={{ fontWeight: 700, color: s === "US" ? "#60a5fa" : s === "IT" ? "#34d399" : "#f87171" }}>
                          {s}: {cnt} obj
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                {/* Scenario Victory Outcomes Rules Table */}
                {scenarioTable.length > 0 ? (
                  <table>
                    <thead>
                      <tr>
                        <th style={{ width: 140 }}>Objetivos Capturados</th>
                        <th>Resultado Oficial (Reglamento)</th>
                        <th>Desenlace {scenarioData.tracked_side || "US"} (Tracked)</th>
                        <th>Desenlace Dual {scenarioData.opponent_side || "Rival"} (Zero-Sum)</th>
                        <th>Continuación Campaña</th>
                        <th>Regla / Nota</th>
                      </tr>
                    </thead>
                    <tbody>
                      {scenarioTable.map((row, idx) => {
                        const min = row.captured?.min ?? 0;
                        const max = row.captured?.max ?? 0;
                        const rangeStr = min === max ? `${min} obj` : `${min} - ${max} obj`;
                        const isDraw = row.canonical_class === "draw";

                        return (
                          <tr key={idx} style={{ background: isDraw ? "#1e293b44" : undefined }}>
                            <td>
                              <b style={{ color: "#f8fafc", fontSize: 13 }}>{rangeStr}</b>
                            </td>
                            <td>
                              <span style={{ fontWeight: 600, color: "#e2e8f0" }}>{row.result || "-"}</span>
                            </td>
                            <td>
                              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                <OutcomeBadge outcomeClass={row.canonical_class || row.outcome_class} />
                                <span style={{ fontSize: 11, color: "#94a3b8" }}>
                                  ({row.canonical_score !== undefined ? (row.canonical_score > 0 ? "+1" : row.canonical_score < 0 ? "-1" : "0") : "-"})
                                </span>
                              </div>
                            </td>
                            <td>
                              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                <OutcomeBadge outcomeClass={row.dual_class} />
                                <span style={{ fontSize: 11, color: "#94a3b8" }}>
                                  ({row.dual_score !== undefined ? (row.dual_score > 0 ? "+1" : row.dual_score < 0 ? "-1" : "0") : "-"})
                                </span>
                              </div>
                            </td>
                            <td>
                              {row.next_scenario ? (
                                <span style={{ color: "#38bdf8", fontWeight: 600, fontSize: 12 }}>
                                  Escenario {row.next_scenario} {row.next_page ? `(p. ${row.next_page})` : ""}
                                </span>
                              ) : (
                                <span style={{ color: "#64748b", fontSize: 11 }}>Fin de rama</span>
                              )}
                            </td>
                            <td>
                              <span style={{ fontSize: 11, color: "#94a3b8" }}>{row.note || "-"}</span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                ) : (
                  <div className="muted" style={{ fontStyle: "italic", padding: "8px 0" }}>
                    No hay tabla de condiciones de victoria especificada en el archivo de escenario.
                  </div>
                )}
              </>
            ) : (
              <div className="muted" style={{ fontStyle: "italic" }}>
                Información de escenario no disponible para {scenarioId || "desconocido"}.
              </div>
            )}
          </div>
        )}
      </div>

      {/* 2. TABLA UNIFICADA BILATERAL: DESENLACES, CONTROL VP Y TÁCTICA (ZERO-SUM DUAL) */}
      <h3 style={{ margin: "18px 0 8px 0" }}>
        Matriz Bilateral Unificada de Desenlaces, Control VP y Táctica (Zero-Sum Dual)
      </h3>
      <div className="muted" style={{ marginBottom: 8, fontSize: 12 }}>
        Clasificación canónica de resultados de combate y victoria según el reglamento unificado (desenlaces, tasas efectivas, variación de Victory Points y balance táctico de bajas/daño).
      </div>
      <div style={{ overflowX: "auto", border: "1px solid #334155", borderRadius: 6, marginBottom: 16 }}>
        <table style={{ margin: 0, minWidth: 1200 }}>
          <thead>
            <tr style={{ fontSize: 11, letterSpacing: "0.5px" }}>
              <th colSpan={4} style={{ textAlign: "center", background: "#0c1527", borderRight: "2px solid #334155", padding: "6px 8px" }}>
                ENFRENTAMIENTO
              </th>
              <th colSpan={5} style={{ textAlign: "center", background: "#0f2027", borderRight: "2px solid #334155", padding: "6px 8px" }}>
                DESENLACES CANÓNICOS (REGLAMENTO)
              </th>
              <th colSpan={3} style={{ textAlign: "center", background: "#172554", borderRight: "2px solid #334155", padding: "6px 8px" }}>
                EFECTIVIDAD GLOBAL
              </th>
              <th colSpan={7} style={{ textAlign: "center", background: "#1c1917", borderRight: "2px solid #334155", padding: "6px 8px" }}>
                CONTROL DE PUNTOS DE VICTORIA (VP)
              </th>
              <th colSpan={3} style={{ textAlign: "center", background: "#1e1b4b", padding: "6px 8px" }}>
                DESGASTE TÁCTICO
              </th>
            </tr>
            <tr style={{ fontSize: 11 }}>
              <th style={{ background: "#0f172a" }}>Escenario</th>
              <th style={{ background: "#0f172a" }}>Bando</th>
              <th style={{ background: "#0f172a" }}>Oponente</th>
              <th style={{ background: "#0f172a", borderRight: "2px solid #334155" }}>Perfil / Enfrentamiento</th>
              <th style={{ background: "#132328" }}>Vittoria Totale</th>
              <th style={{ background: "#132328" }}>Vittoria</th>
              <th style={{ background: "#132328" }}>Pareggio</th>
              <th style={{ background: "#132328" }}>Sconfitta</th>
              <th style={{ background: "#132328", borderRight: "2px solid #334155" }}>Sconfitta Totale</th>
              <th style={{ background: "#1e293b" }}>Win Rate</th>
              <th style={{ background: "#1e293b" }}>Loss Rate</th>
              <th style={{ background: "#1e293b", borderRight: "2px solid #334155" }}>Score Medio</th>
              <th style={{ background: "#26201b" }} title="Puntos de Victoria iniciales promedio">VP Inicial</th>
              <th style={{ background: "#26201b" }} title="Puntos de Victoria finales promedio">VP Final</th>
              <th style={{ background: "#26201b" }} title="Variación neta promedio de VPs">Δ VP Neto</th>
              <th style={{ background: "#26201b" }} title="Puntos de Victoria ganados en promedio por episodio">VP Gan. (Med.)</th>
              <th style={{ background: "#26201b", color: "#86efac", fontWeight: 700 }} title="Total acumulado de Puntos de Victoria capturados en todos los episodios">VP Gan. (Acum.)</th>
              <th style={{ background: "#26201b" }} title="Puntos de Victoria perdidos en promedio por episodio">VP Perd. (Med.)</th>
              <th style={{ background: "#26201b", borderRight: "2px solid #334155", color: "#fca5a5", fontWeight: 700 }} title="Total acumulado de Puntos de Victoria perdidos en todos los episodios">VP Perd. (Acum.)</th>
              <th style={{ background: "#272248" }}>Bajas Propias</th>
              <th style={{ background: "#272248" }}>Bajas Rival</th>
              <th style={{ background: "#272248" }}>Daño Total</th>
            </tr>
          </thead>
          <tbody>
            {matchupRows.length > 0 ? (
              matchupRows.map((m) => {
                const scoreColor = m.outcome_score > 0 ? "#22c55e" : m.outcome_score < 0 ? "#ef4444" : "#e2e8f0";
                const netVal = m.vpNet;
                const netColor = netVal > 0 ? "#22c55e" : netVal < 0 ? "#ef4444" : "#e2e8f0";

                return (
                  <tr
                    key={m.key}
                    style={{
                      borderBottom: m.isLastInGroup ? "2px solid #334155" : "1px solid #1e293b",
                    }}
                  >
                    {m.isFirstInGroup && (
                      <td
                        rowSpan={m.groupSize}
                        style={{
                          verticalAlign: "middle",
                          textAlign: "center",
                          background: "#0c1527",
                          borderRight: "1px solid #334155",
                          borderBottom: "2px solid #334155",
                          padding: "10px 8px",
                        }}
                      >
                        <span style={{ color: "#38bdf8", fontWeight: 700, fontSize: 12, display: "inline-block" }}>
                          {m.scenarioId || "-"}
                        </span>
                        <div className="muted" style={{ fontSize: 10, marginTop: 4 }}>
                          ({m.groupSize} {m.groupSize === 1 ? "enfrentamiento" : "enfrentamientos"})
                        </div>
                      </td>
                    )}
                    {m.isFirstInSideGroup && (
                      <td
                        rowSpan={m.sideGroupSize}
                        style={{
                          verticalAlign: "middle",
                          background: "#0f172a",
                          borderRight: "1px solid #334155",
                          borderBottom: m.isLastInGroup ? "2px solid #334155" : m.isLastInSideGroup ? "1px solid #334155" : undefined,
                          padding: "8px 10px",
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "center", gap: 5, flexWrap: "wrap" }}>
                          <span style={{ color: m.sideColor, fontWeight: 700, fontSize: 13 }}>
                            {m.side === "US" ? "🇺🇸 US" : m.side === "IT" ? "🇮🇹 IT" : m.side === "GE" ? "🇩🇪 GE" : m.side}
                          </span>
                          {Boolean(m.ownController) && (
                            <span className="muted" style={{ fontSize: 11 }}>
                              ({m.ownController})
                            </span>
                          )}
                        </div>
                        {m.sideGroupSize && m.sideGroupSize > 1 ? (
                          <div className="muted" style={{ fontSize: 10, marginTop: 4 }}>
                            ({m.sideGroupSize} enf.)
                          </div>
                        ) : null}
                      </td>
                    )}
                    <td>
                      <span style={{ color: m.oppColor, fontWeight: 600, fontSize: 12 }}>
                        {m.oppSide === "US" ? "🇺🇸 US" : m.oppSide === "IT" ? "🇮🇹 IT" : m.oppSide === "GE" ? "🇩🇪 GE" : m.oppSide}
                      </span>
                      {Boolean(m.oppController) && (
                        <span className="muted" style={{ fontSize: 11, marginLeft: 4 }}>
                          ({m.oppController})
                        </span>
                      )}
                    </td>
                    <td style={{ borderRight: "2px solid #334155" }}>
                      <span style={{ color: "#38bdf8", fontSize: 11, fontWeight: 600 }}>
                        {m.matchupProfile}
                      </span>
                      <span className="muted" style={{ fontSize: 10, marginLeft: 4 }}>
                        ({m.episodes} eps)
                      </span>
                    </td>
                    <td>
                      <span style={{ color: m.total_victory > 0 ? "#34d399" : "#64748b", fontWeight: m.total_victory > 0 ? 700 : 400 }}>
                        {m.episodes > 0 ? `${(m.total_victory * 100).toFixed(1)}%` : "-"}
                      </span>
                    </td>
                    <td>
                      <span style={{ color: m.victory > 0 ? "#86efac" : "#64748b", fontWeight: m.victory > 0 ? 600 : 400 }}>
                        {m.episodes > 0 ? `${(m.victory * 100).toFixed(1)}%` : "-"}
                      </span>
                    </td>
                    <td>
                      <span style={{ color: m.draw > 0 ? "#fde047" : "#64748b" }}>
                        {m.episodes > 0 ? `${(m.draw * 100).toFixed(1)}%` : "-"}
                      </span>
                    </td>
                    <td>
                      <span style={{ color: m.defeat > 0 ? "#fdba74" : "#64748b" }}>
                        {m.episodes > 0 ? `${(m.defeat * 100).toFixed(1)}%` : "-"}
                      </span>
                    </td>
                    <td style={{ borderRight: "2px solid #334155" }}>
                      <span style={{ color: m.total_defeat > 0 ? "#fca5a5" : "#64748b", fontWeight: m.total_defeat > 0 ? 700 : 400 }}>
                        {m.episodes > 0 ? `${(m.total_defeat * 100).toFixed(1)}%` : "-"}
                      </span>
                    </td>
                    <td>
                      <b style={{ color: m.episodes > 0 && m.win_rate >= 0.5 ? "#22c55e" : "#e2e8f0", fontSize: 13 }}>
                        {m.episodes > 0 ? `${(m.win_rate * 100).toFixed(1)}%` : "-"}
                      </b>
                    </td>
                    <td>
                      <span style={{ color: m.episodes > 0 && m.loss_rate >= 0.5 ? "#ef4444" : "#94a3b8" }}>
                        {m.episodes > 0 ? `${(m.loss_rate * 100).toFixed(1)}%` : "-"}
                      </span>
                    </td>
                    <td style={{ borderRight: "2px solid #334155" }}>
                      <b style={{ color: m.episodes > 0 ? scoreColor : "#64748b", fontSize: 13 }}>
                        {m.episodes > 0 ? (m.outcome_score >= 0 ? `+${m.outcome_score.toFixed(2)}` : m.outcome_score.toFixed(2)) : "-"}
                      </b>
                    </td>
                    <td>{m.vpInitial}</td>
                    <td>{m.vpFinal}</td>
                    <td>
                      <b style={{ color: netColor, fontSize: 13 }}>
                        {netVal >= 0 ? `+${Number(netVal).toFixed(2)}` : Number(netVal).toFixed(2)}
                      </b>
                    </td>
                    <td>
                      <span style={{ color: "#86efac" }}>
                        {m.vpGained !== "-" ? `+${m.vpGained}` : "-"}
                      </span>
                    </td>
                    <td>
                      <b style={{ color: String(m.vpGainedTotal).startsWith("+") ? "#22c55e" : "#94a3b8", fontSize: 12 }}>
                        {m.vpGainedTotal}
                      </b>
                    </td>
                    <td>
                      <span style={{ color: "#fca5a5" }}>
                        {m.vpLost !== "-" ? `-${m.vpLost}` : "-"}
                      </span>
                    </td>
                    <td style={{ borderRight: "2px solid #334155" }}>
                      <b style={{ color: String(m.vpLostTotal).startsWith("-") ? "#ef4444" : "#94a3b8", fontSize: 12 }}>
                        {m.vpLostTotal}
                      </b>
                    </td>
                    <td>
                      <span style={{ color: "#f87171", fontWeight: 600 }}>{m.avgLost}</span>
                    </td>
                    <td>
                      <span style={{ color: "#34d399", fontWeight: 600 }}>{m.avgKills}</span>
                    </td>
                    <td>
                      <span style={{ color: "#e2e8f0" }}>{m.avgDmg}</span>
                    </td>
                  </tr>
                );
              })
            ) : (
              <tr>
                <td colSpan={22} className="muted" style={{ textAlign: "center", padding: "16px 0" }}>
                  No hay enfrentamientos que coincidan con los filtros seleccionados.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Visual Funnel Chart for VP Progress and Conversions */}
      <FunnelChart diagnosticsSummary={currentEval.diagnostics_summary_eval} />

      {/* Matchup Profiles */}
      <h3 style={{ margin: "18px 0 8px 0" }}>Matchup Profiles ({filteredResults.length})</h3>
      {filteredResults.length === 0 ? (
        <div className="muted" style={{ padding: "16px 0", fontStyle: "italic" }}>
          No hay perfiles de simulación que coincidan con los filtros seleccionados.
        </div>
      ) : (
        <table>
          <thead>
            <tr>
              <th>escenario</th>
              <th>matchup_profile</th>
              <th>bando</th>
              <th>oponente</th>
              <th>episodes</th>
              <th>win_rate</th>
              <th>timeout_rate</th>
              <th>avg_steps</th>
              <th>avg_return</th>
              <th>captured_avg</th>
              <th>gate_score</th>
              <th>status</th>
            </tr>
          </thead>
          <tbody>
            {filteredResults.map((r, i) => {
              const displaySide = selectedSide !== "all"
                ? selectedSide
                : String(r.tracked_side || "ALL");
              const sideRate = selectedSide !== "all" && r.winner_side_rates?.[selectedSide] !== undefined
                ? r.winner_side_rates[selectedSide]
                : r.win_rate;
              const sideColor = displaySide === "US" ? "#60a5fa" : displaySide === "IT" ? "#34d399" : displaySide === "GE" ? "#f87171" : "#cbd5e1";
              const oppInfo = getOpponentInfo(displaySide, allSides, r);

              // Detect true scenario for this result row
              const rowSides = Array.from(
                new Set([
                  ...Object.keys(r.controller_by_side || {}),
                  ...Object.keys(r.policy_by_side || {}),
                  ...Object.keys(r.winner_side_rates || {}),
                ])
              ).map((s) => s.toUpperCase());

              let rowScen = String(
                r.scenario_id ||
                r.scenario ||
                (Array.isArray(r.seed_games) && r.seed_games[0]?.scenario_id) ||
                ""
              );
              if (!rowScen) {
                if (rowSides.includes("IT")) {
                  rowScen = currentEval?.scenario_ids?.[0] || "battaglia_cittadina_2_1";
                } else if (rowSides.includes("GE")) {
                  rowScen = currentEval?.scenario_ids?.[1] || "mettete_i_piedi_terra_1";
                } else {
                  rowScen = currentEval?.scenario_id || "-";
                }
              }

              return (
                <tr key={i}>
                  <td>
                    <span style={{ color: "#38bdf8", fontWeight: 700, fontSize: 11 }}>
                      {rowScen}
                    </span>
                  </td>
                  <td><b>{r.matchup_profile || `Profile ${i}`}</b></td>
                  <td>
                    <span style={{ color: sideColor, fontWeight: 700, fontSize: 11 }}>
                      {displaySide}
                    </span>
                  </td>
                  <td>
                    <span style={{ color: oppInfo.color, fontWeight: 600, fontSize: 11 }}>
                      {oppInfo.label}
                    </span>
                    {Boolean(oppInfo.controller) && (
                      <span className="muted" style={{ fontSize: 10, marginLeft: 4 }}>
                        ({oppInfo.controller})
                      </span>
                    )}
                  </td>
                  <td>{r.episodes ?? "-"}</td>
                  <td style={{ color: Number(sideRate || 0) >= 0.5 ? "#22c55e" : "#e2e8f0", fontWeight: selectedSide !== "all" ? 700 : 400 }}>
                    {sideRate !== undefined ? `${(Number(sideRate) * 100).toFixed(1)}%` : "-"}
                  </td>
                  <td style={{ color: Number(r.timeout_rate || 0) > 0.25 ? "#ef4444" : "#e2e8f0" }}>
                    {r.timeout_rate !== undefined ? `${(Number(r.timeout_rate) * 100).toFixed(1)}%` : "-"}
                  </td>
                  <td>{Number(r.avg_steps || 0).toFixed(1)}</td>
                  <td>{Number(r.avg_return || 0).toFixed(2)}</td>
                  <td>{Number(r.tracked_captured_avg || 0).toFixed(2)}</td>
                  <td>{r.score !== undefined ? Number(r.score).toFixed(3) : "-"}</td>
                  <td>
                    <span style={{ color: r.gate_ok ? "#22c55e" : "#ef4444", fontWeight: "bold" }}>
                      {r.gate_ok ? "PASS" : "FAIL"}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      {/* Side Combat and Tactical Effectiveness Breakdown */}
      <SideCombatTable results={filteredResults} filterSide={selectedSide} />
    </div>
  );
}
