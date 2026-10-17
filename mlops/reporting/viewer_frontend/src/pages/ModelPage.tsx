import { useEffect, useMemo, useState } from "react";
import {
  fetchModel,
  fetchModelEvals,
  fetchReplayLog,
  fetchReplayMeta,
  fetchReplaySteps,
  fetchTrainSummary,
} from "../api";
import { formatLocalDate } from "../dateUtils";
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

  // Navegación de secciones
  const [section, setSection] = useState<SectionKey>("topology");
  const [topologyTab, setTopologyTab] = useState<"diagram" | "head-diagnostics" | "channel-attribution">("diagram");
  const [trainTab, setTrainTab] = useState<TrainTabKey>("train-detail");
  const [evalTab, setEvalTab] = useState<EvalTabKey>("vp-summary");
  const [metaTab, setMetaTab] = useState<MetaTabKey>("overview");

  const [evalRowsByKey, setEvalRowsByKey] = useState<Record<string, EvalRow[]>>({});
  const [selectedEvalId, setSelectedEvalId] = useState("");

  const [replayMeta, setReplayMeta] = useState<ReplayMetaPayload | null>(null);
  const [replaySteps, setReplaySteps] = useState<Dict | null>(null);
  const [replayLog, setReplayLog] = useState<Dict | null>(null);
  const [selectedEpisodeId, setSelectedEpisodeId] = useState("episode_0");
  const [selectedStepIndex, setSelectedStepIndex] = useState(0);

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
  }, [engine, modelId]);

  // 2. Cargar train summary al cambiar selectedTrainRun
  useEffect(() => {
    if (!selectedTrainRun) return;
    async function run() {
      try {
        const s = await fetchTrainSummary(selectedTrainRun);
        setTrainSummary(s);
      } catch {
        setTrainSummary(null);
      }
    }
    void run();
  }, [selectedTrainRun]);

  // 3. Cargar eval rows al cambiar train_run o scenario (con caché en memoria)
  useEffect(() => {
    if (!selectedTrainRun) return;
    const key = `${selectedTrainRun}::${selectedScenario}`;
    if (evalRowsByKey[key]) return;

    let cancelled = false;
    async function run() {
      try {
        const payload = await fetchModelEvals(engine, modelId, selectedTrainRun, selectedScenario);
        if (cancelled) return;
        const rows = Array.isArray(payload.rows) ? (payload.rows as EvalRow[]) : [];
        setEvalRowsByKey((prev) => ({ ...prev, [key]: rows }));
      } catch {
        // ignore
      }
    }
    void run();
    return () => {
      cancelled = true;
    };
  }, [engine, modelId, selectedTrainRun, selectedScenario, evalRowsByKey]);

  const trains = useMemo(
    () => (Array.isArray(model?.train_history) ? (model!.train_history as TrainRow[]) : []),
    [model]
  );

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
        setSelectedEpisodeId(episodeId);

        const [steps, log] = await Promise.all([
          fetchReplaySteps(selectedEvalSourcePath, episodeId, 0, 499),
          fetchReplayLog(selectedEvalSourcePath, 0, 40, false),
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

  // Cargar steps si cambia episodio
  useEffect(() => {
    async function run() {
      if (!selectedEvalSourcePath || !selectedEpisodeId) return;
      try {
        const steps = await fetchReplaySteps(selectedEvalSourcePath, selectedEpisodeId, 0, 499);
        setReplaySteps(steps);
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
                  <div><b>{String(t.run_id || "")}</b></div>
                  <div className="muted" style={{ fontSize: 11 }}>
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
                      return <option key={id} value={id}>{id}</option>;
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

            {section === "eval" && evalTab === "vp-summary" && (
              <VpSummaryTab evalRows={evalRows} selectedEval={selectedEval} />
            )}
            {section === "eval" && evalTab === "eval-head-diagnostics" && (
              <HeadDiagnosticsTab evalRows={evalRows} />
            )}
            {section === "eval" && evalTab === "eval-metrics" && (
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
