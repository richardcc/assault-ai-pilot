import { Fragment, useMemo, useState } from "react";
import type { EvalResultRow, EvalRow } from "../../types";

type ActionDetail = {
  action_kind: string;
  count: number;
  damage: number;
  kills: number;
};

type SideActionGroup = {
  side: string;
  sideColor: string;
  controller: string;
  totalActions: number;
  totalDamage: number;
  totalKills: number;
  actions: ActionDetail[];
};

type BilateralTacticalRow = {
  scenarioId: string;
  side: string;
  sideColor: string;
  ownController: string;
  oppSide: string;
  oppColor: string;
  oppController: string;
  matchupProfile: string;
  episodes: number;
  totalActions: number;
  movePct: string;
  waitPct: string;
  rangedPct: string;
  assaultPct: string;
  mctsOverwritten: number;
  mctsTotal: number;
  mctsOverridePct: string;
  damageTotal: number;
  killsTotal: number;
  isAggregateRow?: boolean;
  isFirstInGroup?: boolean;
  groupSize?: number;
  isFirstInSideGroup?: boolean;
  sideGroupSize?: number;
};

function pct(value: number, total: number): string {
  if (!Number.isFinite(value) || !Number.isFinite(total) || total <= 0) return "N/A";
  return `${((100 * value) / total).toFixed(1)}%`;
}

const CANONICAL_CATALOG_ACTIONS: string[] = [
  "MOVE",
  "WAIT",
  "OPPORTUNITY_FIRE",
  "OPPORTUNITY_SKIP",
  "RANGED_DIRECT",
  "RANGED_INDIRECT",
  "FIRE_SMOKE",
  "FIRE_MOVE",
  "MOVE_FIRE",
  "ASSAULT",
  "EXPLOSIVE_CHARGE",
  "MINE_DETECTION",
];

function sanitizeController(val: string): string {
  if (!val) return "-";
  let s = String(val).trim();
  if (s.toLowerCase() === "muzero") return "EfficientZeroV2";
  if (s.toLowerCase() === "mcts") return "EfficientZeroV2";
  if (s.toLowerCase() === "random") return "Random";
  s = s.replace(/muzero/gi, "EfficientZeroV2");
  return s;
}

function resolveController(
  side: string,
  ctrlsMap: Record<string, string>,
  policiesMap?: Record<string, string>,
  defaultFallback: string = ""
): string {
  const norm = String(side || "").toUpperCase();
  const isUnknown = (val?: string) => !val || String(val).trim().toLowerCase() === "unknown";

  const direct = ctrlsMap[norm] || ctrlsMap[side];
  if (!isUnknown(direct)) return sanitizeController(direct);
  for (const [k, v] of Object.entries(ctrlsMap || {})) {
    if (k.toUpperCase() === norm && !isUnknown(v)) return sanitizeController(v);
  }

  if (policiesMap) {
    const pDirect = policiesMap[norm] || policiesMap[side];
    if (!isUnknown(pDirect)) return sanitizeController(pDirect);
    for (const [k, v] of Object.entries(policiesMap || {})) {
      if (k.toUpperCase() === norm && !isUnknown(v)) return sanitizeController(v);
    }
  }

  return sanitizeController(defaultFallback) || "-";
}

function getSideDisplay(s: string) {
  const norm = String(s || "").toUpperCase();
  if (norm === "US") return { label: "🇺🇸 US", color: "#60a5fa", bg: "#172554" };
  if (norm === "IT") return { label: "🇮🇹 IT", color: "#34d399", bg: "#064e3b" };
  if (norm === "GE" || norm === "DE") return { label: "🇩🇪 GE", color: "#f87171", bg: "#7f1d1d" };
  if (norm === "UK" || norm === "GB") return { label: "🇬🇧 UK", color: "#38bdf8", bg: "#0369a1" };
  if (norm === "RU" || norm === "SU") return { label: "🇷🇺 RU", color: "#e11d48", bg: "#881337" };
  return { label: norm, color: "#e2e8f0", bg: "#334155" };
}


export function getParticipatingSides(r: EvalResultRow): string[] {
  const sides = new Set<string>();

  if (r.winner_side_rates) {
    for (const s of Object.keys(r.winner_side_rates)) {
      if (s && s !== 'UNKNOWN' && s !== 'UNK') sides.add(s.toUpperCase());
    }
  }
  if (r.vp_net_avg_by_side) {
    for (const s of Object.keys(r.vp_net_avg_by_side)) {
      if (s && s !== 'UNKNOWN' && s !== 'UNK') sides.add(s.toUpperCase());
    }
  }
  if (r.phase_2_9_eval_kpis_by_side) {
    for (const s of Object.keys(r.phase_2_9_eval_kpis_by_side)) {
      if (s && s !== 'UNKNOWN' && s !== 'UNK') sides.add(s.toUpperCase());
    }
  }

  if (Array.isArray(r.seed_games)) {
    for (const sg of r.seed_games) {
      if (sg?.side_metrics) {
        for (const s of Object.keys(sg.side_metrics)) {
          if (s && s !== 'UNKNOWN' && s !== 'UNK') sides.add(s.toUpperCase());
        }
      }
    }
  }

  const sum = (r.eval_decision_summary || {}) as Record<string, unknown>;
  const by = (sum.by_action_kind_and_side || {}) as Record<string, Record<string, unknown>>;
  for (const src of Object.values(by)) {
    const s = String(src.unit_side || '').toUpperCase();
    if (s && s !== 'UNKNOWN' && s !== 'UNK') sides.add(s);
  }

  if (!sides.size) {
    if (r.tracked_side) sides.add(String(r.tracked_side).toUpperCase());
    if (r.opponent_side) sides.add(String(r.opponent_side).toUpperCase());
  }

  if (!sides.size && r.controller_by_side) {
    for (const s of Object.keys(r.controller_by_side)) {
      if (s && s !== 'UNKNOWN' && s !== 'UNK') sides.add(s.toUpperCase());
    }
  }

  return Array.from(sides).sort();
}

export function resolveScenarioId(r: EvalResultRow, fallbackEval?: EvalRunRow | null): string {
  const directScen = r.scenario_id || r.scenario;
  if (directScen && !directScen.startsWith('multi:') && !directScen.includes('|')) {
    return directScen;
  }

  if (Array.isArray(r.seed_games) && r.seed_games.length > 0) {
    const sg0 = r.seed_games[0];
    const sgScen = sg0?.scenario_id || sg0?.scenario;
    if (sgScen && !String(sgScen).startsWith('multi:') && !String(sgScen).includes('|')) {
      return String(sgScen);
    }
  }

  const parts = getParticipatingSides(r);
  if (parts.includes('IT')) {
    return fallbackEval?.scenario_ids?.[0] || 'battaglia_cittadina_2_1';
  }
  if (parts.includes('GE')) {
    return fallbackEval?.scenario_ids?.[1] || 'mettete_i_piedi_terra_1';
  }

  if (fallbackEval?.scenario_id && !fallbackEval.scenario_id.startsWith('multi:') && !fallbackEval.scenario_id.includes('|')) {
    return fallbackEval.scenario_id;
  }
  return 'escenario';
}

export function EvalDecisionsTab({
  selectedEval,
  mainResult,
}: {
  selectedEval?: EvalRow | null;
  mainResult?: EvalResultRow | null;
}) {
  const [selectedScenario, setSelectedScenario] = useState<string>("all");
  const [selectedMatchup, setSelectedMatchup] = useState<string>("all");
  const [selectedSide, setSelectedSide] = useState<string>("all");
  const [hideZeroActions, setHideZeroActions] = useState<boolean>(false);

  // Extract all evaluation results from the benchmark
  const rawResults: EvalResultRow[] = useMemo(() => {
    if (selectedEval?.results && Array.isArray(selectedEval.results) && selectedEval.results.length > 0) {
      return selectedEval.results;
    }
    if (mainResult) {
      return [mainResult];
    }
    return [];
  }, [selectedEval, mainResult]);

  if (!rawResults.length) {
    return (
      <div className="muted" style={{ padding: 16 }}>
        No hay datos de decisiones tácticas disponibles para esta evaluación.
      </div>
    );
  }

  // Available scenarios from raw results
  const availableScenarios = useMemo(() => {
    const sSet = new Set<string>();
    for (const r of rawResults) {
      const sc = resolveScenarioId(r, selectedEval);
      if (sc && sc !== "escenario") sSet.add(sc);
    }
    if (Array.isArray(selectedEval?.scenario_ids)) {
      selectedEval!.scenario_ids.forEach((s) => s && sSet.add(s));
    }
    return Array.from(sSet).sort();
  }, [rawResults, selectedEval]);

  // Available matchup options for filtering
  const availableMatchups = useMemo(() => {
    const map = new Map<string, { id: string; profile: string; episodes: number }>();
    for (const [idx, r] of rawResults.entries()) {
      if (selectedScenario !== "all") {
        const sc = resolveScenarioId(r, selectedEval);
        if (sc.toLowerCase() !== selectedScenario.toLowerCase()) continue;
      }
      const prof = r.matchup_profile || `result_${idx}`;
      if (!map.has(prof)) {
        map.set(prof, { id: prof, profile: prof, episodes: 0 });
      }
      map.get(prof)!.episodes += Number(r.episodes || 10);
    }
    return Array.from(map.values());
  }, [rawResults, selectedScenario, selectedEval]);

  // Results subset based on selected scenario and matchup
  const activeResults = useMemo(() => {
    return rawResults.filter((r, idx) => {
      if (selectedScenario !== "all") {
        const sc = resolveScenarioId(r, selectedEval);
        if (sc.toLowerCase() !== selectedScenario.toLowerCase()) return false;
      }
      if (selectedMatchup !== "all") {
        const prof = r.matchup_profile || `result_${idx}`;
        if (prof !== selectedMatchup) return false;
      }
      return true;
    });
  }, [rawResults, selectedScenario, selectedMatchup, selectedEval]);

  // 1. DISCOVER ALL PARTICIPATING SIDES DYNAMICALLY (strictly with actual decisions/actions)
  const allDiscoveredSides = useMemo(() => {
    const sSet = new Set<string>();
    for (const r of activeResults) {
      const parts = getParticipatingSides(r);
      for (const s of parts) sSet.add(s);
    }
    if (!sSet.size) {
      for (const r of activeResults) {
        for (const s of Object.keys((r.controller_by_side || {}) as Record<string, string>)) {
          sSet.add(s.toUpperCase());
        }
      }
    }
    return Array.from(sSet).sort();
  }, [activeResults]);

  // Active sides after side filter
  const activeSides = useMemo(() => {
    if (selectedSide === "all") return allDiscoveredSides;
    return allDiscoveredSides.filter((s) => s.toUpperCase() === selectedSide.toUpperCase());
  }, [allDiscoveredSides, selectedSide]);

  // 2. TABLA A: BANDO POR FILAS - Construcción de grupos de acciones por Bando
  const { sideActionGroups, globalTotals, kpis, ownRows, topRows } = useMemo(() => {
    const aggBySideAction = new Map<string, Map<string, { count: number; damage: number; kills: number }>>();
    const aggOwnershipBySide = new Map<
      string,
      { side: string; rows: number; policy_kept: number; overwritten: number; override_signal_rows: number; unknown_override_rows: number }
    >();
    const aggTops = new Map<string, { action_id: string; action_kind: string; side: string; count: number; damage: number; kills: number }>();

    let totalEpisodes = 0;
    let totalDecisions = 0;
    let totalDamage = 0;
    let totalKills = 0;
    let totalMove = 0;
    let totalCombat = 0;
    let totalSpecial = 0;
    let totalMctsOverwritten = 0;
    let totalPolicyDecisions = 0;

    for (const s of allDiscoveredSides) {
      aggBySideAction.set(s, new Map());
    }

    for (const r of activeResults) {
      totalEpisodes += Number(r.episodes || 10);
      const summary = (r.eval_decision_summary || {}) as Record<string, unknown>;
      const by = (summary.by_action_kind_and_side || {}) as Record<string, Record<string, unknown>>;
      const own = (summary.decision_ownership_by_side || {}) as Record<string, Record<string, unknown>>;
      const tops = Array.isArray(r.eval_decisions_top) ? (r.eval_decisions_top as Record<string, unknown>[]) : [];

      for (const src of Object.values(by)) {
        const kind = String(src.action_kind || "UNKNOWN");
        const s = String(src.unit_side || "UNK").toUpperCase();
        if (!s || s === "UNKNOWN" || s === "UNK") continue;

        const count = Number(src.count || 0);
        const damage = Number(src.damage_sum || 0);
        const kills = Number(src.kills_sum || 0);

        totalDecisions += count;
        totalDamage += damage;
        totalKills += kills;

        if (kind === "MOVE") totalMove += count;
        if (["RANGED_DIRECT", "RANGED_INDIRECT", "FIRE_MOVE", "MOVE_FIRE", "OPPORTUNITY_FIRE"].includes(kind)) totalCombat += count;
        if (["ASSAULT", "EXPLOSIVE_CHARGE", "MINE_DETECTION"].includes(kind)) totalSpecial += count;

        if (!aggBySideAction.has(s)) aggBySideAction.set(s, new Map());
        const sMap = aggBySideAction.get(s)!;
        const cur = sMap.get(kind) || { count: 0, damage: 0, kills: 0 };
        cur.count += count;
        cur.damage += damage;
        cur.kills += kills;
        sMap.set(kind, cur);
      }

      for (const [sideKey, src] of Object.entries(own)) {
        const s = sideKey.toUpperCase();
        if (!s || s === "UNKNOWN" || s === "UNK") continue;

        const rCount = Number(src.rows || 0);
        const kept = Number(src.policy_kept || 0);
        const overw = Number(src.overwritten || 0);
        const sig = Number(src.override_signal_rows || 0);
        const unk = Number(src.unknown_override_rows || 0);

        totalPolicyDecisions += rCount;
        totalMctsOverwritten += overw;

        const existing = aggOwnershipBySide.get(s) || {
          side: s,
          rows: 0,
          policy_kept: 0,
          overwritten: 0,
          override_signal_rows: 0,
          unknown_override_rows: 0,
        };
        existing.rows += rCount;
        existing.policy_kept += kept;
        existing.overwritten += overw;
        existing.override_signal_rows += sig;
        existing.unknown_override_rows += unk;
        aggOwnershipBySide.set(s, existing);
      }

      for (const t of tops) {
        const actionId = String(t.action_id || "");
        const kind = String(t.action_kind || "");
        const s = String(t.unit_side || "").toUpperCase();
        const count = Number(t.count || 0);
        const damage = Number(t.damage_sum || 0);
        const kills = Number(t.kills_sum || 0);

        const key = `${actionId}::${s}`;
        const existing = aggTops.get(key) || { action_id: actionId, action_kind: kind, side: s, count: 0, damage: 0, kills: 0 };
        existing.count += count;
        existing.damage += damage;
        existing.kills += kills;
        aggTops.set(key, existing);
      }
    }

    // Build the per-side action groups for Tabla A (Bando por Filas)
    const groups: SideActionGroup[] = [];
    let grandActions = 0;
    let grandDamage = 0;
    let grandKills = 0;

    for (const s of activeSides) {
      const sMap = aggBySideAction.get(s) || new Map();
      const sideInfo = getSideDisplay(s);

      // Collect all canonical + observed actions for this side
      const actionKindsSet = new Set([...CANONICAL_CATALOG_ACTIONS, ...Array.from(sMap.keys())]);
      let actionList: ActionDetail[] = [];
      let sideTotAct = 0;
      let sideTotDmg = 0;
      let sideTotKills = 0;

      for (const ak of actionKindsSet) {
        const data = sMap.get(ak) || { count: 0, damage: 0, kills: 0 };
        sideTotAct += data.count;
        sideTotDmg += data.damage;
        sideTotKills += data.kills;

        actionList.push({
          action_kind: ak,
          count: data.count,
          damage: data.damage,
          kills: data.kills,
        });
      }

      // Sort actions: executed actions first by count desc, then unexecuted in canonical order
      actionList.sort((a, b) => {
        if (b.count !== a.count) return b.count - a.count;
        const ia = CANONICAL_CATALOG_ACTIONS.indexOf(a.action_kind);
        const ib = CANONICAL_CATALOG_ACTIONS.indexOf(b.action_kind);
        if (ia !== -1 && ib !== -1) return ia - ib;
        return a.action_kind.localeCompare(b.action_kind);
      });

      if (hideZeroActions) {
        actionList = actionList.filter((a) => a.count > 0);
      }

      grandActions += sideTotAct;
      grandDamage += sideTotDmg;
      grandKills += sideTotKills;

      // Extract controller for side
      const sampleResult = activeResults.find((r) => getParticipatingSides(r).includes(s)) || activeResults[0];
      const ctrls = (sampleResult?.controller_by_side || {}) as Record<string, string>;
      const pols = (sampleResult?.policy_by_side || {}) as Record<string, string>;
      const ctrlName = resolveController(s, ctrls, pols, "EfficientZeroV2 (MCTS)");

      groups.push({
        side: s,
        sideColor: sideInfo.color,
        controller: ctrlName,
        totalActions: sideTotAct,
        totalDamage: sideTotDmg,
        totalKills: sideTotKills,
        actions: actionList,
      });
    }

    const ownRowsList = Array.from(aggOwnershipBySide.values()).sort((a, b) => a.side.localeCompare(b.side));
    const topRowsList = Array.from(aggTops.values())
      .sort((a, b) => b.count - a.count)
      .slice(0, 25);

    return {
      sideActionGroups: groups,
      globalTotals: {
        actions: grandActions,
        damage: grandDamage,
        kills: grandKills,
      },
      kpis: {
        episodes: totalEpisodes,
        decisions: totalDecisions,
        move: totalMove,
        combat: totalCombat,
        special: totalSpecial,
        damage: totalDamage,
        kills: totalKills,
        mctsOverwritten: totalMctsOverwritten,
        policyDecisions: totalPolicyDecisions,
      },
      ownRows: ownRowsList,
      topRows: topRowsList,
    };
  }, [activeResults, activeSides, allDiscoveredSides, hideZeroActions]);

  // 3. TABLA B: MATRIZ BILATERAL TÁCTICA CON FILA AGREGADA POR BANDO (DESGLOSADA POR CADA ESCENARIO)
  const bilateralMatchupRows: BilateralTacticalRow[] = useMemo(() => {
    const finalGroupedList: BilateralTacticalRow[] = [];

    // Group rawResults by scenario cleanly
    const scenarioMap = new Map<string, EvalResultRow[]>();
    for (const r of rawResults) {
      const scenKey = resolveScenarioId(r, selectedEval);
      if (selectedScenario !== "all" && scenKey.toLowerCase() !== selectedScenario.toLowerCase()) {
        continue;
      }
      if (!scenarioMap.has(scenKey)) scenarioMap.set(scenKey, []);
      scenarioMap.get(scenKey)!.push(r);
    }

    for (const [scenKey, sResults] of scenarioMap) {
      // Collect only the truly participating sides for this scenario
      const scenSidesSet = new Set<string>();
      for (const r of sResults) {
        const parts = getParticipatingSides(r);
        for (const s of parts) scenSidesSet.add(s);
      }
      const scenSides = Array.from(scenSidesSet)
        .filter((s) => s && s !== "UNKNOWN" && s !== "UNK")
        .sort();

      const scenRows: BilateralTacticalRow[] = [];

      // For each Bando, create the AGGREGATE ROW first, followed by each MATCHUP ROW
      for (const s of scenSides) {
        if (selectedSide !== "all" && s.toUpperCase() !== selectedSide.toUpperCase()) {
          continue;
        }

        const sideInfo = getSideDisplay(s);

        // Gather all matchups where this side participates
        const sideMatchupRows: BilateralTacticalRow[] = [];
        let aggEps = 0;
        let aggActions = 0;
        let aggMove = 0;
        let aggWait = 0;
        let aggRanged = 0;
        let aggAssault = 0;
        let aggOverwritten = 0;
        let aggMctsTotal = 0;
        let aggDmg = 0;
        let aggKills = 0;
        let mainCtrl = "";

        for (const [rIdx, r] of sResults.entries()) {
          const prof = r.matchup_profile || `perfil_${rIdx}`;
          if (selectedMatchup !== "all" && prof !== selectedMatchup) {
            continue;
          }

          const rSides = getParticipatingSides(r);
          if (!rSides.includes(s)) {
            continue;
          }

          const eps = Number(r.episodes || 10);
          const ctrls = (r.controller_by_side || {}) as Record<string, string>;
          const policies = (r.policy_by_side || {}) as Record<string, string>;

          const sum = (r.eval_decision_summary || {}) as Record<string, unknown>;
          const by = (sum.by_action_kind_and_side || {}) as Record<string, Record<string, unknown>>;
          const own = (sum.decision_ownership_by_side || {}) as Record<string, Record<string, unknown>>;

          const opp = rSides.find((x) => x !== s) || (s === "IT" ? "US" : s === "US" ? "IT" : "GE");
          const oppInfo = getSideDisplay(opp);

          const ownCtrl = resolveController(s, ctrls, policies, "EfficientZeroV2 (MCTS)");
          const oppCtrl = resolveController(opp, ctrls, policies, "EfficientZeroV2 (MCTS)");
          if (!mainCtrl) mainCtrl = ownCtrl;

          let rAct = 0, rMove = 0, rWait = 0, rRanged = 0, rAssault = 0, rDmg = 0, rKills = 0;
          for (const src of Object.values(by)) {
            if (String(src.unit_side || "").toUpperCase() === s) {
              const kind = String(src.action_kind || "");
              const cnt = Number(src.count || 0);
              rAct += cnt;
              rDmg += Number(src.damage_sum || 0);
              rKills += Number(src.kills_sum || 0);

              if (kind === "MOVE") rMove += cnt;
              else if (kind === "WAIT") rWait += cnt;
              else if (["RANGED_DIRECT", "RANGED_INDIRECT", "FIRE_MOVE", "MOVE_FIRE", "OPPORTUNITY_FIRE"].includes(kind)) rRanged += cnt;
              else if (["ASSAULT", "EXPLOSIVE_CHARGE", "MINE_DETECTION"].includes(kind)) rAssault += cnt;
            }
          }

          const ownData = (own[s] || {}) as Record<string, unknown>;
          const mctsTot = Number(ownData.rows || rAct);
          const mctsOver = Number(ownData.overwritten || 0);

          aggEps += eps;
          aggActions += rAct;
          aggMove += rMove;
          aggWait += rWait;
          aggRanged += rRanged;
          aggAssault += rAssault;
          aggOverwritten += mctsOver;
          aggMctsTotal += mctsTot;
          aggDmg += rDmg;
          aggKills += rKills;

          sideMatchupRows.push({
            scenarioId: scenKey,
            side: s,
            sideColor: sideInfo.color,
            ownController: ownCtrl,
            oppSide: opp,
            oppColor: oppInfo.color,
            oppController: oppCtrl,
            matchupProfile: prof,
            episodes: eps,
            totalActions: rAct,
            movePct: pct(rMove, rAct),
            waitPct: pct(rWait, rAct),
            rangedPct: pct(rRanged, rAct),
            assaultPct: pct(rAssault, rAct),
            mctsOverwritten: mctsOver,
            mctsTotal: mctsTot,
            mctsOverridePct: pct(mctsOver, mctsTot),
            damageTotal: rDmg,
            killsTotal: rKills,
            isAggregateRow: false,
          });
        }

        if (!sideMatchupRows.length) continue;

        // 1. ADD AGGREGATE ROW FOR THIS BANDO
        const sideAggRow: BilateralTacticalRow = {
          scenarioId: scenKey,
          side: s,
          sideColor: sideInfo.color,
          ownController: mainCtrl || "EfficientZeroV2",
          oppSide: "Todos los rivales",
          oppColor: "#94a3b8",
          oppController: "Global",
          matchupProfile: `◀▶ AGREGADO TOTAL (${sideMatchupRows.length} enfrentamientos)`,
          episodes: aggEps,
          totalActions: aggActions,
          movePct: pct(aggMove, aggActions),
          waitPct: pct(aggWait, aggActions),
          rangedPct: pct(aggRanged, aggActions),
          assaultPct: pct(aggAssault, aggActions),
          mctsOverwritten: aggOverwritten,
          mctsTotal: aggMctsTotal,
          mctsOverridePct: pct(aggOverwritten, aggMctsTotal),
          damageTotal: aggDmg,
          killsTotal: aggKills,
          isAggregateRow: true,
        };

        const totalSideRows = 1 + sideMatchupRows.length;

        // Push aggregate row with side header
        scenRows.push({
          ...sideAggRow,
          isFirstInSideGroup: true,
          sideGroupSize: totalSideRows,
        });

        // Push individual matchup rows
        for (const item of sideMatchupRows) {
          scenRows.push({
            ...item,
            isFirstInSideGroup: false,
            sideGroupSize: totalSideRows,
          });
        }
      }

      // Mark scenario group size
      scenRows.forEach((item, idx) => {
        finalGroupedList.push({
          ...item,
          isFirstInGroup: idx === 0,
          groupSize: scenRows.length,
        });
      });
    }

    return finalGroupedList;
  }, [rawResults, selectedScenario, selectedSide, selectedMatchup, selectedEval]);

  const isAggregated = selectedMatchup === "all";

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
        <div>
          <h3 style={{ margin: "0 0 4px 0" }}>🎯 Decisiones Tácticas & Distribución de Acciones (KBI)</h3>
          <div className="muted" style={{ fontSize: 12 }}>
            Desglose con <b>Bando por Filas</b> para adaptación dinámica a cualquier número de bandos en el experimento, agregación sistemática de acciones canónicas y matriz bilateral.
          </div>
        </div>
      </div>

      {/* Filter Bar (Visual alignment with VpSummaryTab) */}
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
          <span>🔍</span> Agregación & Filtros:
        </span>

        {/* Scenario Filter */}
        {availableScenarios.length > 1 && (
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <label htmlFor="decisions-filter-scenario" style={{ fontSize: 12, color: "#94a3b8", fontWeight: 600 }}>
              Escenario:
            </label>
            <select
              id="decisions-filter-scenario"
              value={selectedScenario}
              onChange={(e) => setSelectedScenario(e.target.value)}
              style={{
                padding: "4px 8px",
                background: "#1e293b",
                color: "#e2e8f0",
                border: selectedScenario !== "all" ? "1px solid #38bdf8" : "1px solid #475569",
                borderRadius: 5,
                fontSize: 12,
                fontWeight: selectedScenario === "all" ? 700 : 500,
              }}
            >
              <option value="all">Todos los escenarios ({availableScenarios.length})</option>
              {availableScenarios.map((sc) => (
                <option key={sc} value={sc}>
                  {sc}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Matchup Profile Filter */}
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <label htmlFor="decisions-filter-matchup" style={{ fontSize: 12, color: "#94a3b8", fontWeight: 600 }}>
            Enfrentamiento:
          </label>
          <select
            id="decisions-filter-matchup"
            value={selectedMatchup}
            onChange={(e) => setSelectedMatchup(e.target.value)}
            style={{
              padding: "4px 10px",
              background: "#1e293b",
              color: "#e2e8f0",
              border: selectedMatchup !== "all" ? "1px solid #38bdf8" : "1px solid #475569",
              borderRadius: 5,
              fontSize: 12,
              fontWeight: selectedMatchup === "all" ? 700 : 500,
            }}
          >
            <option value="all">
              ⚡ Todos los enfrentamientos (Agregado Total - {availableMatchups.reduce((acc, m) => acc + m.episodes, 0)} eps)
            </option>
            {availableMatchups.map((m) => (
              <option key={m.id} value={m.id}>
                {m.profile} ({m.episodes} eps)
              </option>
            ))}
          </select>
        </div>

        {/* Side Filter */}
        {allDiscoveredSides.length > 0 && (
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <label htmlFor="decisions-filter-side" style={{ fontSize: 12, color: "#94a3b8", fontWeight: 600 }}>
              Bando:
            </label>
            <select
              id="decisions-filter-side"
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
              <option value="all">Todos los bandos ({allDiscoveredSides.length})</option>
              {allDiscoveredSides.map((s) => {
                const sInfo = getSideDisplay(s);
                return (
                  <option key={s} value={s}>
                    {sInfo.label}
                  </option>
                );
              })}
            </select>
          </div>
        )}

        {/* Toggle to hide zero-count actions */}
        <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "#94a3b8", cursor: "pointer" }}>
          <input
            type="checkbox"
            checked={hideZeroActions}
            onChange={(e) => setHideZeroActions(e.target.checked)}
            style={{ cursor: "pointer" }}
          />
          Ocultar acciones con 0 ejecuciones
        </label>

        {(selectedScenario !== "all" || selectedMatchup !== "all" || selectedSide !== "all" || hideZeroActions) && (
          <button
            onClick={() => {
              setSelectedScenario("all");
              setSelectedMatchup("all");
              setSelectedSide("all");
              setHideZeroActions(false);
            }}
            style={{
              background: "#334155",
              color: "#e2e8f0",
              border: "1px solid #475569",
              padding: "4px 10px",
              borderRadius: 5,
              fontSize: 11,
              cursor: "pointer",
              fontWeight: 600,
            }}
          >
            ✕ Restablecer (Ver Agregado Total)
          </button>
        )}

        <div style={{ marginLeft: "auto", fontSize: 12, color: "#94a3b8" }}>
          Bandos descubiertos: <b style={{ color: "#38bdf8" }}>{allDiscoveredSides.join(", ")}</b> | Vista:{" "}
          <b style={{ color: isAggregated ? "#34d399" : "#38bdf8" }}>
            {isAggregated ? `⚡ Agregado Total (${activeResults.length} perfiles, ${kpis.episodes} eps)` : `Perfil Individual (${kpis.episodes} eps)`}
          </b>
        </div>
      </div>

      {/* Global Tactical KPI Strip */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(8, minmax(0, 1fr))",
          gap: 6,
          marginBottom: 16,
        }}
      >
        {[
          { k: "Episodios", v: `${kpis.episodes} eps`, color: "#38bdf8" },
          { k: "Total Decisiones", v: kpis.decisions.toLocaleString(), color: "#f8fafc" },
          { k: "Movimiento", v: `${pct(kpis.move, kpis.decisions)} (${kpis.move})`, color: "#a5b4fc" },
          { k: "Fuego & Ataques", v: `${pct(kpis.combat, kpis.decisions)} (${kpis.combat})`, color: "#fdba74" },
          { k: "Asalto / Especial", v: `${pct(kpis.special, kpis.decisions)} (${kpis.special})`, color: "#f472b6" },
          { k: "Daño Total", v: kpis.damage.toFixed(1), color: "#f87171" },
          { k: "Bajas Causadas", v: kpis.kills.toFixed(0), color: "#ef4444" },
          {
            k: "MCTS Override",
            v: `${pct(kpis.mctsOverwritten, kpis.policyDecisions)} (${kpis.mctsOverwritten})`,
            color: kpis.mctsOverwritten > 0 ? "#38bdf8" : "#94a3b8",
          },
        ].map(({ k, v, color }) => (
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
                color,
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

      {/* RESUMEN COMPARATIVO POR BANDO (1 FILA POR BANDO) */}
      <h4 style={{ margin: "0 0 6px 0", color: "#f8fafc" }}>
        Resumen Táctico Comparativo por Bando {isAggregated ? "(Agregado Total de la Evaluación)" : `(${selectedMatchup})`}
      </h4>
      <div className="muted" style={{ marginBottom: 8, fontSize: 12 }}>
        Comparativa global de volumen táctico y balance de acciones por bando en filas independientes.
      </div>
      <div style={{ overflowX: "auto", border: "1px solid #334155", borderRadius: 6, marginBottom: 20 }}>
        <table style={{ margin: 0 }}>
          <thead>
            <tr>
              <th style={{ background: "#0f172a" }}>Bando</th>
              <th style={{ background: "#0f172a" }}>Controlador / Red</th>
              <th style={{ background: "#0f172a" }}>Total Acciones</th>
              <th style={{ background: "#0f172a" }}>% Movimiento</th>
              <th style={{ background: "#0f172a" }}>% Espera (Wait)</th>
              <th style={{ background: "#0f172a" }}>% Fuego / Disparo</th>
              <th style={{ background: "#0f172a" }}>% Asalto / Brecha</th>
              <th style={{ background: "#0f172a" }}>Daño Infligido</th>
              <th style={{ background: "#0f172a" }}>Bajas Causadas</th>
            </tr>
          </thead>
          <tbody>
            {!sideActionGroups.length ? (
              <tr>
                <td colSpan={9} className="muted">
                  No hay datos de bandos disponibles.
                </td>
              </tr>
            ) : (
              sideActionGroups.map((g) => {
                const sInfo = getSideDisplay(g.side);
                const moveCnt = g.actions.find((a) => a.action_kind === "MOVE")?.count || 0;
                const waitCnt = g.actions.find((a) => a.action_kind === "WAIT")?.count || 0;
                const fireCnt = g.actions
                  .filter((a) => ["RANGED_DIRECT", "RANGED_INDIRECT", "FIRE_MOVE", "MOVE_FIRE", "OPPORTUNITY_FIRE"].includes(a.action_kind))
                  .reduce((sum, a) => sum + a.count, 0);
                const assaultCnt = g.actions
                  .filter((a) => ["ASSAULT", "EXPLOSIVE_CHARGE", "MINE_DETECTION"].includes(a.action_kind))
                  .reduce((sum, a) => sum + a.count, 0);

                return (
                  <tr key={g.side}>
                    <td>
                      <b style={{ color: sInfo.color, fontSize: 13 }}>{sInfo.label}</b>
                    </td>
                    <td>
                      <span style={{ fontSize: 11, color: "#94a3b8" }}>{g.controller}</span>
                    </td>
                    <td style={{ fontWeight: 700, color: "#f8fafc" }}>{g.totalActions}</td>
                    <td>
                      {pct(moveCnt, g.totalActions)} ({moveCnt})
                    </td>
                    <td>
                      {pct(waitCnt, g.totalActions)} ({waitCnt})
                    </td>
                    <td style={{ color: "#fdba74" }}>
                      {pct(fireCnt, g.totalActions)} ({fireCnt})
                    </td>
                    <td style={{ color: "#f472b6" }}>
                      {pct(assaultCnt, g.totalActions)} ({assaultCnt})
                    </td>
                    <td style={{ color: g.totalDamage > 0 ? "#f87171" : undefined, fontWeight: 600 }}>
                      {g.totalDamage.toFixed(1)}
                    </td>
                    <td style={{ color: g.totalKills > 0 ? "#ef4444" : undefined, fontWeight: 700 }}>
                      {g.totalKills.toFixed(0)}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
          {sideActionGroups.length > 0 && (
            <tfoot>
              <tr style={{ background: "#0f172a", fontWeight: "bold", borderTop: "2px solid #334155" }}>
                <td style={{ color: "#38bdf8" }}>Total Global</td>
                <td style={{ color: "#94a3b8" }}>Todos los controladores</td>
                <td style={{ color: "#f8fafc" }}>{globalTotals.actions}</td>
                <td>{pct(kpis.move, globalTotals.actions)}</td>
                <td>-</td>
                <td style={{ color: "#fdba74" }}>{pct(kpis.combat, globalTotals.actions)}</td>
                <td style={{ color: "#f472b6" }}>{pct(kpis.special, globalTotals.actions)}</td>
                <td style={{ color: "#f87171" }}>{globalTotals.damage.toFixed(1)}</td>
                <td style={{ color: "#ef4444" }}>{globalTotals.kills.toFixed(0)}</td>
              </tr>
            </tfoot>
          )}
        </table>
      </div>

      {/* TABLA A: BANDO POR FILAS - DETALLE DE ACCIONES CANÓNICAS */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
        <h4 style={{ margin: 0, color: "#f8fafc" }}>
          Tabla A: Distribución Canónica de Acciones con Bando por Filas {isAggregated ? "(Agregado Total de la Evaluación)" : `(${selectedMatchup})`}
        </h4>
        <span style={{ fontSize: 11, color: "#94a3b8" }}>
          Estructura invariante por filas | {sideActionGroups.length} bando(s) activo(s)
        </span>
      </div>
      <div className="muted" style={{ marginBottom: 8, fontSize: 12 }}>
        Cada bando cuenta con su propio bloque jerárquico de filas con sus acciones ejecutadas y catálogo canónico. No expande horizontalmente al añadirse nuevos bandos.
      </div>

      <div style={{ overflowX: "auto", border: "1px solid #334155", borderRadius: 6, marginBottom: 20 }}>
        <table style={{ margin: 0 }}>
          <thead>
            <tr>
              <th style={{ background: "#0f172a", width: 140 }}>Bando</th>
              <th style={{ background: "#0f172a", minWidth: 200 }}>Acción Canónica (action_kind)</th>
              <th style={{ background: "#0f172a", textAlign: "right" }}>count</th>
              <th style={{ background: "#0f172a", textAlign: "right" }}>% count (bando)</th>
              <th style={{ background: "#0f172a", textAlign: "right" }}>daño infligido</th>
              <th style={{ background: "#0f172a", textAlign: "right" }}>% daño</th>
              <th style={{ background: "#0f172a", textAlign: "right" }}>bajas causadas</th>
              <th style={{ background: "#0f172a", textAlign: "right" }}>% bajas</th>
            </tr>
          </thead>
          <tbody>
            {!sideActionGroups.length ? (
              <tr>
                <td colSpan={8} className="muted">
                  No hay datos de acciones disponibles.
                </td>
              </tr>
            ) : (
              sideActionGroups.map((g) => {
                const sInfo = getSideDisplay(g.side);
                const rowSpanCount = g.actions.length + 1; // actions + subtotal row

                return (
                  <Fragment key={`bando-group-${g.side}`}>
                    {g.actions.map((act, actIdx) => {
                      const isSpecial = ["EXPLOSIVE_CHARGE", "MINE_DETECTION", "ASSAULT"].includes(act.action_kind);
                      const isRanged = ["RANGED_DIRECT", "RANGED_INDIRECT", "FIRE_MOVE", "MOVE_FIRE", "OPPORTUNITY_FIRE"].includes(act.action_kind);

                      return (
                        <tr
                          key={`${g.side}-${act.action_kind}`}
                          style={{
                            background: actIdx % 2 === 0 ? "transparent" : "#1e293b15",
                          }}
                        >
                          {actIdx === 0 && (
                            <td
                              rowSpan={rowSpanCount}
                              style={{
                                verticalAlign: "top",
                                background: "#0c1322",
                                borderRight: "2px solid #334155",
                                padding: "12px 10px",
                              }}
                            >
                              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                                <span style={{ fontSize: 14, fontWeight: 700, color: sInfo.color }}>
                                  {sInfo.label}
                                </span>
                                <span style={{ fontSize: 10, color: "#94a3b8" }}>{g.controller}</span>
                                <div
                                  style={{
                                    marginTop: 8,
                                    fontSize: 11,
                                    color: "#f8fafc",
                                    background: "#1e293b",
                                    padding: "4px 6px",
                                    borderRadius: 4,
                                    border: "1px solid #334155",
                                  }}
                                >
                                  <div>
                                    Total: <b>{g.totalActions}</b>
                                  </div>
                                  <div>
                                    Daño: <b>{g.totalDamage.toFixed(1)}</b>
                                  </div>
                                  <div>
                                    Bajas: <b>{g.totalKills.toFixed(0)}</b>
                                  </div>
                                </div>
                              </div>
                            </td>
                          )}
                          <td>
                            <b
                              style={{
                                color: isSpecial ? "#f472b6" : isRanged ? "#fb923c" : act.action_kind === "MOVE" ? "#60a5fa" : undefined,
                              }}
                            >
                              {act.action_kind}
                            </b>
                            {isSpecial && (
                              <span
                                style={{
                                  marginLeft: 6,
                                  fontSize: 9,
                                  padding: "1px 4px",
                                  borderRadius: 3,
                                  background: "#831843",
                                  color: "#fbcfe8",
                                  fontWeight: 700,
                                }}
                              >
                                ESPECIAL
                              </span>
                            )}
                          </td>
                          <td style={{ textAlign: "right", fontWeight: act.count > 0 ? 600 : 400, color: act.count === 0 ? "#64748b" : "#f8fafc" }}>
                            {act.count}
                          </td>
                          <td style={{ textAlign: "right", color: act.count === 0 ? "#64748b" : "#e2e8f0" }}>
                            {pct(act.count, g.totalActions)}
                          </td>
                          <td style={{ textAlign: "right", color: act.damage > 0 ? "#f87171" : "#64748b" }}>
                            {act.damage.toFixed(2)}
                          </td>
                          <td style={{ textAlign: "right", color: act.damage > 0 ? "#f87171" : "#64748b" }}>
                            {pct(act.damage, g.totalDamage)}
                          </td>
                          <td style={{ textAlign: "right", color: act.kills > 0 ? "#ef4444" : "#64748b", fontWeight: act.kills > 0 ? 700 : 400 }}>
                            {act.kills.toFixed(0)}
                          </td>
                          <td style={{ textAlign: "right", color: act.kills > 0 ? "#ef4444" : "#64748b" }}>
                            {pct(act.kills, g.totalKills)}
                          </td>
                        </tr>
                      );
                    })}

                    {/* Subtotal row for this Bando */}
                    <tr style={{ background: "#111c30", fontWeight: "bold", borderTop: "1px solid #334155", borderBottom: "2px solid #334155" }}>
                      <td style={{ color: sInfo.color }}>Subtotal {sInfo.label}</td>
                      <td style={{ textAlign: "right", color: "#f8fafc" }}>{g.totalActions}</td>
                      <td style={{ textAlign: "right", color: "#34d399" }}>100.0%</td>
                      <td style={{ textAlign: "right", color: "#f87171" }}>{g.totalDamage.toFixed(2)}</td>
                      <td style={{ textAlign: "right", color: "#f87171" }}>100.0%</td>
                      <td style={{ textAlign: "right", color: "#ef4444" }}>{g.totalKills.toFixed(0)}</td>
                      <td style={{ textAlign: "right", color: "#ef4444" }}>100.0%</td>
                    </tr>
                  </Fragment>
                );
              })
            )}
          </tbody>
          {sideActionGroups.length > 0 && (
            <tfoot>
              <tr style={{ background: "#0a0f1d", fontWeight: "bold", borderTop: "2px solid #38bdf8" }}>
                <td colSpan={2} style={{ color: "#38bdf8", fontSize: 13 }}>
                  Total Global Acumulado (Todos los Bandos)
                </td>
                <td style={{ textAlign: "right", color: "#f8fafc", fontSize: 13 }}>{globalTotals.actions}</td>
                <td style={{ textAlign: "right", color: "#34d399" }}>100.0%</td>
                <td style={{ textAlign: "right", color: "#f87171", fontSize: 13 }}>{globalTotals.damage.toFixed(2)}</td>
                <td style={{ textAlign: "right", color: "#f87171" }}>100.0%</td>
                <td style={{ textAlign: "right", color: "#ef4444", fontSize: 13 }}>{globalTotals.kills.toFixed(0)}</td>
                <td style={{ textAlign: "right", color: "#ef4444" }}>100.0%</td>
              </tr>
            </tfoot>
          )}
        </table>
      </div>

      {/* TABLA B: MATRIZ BILATERAL TÁCTICA DE ENFRENTAMIENTOS (COMO EN LA SEGUNDA IMAGEN) */}
      <h4 style={{ margin: "18px 0 6px 0", color: "#f8fafc" }}>
        Tabla B: Matriz Bilateral Táctica de Enfrentamientos con Fila de Agregado por Bando (Estructura Unificada)
      </h4>
      <div className="muted" style={{ marginBottom: 8, fontSize: 12 }}>
        Desglose sistemático agrupado por Escenario y Bando bilateral para todos los enfrentamientos del benchmark. Incluye una fila de <b>Agregado Total</b> para cada bando con la correlación de volumen táctico, mezcla de acciones y sobreescrituras de la red neuronal.
      </div>

      <div style={{ overflowX: "auto", border: "1px solid #334155", borderRadius: 6, marginBottom: 20 }}>
        <table style={{ margin: 0, minWidth: 1050 }}>
          <thead>
            <tr style={{ fontSize: 11 }}>
              <th colSpan={4} style={{ textAlign: "center", background: "#0c1527", borderRight: "2px solid #334155", padding: "6px 8px" }}>
                ENFRENTAMIENTO
              </th>
              <th colSpan={6} style={{ textAlign: "center", background: "#0f2027", borderRight: "2px solid #334155", padding: "6px 8px" }}>
                COMPOSICIÓN TÁCTICA & EJECUCIÓN
              </th>
              <th colSpan={3} style={{ textAlign: "center", background: "#172554", padding: "6px 8px" }}>
                DESGASTE & OVERRIDE
              </th>
            </tr>
            <tr style={{ fontSize: 11 }}>
              <th style={{ background: "#0f172a" }}>Escenario</th>
              <th style={{ background: "#0f172a" }}>Bando</th>
              <th style={{ background: "#0f172a" }}>Oponente</th>
              <th style={{ background: "#0f172a", borderRight: "2px solid #334155" }}>Perfil / Enfrentamiento</th>
              <th style={{ background: "#132328" }}>Eps</th>
              <th style={{ background: "#132328" }}>Total Acciones</th>
              <th style={{ background: "#132328" }}>% Move</th>
              <th style={{ background: "#132328" }}>% Wait</th>
              <th style={{ background: "#132328" }}>% Fuego / Ranged</th>
              <th style={{ background: "#132328", borderRight: "2px solid #334155" }}>% Asalto / Esp.</th>
              <th style={{ background: "#1e293b" }}>MCTS Override</th>
              <th style={{ background: "#1e293b" }}>Daño Total</th>
              <th style={{ background: "#1e293b" }}>Bajas</th>
            </tr>
          </thead>
          <tbody>
            {!bilateralMatchupRows.length ? (
              <tr>
                <td colSpan={13} className="muted">
                  No hay filas de enfrentamiento disponibles.
                </td>
              </tr>
            ) : (
              bilateralMatchupRows.map((r, idx) => {
                const sInfo = getSideDisplay(r.side);
                const oppInfo = getSideDisplay(r.oppSide);
                const isAgg = r.isAggregateRow;

                return (
                  <tr
                    key={`${r.scenarioId}-${r.matchupProfile}-${r.side}-${idx}`}
                    style={{
                      background: isAgg ? "#1e293b90" : undefined,
                      borderTop: isAgg ? "1px solid #38bdf840" : undefined,
                    }}
                  >
                    {r.isFirstInGroup && (
                      <td
                        rowSpan={r.groupSize}
                        style={{
                          background: "#0a0f1d",
                          fontWeight: 700,
                          color: "#94a3b8",
                          verticalAlign: "middle",
                          borderRight: "1px solid #1e293b",
                          fontSize: 12,
                        }}
                      >
                        {r.scenarioId}
                      </td>
                    )}
                    {r.isFirstInSideGroup && (
                      <td
                        rowSpan={r.sideGroupSize}
                        style={{
                          background: "#0c1322",
                          verticalAlign: "middle",
                          borderRight: "1px solid #1e293b",
                          fontWeight: 700,
                        }}
                      >
                        <span style={{ color: sInfo.color, fontSize: 13 }}>{sInfo.label}</span>
                        <div style={{ fontSize: 10, color: "#64748b", fontWeight: 500 }}>{r.ownController}</div>
                      </td>
                    )}
                    <td>
                      {isAgg ? (
                        <span style={{ color: "#94a3b8", fontStyle: "italic" }}>{r.oppSide}</span>
                      ) : (
                        <>
                          <span style={{ color: oppInfo.color, fontWeight: 600 }}>{oppInfo.label}</span>
                          <span style={{ fontSize: 10, color: "#64748b", marginLeft: 4 }}>({r.oppController})</span>
                        </>
                      )}
                    </td>
                    <td style={{ borderRight: "2px solid #334155" }}>
                      {isAgg ? (
                        <span style={{ color: "#34d399", fontWeight: 700, display: "flex", alignItems: "center", gap: 5 }}>
                          <span>⚡</span> {r.matchupProfile}
                        </span>
                      ) : (
                        <b>{r.matchupProfile}</b>
                      )}
                    </td>
                    <td>{r.episodes}</td>
                    <td style={{ fontWeight: 700, color: isAgg ? "#38bdf8" : "#f8fafc" }}>{r.totalActions}</td>
                    <td>{r.movePct}</td>
                    <td>{r.waitPct}</td>
                    <td style={{ color: "#fdba74" }}>{r.rangedPct}</td>
                    <td style={{ borderRight: "2px solid #334155", color: "#f472b6" }}>{r.assaultPct}</td>
                    <td style={{ color: r.mctsOverwritten > 0 ? "#38bdf8" : undefined, fontWeight: isAgg ? 700 : 400 }}>
                      {r.mctsOverridePct} ({r.mctsOverwritten})
                    </td>
                    <td style={{ color: r.damageTotal > 0 ? "#f87171" : undefined, fontWeight: isAgg ? 700 : 600 }}>
                      {r.damageTotal.toFixed(1)}
                    </td>
                    <td style={{ color: r.killsTotal > 0 ? "#ef4444" : undefined, fontWeight: isAgg ? 800 : 700 }}>
                      {r.killsTotal.toFixed(0)}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* TABLA C: PROPIEDAD DE LA DECISIÓN (POLICY VS MCTS OVERWRITE) */}
      <h4 style={{ margin: "18px 0 6px 0", color: "#f8fafc" }}>
        Tabla C: Propiedad de la Decisión & Sobreescritura MCTS por Bando {isAggregated ? "(Agregado Total)" : `(${selectedMatchup})`}
      </h4>
      <div className="muted" style={{ marginBottom: 8, fontSize: 12 }}>
        Telemetría canónica de alineamiento entre la política directa de la red neuronal y las decisiones finales tras la búsqueda MCTS.
      </div>
      <div style={{ overflowX: "auto", border: "1px solid #334155", borderRadius: 6, marginBottom: 20 }}>
        <table style={{ margin: 0 }}>
          <thead>
            <tr>
              <th style={{ background: "#0f172a" }}>Bando</th>
              <th style={{ background: "#0f172a" }}>Total Decisiones</th>
              <th style={{ background: "#0f172a" }}>Política Mantenida</th>
              <th style={{ background: "#0f172a" }}>Sobreescrito por MCTS</th>
              <th style={{ background: "#0f172a" }}>override_signal_rows</th>
              <th style={{ background: "#0f172a" }}>unknown_override_rows</th>
            </tr>
          </thead>
          <tbody>
            {!ownRows.length ? (
              <tr>
                <td colSpan={6} className="muted">
                  No hay filas de propiedad registradas.
                </td>
              </tr>
            ) : (
              ownRows.map((r) => {
                const sInfo = getSideDisplay(r.side);
                return (
                  <tr key={r.side}>
                    <td>
                      <b style={{ color: sInfo.color }}>{sInfo.label}</b>
                    </td>
                    <td style={{ fontWeight: 600 }}>{r.rows}</td>
                    <td style={{ color: "#34d399" }}>
                      {r.policy_kept} ({pct(r.policy_kept, r.rows)})
                    </td>
                    <td style={{ color: r.overwritten > 0 ? "#38bdf8" : undefined, fontWeight: r.overwritten > 0 ? 600 : 400 }}>
                      {r.overwritten} ({pct(r.overwritten, r.rows)})
                    </td>
                    <td>{r.override_signal_rows}</td>
                    <td>{r.unknown_override_rows}</td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* TABLA D: TOP 25 ACCIONES ESPECÍFICAS EJECUTADAS */}
      <h4 style={{ margin: "18px 0 6px 0", color: "#f8fafc" }}>
        Tabla D: Top 25 Acciones Específicas Ejecutadas {isAggregated ? "(Agregado Total)" : `(${selectedMatchup})`}
      </h4>
      <div className="muted" style={{ marginBottom: 8, fontSize: 12 }}>
        Acciones individuales más frecuentes con coordenadas exactas, daño acumulado y bajas confirmadas.
      </div>
      <div style={{ overflowX: "auto", border: "1px solid #334155", borderRadius: 6 }}>
        <table style={{ margin: 0 }}>
          <thead>
            <tr>
              <th style={{ background: "#0f172a" }}>action_id</th>
              <th style={{ background: "#0f172a" }}>Tipo de Acción</th>
              <th style={{ background: "#0f172a" }}>Bando</th>
              <th style={{ background: "#0f172a" }}>Frecuencia (Count)</th>
              <th style={{ background: "#0f172a" }}>Daño Acumulado</th>
              <th style={{ background: "#0f172a" }}>Bajas Totales</th>
            </tr>
          </thead>
          <tbody>
            {!topRows.length ? (
              <tr>
                <td colSpan={6} className="muted">
                  No hay acciones destacadas registradas.
                </td>
              </tr>
            ) : (
              topRows.map((r, i) => {
                const sInfo = getSideDisplay(r.side);
                return (
                  <tr key={`${r.action_id}-${i}`}>
                    <td>
                      <code>{r.action_id}</code>
                    </td>
                    <td>
                      <b
                        style={{
                          color: ["EXPLOSIVE_CHARGE", "MINE_DETECTION", "ASSAULT"].includes(r.action_kind)
                            ? "#f472b6"
                            : ["RANGED_DIRECT", "RANGED_INDIRECT"].includes(r.action_kind)
                            ? "#fb923c"
                            : undefined,
                        }}
                      >
                        {r.action_kind}
                      </b>
                    </td>
                    <td>
                      <span style={{ color: sInfo.color, fontWeight: 600 }}>{sInfo.label}</span>
                    </td>
                    <td style={{ fontWeight: 600 }}>{r.count}</td>
                    <td style={{ color: r.damage > 0 ? "#f87171" : undefined }}>{r.damage.toFixed(2)}</td>
                    <td style={{ color: r.kills > 0 ? "#ef4444" : undefined, fontWeight: r.kills > 0 ? 700 : 400 }}>
                      {r.kills.toFixed(0)}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
