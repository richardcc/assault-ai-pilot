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

type SectionKey = "topology" | "eval" | "train" | "meta";

type TrainTabKey = "train-detail" | "train-head-diagnostics" | "objective-reward-config" | "network-topology";
type EvalTabKey = "vp-summary" | "eval-head-diagnostics" | "eval-metrics" | "eval-decisions" | "match-replay" | "replay-log";
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
  const [section, setSection] = useState<SectionKey>("topology");
  const [topologyTab, setTopologyTab] = useState<"diagram" | "head-diagnostics" | "channel-attribution" | "macro-planner">("diagram");
  const [trainTab, setTrainTab] = useState<TrainTabKey>("train-detail");
  const [evalTab, setEvalTab] = useState<EvalTabKey>("vp-summary");
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
      const v = String(s || "").trim();
      if (v && !v.startsWith("multi:")) out.add(v);
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

  // Cargar metadatos del Replay bajo demanda (SOLO si estamos en la pestaña de Replay)
  const isReplayActive = section === "eval" && (evalTab === "match-replay" || evalTab === "replay-log");
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

  // Cargar steps y log si cambia episodio
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
    if (ep.matchup) return String(ep.matchup).toLowerCase();
    const an = String(ep.agent_name || "").toLowerCase();
    if (an.includes("random_us") || an.includes("side_b")) return "mcts_vs_random_def";
    if (an.includes("random_it") || an.includes("random_ge") || an.includes("side_a")) return "mcts_vs_random_atk";
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
        if (filterMatchup === "vs_random_def" && m !== "mcts_vs_random_def") return false;
        if (filterMatchup === "vs_random_atk" && m !== "mcts_vs_random_atk") return false;
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
        if (filterWinner === "MCTS_WIN") {
          if (m === "selfplay") return true;
          if (m === "mcts_vs_random_def") return w === "GE" || w === "IT";
          if (m === "mcts_vs_random_atk") return w === "US";
          return w !== "" && w !== "EMPATE";
        }
        if (filterWinner === "MCTS_LOSS") {
          if (m === "selfplay") return false;
          if (m === "mcts_vs_random_def") return w === "US";
          if (m === "mcts_vs_random_atk") return w === "GE" || w === "IT";
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
        ? "🔴 GE Ganó"
        : winner === "IT"
        ? "🟢 IT Ganó"
        : winner === "US"
        ? "🔵 US Ganó"
        : winner === "EMPATE"
        ? "⚖️ Empate"
        : "";
    const scenBadge = ep.scenario_id?.includes("mettete")
      ? "🏖️ Mettete"
      : ep.scenario_id?.includes("cittadina")
      ? "🏙️ Cittadina"
      : "";
    const m = getEpisodeMatchup(ep);
    const matchupBadge =
      m === "selfplay"
        ? "⚔️ Self-Play"
        : m === "mcts_vs_random_def"
        ? "🛡️ vs Rand(US)"
        : m === "mcts_vs_random_atk"
        ? "⚔️ vs Rand(Eje)"
        : "🎲 vs Random";
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
      <div className="bar" style={{ justifyContent: "space-between" }}>
        <h1 style={{ margin: 0, fontSize: 18 }}>Model Detail - {String(model?.model_id || modelId || "")}</h1>
        <div className="bar">
          <button onClick={() => window.open("/", "_self")}>Back to Catalog</button>
          <button
            onClick={() => window.open("/docs", "_blank")}
            style={{
              background: "#0284c7",
              color: "#ffffff",
              border: "none",
              borderRadius: 4,
              padding: "4px 10px",
              fontSize: 11,
              fontWeight: 700,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: 4,
            }}
            title="Abrir Centro Interactivo de Documentación Técnica"
          >
            <span>📚</span> Documentación
          </button>
          <button
            onClick={() =>
              window.open(
                `/elo?engine=${encodeURIComponent(String(model?.engine || engine))}&model=${encodeURIComponent(String(model?.model_id || modelId || "__all__"))}`,
                "_blank",
                "noopener,noreferrer"
              )
            }
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
            title="Refrescar catálogo y evaluaciones"
          >
            🔄 Actualizar Datos
          </button>
          <button
            onClick={async () => {
              const target = String(model?.model_id || modelId || "");
              if (!target) return;
              if (
                !window.confirm(
                  `⚠️ ¿Estás seguro de que deseas ELIMINAR COMPLETAMENTE el experimento "${target}" y todos sus ficheros en disco?\nEsta acción no se puede deshacer.`
                )
              ) {
                return;
              }
              try {
                const res = await deleteModelExperiment(target, String(model?.engine || engine));
                alert(`✅ Experimento eliminado con éxito (${res.freed_mb ?? 0} MB liberados).`);
                window.location.href = "/";
              } catch (err: any) {
                alert(`❌ Error al eliminar experimento: ${err.message || err}`);
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
            }}
            title="Eliminar este modelo y todos sus ficheros en disco"
          >
            🗑️ Eliminar Experimento
          </button>
        </div>
      </div>

      <div className="panel" style={{ padding: "8px 10px" }}>
        <div className="kpi-grid">
          <div className="kpi">
            <div className="k">model_id</div>
            <div className="v" style={{ wordBreak: "break-all", fontSize: 11 }}>{String(model?.model_id || modelId || "")}</div>
          </div>
          <div className="kpi">
            <div className="k">engine / algorithm</div>
            <div className="v">{String(model?.engine || engine)} / {String((model as Dict)?.algorithm || "-")}</div>
          </div>
          <div className="kpi">
            <div className="k">trains / evals count</div>
            <div className="v">{trains.length} trains / {String((model as Dict)?.eval_history_total_count ?? evalRows.length)} evals</div>
          </div>
          <div className="kpi">
            <div className="k">config_fingerprint</div>
            <div className="v" style={{ wordBreak: "break-all", fontSize: 10 }}>{String(model?.config_fingerprint || "-")}</div>
          </div>
          <div className="kpi" style={{ borderLeft: "2px solid #38bdf8" }}>
            <div className="k">⏱️ training_duration_total</div>
            <div
              className="v"
              style={{ color: "#38bdf8", fontWeight: 700, fontSize: 13 }}
              title={formatDurationDetailed(totalModelTrainDurationSec)}
            >
              {totalModelTrainDurationSec > 0 ? formatDuration(totalModelTrainDurationSec) : "-"}
            </div>
          </div>
        </div>
      </div>

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
              className={`tabBtn ${section === "topology" ? "active" : ""}`}
              onClick={() => setSection("topology")}
              style={{ padding: "4px 10px", fontSize: 12, fontWeight: 700, color: section === "topology" ? "#38bdf8" : undefined }}
            >
              🧠 Network Topology
            </button>
            <button
              className={`tabBtn ${section === "eval" ? "active" : ""}`}
              onClick={() => setSection("eval")}
              style={{ padding: "4px 10px", fontSize: 12 }}
            >
              Eval Metrics
            </button>
            <button
              className={`tabBtn ${section === "train" ? "active" : ""}`}
              onClick={() => setSection("train")}
              style={{ padding: "4px 10px", fontSize: 12 }}
            >
              Train Runs & Metrics
            </button>
            <button
              className={`tabBtn ${section === "meta" ? "active" : ""}`}
              onClick={() => setSection("meta")}
              style={{ padding: "4px 10px", fontSize: 12 }}
            >
              Meta
            </button>
          </div>

          {/* Sub-tabs per section */}
          <div className="tabs" style={{ marginBottom: 10 }}>

            {section === "topology" && (
              <>
                <button className={`tabBtn ${topologyTab === "diagram" ? "active" : ""}`} onClick={() => setTopologyTab("diagram")}>
                  📐 Topología & Arquitectura
                </button>
                <button className={`tabBtn ${topologyTab === "head-diagnostics" ? "active" : ""}`} onClick={() => setTopologyTab("head-diagnostics")}>
                  🔬 Análisis de Cabezas (Head Diagnostics)
                </button>
                <button className={`tabBtn ${topologyTab === "channel-attribution" ? "active" : ""}`} onClick={() => setTopologyTab("channel-attribution")}>
                  📊 Atribución de Canales
                </button>
                <button className={`tabBtn ${topologyTab === "macro-planner" ? "active" : ""}`} onClick={() => setTopologyTab("macro-planner")}>
                  ♟️ Planificador Macro (Nivel 1)
                </button>
              </>
            )}

            {section === "train" && (
              <>
                <button className={`tabBtn ${trainTab === "train-detail" ? "active" : ""}`} onClick={() => setTrainTab("train-detail")}>
                  Train Detail
                </button>
                <button className={`tabBtn ${trainTab === "network-topology" ? "active" : ""}`} onClick={() => setTrainTab("network-topology")}>
                  Network Topology
                </button>
                <button className={`tabBtn ${trainTab === "train-head-diagnostics" ? "active" : ""}`} onClick={() => setTrainTab("train-head-diagnostics")}>
                  Train Head Diagnostics
                </button>
                <button className={`tabBtn ${trainTab === "objective-reward-config" ? "active" : ""}`} onClick={() => setTrainTab("objective-reward-config")}>
                  Objective/Reward Config
                </button>
              </>
            )}

            {section === "eval" && (
              <>
                <button className={`tabBtn ${evalTab === "vp-summary" ? "active" : ""}`} onClick={() => setEvalTab("vp-summary")}>
                  VP Summary
                </button>
                <button className={`tabBtn ${evalTab === "eval-head-diagnostics" ? "active" : ""}`} onClick={() => setEvalTab("eval-head-diagnostics")}>
                  Eval Head Diagnostics
                </button>
                <button className={`tabBtn ${evalTab === "eval-metrics" ? "active" : ""}`} onClick={() => setEvalTab("eval-metrics")}>
                  Eval Metrics
                </button>
                <button className={`tabBtn ${evalTab === "eval-decisions" ? "active" : ""}`} onClick={() => setEvalTab("eval-decisions")}>
                  Eval KBI Decisions
                </button>
                <button className={`tabBtn ${evalTab === "match-replay" ? "active" : ""}`} onClick={() => setEvalTab("match-replay")}>
                  Match Replay
                </button>
                <button className={`tabBtn ${evalTab === "replay-log" ? "active" : ""}`} onClick={() => setEvalTab("replay-log")}>
                  Replay Log
                </button>
              </>
            )}

            {section === "meta" && (
              <button className={`tabBtn ${metaTab === "overview" ? "active" : ""}`} onClick={() => setMetaTab("overview")}>
                Overview & Evals Index
              </button>
            )}
          </div>

          {/* Barra de filtros de evaluación y selector de partidas */}
          {section === "eval" && evalRows.length > 0 && (
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
              {/* Fila 1: Selectores principales */}
              <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
                {/* Selector de Benchmark Eval */}
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span className="muted" style={{ fontSize: 12, fontWeight: 700 }}>📊 Benchmark:</span>
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

                {(evalTab === "match-replay" || evalTab === "replay-log") && (
                  <>
                    {/* Filtro por Escenario */}
                    <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                      <span className="muted" style={{ fontSize: 12, fontWeight: 600 }}>🗺️ Escenario:</span>
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
                        <option value="all">Todos los escenarios ({rawEpisodesMeta.length})</option>
                        <option value="mettete">🏖️ Mettete i piedi a terra (Playas)</option>
                        <option value="cittadina">🏙️ Battaglia Cittadina (Urbano)</option>
                      </select>
                    </div>

                    {/* Filtro por Matchup / Jugador */}
                    <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                      <span className="muted" style={{ fontSize: 12, fontWeight: 600 }}>🎮 Tipo Jugador:</span>
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
                        <option value="all">Todos los matchups</option>
                        <option value="selfplay">⚔️ Self-Play (MCTS vs MCTS)</option>
                        <option value="vs_random">🎲 MCTS vs Random (Todos)</option>
                        <option value="vs_random_def">🛡️ MCTS Defensor vs Random Atacante (US)</option>
                        <option value="vs_random_atk">⚔️ MCTS Atacante vs Random Defensor (Eje)</option>
                      </select>
                    </div>

                    {/* Filtro por Ganador / Resultado */}
                    <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                      <span className="muted" style={{ fontSize: 12, fontWeight: 600 }}>🏆 Ganador:</span>
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
                        <option value="all">Todos los resultados</option>
                        <option value="MCTS_WIN">🏆 Victorias MCTS (Modelo Gana)</option>
                        <option value="MCTS_LOSS">⚠️ Derrotas MCTS (Random Gana)</option>
                        <option value="US">🔵 Ganó US (Aliados)</option>
                        <option value="GE">🔴 Ganó GE (Alemania)</option>
                        <option value="IT">🟢 Ganó IT (Italia)</option>
                        <option value="EJE">🛡️ Ganó Eje (GE o IT)</option>
                        <option value="EMPATE">⚖️ Empates Tácticos</option>
                      </select>
                    </div>

                    {/* Buscador de Seed o ID */}
                    <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                      <span className="muted" style={{ fontSize: 12 }}>🔍</span>
                      <input
                        type="text"
                        placeholder="Buscar seed o ep..."
                        value={searchSeedOrId}
                        onChange={(e) => setSearchSeedOrId(e.target.value)}
                        style={{
                          background: "#0f172a",
                          border: searchSeedOrId ? "1px solid #facc15" : "1px solid #475569",
                          color: "#f8fafc",
                          padding: "4px 8px",
                          borderRadius: 4,
                          fontSize: 12,
                          width: 130,
                        }}
                      />
                    </div>
                  </>
                )}
              </div>

              {/* Fila 2: Chips de acceso rápido y selector de partida activa */}
              {(evalTab === "match-replay" || evalTab === "replay-log") && (
                <div style={{ display: "flex", flexDirection: "column", gap: 6, paddingTop: 4, borderTop: "1px dashed #334155" }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 6 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 4, flexWrap: "wrap" }}>
                      <span style={{ fontSize: 11, color: "#64748b", fontWeight: 700, marginRight: 2 }}>FILTROS RÁPIDOS:</span>
                      <button
                        onClick={() => { setFilterScenario("all"); setFilterMatchup("all"); setFilterWinner("all"); setSearchSeedOrId(""); }}
                        style={{
                          padding: "2px 7px", fontSize: 11, borderRadius: 4, cursor: "pointer", border: "1px solid #475569",
                          background: filterScenario === "all" && filterMatchup === "all" && filterWinner === "all" && !searchSeedOrId ? "#334155" : "transparent",
                          color: "#cbd5e1"
                        }}
                      >
                        Todas
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
                        🏖️ Mettete
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
                        ⚔️ Self-Play MCTS
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
                        🎲 vs Random
                      </button>
                      <button
                        onClick={() => setFilterWinner((prev) => (prev === "MCTS_WIN" ? "all" : "MCTS_WIN"))}
                        style={{
                          padding: "2px 7px", fontSize: 11, borderRadius: 4, cursor: "pointer",
                          border: filterWinner === "MCTS_WIN" ? "1px solid #22c55e" : "1px solid #475569",
                          background: filterWinner === "MCTS_WIN" ? "rgba(34, 197, 94, 0.2)" : "transparent",
                          color: filterWinner === "MCTS_WIN" ? "#4ade80" : "#cbd5e1"
                        }}
                      >
                        🏆 Victorias MCTS
                      </button>
                      <button
                        onClick={() => setFilterWinner((prev) => (prev === "MCTS_LOSS" ? "all" : "MCTS_LOSS"))}
                        style={{
                          padding: "2px 7px", fontSize: 11, borderRadius: 4, cursor: "pointer",
                          border: filterWinner === "MCTS_LOSS" ? "1px solid #ef4444" : "1px solid #475569",
                          background: filterWinner === "MCTS_LOSS" ? "rgba(239, 68, 68, 0.2)" : "transparent",
                          color: filterWinner === "MCTS_LOSS" ? "#f87171" : "#cbd5e1"
                        }}
                      >
                        ⚠️ Derrotas / Casos Límite
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
                        {filteredEpisodes.length} de {rawEpisodesMeta.length} partidas
                      </span>
                      {(filterScenario !== "all" || filterMatchup !== "all" || filterWinner !== "all" || Boolean(searchSeedOrId)) && (
                        <button
                          onClick={() => { setFilterScenario("all"); setFilterMatchup("all"); setFilterWinner("all"); setSearchSeedOrId(""); }}
                          title="Restablecer todos los filtros"
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
                          ✕ Limpiar
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Selector desplegable de partida */}
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 2 }}>
                    <span style={{ fontSize: 12, fontWeight: 700, color: "#f8fafc", whiteSpace: "nowrap" }}>
                      🎬 Partida Activa:
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
                        ⚠️ Ninguna partida coincide con los filtros seleccionados. Cambia los filtros o pulsa "Limpiar".
                      </div>
                    )}
                  </div>
                </div>
              )}
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
              />
            )}
            {section === "train" && trainTab === "train-detail" && (
              <TrainDetailTab trainRow={selectedTrainRow} trainSummary={trainSummary} />
            )}
            {section === "train" && trainTab === "network-topology" && (
              <NetworkTopologyTab
                trainRow={selectedTrainRow}
                trainSummary={trainSummary}
                evalRows={evalRows}
                activeSubTab={topologyTab}
                onSubTabChange={setTopologyTab}
              />
            )}
            {section === "train" && trainTab === "train-head-diagnostics" && (
              <TrainHeadDiagnosticsTab trainRow={selectedTrainRow} trainSummary={trainSummary} />
            )}
            {section === "train" && trainTab === "objective-reward-config" && (
              <ObjectiveRewardConfigTab trainRow={selectedTrainRow} />
            )}

            {section === "eval" && loadingEvals && !evalRows.length && (
              <div className="muted" style={{ padding: 16 }}>⏳ Cargando evaluaciones del run seleccionado...</div>
            )}
            {section === "eval" && !loadingEvals && !evalRows.length && (
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
            {section === "eval" && evalRows.length > 0 && evalTab === "vp-summary" && (
              <VpSummaryTab evalRows={evalRows} selectedEval={selectedEval} />
            )}
            {section === "eval" && evalRows.length > 0 && evalTab === "eval-head-diagnostics" && (
              <HeadDiagnosticsTab evalRows={evalRows} />
            )}
            {section === "eval" && evalRows.length > 0 && evalTab === "eval-metrics" && (
              <EvalMetricsTab evalRows={evalRows} />
            )}
            {section === "eval" && evalRows.length > 0 && evalTab === "eval-decisions" && (
              <EvalDecisionsTab mainResult={mainResult} />
            )}
            {section === "eval" && evalRows.length > 0 && evalTab === "match-replay" && (
              <MatchReplayTab
                selectedEvalSourcePath={selectedEvalSourcePath}
                replayMeta={replayMeta}
                replaySteps={replaySteps}
                stepIndex={selectedStepIndex}
                onStepIndexChange={setSelectedStepIndex}
              />
            )}
            {section === "eval" && evalRows.length > 0 && evalTab === "replay-log" && (
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
