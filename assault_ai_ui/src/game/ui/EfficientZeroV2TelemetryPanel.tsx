import { useState, useEffect } from "react";
import { apiUrl } from "../../config/backend";

type CandidateMove = {
  action_id: string;
  visit_count: number;
  q_value: number;
  prior: number;
  value: number;
};

type TacticalHeads = {
  threat_map_max?: number;
  threat_map_mean?: number;
  threat_grid?: number[][];
  morale_distribution?: number[];
};

type TelemetryData = {
  engine?: string;
  run_id?: string;
  checkpoint?: string;
  root_value?: number;
  win_prob?: number;
  active_side?: string;
  simulations?: number;
  legal_count?: number;
  top_candidates?: CandidateMove[];
  tactical_heads?: TacticalHeads;
  replan_units?: Array<{ unit_id: string; score: number }>;
};

type CheckpointOption = {
  run_id: string;
  checkpoint_name: string;
  checkpoint_path: string;
  scenario_id: string;
  iterations: number;
  hidden_dim: number;
  is_active: boolean;
};

type Props = {
  telemetry?: TelemetryData | null;
  onRefreshTelemetry?: () => void;
};

export function EfficientZeroV2TelemetryPanel({ telemetry, onRefreshTelemetry }: Props) {
  const [config, setConfig] = useState<{
    engine: string;
    active_checkpoint?: string;
    active_run_id?: string;
    simulations: number;
    device: string;
    checkpoints: CheckpointOption[];
  } | null>(null);

  const [loading, setLoading] = useState(false);
  const [showThreatGrid, setShowThreatGrid] = useState(false);

  const fetchConfig = async () => {
    try {
      const res = await fetch(apiUrl("/api/game/ai-config"));
      if (res.ok) {
        const data = await res.json();
        setConfig(data);
      }
    } catch (e) {
      console.warn("Failed to load AI config", e);
    }
  };

  useEffect(() => {
    fetchConfig();
  }, []);

  const handleSelectCheckpoint = async (ckptPath: string) => {
    if (!ckptPath) return;
    setLoading(true);
    try {
      const res = await fetch(apiUrl("/api/game/ai-config"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ checkpoint_path: ckptPath }),
      });
      if (res.ok) {
        const updated = await res.json();
        setConfig(updated);
        onRefreshTelemetry?.();
      }
    } catch (e) {
      console.error("Failed to update checkpoint", e);
    } finally {
      setLoading(false);
    }
  };

  const handleSetSimulations = async (sims: number) => {
    try {
      const res = await fetch(apiUrl("/api/game/ai-config"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ simulations: sims }),
      });
      if (res.ok) {
        const updated = await res.json();
        setConfig(updated);
      }
    } catch (e) {
      console.error("Failed to update simulations", e);
    }
  };

  const winProb = telemetry?.win_prob ?? 0.5;
  const rootValue = telemetry?.root_value ?? 0.0;
  const activeSide = telemetry?.active_side || "GE";
  const axisWinPct = Math.round(winProb * 100);
  const alliedWinPct = 100 - axisWinPct;

  const topCandidates = telemetry?.top_candidates || [];
  const maxVisits = Math.max(1, ...(topCandidates.map((c) => c.visit_count) || [1]));

  const tacticalHeads = telemetry?.tactical_heads;
  const morale = tacticalHeads?.morale_distribution || [];
  const moraleLabels = ["Confident", "Steady", "Shaken", "Broken"];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12, padding: "4px 2px", fontSize: 13, color: "#e2e8f0" }}>
      {/* HEADER / CHECKPOINT SELECTION */}
      <div style={{ background: "rgba(15, 23, 42, 0.75)", border: "1px solid rgba(56, 189, 248, 0.3)", borderRadius: 6, padding: 8 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
          <span style={{ fontWeight: "bold", color: "#38bdf8", display: "flex", alignItems: "center", gap: 6 }}>
            <span>⚡ EfficientZero V2</span>
            <span style={{ fontSize: 10, background: config?.device === "cuda" ? "#15803d" : "#475569", padding: "1px 5px", borderRadius: 4, color: "#fff" }}>
              {config?.device?.toUpperCase() || "GPU"}
            </span>
          </span>
          <span style={{ fontSize: 11, color: "#94a3b8" }}>
            {telemetry?.simulations || config?.simulations || 80} MCTS Sims
          </span>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <label style={{ fontSize: 11, color: "#94a3b8" }}>Modelo / Checkpoint Activo:</label>
          <select
            style={{
              background: "#0f172a",
              color: "#f8fafc",
              border: "1px solid #334155",
              borderRadius: 4,
              padding: "4px 8px",
              fontSize: 11,
              width: "100%",
              cursor: "pointer",
            }}
            value={config?.active_checkpoint || ""}
            onChange={(e) => handleSelectCheckpoint(e.target.value)}
            disabled={loading}
          >
            {(config?.checkpoints || []).map((ckpt) => (
              <option key={ckpt.checkpoint_path} value={ckpt.checkpoint_path}>
                {ckpt.run_id} ({ckpt.checkpoint_name}) - iter {ckpt.iterations}
              </option>
            ))}
          </select>
        </div>

        {/* SIMULATION BUDGET SELECTOR PILLS */}
        <div style={{ display: "flex", gap: 6, marginTop: 8, alignItems: "center" }}>
          <span style={{ fontSize: 11, color: "#94a3b8" }}>Presupuesto MCTS:</span>
          {[40, 80, 160, 300].map((sims) => {
            const isCurrent = (config?.simulations || 80) === sims;
            return (
              <button
                key={sims}
                onClick={() => handleSetSimulations(sims)}
                style={{
                  background: isCurrent ? "#0284c7" : "#1e293b",
                  color: isCurrent ? "#ffffff" : "#94a3b8",
                  border: isCurrent ? "1px solid #38bdf8" : "1px solid #334155",
                  borderRadius: 4,
                  padding: "2px 8px",
                  fontSize: 11,
                  cursor: "pointer",
                  fontWeight: isCurrent ? "bold" : "normal",
                }}
              >
                {sims}
              </button>
            );
          })}
        </div>
      </div>

      {/* WIN RATE / TACTICAL EVALUATION BAR */}
      <div style={{ background: "rgba(15, 23, 42, 0.75)", border: "1px solid rgba(148, 163, 184, 0.2)", borderRadius: 6, padding: 8 }}>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, marginBottom: 4 }}>
          <span style={{ color: "#38bdf8", fontWeight: "bold" }}>Eje (GE): {axisWinPct}%</span>
          <span style={{ color: "#cbd5e1" }}>Root Value v = {rootValue > 0 ? `+${rootValue.toFixed(3)}` : rootValue.toFixed(3)}</span>
          <span style={{ color: "#f87171", fontWeight: "bold" }}>Aliados (US): {alliedWinPct}%</span>
        </div>
        <div style={{ width: "100%", height: 10, background: "#1e293b", borderRadius: 5, overflow: "hidden", display: "flex" }}>
          <div style={{ width: `${axisWinPct}%`, background: "linear-gradient(90deg, #0284c7, #38bdf8)", transition: "width 0.4s ease" }} />
          <div style={{ width: `${alliedWinPct}%`, background: "linear-gradient(90deg, #f87171, #ef4444)", transition: "width 0.4s ease" }} />
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "#64748b", marginTop: 4 }}>
          <span>Acciones Legales: {telemetry?.legal_count ?? "-"}</span>
          <span>Turno de: <strong style={{ color: activeSide === "GE" ? "#38bdf8" : "#f87171" }}>{activeSide}</strong></span>
        </div>
      </div>

      {/* TOP MCTS CANDIDATE MOVES */}
      <div style={{ background: "rgba(15, 23, 42, 0.75)", border: "1px solid rgba(148, 163, 184, 0.2)", borderRadius: 6, padding: 8 }}>
        <div style={{ fontWeight: "bold", fontSize: 12, color: "#f1f5f9", marginBottom: 6, display: "flex", justifyContent: "space-between" }}>
          <span>🌳 Árbol MCTS (Top Acciones Evaluadas)</span>
          <span style={{ fontSize: 10, color: "#64748b" }}>Visitas / Q</span>
        </div>
        {topCandidates.length === 0 ? (
          <div style={{ color: "#64748b", fontStyle: "italic", fontSize: 11, textAlign: "center", padding: "8px 0" }}>
            Esperando primer movimiento de IA para desplegar árbol de búsqueda...
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {topCandidates.map((cand, idx) => {
              const visitPct = Math.round((cand.visit_count / maxVisits) * 100);
              return (
                <div key={cand.action_id || idx} style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11 }}>
                    <span style={{ fontFamily: "monospace", color: idx === 0 ? "#4ade80" : "#e2e8f0" }}>
                      {idx === 0 ? "★ " : `${idx + 1}. `}{cand.action_id}
                    </span>
                    <span style={{ fontSize: 10, color: "#94a3b8" }}>
                      N={cand.visit_count} | Q={cand.q_value > 0 ? `+${cand.q_value.toFixed(2)}` : cand.q_value.toFixed(2)}
                    </span>
                  </div>
                  <div style={{ width: "100%", height: 4, background: "#1e293b", borderRadius: 2, overflow: "hidden" }}>
                    <div style={{ width: `${visitPct}%`, height: "100%", background: idx === 0 ? "#22c55e" : "#0284c7" }} />
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* TACTICAL HEADS (THREAT & MORALE) */}
      <div style={{ background: "rgba(15, 23, 42, 0.75)", border: "1px solid rgba(148, 163, 184, 0.2)", borderRadius: 6, padding: 8 }}>
        <div style={{ fontWeight: "bold", fontSize: 12, color: "#f1f5f9", marginBottom: 6, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span>🎯 Redes Auxiliares Tácticas (Heads)</span>
          {tacticalHeads?.threat_grid && (
            <button
              onClick={() => setShowThreatGrid(!showThreatGrid)}
              style={{
                background: showThreatGrid ? "#0284c7" : "#334155",
                color: "#fff",
                border: "none",
                borderRadius: 4,
                padding: "2px 6px",
                fontSize: 10,
                cursor: "pointer",
              }}
            >
              {showThreatGrid ? "Ocultar Mapa" : "Ver Threat Grid"}
            </button>
          )}
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, fontSize: 11 }}>
          <div style={{ background: "#1e293b", padding: 6, borderRadius: 4 }}>
            <div style={{ color: "#94a3b8", fontSize: 10 }}>Amenaza Máxima</div>
            <div style={{ fontWeight: "bold", color: "#f87171", fontSize: 13 }}>
              {tacticalHeads?.threat_map_max != null ? tacticalHeads.threat_map_max.toFixed(2) : "-"}
            </div>
          </div>
          <div style={{ background: "#1e293b", padding: 6, borderRadius: 4 }}>
            <div style={{ color: "#94a3b8", fontSize: 10 }}>Amenaza Media</div>
            <div style={{ fontWeight: "bold", color: "#fbbf24", fontSize: 13 }}>
              {tacticalHeads?.threat_map_mean != null ? tacticalHeads.threat_map_mean.toFixed(2) : "-"}
            </div>
          </div>
        </div>

        {morale.length > 0 && (
          <div style={{ marginTop: 8 }}>
            <div style={{ fontSize: 10, color: "#94a3b8", marginBottom: 4 }}>Distribución de Moral Predicha:</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 4 }}>
              {morale.map((prob, i) => (
                <div key={i} style={{ background: "#1e293b", padding: 4, borderRadius: 4, textAlign: "center" }}>
                  <div style={{ fontSize: 9, color: "#64748b" }}>{moraleLabels[i] || `C${i}`}</div>
                  <div style={{ fontSize: 11, fontWeight: "bold", color: i === 0 ? "#4ade80" : (i === 3 ? "#ef4444" : "#e2e8f0") }}>
                    {Math.round(prob * 100)}%
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* THREAT HEATMAP MINI GRID */}
        {showThreatGrid && tacticalHeads?.threat_grid && (
          <div style={{ marginTop: 8, padding: 6, background: "#0b0f19", borderRadius: 4, overflowX: "auto" }}>
            <div style={{ fontSize: 10, color: "#94a3b8", marginBottom: 4 }}>Matriz Espacial de Amenaza (16x16):</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(16, 12px)", gap: 1 }}>
              {tacticalHeads.threat_grid.flat().map((val, cellIdx) => {
                const normVal = Math.min(1.0, Math.max(0.0, val));
                const bg = `rgba(239, 68, 68, ${normVal})`;
                return (
                  <div
                    key={cellIdx}
                    title={`Threat: ${val.toFixed(2)}`}
                    style={{
                      width: 12,
                      height: 12,
                      background: normVal > 0.05 ? bg : "#1e293b",
                      border: "1px solid rgba(0,0,0,0.2)",
                    }}
                  />
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* REPLAN CANDIDATE UNITS */}
      {(telemetry?.replan_units || []).length > 0 && (
        <div style={{ background: "rgba(15, 23, 42, 0.75)", border: "1px solid rgba(148, 163, 184, 0.2)", borderRadius: 6, padding: 8 }}>
          <div style={{ fontWeight: "bold", fontSize: 11, color: "#cbd5e1", marginBottom: 4 }}>
            🎯 Prioridad de Activación (Prefilter Replan)
          </div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {telemetry!.replan_units!.map((u) => (
              <span key={u.unit_id} style={{ fontSize: 10, background: "#1e293b", border: "1px solid #334155", padding: "2px 6px", borderRadius: 4 }}>
                <strong style={{ color: "#38bdf8" }}>{u.unit_id}</strong>: {u.score}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
