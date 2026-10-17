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
import type { Dict, EvalResultRow, EvalRow, ModelPayload, ReplayMetaPayload, TrainRow } from "../types";
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
      if (trains.length > 0 && trains[0].run_id) {
        setSelectedTrainRun(String(trains[0].run_id));
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

  return (
    <div className="wrap">
      <div className="bar" style={{ justifyContent: "space-between" }}>
        <h1 style={{ margin: 0, fontSize: 18 }}>Model Detail - {String(model?.model_id || modelId || "")}</h1>
        <div className="bar">
          <button onClick={() => window.open("/", "_self")}>Back to Catalog</button>
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

          {/* Barra de filtros de evaluación (visible solo en sección Eval) */}
          {section === "eval" && (
            <div className="bar" style={{ marginBottom: 12, padding: "6px 8px", background: "#1e293b", borderRadius: 6 }}>
              <div className="muted" style={{ fontSize: 12 }}>Eval:</div>
              <select value={selectedEvalId} onChange={(e) => setSelectedEvalId(e.target.value)} style={{ maxWidth: 300 }}>
                {evalRows.map((r) => {
                  const id = String(r.eval_id || "");
                  return <option key={id} value={id}>{id || "(no eval_id)"}</option>;
                })}
              </select>

              {(evalTab === "match-replay" || evalTab === "replay-log") && (
                <>
                  <div className="muted" style={{ fontSize: 12, marginLeft: 8 }}>Episode:</div>
                  <select value={selectedEpisodeId} onChange={(e) => setSelectedEpisodeId(e.target.value)}>
                    {(Array.isArray(replayMeta?.episodes_meta) ? replayMeta!.episodes_meta! : []).map((ep, i) => {
                      const id = String(ep.episode_id || `episode_${i}`);
                      const stepCount = ep.rows || ep.steps_count || 0;
                      const seedText = ep.seed !== undefined && ep.seed !== null ? `Seed ${ep.seed}` : "";
                      const infoParts = [seedText, stepCount ? `${stepCount} pasos` : ""].filter(Boolean);
                      const label = infoParts.length > 0 ? `${id} (${infoParts.join(" - ")})` : id;
                      return <option key={id} value={id}>{label}</option>;
                    })}
                  </select>
                </>
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
            {section === "eval" && (!loadingEvals || evalRows.length > 0) && evalTab === "vp-summary" && (
              <VpSummaryTab evalRows={evalRows} selectedEval={selectedEval} />
            )}
            {section === "eval" && (!loadingEvals || evalRows.length > 0) && evalTab === "eval-head-diagnostics" && (
              <HeadDiagnosticsTab evalRows={evalRows} />
            )}
            {section === "eval" && (!loadingEvals || evalRows.length > 0) && evalTab === "eval-metrics" && (
              <EvalMetricsTab evalRows={evalRows} />
            )}
            {section === "eval" && evalTab === "eval-decisions" && (
              <EvalDecisionsTab mainResult={mainResult} />
            )}
            {section === "eval" && evalTab === "match-replay" && (
              <MatchReplayTab
                selectedEvalSourcePath={selectedEvalSourcePath}
                replayMeta={replayMeta}
                replaySteps={replaySteps}
                stepIndex={selectedStepIndex}
                onStepIndexChange={setSelectedStepIndex}
              />
            )}
            {section === "eval" && evalTab === "replay-log" && (
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
