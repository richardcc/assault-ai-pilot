import { useMemo, useState } from "react";
import type { EvalResultRow, EvalRow } from "../../types";
import { formatLocalDate } from "../../dateUtils";
import { SideCombatTable } from "../../components/SideCombatTable";

export function EvalMetricsTab({ evalRows }: { evalRows: EvalRow[] }) {
  const [selectedEngine, setSelectedEngine] = useState<string>("all");
  const [selectedProfile, setSelectedProfile] = useState<string>("all");
  const [selectedSide, setSelectedSide] = useState<string>("all");

  // Total raw results count before filters
  const totalRawProfiles = useMemo(() => {
    let count = 0;
    for (const er of evalRows) {
      if (Array.isArray(er.results)) count += er.results.length;
    }
    return count;
  }, [evalRows]);

  // Discover available options across all eval rows
  const { availableEngines, availableProfiles, availableSides } = useMemo(() => {
    const engines = new Set<string>();
    const profiles = new Set<string>();
    const sides = new Set<string>();

    for (const er of evalRows) {
      if (er.engine) engines.add(er.engine);
      const results = Array.isArray(er.results) ? (er.results as EvalResultRow[]) : [];
      for (const r of results) {
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
            if (p) engines.add(p);
          }
        }
        if (r.controller_by_side) {
          for (const [s, c] of Object.entries(r.controller_by_side)) {
            sides.add(s);
            if (c) engines.add(c);
          }
        }
      }
    }
    return {
      availableEngines: Array.from(engines).sort(),
      availableProfiles: Array.from(profiles).sort(),
      availableSides: Array.from(sides).sort(),
    };
  }, [evalRows]);

  // Filter evaluation rows and their embedded matchup results
  const filteredEvalRows = useMemo(() => {
    return evalRows
      .map((er) => {
        const rowEngine = String(er.engine || "").toLowerCase();
        const results = Array.isArray(er.results) ? (er.results as EvalResultRow[]) : [];

        const filteredResults = results.filter((r) => {
          // 1. Engine Filter
          if (selectedEngine !== "all") {
            const selEng = selectedEngine.toLowerCase();
            const matchesRowEngine = rowEngine.includes(selEng);
            const matchesPolicy = Object.values(r.policy_by_side || {}).some((p) =>
              String(p || "").toLowerCase().includes(selEng)
            );
            const matchesController = Object.values(r.controller_by_side || {}).some((c) =>
              String(c || "").toLowerCase().includes(selEng)
            );
            const matchesAgent = String(r.agent_name || "").toLowerCase().includes(selEng);
            if (!matchesRowEngine && !matchesPolicy && !matchesController && !matchesAgent) {
              return false;
            }
          }

          // 2. Simulation Type / Matchup Profile Filter
          if (selectedProfile !== "all") {
            const prof = String(r.matchup_profile || "");
            const grp = String(r.matchup_group || "");
            if (prof !== selectedProfile && grp !== selectedProfile) {
              return false;
            }
          }

          // 3. Side / Bando Filter
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

          return true;
        });

        return {
          ...er,
          results: filteredResults,
        };
      })
      .filter((er) => {
        const hasResults = er.results.length > 0;
        if (!hasResults && (selectedProfile !== "all" || selectedSide !== "all" || selectedEngine !== "all")) {
          return false;
        }
        return true;
      });
  }, [evalRows, selectedEngine, selectedProfile, selectedSide]);

  // Flatten filtered results for aggregate combat calculation
  const allFilteredResults: EvalResultRow[] = useMemo(() => {
    const list: EvalResultRow[] = [];
    for (const er of filteredEvalRows) {
      if (Array.isArray(er.results)) {
        list.push(...(er.results as EvalResultRow[]));
      }
    }
    return list;
  }, [filteredEvalRows]);

  const hasActiveFilters = selectedEngine !== "all" || selectedProfile !== "all" || selectedSide !== "all";

  const resetFilters = () => {
    setSelectedEngine("all");
    setSelectedProfile("all");
    setSelectedSide("all");
  };

  if (!evalRows.length) return <div className="muted">No evaluation rows available.</div>;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 10, marginBottom: 8 }}>
        <div>
          <h3 style={{ margin: "0 0 4px 0" }}>Evaluation Runs & Matchup Metrics</h3>
          <div className="muted">
            Detailed breakdown of evaluation runs by scenario, engine, and simulation profile.
          </div>
        </div>
      </div>

      {/* Interactive Filter Bar */}
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

        {/* Filter by Bando (Side) */}
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <label htmlFor="filter-side" style={{ fontSize: 12, color: "#94a3b8", fontWeight: 600 }}>
            Bando:
          </label>
          <select
            id="filter-side"
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

        {/* Filter by Engine */}
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <label htmlFor="filter-engine" style={{ fontSize: 12, color: "#94a3b8", fontWeight: 600 }}>
            Engine:
          </label>
          <select
            id="filter-engine"
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

        {/* Filter by Simulation Type (Matchup Profile) */}
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <label htmlFor="filter-profile" style={{ fontSize: 12, color: "#94a3b8", fontWeight: 600 }}>
            Tipo Simulación:
          </label>
          <select
            id="filter-profile"
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

        {/* Reset Filters Button */}
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

        {/* Filter Status Badge */}
        <div style={{ marginLeft: "auto", fontSize: 12, color: "#94a3b8" }}>
          Mostrando <b style={{ color: "#38bdf8" }}>{allFilteredResults.length}</b> de {totalRawProfiles} perfiles
        </div>
      </div>

      {/* Main Metrics Table */}
      {filteredEvalRows.length === 0 ? (
        <div className="muted" style={{ padding: "24px 0", textAlign: "center", fontStyle: "italic" }}>
          No hay ejecuciones de evaluación que coincidan con los filtros seleccionados.
        </div>
      ) : (
        <table>
          <thead>
            <tr>
              <th>eval_id</th>
              <th>engine</th>
              <th>created_at</th>
              <th>scenario</th>
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
            {filteredEvalRows.map((er) => {
              const results = Array.isArray(er.results) ? (er.results as EvalResultRow[]) : [];
              if (!results.length) {
                return (
                  <tr key={String(er.eval_id || Math.random())}>
                    <td><b>{String(er.eval_id || "-")}</b></td>
                    <td><span style={{ fontSize: 11, color: "#94a3b8" }}>{String(er.engine || "-")}</span></td>
                    <td>{formatLocalDate(er.created_at_utc)}</td>
                    <td>{String(er.scenario_id || "-")}</td>
                    <td colSpan={11} className="muted">No result profiles</td>
                  </tr>
                );
              }

              return results.map((r, idx) => {
                // Determine side specific metrics if bando filtered
                const sideRate = selectedSide !== "all" && r.winner_side_rates?.[selectedSide] !== undefined
                  ? r.winner_side_rates[selectedSide]
                  : r.win_rate;

                const displaySide = selectedSide !== "all"
                  ? selectedSide
                  : String(r.tracked_side || "ALL");

                const sideColor = displaySide === "US" ? "#60a5fa" : displaySide === "IT" ? "#34d399" : displaySide === "GE" ? "#f87171" : "#cbd5e1";

                const oppSide = displaySide === "US" ? "IT" : displaySide === "IT" ? "US" : displaySide === "GE" ? "US" : String(r.opponent_side || "-");
                const oppLabel = oppSide === "US" ? "🇺🇸 US" : oppSide === "IT" ? "🇮🇹 IT" : oppSide === "GE" ? "🇩🇪 GE" : oppSide;
                const oppColor = oppSide === "US" ? "#60a5fa" : oppSide === "IT" ? "#34d399" : oppSide === "GE" ? "#f87171" : "#cbd5e1";
                const oppCtrlMap = (r.controller_by_side || r.policy_by_side || {}) as Record<string, string>;
                const oppCtrl = oppCtrlMap[oppSide] || oppCtrlMap[oppSide.toLowerCase()] || "";

                return (
                  <tr key={`${er.eval_id}-${r.matchup_profile || idx}-${idx}`}>
                    {idx === 0 ? (
                      <td rowSpan={results.length} style={{ verticalAlign: "top" }}>
                        <b>{String(er.eval_id || "-")}</b>
                      </td>
                    ) : null}
                    {idx === 0 ? (
                      <td rowSpan={results.length} style={{ verticalAlign: "top" }}>
                        <span style={{ fontSize: 11, color: "#a5b4fc", fontWeight: 600 }}>
                          {String(er.engine || "efficientzero_v2")}
                        </span>
                      </td>
                    ) : null}
                    {idx === 0 ? (
                      <td rowSpan={results.length} style={{ verticalAlign: "top" }}>
                        {formatLocalDate(er.created_at_utc)}
                      </td>
                    ) : null}
                    {idx === 0 ? (
                      <td rowSpan={results.length} style={{ verticalAlign: "top" }}>
                        {String(er.scenario_id || "-")}
                      </td>
                    ) : null}
                    <td><b>{String(r.matchup_profile || "-")}</b></td>
                    <td>
                      <span style={{ color: sideColor, fontWeight: 700, fontSize: 11 }}>
                        {displaySide}
                      </span>
                    </td>
                    <td>
                      <span style={{ color: oppColor, fontWeight: 600, fontSize: 11 }}>
                        {oppLabel}
                      </span>
                      {Boolean(oppCtrl) && (
                        <span className="muted" style={{ fontSize: 10, marginLeft: 4 }}>
                          ({oppCtrl})
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
                      <span style={{ color: r.gate_ok ? "#22c55e" : "#ef4444", fontWeight: 700 }}>
                        {r.gate_ok ? "PASS" : "FAIL"}
                      </span>
                    </td>
                  </tr>
                );
              });
            })}
          </tbody>
        </table>
      )}

      {/* Aggregate Combat & Tactical Effectiveness Breakdown with filtered results */}
      <SideCombatTable results={allFilteredResults} filterSide={selectedSide} />
    </div>
  );
}
