import { useEffect, useMemo, useState } from "react";
import {
  deleteModelExperiment,
  fetchModel,
  fetchModelEvals,
  fetchReplayLog,
  fetchReplayMeta,
  fetchReplaySteps,
  fetchTrainSummary,
} from "../api";
import { calculateDurationSeconds, formatDuration, formatDurationDetailed, formatLocalDate } from "../dateUtils";
import type { Dict, EvalResultRow, EvalRow, ModelPayload, ReplayMetaEpisode, ReplayMetaPayload, TrainRow } from "../types";
import { TrainDetailTab } from "./model-tabs/TrainDetailTab";
import { TrainHeadDiagnosticsTab } from "./model-tabs/TrainHeadDiagnosticsTab";
import { ObjectiveRewardConfigTab } from "./model-tabs/ObjectiveRewardConfigTab";
import { VpSummaryTab } from "./model-tabs/VpSummaryTab";
import { HeadDiagnosticsTab } from "./model-tabs/HeadDiagnosticsTab";
import { EvalMetricsTab } from "./model-tabs/EvalMetricsTab";
import { EvalDecisionsTab } from "./model-tabs/EvalDecisionsTab";
import { MatchReplayTab } from "./model-tabs/MatchReplayTab";
import { ReplayTab } from "./model-tabs/ReplayTab";
import { MetaTab } from "./model-tabs/MetaTab";
import { NetworkTopologyTab } from "./model-tabs/NetworkTopologyTab";

type SectionKey = "topology" | "train" | "eval" | "replay" | "meta";

type TrainTabKey = "train-detail" | "train-head-diagnostics" | "objective-reward-config";
type EvalTabKey = "matchups-vp" | "benchmark-matrix" | "tactical-decisions" | "xai-heads";
type ReplayTabKey = "tactical-map" | "event-log";
type MetaTabKey = "overview";

function rowScenarioIds(row: Dict): string[] {
  const ids = Array.isArray(row.scenario_ids) ? row.scenario_ids : [];
  const clean = ids.map((x) => String(x || "").trim()).filter((x) => x && !x.startsWith("multi:"));
  if (clean.length) return Array.from(new Set(clean));
  const sid = String(row.scenario_id || "").trim();
  return sid && !sid.startsWith("multi:") ? [sid] : [];
}

export function ModelPage() {
  const qs = new URLSearchParams(window.location.search);
  const engine = qs.get("engine") || "";
  const modelId = qs.get("model") || qs.get("model_id") || "";

  const [model, setModel] = useState<ModelPayload | null>(null);
  const [selectedScenario, setSelectedScenario] = useState("__all__");
  const [selectedTrainRun, setSelectedTrainRun] = useState("");
  const [trainSummary, setTrainSummary] = useState<Dict | null>(null);
  const [trainSummaryByRun, setTrainSummaryByRun] = useState<Record<string, Dict>>({});

  // Navegación de secciones
  const [section, setSection] = useState<SectionKey>("eval");
  const [topologyTab, setTopologyTab] = useState<"diagram" | "channel-attribution" | "macro-planner">("diagram");
  const [trainTab, setTrainTab] = useState<TrainTabKey>("train-detail");
  const [evalTab, setEvalTab] = useState<EvalTabKey>("matchups-vp");
  const [replayTab, setReplayTab] = useState<ReplayTabKey>("tactical-map");
  const [metaTab, setMetaTab] = useState<MetaTabKey>("overview");

  const [evalRowsByKey, setEvalRowsByKey] = useState<Record<string, EvalRow[]>>({});
  const [selectedEvalId, setSelectedEvalId] = useState("");
  const [loadingEvals, setLoadingEvals] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  const [replayMeta, setReplayMeta] = useState<ReplayMetaPayload | null>(null);
  const [replaySteps, setReplaySteps] = useState<Dict | null>(null);
  const [replayLog, setReplayLog] = useState<Dict | null>(null);
  const [selectedEpisodeId, setSelectedEpisodeId] = useState("episode_0");
  const [selectedStepIndex, setSelectedStepIndex] = useState(0);
  const [filterScenario, setFilterScenario] = useState<string>("all");
  const [filterMatchup, setFilterMatchup] = useState<string>("all");
  const [filterWinner, setFilterWinner] = useState<string>("all");
  const [searchSeedOrId, setSearchSeedOrId] = useState<string>("");

  const handleRefresh = async () => {
    setEvalRowsByKey({});
    setTrainSummaryByRun({});
    setRefreshKey((k) => k + 1);
    try {
      const m = await fetchModel(engine, modelId);
      setModel(m);
    } catch {
      // ignore
    }
  };

  // 1. Cargar modelo al iniciar
  useEffect(() => {
    async function run() {
      const m = await fetchModel(engine, modelId);
      setModel(m);
      const trains = Array.isArray(m.train_history) ? (m.train_history as TrainRow[]) : [];
      const preferredRun = m.initial_train_run_id
        ? String(m.initial_train_run_id)
        : trains.find((t) => Number(t.evals_count ?? 0) > 0)?.run_id
        ? String(trains.find((t) => Number(t.evals_count ?? 0) > 0)!.run_id)
        : trains[0]?.run_id
        ? String(trains[0].run_id)
        : "";
      if (preferredRun) {
        setSelectedTrainRun(preferredRun);
      }
    }
    void run();
  }, [engine, modelId, refreshKey]);

  // 2. Cargar train summary al cambiar selectedTrainRun (con caché cliente en memoria)
  useEffect(() => {
    if (!selectedTrainRun) return;
    if (trainSummaryByRun[selectedTrainRun]) {
      setTrainSummary(trainSummaryByRun[selectedTrainRun]);
      return;
    }
    let cancelled = false;
    async function run() {
      try {
        const s = await fetchTrainSummary(selectedTrainRun);
        if (cancelled) return;
        setTrainSummary(s);
        setTrainSummaryByRun((prev) => ({ ...prev, [selectedTrainRun]: s }));
      } catch {
        if (!cancelled) setTrainSummary(null);
      }
    }
    void run();
    return () => {
      cancelled = true;
    };
  }, [selectedTrainRun, trainSummaryByRun]);

  // 3. Cargar eval rows al cambiar train_run o scenario (con caché en memoria)
  useEffect(() => {
    if (!selectedTrainRun) return;
    const key = `${selectedTrainRun}::${selectedScenario}`;
    if (evalRowsByKey[key] && evalRowsByKey[key].length > 0) return;

    let cancelled = false;
    setLoadingEvals(true);
    async function run() {
      try {
        const payload = await fetchModelEvals(engine, modelId, selectedTrainRun, selectedScenario);
        if (cancelled) return;
        const rows = Array.isArray(payload.rows) ? (payload.rows as EvalRow[]) : [];
        setEvalRowsByKey((prev) => ({ ...prev, [key]: rows }));
      } catch {
        // ignore
      } finally {
        if (!cancelled) setLoadingEvals(false);
      }
    }
    void run();
    return () => {
      cancelled = true;
    };
  }, [engine, modelId, selectedTrainRun, selectedScenario, refreshKey]);

  const trains = useMemo(
    () => (Array.isArray(model?.train_history) ? (model!.train_history as TrainRow[]) : []),
    [model]
  );

  const totalModelTrainDurationSec = useMemo(() => {
    let total = 0;
    for (const t of trains) {
      let dur = typeof t.duration_seconds === "number" ? t.duration_seconds : null;
      if (dur === null || dur === undefined) {
        dur = calculateDurationSeconds(
          t.phase_started_at as string | undefined,
          t.phase_finished_at as string | undefined
        );
      }
      if (dur !== null && dur >= 0) {
        total += dur;
      }
    }
    return total;
  }, [trains]);

  const selectedTrainRow = useMemo(
    () => trains.find((t) => String(t.run_id || "") === selectedTrainRun) || trains[0] || null,
    [trains, selectedTrainRun]
  );

  const scenarios = useMemo(() => {
    const out = new Set<string>();
    const seen = Array.isArray(model?.scenarios_seen) ? model!.scenarios_seen : [];
    for (const s of seen) {
      let v = String(s || "").trim();
      if (!v) continue;
      if (v.startsWith("multi:")) v = v.substring(6).trim();
      const parts = v.includes("|") ? v.split("|").map((p) => p.trim()).filter(Boolean) : [v];
      for (const p of parts) if (p) out.add(p);
    }
    for (const tr of trains) for (const sid of rowScenarioIds(tr)) out.add(sid);
    return Array.from(out).sort();
  }, [model, trains]);

  const evalRows = useMemo(
    () => evalRowsByKey[`${selectedTrainRun}::${selectedScenario}`] || [],
    [evalRowsByKey, selectedTrainRun, selectedScenario]
  );

  useEffect(() => {
    if (!evalRows.length) {
      setSelectedEvalId("");
      return;
    }
    if (!selectedEvalId || !evalRows.some((r) => String(r.eval_id || "") === selectedEvalId)) {
      setSelectedEvalId(String(evalRows[0].eval_id || ""));
    }
  }, [evalRows, selectedEvalId]);

  const selectedEval = useMemo(
    () => evalRows.find((r) => String(r.eval_id || "") === selectedEvalId) || evalRows[0] || null,
    [evalRows, selectedEvalId]
  );
  const selectedEvalSourcePath = String((selectedEval || {}).source_path || "").trim();

  const mainResult = useMemo(() => {
    for (const ev of [selectedEval].filter(Boolean) as EvalRow[]) {
      const results = Array.isArray(ev.results) ? (ev.results as EvalResultRow[]) : [];
      if (results.length) return results[0];
    }
    return null;
  }, [selectedEval]);

  // Load Replay metadata on demand (ONLY if in Replay tab)
  const isReplayActive = section === "replay";
  useEffect(() => {
    if (!isReplayActive || !selectedEvalSourcePath) return;

    let cancelled = false;
    async function run() {
      setReplayMeta(null);
      setReplaySteps(null);
      setReplayLog(null);
      try {
        const meta = await fetchReplayMeta(selectedEvalSourcePath);
        if (cancelled) return;
        setReplayMeta(meta);
        const eps = Array.isArray(meta.episodes_meta) ? meta.episodes_meta : [];
        const episodeId = String((eps[0] || {}).episode_id || "episode_0");
        let epIdx = 0;
        if (episodeId.startsWith("episode_")) {
          const parsed = parseInt(episodeId.split("_")[1], 10);
          if (!isNaN(parsed)) epIdx = parsed;
        }
        const [steps, log] = await Promise.all([
          fetchReplaySteps(selectedEvalSourcePath, episodeId, 0, 1999),
          fetchReplayLog(selectedEvalSourcePath, epIdx, 2000, true),
        ]);
        if (cancelled) return;
        setReplaySteps(steps);
        setReplayLog(log);
        setSelectedStepIndex(0);
      } catch {
        if (cancelled) return;
        setReplayMeta(null);
        setReplaySteps(null);
        setReplayLog(null);
      }
    }
    void run();
    return () => {
      cancelled = true;
    };
  }, [isReplayActive, selectedEvalSourcePath]);

  // Load steps and log when episode changes
  useEffect(() => {
    async function run() {
      if (!selectedEvalSourcePath || !selectedEpisodeId) return;
      try {
        let epIdx = 0;
        if (selectedEpisodeId.startsWith("episode_")) {
          const parsed = parseInt(selectedEpisodeId.split("_")[1], 10);
          if (!isNaN(parsed)) epIdx = parsed;
        }
        const [steps, log] = await Promise.all([
          fetchReplaySteps(selectedEvalSourcePath, selectedEpisodeId, 0, 1999),
          fetchReplayLog(selectedEvalSourcePath, epIdx, 2000, true),
        ]);
        setReplaySteps(steps);
        setReplayLog(log);
        setSelectedStepIndex(0);
      } catch {
        // episode steps not available
      }
    }
    void run();
  }, [selectedEvalSourcePath, selectedEpisodeId]);

  const rawEpisodesMeta = useMemo(
    () => (Array.isArray(replayMeta?.episodes_meta) ? (replayMeta!.episodes_meta! as ReplayMetaEpisode[]) : []),
    [replayMeta]
  );

  const getEpisodeMatchup = (ep: ReplayMetaEpisode): string => {
    // 1. Check controller_by_side mapping directly if available
    const ctrl = ep.controller_by_side as Record<string, string> | undefined;
    if (ctrl && typeof ctrl === "object") {
      const atkSide = (ep as any).attacker_side || "US";
      const sidesInCtrl = Object.keys(ctrl);
      const defSide =
        (ep as any).defender_side ||
        sidesInCtrl.find((s) => s.toUpperCase() !== atkSide.toUpperCase()) ||
        "IT";
      const atkCtrl = String(ctrl[atkSide] || ctrl.US || "").toLowerCase();
      const defCtrl = String(ctrl[defSide] || "").toLowerCase();
      const atkIsAi = atkCtrl.includes("efficientzero") || atkCtrl.includes("ezv2") || atkCtrl.includes("mcts");
      const defIsAi = defCtrl.includes("efficientzero") || defCtrl.includes("ezv2") || defCtrl.includes("mcts");
      const atkIsRand = atkCtrl.includes("random");
      const defIsRand = defCtrl.includes("random");
      if (atkIsAi && defIsAi) return "selfplay";
      if (atkIsAi && defIsRand) return "vs_random_atk";
      if (defIsAi && atkIsRand) return "vs_random_def";
    }

    // 2. Check canonical matchup string
    const rawMatchup = String(ep.matchup || "").toLowerCase();
    if (rawMatchup) {
      if (rawMatchup === "selfplay" || rawMatchup === "ezv2_selfplay") return "selfplay";
      if (rawMatchup === "vs_random_atk" || rawMatchup === "ezv2_vs_random_atk" || rawMatchup === "mcts_vs_random_atk") return "vs_random_atk";
      if (rawMatchup === "vs_random_def" || rawMatchup === "ezv2_vs_random_def" || rawMatchup === "mcts_vs_random_def") return "vs_random_def";
      if (rawMatchup.includes("random")) return "vs_random";
    }

    // 3. Fallback to parsing agent_name (ezv2_vs_random_US -> Agent is US Attacker vs Random IT Defender)
    const an = String(ep.agent_name || "").toLowerCase();
    if (an.includes("stub") || an === "selfplay" || an.includes("selfplay")) return "selfplay";
    if (an.includes("random_us") || (an.includes("side_b") && an.includes("random"))) return "vs_random_atk";
    if (an.includes("random_it") || an.includes("random_ge") || (an.includes("side_a") && an.includes("random"))) return "vs_random_def";
    if (an.includes("random")) return "vs_random";
    return "selfplay";
  };

  const filteredEpisodes = useMemo(() => {
    return rawEpisodesMeta.filter((ep) => {
      // 1. Scenario Filter
      if (filterScenario !== "all") {
        const sid = String(ep.scenario_id || "").toLowerCase();
        if (filterScenario === "mettete" && !sid.includes("mettete")) return false;
        if (filterScenario === "cittadina" && !sid.includes("cittadina")) return false;
      }

      // 2. Matchup Filter
      if (filterMatchup !== "all") {
        const m = getEpisodeMatchup(ep);
        if (filterMatchup === "selfplay" && m !== "selfplay") return false;
        if (filterMatchup === "vs_random" && !m.includes("random")) return false;
        if (filterMatchup === "vs_random_def" && m !== "vs_random_def") return false;
        if (filterMatchup === "vs_random_atk" && m !== "vs_random_atk") return false;
      }

      // 3. Winner Filter
      if (filterWinner !== "all") {
        const w = String(ep.winner || "").toUpperCase();
        const m = getEpisodeMatchup(ep);
        if (filterWinner === "US" && w !== "US") return false;
        if (filterWinner === "GE" && w !== "GE") return false;
        if (filterWinner === "IT" && w !== "IT") return false;
        if (filterWinner === "EJE" && w !== "GE" && w !== "IT") return false;
        if (filterWinner === "EMPATE" && w !== "EMPATE" && !w.includes("DRAW")) return false;
        if (filterWinner === "EZV2_WIN" || filterWinner === "MCTS_WIN") {
          if (m === "selfplay") return true;
          if (m === "vs_random_atk") return w === "US";
          if (m === "vs_random_def") return w === "GE" || w === "IT";
          return w !== "" && w !== "EMPATE" && !w.includes("DRAW");
        }
        if (filterWinner === "EZV2_LOSS" || filterWinner === "MCTS_LOSS") {
          if (m === "selfplay") return false;
          if (m === "vs_random_atk") return w === "GE" || w === "IT";
          if (m === "vs_random_def") return w === "US";
          return false;
        }
      }

      // 4. Text/Seed Search
      if (searchSeedOrId.trim()) {
        const query = searchSeedOrId.trim().toLowerCase();
        const epId = String(ep.episode_id || "").toLowerCase();
        const seedStr = ep.seed !== undefined ? String(ep.seed) : "";
        if (!epId.includes(query) && !seedStr.includes(query) && !`seed ${seedStr}`.includes(query)) {
          return false;
        }
      }

      return true;
    });
  }, [rawEpisodesMeta, filterScenario, filterMatchup, filterWinner, searchSeedOrId]);

  useEffect(() => {
    if (filteredEpisodes.length > 0) {
      const exists = filteredEpisodes.some((ep) => ep.episode_id === selectedEpisodeId);
      if (!exists) {
        setSelectedEpisodeId(String(filteredEpisodes[0].episode_id));
      }
    }
  }, [filteredEpisodes, selectedEpisodeId]);

  const getEpisodeOptionLabel = (ep: ReplayMetaEpisode, index: number) => {
    const id = String(ep.episode_id || `episode_${index}`);
    const winner = ep.winner ? String(ep.winner).toUpperCase() : "";
    const winBadge =
      winner === "GE"
        ? "🇩🇪 GE Won"
        : winner === "IT"
        ? "🇮🇹 IT Won"
        : winner === "US"
        ? "🇺🇸 US Won"
        : winner === "EMPATE" || winner.includes("DRAW")
        ? "🤝 Draw"
        : "";
    const scenBadge = ep.scenario_id?.includes("mettete")
      ? "🌊 Mettete"
      : ep.scenario_id?.includes("cittadina")
      ? "🏙️ Cittadina"
      : "";
    let matchupBadge = "";
    const ctrl = ep.controller_by_side as Record<string, string> | undefined;
    const atkSide = (ep as any).attacker_side || "US";
    const sidesInCtrl = ctrl && typeof ctrl === "object" ? Object.keys(ctrl) : [];
    const defSide =
      (ep as any).defender_side ||
      sidesInCtrl.find((s) => s.toUpperCase() !== atkSide.toUpperCase()) ||
      (ep.scenario_id?.includes("cittadina") || ep.scenario_id?.includes("mettete") ? "IT" : "IT");

    if (ctrl && typeof ctrl === "object" && sidesInCtrl.length > 0) {
      const atkCtrl = String(ctrl[atkSide] || ctrl.US || "").toLowerCase();
      const defCtrl = String(ctrl[defSide] || "").toLowerCase();
      const atkIsAi = atkCtrl.includes("efficientzero") || atkCtrl.includes("ezv2") || atkCtrl.includes("mcts");
      const defIsAi = defCtrl.includes("efficientzero") || defCtrl.includes("ezv2") || defCtrl.includes("mcts");
      const atkIsRand = atkCtrl.includes("random");
      const defIsRand = defCtrl.includes("random");
      if (atkIsAi && defIsAi) {
        matchupBadge = `⚔️ EZv2 Self-Play (${defSide} Def vs ${atkSide} Atk)`;
      } else if (atkIsAi && defIsRand) {
        matchupBadge = `⚔️ EZv2 (${atkSide} Atk) vs Rand (${defSide} Def)`;
      } else if (defIsAi && atkIsRand) {
        matchupBadge = `🛡️ EZv2 (${defSide} Def) vs Rand (${atkSide} Atk)`;
      }
    }
    if (!matchupBadge) {
      const m = getEpisodeMatchup(ep);
      matchupBadge =
        m === "selfplay"
          ? `⚔️ EZv2 Self-Play (${defSide} Def vs ${atkSide} Atk)`
          : m === "vs_random_def"
          ? `🛡️ EZv2 (${defSide} Def) vs Rand (${atkSide} Atk)`
          : m === "vs_random_atk"
          ? `⚔️ EZv2 (${atkSide} Atk) vs Rand (${defSide} Def)`
          : "🎯 vs Random";
    }
    const seedText = ep.seed !== undefined ? `Seed ${ep.seed}` : "";
    const stepCount = ep.rows || ep.steps_count || 0;

    const parts = [
      id,
      winBadge,
      scenBadge,
      matchupBadge,
      seedText,
      stepCount ? `${stepCount}p` : "",
    ].filter(Boolean);

    return parts.join(" | ");
  };

  return (
    <div className="wrap">
      {/* Unified Compact Header: Title, Actions and Metadata */}
      <header
        className="panel"
        style={{
          padding: "6px 12px",
          display: "flex",
          flexDirection: "column",
          gap: 6,
          flexShrink: 0,
          background: "linear-gradient(180deg, #162032 0%, #0f172a 100%)",
          border: "1px solid #334155",
        }}
      >
        {/* Fila 1: Título y Acciones principales */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0, flex: 1 }}>
            <span style={{ fontSize: 11, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.5px" }}>
              Model Detail
            </span>
            <span style={{ color: "#475569" }}>|</span>
            <h1
              style={{
                margin: 0,
                fontSize: 14,
                fontWeight: 700,
                color: "#f8fafc",
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
              title={String(model?.model_id || modelId || "")}
            >
              {String(model?.model_id || modelId || "")}
            </h1>
          </div>

          <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
            <button
              onClick={() => window.open("/", "_self")}
              style={{ padding: "4px 8px", fontSize: 11, borderRadius: 4, background: "#1e293b", border: "1px solid #475569" }}
            >
              Back to Catalog
            </button>
            <button
              onClick={() => window.open("/docs/", "_blank")}
              style={{
                background: "#0284c7",
                color: "#ffffff",
                border: "none",
                borderRadius: 4,
                padding: "4px 8px",
                fontSize: 11,
                fontWeight: 700,
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: 4,
              }}
              title="Open Interactive Technical Documentation Hub"
            >
              <span>📚</span> Documentation
            </button>
            <button
              onClick={() => window.open("http://127.0.0.1:8780", "_blank")}
              style={{
                background: "#065f46",
                color: "#6ee7b7",
                border: "1px solid #10b981",
                borderRadius: 4,
                padding: "4px 8px",
                fontSize: 11,
                fontWeight: 700,
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: 4,
              }}
              title="Open Tactical Unit & Formation Catalog Editor (Port 8780)"
            >
              <span>🎖️</span> Unit Editor (8780)
            </button>
            <button
              onClick={() => window.open("http://127.0.0.1:8001/docs", "_blank")}
              style={{
                background: "#1e293b",
                color: "#fde047",
                border: "1px solid #eab308",
                borderRadius: 4,
                padding: "4px 8px",
                fontSize: 11,
                fontWeight: 700,
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: 4,
              }}
              title="Open FastAPI Swagger Interactive Docs (Port 8001)"
            >
              <span>⚡</span> Swagger API (8001)
            </button>
            <button
              onClick={() =>
                window.open(
                  `/elo?engine=${encodeURIComponent(String(model?.engine || engine))}&model=${encodeURIComponent(String(model?.model_id || modelId || "__all__"))}`,
                  "_blank",
                  "noopener,noreferrer"
                )
              }
              style={{ padding: "4px 8px", fontSize: 11, borderRadius: 4, background: "#1e293b", border: "1px solid #475569" }}
            >
              ELO Leaderboard
            </button>
            <button
              onClick={() => void handleRefresh()}
              style={{
                background: "#38bdf820",
                border: "1px solid #38bdf880",
                color: "#38bdf8",
                fontWeight: "bold",
                fontSize: 11,
                padding: "4px 8px",
                cursor: "pointer",
                borderRadius: 4,
              }}
              title="Refresh catalog and evaluations"
            >
              🔄 Refresh Data
            </button>
            <button
              onClick={async () => {
                const target = String(model?.model_id || modelId || "");
                if (!target) return;
                if (
                  !window.confirm(
                    `⚠️ Are you sure you want to COMPLETELY DELETE experiment "${target}" and all its files on disk?\nThis action cannot be undone.`
                  )
                ) {
                  return;
                }
                try {
                  const res = await deleteModelExperiment(target, String(model?.engine || engine));
                  alert(`✅ Experiment successfully deleted (${res.freed_mb ?? 0} MB freed).`);
                  window.location.href = "/";
                } catch (err: any) {
                  alert(`❌ Error deleting experiment: ${err.message || err}`);
                }
              }}
              style={{
                background: "#ef444420",
                border: "1px solid #ef444480",
                color: "#fca5a5",
                fontWeight: "bold",
                fontSize: 11,
                padding: "4px 8px",
                cursor: "pointer",
                borderRadius: 4,
              }}
              title="Delete this model and all its files on disk"
            >
              🗑️ Delete Experiment
            </button>
          </div>
        </div>

        {/* Row 2: Compact Metadata in a single horizontal row */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            fontSize: 11,
            flexWrap: "wrap",
            paddingTop: 4,
            borderTop: "1px solid #1e293b",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <span style={{ color: "#64748b" }}>model_id:</span>
            <code style={{ fontSize: 10, background: "#1e293b", padding: "1px 4px", borderRadius: 3, color: "#cbd5e1" }} title={String(model?.model_id || modelId || "")}>
              {String(model?.model_id || modelId || "")}
            </code>
          </div>

          <span style={{ color: "#334155" }}>•</span>

          <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <span style={{ color: "#64748b" }}>engine / algorithm:</span>
            <span style={{ color: "#38bdf8", fontWeight: 600 }}>
              {String(model?.engine || engine)} / {String((model as Dict)?.algorithm || "-")}
            </span>
          </div>

          <span style={{ color: "#334155" }}>•</span>

          <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <span style={{ color: "#64748b" }}>trains / evals count:</span>
            <span style={{ color: "#e2e8f0" }}>
              <strong style={{ color: "#a78bfa" }}>{(model as Dict)?.train_runs_count ?? trains.length}</strong> trains / <strong style={{ color: "#34d399" }}>{String((model as Dict)?.eval_history_total_count ?? evalRows.length)}</strong> evals
            </span>
          </div>

          <span style={{ color: "#334155" }}>•</span>

          <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <span style={{ color: "#64748b" }}>config_fingerprint:</span>
            <code style={{ fontSize: 10, background: "#1e293b", padding: "1px 4px", borderRadius: 3, color: "#94a3b8" }}>
              {String(model?.config_fingerprint || "-")}
            </code>
          </div>

          <span style={{ color: "#334155" }}>•</span>

          <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <span style={{ color: "#64748b" }}>⏱️ training_duration_total:</span>
            <span
              style={{ color: "#38bdf8", fontWeight: 700 }}
              title={formatDurationDetailed(totalModelTrainDurationSec || Number(trainSummary?.timing_summary?.total_elapsed_s || 0))}
            >
              {totalModelTrainDurationSec > 0
                ? formatDuration(totalModelTrainDurationSec)
                : trainSummary?.timing_summary?.total_elapsed_s
                ? formatDuration(Number(trainSummary.timing_summary.total_elapsed_s))
                : "-"}
            </span>
          </div>
        </div>
      </header>

      <div className="main">
        {/* Panel lateral: Train Runs & Scenarios */}
        <section className="panel">
          <h2>Train History</h2>
          <div className="muted" style={{ marginBottom: 4 }}>Scenario Filter</div>
          <select value={selectedScenario} onChange={(e) => setSelectedScenario(e.target.value)} style={{ width: "100%", marginBottom: 8 }}>
            <option value="__all__">all scenarios</option>
            {scenarios.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>

          <div className="muted" style={{ marginBottom: 4 }}>Train Runs ({trains.length})</div>
          <div className="list">
            {!trains.length ? (
              <div className="muted">No training runs recorded.</div>
            ) : (
              trains.map((t) => (
                <div
                  key={String(t.run_id || "")}
                  className={`item ${selectedTrainRun === String(t.run_id || "") ? "active" : ""}`}
                  onClick={() => setSelectedTrainRun(String(t.run_id || ""))}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <b>{String(t.run_id || "")}</b>
                    <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
                      {typeof t.evals_count === "number" && t.evals_count > 0 ? (
                        <span
                          style={{
                            fontSize: 10,
                            color: "#38bdf8",
                            background: "#0284c720",
                            border: "1px solid #0284c750",
                            padding: "1px 5px",
                            borderRadius: 3,
                            fontWeight: 600,
                          }}
                          title={`${t.evals_count} evaluación(es) asociada(s)`}
                        >
                          🎯 {t.evals_count} eval{t.evals_count > 1 ? "s" : ""}
                        </span>
                      ) : (
                        <span
                          style={{
                            fontSize: 10,
                            color: "#64748b",
                            background: "#33415520",
                            border: "1px solid #33415550",
                            padding: "1px 5px",
                            borderRadius: 3,
                          }}
                          title="Sin evaluaciones directas para esta fase"
                        >
                          sin evals
                        </span>
                      )}
                      {typeof t.duration_seconds === "number" && t.duration_seconds >= 0 && (
                        <span
                          style={{
                            fontSize: 11,
                            color: "#34d399",
                            fontWeight: 700,
                            background: "#10b98118",
                            border: "1px solid #10b98140",
                            padding: "1px 5px",
                            borderRadius: 3,
                          }}
                          title={formatDurationDetailed(t.duration_seconds)}
                        >
                          ⏱️ {formatDuration(t.duration_seconds)}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="muted" style={{ fontSize: 11, marginTop: 3 }}>
                    {t.curriculum_phase ? (
                      <span style={{ color: "#38bdf8", fontWeight: 600, marginRight: 4 }}>
                        [{t.curriculum_phase}]
                      </span>
                    ) : null}
                    {formatLocalDate(t.created_at_utc)} | {String(t.scenario_id || "")}
                  </div>
                </div>
              ))
            )}
          </div>
        </section>

        {/* Panel central de análisis con 2 Niveles de Pestañas */}
        <section className="panel">
          {/* Main Sections */}
          <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 8, borderBottom: "1px solid #334155", paddingBottom: 6 }}>
            <button
              className={`tabBtn ${section === "eval" ? "active" : ""}`}
              onClick={() => setSection("eval")}
              style={{ padding: "5px 12px", fontSize: 12, fontWeight: 700, color: section === "eval" ? "#38bdf8" : undefined }}
            >
              ⚔️ Evaluation & Benchmarks
            </button>
            <button
              className={`tabBtn ${section === "replay" ? "active" : ""}`}
              onClick={() => setSection("replay")}
              style={{ padding: "5px 12px", fontSize: 12, fontWeight: 700, color: section === "replay" ? "#38bdf8" : undefined }}
            >
              🎬 Forensic Replay
            </button>
            <button
              className={`tabBtn ${section === "topology" ? "active" : ""}`}
              onClick={() => setSection("topology")}
              style={{ padding: "5px 12px", fontSize: 12, fontWeight: 700, color: section === "topology" ? "#38bdf8" : undefined }}
            >
              🧠 Network Topology
            </button>
            <button
              className={`tabBtn ${section === "train" ? "active" : ""}`}
              onClick={() => setSection("train")}
              style={{ padding: "5px 12px", fontSize: 12, fontWeight: 700, color: section === "train" ? "#38bdf8" : undefined }}
            >
              📈 Training Dynamics
            </button>
            <button
              className={`tabBtn ${section === "meta" ? "active" : ""}`}
              onClick={() => setSection("meta")}
              style={{ padding: "5px 12px", fontSize: 12 }}
            >
              ℹ️ Metadata
            </button>
          </div>

          {/* Sub-tabs per section */}
          <div className="tabs" style={{ marginBottom: 10 }}>

            {section === "eval" && (
              <>
                <button className={`tabBtn ${evalTab === "matchups-vp" ? "active" : ""}`} onClick={() => setEvalTab("matchups-vp")}>
                  🏆 Matchups & VP Summary
                </button>
                <button className={`tabBtn ${evalTab === "benchmark-matrix" ? "active" : ""}`} onClick={() => setEvalTab("benchmark-matrix")}>
                  📋 Benchmark Matrix & Gates
                </button>
                <button className={`tabBtn ${evalTab === "tactical-decisions" ? "active" : ""}`} onClick={() => setEvalTab("tactical-decisions")}>
                  🎯 Tactical Decisions & Actions
                </button>
                <button className={`tabBtn ${evalTab === "xai-heads" ? "active" : ""}`} onClick={() => setEvalTab("xai-heads")}>
                  🔬 Head Diagnostics (XAI)
                </button>
              </>
            )}

            {section === "replay" && (
              <>
                <button className={`tabBtn ${replayTab === "tactical-map" ? "active" : ""}`} onClick={() => setReplayTab("tactical-map")}>
                  🗺️ Tactical Match Viewer (2D Hex)
                </button>
                <button className={`tabBtn ${replayTab === "event-log" ? "active" : ""}`} onClick={() => setReplayTab("event-log")}>
                  📜 Forensic Event Log
                </button>
              </>
            )}

            {section === "topology" && (
              <>
                <button className={`tabBtn ${topologyTab === "diagram" ? "active" : ""}`} onClick={() => setTopologyTab("diagram")}>
                  📐 Topology & Architecture
                </button>
                <button className={`tabBtn ${topologyTab === "channel-attribution" ? "active" : ""}`} onClick={() => setTopologyTab("channel-attribution")}>
                  📊 Channel Attribution (32C)
                </button>
                <button className={`tabBtn ${topologyTab === "macro-planner" ? "active" : ""}`} onClick={() => setTopologyTab("macro-planner")}>
                  ♟️ Doctrinal Macro Planner
                </button>
              </>
            )}

            {section === "train" && (
              <>
                <button className={`tabBtn ${trainTab === "train-detail" ? "active" : ""}`} onClick={() => setTrainTab("train-detail")}>
                  📉 Loss Curves & Dynamics
                </button>
                <button className={`tabBtn ${trainTab === "train-head-diagnostics" ? "active" : ""}`} onClick={() => setTrainTab("train-head-diagnostics")}>
                  🩺 Head Training Losses
                </button>
                <button className={`tabBtn ${trainTab === "objective-reward-config" ? "active" : ""}`} onClick={() => setTrainTab("objective-reward-config")}>
                  🎯 Objective & Reward Config
                </button>
              </>
            )}

            {section === "meta" && (
              <button className={`tabBtn ${metaTab === "overview" ? "active" : ""}`} onClick={() => setMetaTab("overview")}>
                📋 Evaluation Index & Traceability
              </button>
            )}
          </div>

          {/* Selector limpio de Benchmark para la sección de Evaluación */}
          {section === "eval" && evalRows.length > 0 && (
            <div
              style={{
                marginBottom: 12,
                padding: "8px 12px",
                background: "linear-gradient(180deg, #1e293b, #0f172a)",
                border: "1px solid #334155",
                borderRadius: 8,
                display: "flex",
                alignItems: "center",
                flexWrap: "wrap",
                gap: 12,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span className="muted" style={{ fontSize: 12, fontWeight: 700 }}>📊 Benchmark Seleccionado:</span>
                <select
                  value={selectedEvalId}
                  onChange={(e) => setSelectedEvalId(e.target.value)}
                  style={{
                    background: "#0f172a",
                    border: "1px solid #38bdf8",
                    color: "#f8fafc",
                    padding: "4px 10px",
                    borderRadius: 4,
                    fontSize: 12,
                    fontWeight: 600,
                    maxWidth: 280,
                  }}
                >
                  {evalRows.map((r) => {
                    const id = String(r.eval_id || "");
                    return <option key={id} value={id}>{id || "(no eval_id)"}</option>;
                  })}
                </select>
              </div>
              <div style={{ marginLeft: "auto", fontSize: 11, color: "#94a3b8" }}>
                Total de benchmarks evaluados: <b style={{ color: "#38bdf8" }}>{evalRows.length}</b>
              </div>
            </div>
          )}

          {/* Full Forensic Replay Controls & Filter Bar */}
          {section === "replay" && evalRows.length > 0 && (
            <div
              style={{
                marginBottom: 12,
                padding: "10px 12px",
                background: "linear-gradient(180deg, #1e293b, #0f172a)",
                border: "1px solid #334155",
                borderRadius: 8,
                boxShadow: "0 4px 10px rgba(0,0,0,0.25)",
                display: "flex",
                flexDirection: "column",
                gap: 8,
              }}
            >
              {/* Row 1: Selectors (Benchmark, Scenario, Matchup, Winner, Seed) */}
              <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
                {/* Benchmark Selector */}
                <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                  <span className="muted" style={{ fontSize: 12, fontWeight: 600 }}>📊 Benchmark:</span>
                  <select
                    value={selectedEvalId}
                    onChange={(e) => setSelectedEvalId(e.target.value)}
                    style={{
                      background: "#0f172a",
                      border: "1px solid #475569",
                      color: "#f8fafc",
                      padding: "4px 8px",
                      borderRadius: 4,
                      fontSize: 12,
                      maxWidth: 240,
                    }}
                  >
                    {evalRows.map((r) => {
                      const id = String(r.eval_id || "");
                      return <option key={id} value={id}>{id || "(no eval_id)"}</option>;
                    })}
                  </select>
                </div>

                {/* Scenario Filter */}
                <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                  <span className="muted" style={{ fontSize: 12, fontWeight: 600 }}>🗺️ Scenario:</span>
                  <select
                    value={filterScenario}
                    onChange={(e) => setFilterScenario(e.target.value)}
                    style={{
                      background: "#0f172a",
                      border: filterScenario !== "all" ? "1px solid #38bdf8" : "1px solid #475569",
                      color: filterScenario !== "all" ? "#38bdf8" : "#f8fafc",
                      padding: "4px 8px",
                      borderRadius: 4,
                      fontSize: 12,
                      fontWeight: filterScenario !== "all" ? 700 : 400,
                    }}
                  >
                    <option value="all">All Scenarios ({rawEpisodesMeta.length})</option>
                    <option value="mettete">🌊 Mettete i piedi a terra (Beaches)</option>
                    <option value="cittadina">🏙️ Battaglia Cittadina (Urban)</option>
                  </select>
                </div>

                {/* Matchup / Player Filter */}
                <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                  <span className="muted" style={{ fontSize: 12, fontWeight: 600 }}>⚔️ Player Matchup:</span>
                  <select
                    value={filterMatchup}
                    onChange={(e) => setFilterMatchup(e.target.value)}
                    style={{
                      background: "#0f172a",
                      border: filterMatchup !== "all" ? "1px solid #a855f7" : "1px solid #475569",
                      color: filterMatchup !== "all" ? "#c084fc" : "#f8fafc",
                      padding: "4px 8px",
                      borderRadius: 4,
                      fontSize: 12,
                      fontWeight: filterMatchup !== "all" ? 700 : 400,
                    }}
                  >
                    <option value="all">All Matchups</option>
                    <option value="selfplay">⚔️ EZv2 Self-Play (IT Def vs US Atk)</option>
                    <option value="vs_random">🎯 EZv2 vs Random (All)</option>
                    <option value="vs_random_atk">⚔️ EZv2 (US Atk) vs Random (IT Def)</option>
                    <option value="vs_random_def">🛡️ EZv2 (IT Def) vs Random (US Atk)</option>
                  </select>
                </div>

                {/* Winner Filter */}
                <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                  <span className="muted" style={{ fontSize: 12, fontWeight: 600 }}>🏆 Winner:</span>
                  <select
                    value={filterWinner}
                    onChange={(e) => setFilterWinner(e.target.value)}
                    style={{
                      background: "#0f172a",
                      border: filterWinner !== "all" ? "1px solid #22c55e" : "1px solid #475569",
                      color: filterWinner !== "all" ? "#4ade80" : "#f8fafc",
                      padding: "4px 8px",
                      borderRadius: 4,
                      fontSize: 12,
                      fontWeight: filterWinner !== "all" ? 700 : 400,
                    }}
                  >
                    <option value="all">All Results</option>
                    <option value="EZV2_WIN">🏆 EZv2 Wins (Model Victory)</option>
                    <option value="EZV2_LOSS">❌ Random Wins (Defeats / Edge Cases)</option>
                    <option value="US">🇺🇸 US Won (Allies)</option>
                    <option value="GE">🇩🇪 GE Won (Germany)</option>
                    <option value="IT">🇮🇹 IT Won (Italy)</option>
                    <option value="EJE">🛡️ Axis Won (GE or IT)</option>
                    <option value="EMPATE">🤝 Tactical Draws</option>
                  </select>
                </div>

                {/* Seed / ID Search */}
                <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                  <span className="muted" style={{ fontSize: 12 }}>🔍</span>
                  <input
                    type="text"
                    placeholder="Search seed or ep..."
                    value={searchSeedOrId}
                    onChange={(e) => setSearchSeedOrId(e.target.value)}
                    style={{
                      background: "#0f172a",
                      border: searchSeedOrId ? "1px solid #facc15" : "1px solid #475569",
                      color: "#f8fafc",
                      padding: "4px 8px",
                      borderRadius: 4,
                      fontSize: 12,
                      width: 140,
                    }}
                  />
                </div>
              </div>

              {/* Row 2: Quick Filter Chips & Active Match Selector */}
              <div style={{ display: "flex", flexDirection: "column", gap: 6, paddingTop: 4, borderTop: "1px dashed #334155" }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 6 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 4, flexWrap: "wrap" }}>
                    <span style={{ fontSize: 11, color: "#64748b", fontWeight: 700, marginRight: 2 }}>QUICK FILTERS:</span>
                    <button
                      onClick={() => { setFilterScenario("all"); setFilterMatchup("all"); setFilterWinner("all"); setSearchSeedOrId(""); }}
                      style={{
                        padding: "2px 7px", fontSize: 11, borderRadius: 4, cursor: "pointer", border: "1px solid #475569",
                        background: filterScenario === "all" && filterMatchup === "all" && filterWinner === "all" && !searchSeedOrId ? "#334155" : "transparent",
                        color: "#cbd5e1"
                      }}
                    >
                      All
                    </button>
                    <button
                      onClick={() => setFilterScenario((prev) => (prev === "mettete" ? "all" : "mettete"))}
                      style={{
                        padding: "2px 7px", fontSize: 11, borderRadius: 4, cursor: "pointer",
                        border: filterScenario === "mettete" ? "1px solid #38bdf8" : "1px solid #475569",
                        background: filterScenario === "mettete" ? "rgba(56, 189, 248, 0.2)" : "transparent",
                        color: filterScenario === "mettete" ? "#38bdf8" : "#cbd5e1"
                      }}
                    >
                      🌊 Mettete
                    </button>
                    <button
                      onClick={() => setFilterScenario((prev) => (prev === "cittadina" ? "all" : "cittadina"))}
                      style={{
                        padding: "2px 7px", fontSize: 11, borderRadius: 4, cursor: "pointer",
                        border: filterScenario === "cittadina" ? "1px solid #38bdf8" : "1px solid #475569",
                        background: filterScenario === "cittadina" ? "rgba(56, 189, 248, 0.2)" : "transparent",
                        color: filterScenario === "cittadina" ? "#38bdf8" : "#cbd5e1"
                      }}
                    >
                      🏙️ Cittadina
                    </button>
                    <button
                      onClick={() => setFilterMatchup((prev) => (prev === "selfplay" ? "all" : "selfplay"))}
                      style={{
                        padding: "2px 7px", fontSize: 11, borderRadius: 4, cursor: "pointer",
                        border: filterMatchup === "selfplay" ? "1px solid #a855f7" : "1px solid #475569",
                        background: filterMatchup === "selfplay" ? "rgba(168, 85, 247, 0.2)" : "transparent",
                        color: filterMatchup === "selfplay" ? "#c084fc" : "#cbd5e1"
                      }}
                    >
                      ⚔️ EZv2 Self-Play
                    </button>
                    <button
                      onClick={() => setFilterMatchup((prev) => (prev === "vs_random" ? "all" : "vs_random"))}
                      style={{
                        padding: "2px 7px", fontSize: 11, borderRadius: 4, cursor: "pointer",
                        border: filterMatchup === "vs_random" ? "1px solid #a855f7" : "1px solid #475569",
                        background: filterMatchup === "vs_random" ? "rgba(168, 85, 247, 0.2)" : "transparent",
                        color: filterMatchup === "vs_random" ? "#c084fc" : "#cbd5e1"
                      }}
                    >
                      🎯 vs Random
                    </button>
                    <button
                      onClick={() => setFilterWinner((prev) => (prev === "EZV2_WIN" ? "all" : "EZV2_WIN"))}
                      style={{
                        padding: "2px 7px", fontSize: 11, borderRadius: 4, cursor: "pointer",
                        border: filterWinner === "EZV2_WIN" ? "1px solid #22c55e" : "1px solid #475569",
                        background: filterWinner === "EZV2_WIN" ? "rgba(34, 197, 94, 0.2)" : "transparent",
                        color: filterWinner === "EZV2_WIN" ? "#4ade80" : "#cbd5e1"
                      }}
                    >
                      🏆 EZv2 Wins
                    </button>
                    <button
                      onClick={() => setFilterWinner((prev) => (prev === "EZV2_LOSS" ? "all" : "EZV2_LOSS"))}
                      style={{
                        padding: "2px 7px", fontSize: 11, borderRadius: 4, cursor: "pointer",
                        border: filterWinner === "EZV2_LOSS" ? "1px solid #ef4444" : "1px solid #475569",
                        background: filterWinner === "EZV2_LOSS" ? "rgba(239, 68, 68, 0.2)" : "transparent",
                        color: filterWinner === "EZV2_LOSS" ? "#f87171" : "#cbd5e1"
                      }}
                    >
                      ❌ Defeats / Edge Cases
                    </button>
                  </div>

                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span
                      style={{
                        fontSize: 11,
                        fontWeight: 700,
                        color: filteredEpisodes.length > 0 ? "#38bdf8" : "#ef4444",
                        background: "rgba(15, 23, 42, 0.8)",
                        padding: "2px 8px",
                        borderRadius: 4,
                        border: "1px solid #334155",
                      }}
                    >
                      {filteredEpisodes.length} of {rawEpisodesMeta.length} matches
                    </span>
                    {(filterScenario !== "all" || filterMatchup !== "all" || filterWinner !== "all" || Boolean(searchSeedOrId)) && (
                      <button
                        onClick={() => { setFilterScenario("all"); setFilterMatchup("all"); setFilterWinner("all"); setSearchSeedOrId(""); }}
                        title="Reset all filters"
                        style={{
                          padding: "2px 6px",
                          fontSize: 11,
                          background: "rgba(239, 68, 68, 0.15)",
                          border: "1px solid #ef4444",
                          color: "#f87171",
                          borderRadius: 4,
                          cursor: "pointer",
                          fontWeight: 600,
                        }}
                      >
                        🔄 Clear
                      </button>
                    )}
                  </div>
                </div>

                {/* Active Match Dropdown Selector */}
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 2 }}>
                  <span style={{ fontSize: 12, fontWeight: 700, color: "#f8fafc", whiteSpace: "nowrap" }}>
                    🎮 Active Match:
                  </span>
                  {filteredEpisodes.length > 0 ? (
                    <select
                      key={`sel_${selectedEvalId}_${filterScenario}_${filterMatchup}_${filterWinner}_${searchSeedOrId}_${filteredEpisodes.length}`}
                      value={selectedEpisodeId}
                      onChange={(e) => setSelectedEpisodeId(e.target.value)}
                      style={{
                        flex: 1,
                        background: "#0f172a",
                        border: "1px solid #38bdf8",
                        color: "#f8fafc",
                        padding: "6px 10px",
                        borderRadius: 6,
                        fontSize: 12,
                        fontWeight: 600,
                        cursor: "pointer",
                      }}
                    >
                      {filteredEpisodes.map((ep, i) => {
                        const id = String(ep.episode_id || `episode_${i}`);
                        return (
                          <option key={`ep_opt_${id}_${i}`} value={id}>
                            {getEpisodeOptionLabel(ep, i)}
                          </option>
                        );
                      })}
                    </select>
                  ) : (
                    <div style={{ fontSize: 12, color: "#f87171", padding: "4px 8px", background: "rgba(239, 68, 68, 0.1)", borderRadius: 4, border: "1px solid rgba(239, 68, 68, 0.3)", flex: 1 }}>
                      ⚠️ No matches found for selected filters. Adjust filters or click "Clear".
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Contenido de la pestaña activa */}
          <div className="content">
            {section === "topology" && (
              <NetworkTopologyTab
                trainRow={selectedTrainRow}
                trainSummary={trainSummary}
                evalRows={evalRows}
                activeSubTab={topologyTab}
                onSubTabChange={setTopologyTab}
                onNavigateToHeadDiagnostics={() => {
                  setSection("eval");
                  setEvalTab("xai-heads");
                }}
              />
            )}
            {section === "train" && trainTab === "train-detail" && (
              <TrainDetailTab trainRow={selectedTrainRow} trainSummary={trainSummary} />
            )}
            {section === "train" && trainTab === "train-head-diagnostics" && (
              <TrainHeadDiagnosticsTab trainRow={selectedTrainRow} trainSummary={trainSummary} />
            )}
            {section === "train" && trainTab === "objective-reward-config" && (
              <ObjectiveRewardConfigTab trainRow={selectedTrainRow} />
            )}

            {(section === "eval" || section === "replay") && loadingEvals && !evalRows.length && (
              <div className="muted" style={{ padding: 16 }}>⏳ Cargando evaluaciones del run seleccionado...</div>
            )}
            {(section === "eval" || section === "replay") && !loadingEvals && !evalRows.length && (
              <div
                style={{
                  padding: "28px 24px",
                  textAlign: "center",
                  background: "#1e293b80",
                  borderRadius: 8,
                  border: "1px dashed #475569",
                  margin: "12px 0",
                }}
              >
                <div style={{ fontSize: 32, marginBottom: 10 }}>ℹ️</div>
                <div style={{ fontSize: 15, fontWeight: 700, color: "#f8fafc", marginBottom: 6 }}>
                  Sin evaluaciones asociadas a la ejecución seleccionada
                </div>
                <div style={{ fontSize: 12, color: "#94a3b8", maxWidth: 560, margin: "0 auto 16px auto", lineHeight: 1.5 }}>
                  La ejecución de entrenamiento <code style={{ color: "#38bdf8" }}>{selectedTrainRun}</code> no contiene benchmarks de evaluación (XAI / Head Diagnostics).
                </div>
                {trains.find((t) => Number(t.evals_count ?? 0) > 0) && (
                  <button
                    onClick={() => {
                      const evaluatedRun = trains.find((t) => Number(t.evals_count ?? 0) > 0);
                      if (evaluatedRun?.run_id) setSelectedTrainRun(String(evaluatedRun.run_id));
                    }}
                    style={{
                      background: "#0284c725",
                      border: "1px solid #38bdf8",
                      color: "#38bdf8",
                      padding: "8px 16px",
                      borderRadius: 6,
                      fontWeight: 600,
                      cursor: "pointer",
                      fontSize: 12,
                    }}
                  >
                    👉 Cambiar a la última ejecución evaluada ({trains.find((t) => Number(t.evals_count ?? 0) > 0)?.run_id})
                  </button>
                )}
              </div>
            )}
            {section === "eval" && evalRows.length > 0 && evalTab === "matchups-vp" && (
              <VpSummaryTab evalRows={evalRows} selectedEval={selectedEval} />
            )}
            {section === "eval" && evalRows.length > 0 && evalTab === "benchmark-matrix" && (
              <EvalMetricsTab evalRows={evalRows} />
            )}
            {section === "eval" && evalRows.length > 0 && evalTab === "tactical-decisions" && (
              <EvalDecisionsTab selectedEval={selectedEval} mainResult={mainResult} />
            )}
            {section === "eval" && evalRows.length > 0 && evalTab === "xai-heads" && (
              <HeadDiagnosticsTab
                evalRows={evalRows}
                trainRow={selectedTrainRow}
                trainSummary={trainSummary}
              />
            )}

            {section === "replay" && evalRows.length > 0 && replayTab === "tactical-map" && (
              <MatchReplayTab
                selectedEvalSourcePath={selectedEvalSourcePath}
                replayMeta={replayMeta}
                replaySteps={replaySteps}
                stepIndex={selectedStepIndex}
                onStepIndexChange={setSelectedStepIndex}
              />
            )}
            {section === "replay" && evalRows.length > 0 && replayTab === "event-log" && (
              <ReplayTab
                selectedEvalSourcePath={selectedEvalSourcePath}
                replayLog={replayLog}
                replaySteps={replaySteps}
                stepIndex={selectedStepIndex}
              />
            )}

            {section === "meta" && metaTab === "overview" && (
              <MetaTab model={model} evalHistory={Array.isArray(model?.eval_history) ? model!.eval_history! : evalRows} />
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
