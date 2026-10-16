import { useEffect, useMemo, useState } from "react";
import { fetchCatalog, fetchCurriculumCompareLatest, fetchModel, fetchTraceability } from "../api";
import { formatLocalDate } from "../dateUtils";
import type { Dict, EvalResultRow, EvalRow, ModelPayload, TrainRow } from "../types";
import { NetworkTopologyTab } from "./model-tabs/NetworkTopologyTab";

type EngineRow = { engine: string; models: ModelRow[] };
type ModelRow = {
  model_id: string;
  train_runs_count?: number;
  eval_history_total_count?: number;
  latest_train_run_id?: string;
  latest_train_created_at_utc?: string;
  latest_eval_created_at_utc?: string;
  train_history?: Array<{ created_at_utc?: string }>;
  eval_history?: Array<{ created_at_utc?: string }>;
};

export function getModelLatestDate(m: ModelRow): string {
  const dates: string[] = [];
  if (m.latest_train_created_at_utc) dates.push(m.latest_train_created_at_utc);
  if (m.latest_eval_created_at_utc) dates.push(m.latest_eval_created_at_utc);
  if (Array.isArray(m.train_history)) {
    for (const t of m.train_history) {
      if (t?.created_at_utc) dates.push(t.created_at_utc);
    }
  }
  if (Array.isArray(m.eval_history)) {
    for (const e of m.eval_history) {
      if (e?.created_at_utc) dates.push(e.created_at_utc);
    }
  }
  if (dates.length === 0) return "";
  dates.sort();
  return dates[dates.length - 1];
}

export function CatalogPage() {
  const [catalog, setCatalog] = useState<Dict | null>(null);
  const [traceRows, setTraceRows] = useState<Dict[]>([]);
  const [selectedEngine, setSelectedEngine] = useState("");
  const [selectedModel, setSelectedModel] = useState("");
  const [modelDetail, setModelDetail] = useState<ModelPayload | null>(null);
  const [compareRows, setCompareRows] = useState<Dict[]>([]);
  const [compareProfileFilter, setCompareProfileFilter] = useState("all");
  const [compareSideFilter, setCompareSideFilter] = useState("all");
  const [compareEngineFilter, setCompareEngineFilter] = useState("all");
  const [error, setError] = useState("");
  const [summaryTab, setSummaryTab] = useState<"overview" | "topology" | "curriculum" | "compare">("overview");

  async function load() {
    try {
      setError("");
      const [c, t, cmp] = await Promise.all([
        fetchCatalog(),
        fetchTraceability(400),
        fetchCurriculumCompareLatest(400),
      ]);
      setCatalog(c);
      setTraceRows(Array.isArray(t.rows) ? (t.rows as Dict[]) : []);
      const rawCmp = Array.isArray(cmp.rows) ? (cmp.rows as Dict[]) : [];
      const cleanCompareRows = rawCmp
        .map((row) => {
          const clean: Dict = {};
          for (const [k, v] of Object.entries(row)) {
            const cleanKey = String(k || "").replace(/\0/g, "").trim();
            const cleanVal = typeof v === "string" ? v.replace(/\0/g, "").trim() : v;
            clean[cleanKey] = cleanVal;
          }
          return clean;
        })
        .filter((r) => r.phase && String(r.phase) !== "phase");
      setCompareRows(cleanCompareRows);

      const engines = Array.isArray(c.engines) ? (c.engines as EngineRow[]) : [];
      const firstEngine = engines[0];
      const initialEngine = firstEngine?.engine || "";
      setSelectedEngine(initialEngine);
    } catch (e) {
      setError(String((e as Error).message || e));
    }
  }

  useEffect(() => {
    void load();
  }, []);

  // Fetch full model detail whenever selectedEngine & selectedModel change
  useEffect(() => {
    if (!selectedEngine || !selectedModel) {
      setModelDetail(null);
      return;
    }
    let cancelled = false;
    async function fetchDetail() {
      try {
        const m = await fetchModel(selectedEngine, selectedModel);
        if (!cancelled) setModelDetail(m);
      } catch {
        if (!cancelled) setModelDetail(null);
      }
    }
    void fetchDetail();
    return () => {
      cancelled = true;
    };
  }, [selectedEngine, selectedModel]);

  const engines = useMemo(
    () => (Array.isArray(catalog?.engines) ? (catalog!.engines as EngineRow[]) : []),
    [catalog]
  );
  const models = useMemo(() => {
    const raw = engines.find((e) => e.engine === selectedEngine)?.models || [];
    return [...raw].sort((a, b) => {
      const dateA = getModelLatestDate(a);
      const dateB = getModelLatestDate(b);
      const timeA = dateA ? new Date(dateA).getTime() : 0;
      const timeB = dateB ? new Date(dateB).getTime() : 0;
      if (timeB !== timeA) {
        return timeB - timeA; // Descending: latest date first
      }
      return b.model_id.localeCompare(a.model_id);
    });
  }, [engines, selectedEngine]);

  useEffect(() => {
    if (models.length > 0) {
      if (!selectedModel || !models.some((m) => m.model_id === selectedModel)) {
        setSelectedModel(models[0].model_id);
      }
    }
  }, [models, selectedModel]);

  const catalogModel = useMemo(
    () => models.find((m) => m.model_id === selectedModel) || null,
    [models, selectedModel]
  );

  const detailUrl = useMemo(
    () => `/model?engine=${encodeURIComponent(selectedEngine)}&model=${encodeURIComponent(selectedModel)}`,
    [selectedEngine, selectedModel]
  );
  const eloUrl = useMemo(
    () => `/elo?engine=${encodeURIComponent(selectedEngine)}&model=${encodeURIComponent(selectedModel || "__all__")}`,
    [selectedEngine, selectedModel]
  );

  // Data helpers for Overview
  const trains = useMemo(
    () => (Array.isArray(modelDetail?.train_history) ? (modelDetail!.train_history as TrainRow[]) : []),
    [modelDetail]
  );
  const evals = useMemo(
    () => (Array.isArray(modelDetail?.eval_history) ? (modelDetail!.eval_history as EvalRow[]) : []),
    [modelDetail]
  );
  const trainCounts = (modelDetail?.scenario_train_counts || {}) as Record<string, number>;
  const evalCounts = (modelDetail?.scenario_eval_counts || {}) as Record<string, number>;
  const scenariosSeen = Array.from(
    new Set([...(modelDetail?.scenarios_seen || []), ...Object.keys(trainCounts), ...Object.keys(evalCounts)])
  ).sort();

  return (
    <div className="wrap">
      <div className="bar" style={{ justifyContent: "space-between" }}>
        <h1 style={{ margin: 0, fontSize: 18 }}>Curriculum Reporting Viewer</h1>
        <div className="bar">
          <button onClick={() => void load()}>Reload</button>
          <span className="muted">
            schema={String(catalog?.schema_version || "")} | source={String(catalog?.catalog_source || "")}
          </span>
          {error ? <span className="muted" style={{ color: "#fca5a5" }}>error: {error}</span> : null}
        </div>
      </div>

      <div className="grid">
        {/* Engines Panel */}
        <section className="panel">
          <h2>Engines ({engines.length})</h2>
          <div className="list">
            {engines.map((e) => (
              <div
                key={e.engine}
                className={`item ${selectedEngine === e.engine ? "active" : ""}`}
                onClick={() => {
                  setSelectedEngine(e.engine);
                }}
              >
                <div className="bar" style={{ justifyContent: "space-between", alignItems: "center" }}>
                  <b>{e.engine}</b>
                  <button
                    onClick={(ev) => {
                      ev.stopPropagation();
                      window.open(
                        `/elo?engine=${encodeURIComponent(e.engine)}&model=${encodeURIComponent(selectedModel || "__all__")}`,
                        "_blank",
                        "noopener,noreferrer"
                      );
                    }}
                    style={{ fontSize: 11, padding: "3px 8px" }}
                  >
                    ELO
                  </button>
                </div>
                <div className="muted">{e.models?.length ?? 0} models</div>
              </div>
            ))}
          </div>
        </section>

        {/* Models Panel */}
        <section className="panel">
          <h2>Models ({models.length})</h2>
          <div className="list">
            {models.map((m) => {
              const latestDate = getModelLatestDate(m);
              return (
                <div
                  key={m.model_id}
                  className={`item ${selectedModel === m.model_id ? "active" : ""}`}
                  onClick={() => setSelectedModel(m.model_id)}
                  onDoubleClick={() => {
                    window.open(detailUrl, "_blank", "noopener,noreferrer");
                  }}
                >
                  <div className="bar" style={{ justifyContent: "space-between", alignItems: "center" }}>
                    <b style={{ fontSize: 12, wordBreak: "break-all" }}>{m.model_id}</b>
                    <button
                      onClick={(ev) => {
                        ev.stopPropagation();
                        window.open(
                          `/model?engine=${encodeURIComponent(selectedEngine)}&model=${encodeURIComponent(m.model_id)}`,
                          "_blank",
                          "noopener,noreferrer"
                        );
                      }}
                      style={{ fontSize: 11, padding: "3px 8px", whiteSpace: "nowrap" }}
                    >
                      View Detail
                    </button>
                  </div>
                  <div
                    className="muted"
                    style={{
                      fontSize: 11,
                      marginTop: 4,
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      flexWrap: "wrap",
                      gap: 4,
                    }}
                  >
                    <span>
                      trains={m.train_runs_count ?? 0} | evals={m.eval_history_total_count ?? 0}
                    </span>
                    {latestDate ? (
                      <span style={{ fontSize: 11, color: "#93c5fd" }} title={latestDate}>
                        {formatLocalDate(latestDate)}
                      </span>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        {/* Summary Panel with 3 Tabs */}
        <section className="panel">
          <h2>Summary</h2>
          <div className="tabs" style={{ marginBottom: 12 }}>
            <button
              className={`tabBtn ${summaryTab === "overview" ? "active" : ""}`}
              onClick={() => setSummaryTab("overview")}
            >
              Overview
            </button>
            <button
              className={`tabBtn ${summaryTab === "topology" ? "active" : ""}`}
              onClick={() => setSummaryTab("topology")}
              style={{ fontWeight: 700, color: summaryTab === "topology" ? "#38bdf8" : undefined }}
            >
              🧠 Network Topology
            </button>
            <button
              className={`tabBtn ${summaryTab === "curriculum" ? "active" : ""}`}
              onClick={() => setSummaryTab("curriculum")}
            >
              Curriculum Traceability ({traceRows.length})
            </button>
            <button
              className={`tabBtn ${summaryTab === "compare" ? "active" : ""}`}
              onClick={() => setSummaryTab("compare")}
            >
              Curriculum Compare ({compareRows.length})
            </button>
          </div>

          {/* TAB 1: OVERVIEW */}
          {summaryTab === "overview" && (
            <>
              {catalogModel ? (
                <div>
                  {/* Action buttons */}
                  <div className="bar" style={{ marginBottom: 12 }}>
                    <button
                      onClick={() => window.open(detailUrl, "_blank", "noopener,noreferrer")}
                      style={{ background: "#0ea5e9", color: "#0f172a", fontWeight: "bold" }}
                    >
                      → Open Full Model Detail
                    </button>
                    <button onClick={() => window.open(eloUrl, "_blank", "noopener,noreferrer")}>
                      View in ELO Leaderboard
                    </button>
                  </div>

                  {/* Top KPIs */}
                  <div className="kpi-grid" style={{ marginBottom: 14 }}>
                    <div className="kpi">
                      <div className="k">model_id</div>
                      <div className="v" style={{ wordBreak: "break-all", fontSize: 11 }}>
                        {catalogModel.model_id}
                      </div>
                    </div>
                    <div className="kpi">
                      <div className="k">engine / algorithm</div>
                      <div className="v">{selectedEngine} / {String((modelDetail as Dict)?.algorithm || selectedEngine)}</div>
                    </div>
                    <div className="kpi">
                      <div className="k">latest_train_run_id</div>
                      <div className="v" style={{ wordBreak: "break-all", fontSize: 11 }}>
                        {catalogModel.latest_train_run_id || "-"}
                      </div>
                    </div>
                    <div className="kpi">
                      <div className="k">config_fingerprint</div>
                      <div className="v">{String(modelDetail?.config_fingerprint || "-")}</div>
                    </div>
                    <div className="kpi">
                      <div className="k">train_runs_count</div>
                      <div className="v">{catalogModel.train_runs_count ?? trains.length}</div>
                    </div>
                    <div className="kpi">
                      <div className="k">eval_history_total_count</div>
                      <div className="v">{catalogModel.eval_history_total_count ?? evals.length}</div>
                    </div>
                    <div className="kpi">
                      <div className="k">latest_train_date</div>
                      <div className="v" style={{ fontSize: 11 }}>
                        {formatLocalDate(modelDetail?.latest_train_created_at_utc)}
                      </div>
                    </div>
                    <div className="kpi">
                      <div className="k">latest_eval_date</div>
                      <div className="v" style={{ fontSize: 11 }}>
                        {formatLocalDate(catalogModel.latest_eval_created_at_utc)}
                      </div>
                    </div>
                  </div>

                  {/* Scenarios Seen */}
                  {scenariosSeen.length > 0 && (
                    <div style={{ marginBottom: 14 }}>
                      <h3 style={{ margin: "0 0 6px 0", fontSize: 13 }}>Scenarios Seen ({scenariosSeen.length})</h3>
                      <table>
                        <thead>
                          <tr>
                            <th>scenario_id</th>
                            <th>train_count</th>
                            <th>eval_count</th>
                          </tr>
                        </thead>
                        <tbody>
                          {scenariosSeen.map((s) => (
                            <tr key={s}>
                              <td><b>{s}</b></td>
                              <td>{trainCounts[s] ?? 0}</td>
                              <td>{evalCounts[s] ?? 0}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}

                  {/* Recent Training Runs */}
                  {trains.length > 0 && (
                    <div style={{ marginBottom: 14 }}>
                      <h3 style={{ margin: "0 0 6px 0", fontSize: 13 }}>Training Runs ({trains.length})</h3>
                      <table>
                        <thead>
                          <tr>
                            <th>run_id</th>
                            <th>scenario</th>
                            <th>created_at</th>
                            <th>git_commit</th>
                            <th>checkpoint</th>
                          </tr>
                        </thead>
                        <tbody>
                          {trains.slice(0, 8).map((t) => (
                            <tr key={String(t.run_id || Math.random())}>
                              <td><b>{String(t.run_id || "-")}</b></td>
                              <td>{String(t.scenario_id || "-")}</td>
                              <td>{formatLocalDate(t.created_at_utc)}</td>
                              <td><code>{String(t.git_commit || "-").slice(0, 8)}</code></td>
                              <td className="muted" style={{ fontSize: 11 }}>{String(t.latest_checkpoint || "-")}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}

                  {/* Recent Evaluations */}
                  {evals.length > 0 && (
                    <div>
                      <h3 style={{ margin: "0 0 6px 0", fontSize: 13 }}>Evaluation Runs ({evals.length})</h3>
                      <table>
                        <thead>
                          <tr>
                            <th>eval_id</th>
                            <th>scenario</th>
                            <th>created_at</th>
                            <th>profiles</th>
                            <th>win_rate</th>
                            <th>status</th>
                          </tr>
                        </thead>
                        <tbody>
                          {evals.slice(0, 8).map((ev) => {
                            const results = Array.isArray(ev.results) ? (ev.results as EvalResultRow[]) : [];
                            const r0 = results[0];
                            return (
                              <tr key={String(ev.eval_id || Math.random())}>
                                <td><b>{String(ev.eval_id || "-")}</b></td>
                                <td>{String(ev.scenario_id || "-")}</td>
                                <td>{formatLocalDate(ev.created_at_utc)}</td>
                                <td>{results.length}</td>
                                <td>
                                  {r0?.win_rate !== undefined ? `${(Number(r0.win_rate) * 100).toFixed(1)}%` : "-"}
                                </td>
                                <td>
                                  {r0 ? (
                                    <span style={{ color: r0.gate_ok ? "#22c55e" : "#ef4444", fontWeight: "bold" }}>
                                      {r0.gate_ok ? "PASS" : "FAIL"}
                                    </span>
                                  ) : (
                                    <span className="muted">-</span>
                                  )}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              ) : (
                <div className="muted">Select an engine and model to view summary.</div>
              )}
            </>
          )}

          {/* TAB: NETWORK TOPOLOGY */}
          {summaryTab === "topology" && (
            <div>
              <div className="bar" style={{ marginBottom: 12, justifyContent: "space-between" }}>
                <span style={{ fontSize: 13, fontWeight: 700, color: "#38bdf8" }}>
                  Topología Dinámica del Modelo: {catalogModel?.model_id || selectedModel}
                </span>
                <button
                  onClick={() => window.open(detailUrl, "_blank", "noopener,noreferrer")}
                  style={{ background: "#0ea5e9", color: "#0f172a", fontWeight: "bold", fontSize: 11, padding: "4px 8px" }}
                >
                  Abrir Detalle Completo ➔
                </button>
              </div>
              <NetworkTopologyTab
                trainRow={trains[0] || null}
                trainSummary={null}
              />
            </div>
          )}

          {/* TAB 2: CURRICULUM TRACEABILITY */}
          {summaryTab === "curriculum" && (
            <div>
              <h3 style={{ margin: "0 0 6px 0", fontSize: 13 }}>Curriculum Phase Traceability</h3>
              <div className="muted" style={{ marginBottom: 8 }}>
                Recorded history of phases, hard gates, promotion decisions, and diagnostics.
              </div>
              <table>
                <thead>
                  <tr>
                    <th>phase</th>
                    <th>train_run_id</th>
                    <th>recorded_at</th>
                    <th>gate_status</th>
                    <th>hard_gate</th>
                    <th>diagnostic</th>
                    <th>promotion_decision</th>
                  </tr>
                </thead>
                <tbody>
                  {!traceRows.length ? (
                    <tr>
                      <td colSpan={7} className="muted">No curriculum traceability records available.</td>
                    </tr>
                  ) : (
                    traceRows.slice(0, 50).map((r, idx) => (
                      <tr key={idx}>
                        <td><b>{String(r.phase_name || "-")}</b></td>
                        <td><code>{String(r.train_run_id || "-")}</code></td>
                        <td>{formatLocalDate(r.recorded_at_utc as string)}</td>
                        <td>
                          <span
                            style={{
                              color:
                                String(r.gate_result_status).toUpperCase() === "PASSED" ||
                                String(r.gate_result_status).toUpperCase() === "PASS"
                                  ? "#22c55e"
                                  : String(r.gate_result_status).toUpperCase() === "IN_PROGRESS"
                                  ? "#f59e0b"
                                  : "#ef4444",
                              fontWeight: "bold",
                            }}
                          >
                            {String(r.gate_result_status || "-")}
                          </span>
                        </td>
                        <td>{String(r.hard_gate_badge || "-")}</td>
                        <td>{String(r.diagnostic_badge || "-")}</td>
                        <td>
                          <span
                            style={{
                              color: String(r.promotion_decision) === "promoted" ? "#22c55e" : undefined,
                              fontWeight: String(r.promotion_decision) === "promoted" ? "bold" : "normal",
                            }}
                          >
                            {String(r.promotion_decision || "-")}
                          </span>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}

          {/* TAB 3: CURRICULUM COMPARE */}
          {summaryTab === "compare" && (() => {
            const compareProfiles = Array.from(new Set(compareRows.map((r) => String(r.profile || "")).filter(Boolean))).sort();
            const compareSides = ["US", "IT", "GE"];
            const compareEngines = ["muzero", "efficientzero_v2"];

            const filteredCompareRows = compareRows.filter((r) => {
              if (compareProfileFilter !== "all" && String(r.profile || "") !== compareProfileFilter) {
                return false;
              }
              if (compareSideFilter !== "all") {
                const ag = String(r.agent || "").toUpperCase();
                if (!ag.includes(compareSideFilter.toUpperCase())) {
                  return false;
                }
              }
              if (compareEngineFilter !== "all") {
                const ag = String(r.agent || "").toLowerCase();
                const pr = String(r.profile || "").toLowerCase();
                if (!ag.includes(compareEngineFilter.toLowerCase()) && !pr.includes(compareEngineFilter.toLowerCase())) {
                  return false;
                }
              }
              return true;
            });

            const hasActiveCompareFilters = compareProfileFilter !== "all" || compareSideFilter !== "all" || compareEngineFilter !== "all";

            return (
              <div>
                <h3 style={{ margin: "0 0 6px 0", fontSize: 13 }}>Curriculum Compare (Latest)</h3>
                <div className="muted" style={{ marginBottom: 10 }}>
                  Comparativa de métricas entre checkpoint candidato y baseline a través de fases de curriculum.
                </div>

                {/* Filter Toolbar */}
                <div
                  style={{
                    background: "#0f172a",
                    border: "1px solid #334155",
                    borderRadius: 6,
                    padding: "8px 12px",
                    marginBottom: 12,
                    display: "flex",
                    flexWrap: "wrap",
                    alignItems: "center",
                    gap: 10,
                  }}
                >
                  <span style={{ fontSize: 12, fontWeight: 700, color: "#38bdf8", display: "flex", alignItems: "center", gap: 4 }}>
                    <span>🔍</span> Filtros:
                  </span>

                  {/* Bando Filter */}
                  <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                    <label style={{ fontSize: 11, color: "#94a3b8", fontWeight: 600 }}>Bando:</label>
                    <select
                      value={compareSideFilter}
                      onChange={(e) => setCompareSideFilter(e.target.value)}
                      style={{
                        padding: "3px 6px",
                        background: "#1e293b",
                        color: "#e2e8f0",
                        border: compareSideFilter !== "all" ? "1px solid #38bdf8" : "1px solid #475569",
                        borderRadius: 4,
                        fontSize: 11,
                      }}
                    >
                      <option value="all">Todos los bandos</option>
                      {compareSides.map((s) => (
                        <option key={s} value={s}>
                          {s === "US" ? "🇺🇸 US" : s === "IT" ? "🇮🇹 IT" : s === "GE" ? "🇩🇪 GE" : s}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Engine Filter */}
                  <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                    <label style={{ fontSize: 11, color: "#94a3b8", fontWeight: 600 }}>Engine:</label>
                    <select
                      value={compareEngineFilter}
                      onChange={(e) => setCompareEngineFilter(e.target.value)}
                      style={{
                        padding: "3px 6px",
                        background: "#1e293b",
                        color: "#e2e8f0",
                        border: compareEngineFilter !== "all" ? "1px solid #38bdf8" : "1px solid #475569",
                        borderRadius: 4,
                        fontSize: 11,
                      }}
                    >
                      <option value="all">Todos los engines</option>
                      {compareEngines.map((e) => (
                        <option key={e} value={e}>
                          {e}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Simulation Type / Profile Filter */}
                  <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                    <label style={{ fontSize: 11, color: "#94a3b8", fontWeight: 600 }}>Tipo Simulación:</label>
                    <select
                      value={compareProfileFilter}
                      onChange={(e) => setCompareProfileFilter(e.target.value)}
                      style={{
                        padding: "3px 6px",
                        background: "#1e293b",
                        color: "#e2e8f0",
                        border: compareProfileFilter !== "all" ? "1px solid #38bdf8" : "1px solid #475569",
                        borderRadius: 4,
                        fontSize: 11,
                      }}
                    >
                      <option value="all">Todos los tipos ({compareProfiles.length})</option>
                      {compareProfiles.map((p) => (
                        <option key={p} value={p}>
                          {p}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Reset button */}
                  {hasActiveCompareFilters && (
                    <button
                      onClick={() => {
                        setCompareProfileFilter("all");
                        setCompareSideFilter("all");
                        setCompareEngineFilter("all");
                      }}
                      style={{
                        fontSize: 10,
                        padding: "3px 8px",
                        background: "#334155",
                        color: "#f87171",
                        border: "1px solid #64748b",
                        borderRadius: 4,
                        cursor: "pointer",
                        fontWeight: 600,
                      }}
                    >
                      ✕ Limpiar
                    </button>
                  )}

                  <div style={{ marginLeft: "auto", fontSize: 11, color: "#94a3b8" }}>
                    Mostrando <b style={{ color: "#38bdf8" }}>{filteredCompareRows.length}</b> de {compareRows.length} métricas
                  </div>
                </div>

                <table>
                  <thead>
                    <tr>
                      <th>phase</th>
                      <th>profile</th>
                      <th>agent</th>
                      <th>metric</th>
                      <th>baseline</th>
                      <th>candidate</th>
                      <th>delta</th>
                    </tr>
                  </thead>
                  <tbody>
                    {!filteredCompareRows.length ? (
                      <tr>
                        <td colSpan={7} className="muted" style={{ textAlign: "center", fontStyle: "italic", padding: "16px 0" }}>
                          No hay registros comparativos que coincidan con los filtros seleccionados.
                        </td>
                      </tr>
                    ) : (
                      filteredCompareRows.slice(0, 100).map((r, idx) => {
                        const deltaNum = parseFloat(String(r.delta || "0"));
                        const isPositive = !isNaN(deltaNum) && deltaNum > 0;
                        const isNegative = !isNaN(deltaNum) && deltaNum < 0;

                        return (
                          <tr key={`cmp-${idx}`}>
                            <td><b>{String(r.phase || "-")}</b></td>
                            <td>{String(r.profile || "-")}</td>
                            <td>{String(r.agent || "-")}</td>
                            <td>{String(r.metric || "-")}</td>
                            <td>{String(r.baseline || "-")}</td>
                            <td><b>{String(r.candidate || "-")}</b></td>
                            <td
                              style={{
                                color: isPositive ? "#22c55e" : isNegative ? "#ef4444" : "#e2e8f0",
                                fontWeight: "bold",
                              }}
                            >
                              {String(r.delta || "-")}
                            </td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>
            );
          })()}
        </section>
      </div>
    </div>
  );
}
