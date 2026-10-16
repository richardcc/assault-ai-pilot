import { useState } from "react";
import type { Dict } from "../types";

interface FunnelData {
  opportunities: number;
  progress_actions: number;
  conversions: number;
  stalls: number;
}

interface ExplainData {
  converted_after_progress: number;
  converted_without_progress: number;
  progressed_but_not_converted: number;
  stalled_and_not_converted: number;
}

export function FunnelChart({
  diagnosticsSummary,
}: {
  diagnosticsSummary?: Dict;
}) {
  const [selectedSide, setSelectedSide] = useState<string>("global");

  if (!diagnosticsSummary) return null;

  const funnelObj = (diagnosticsSummary.objective_progress_funnel || {}) as Dict;
  const explainObj = (diagnosticsSummary.objective_progress_explain || {}) as Dict;

  const globalFunnel = (funnelObj.global || {}) as Dict;
  const bySideFunnel = (funnelObj.by_side || {}) as Record<string, Dict>;

  const globalExplain = ((explainObj.global || {}) as Dict).conversion_path_counts as Dict | undefined;
  const bySideExplain = (explainObj.by_side || {}) as Record<string, Dict>;

  const sideKeys = Object.keys(bySideFunnel).sort();
  const availableScopes = ["global", ...sideKeys];

  // Resolve active data
  const activeFunnelRaw: Dict =
    selectedSide === "global" ? globalFunnel : bySideFunnel[selectedSide] || {};

  const funnel: FunnelData = {
    opportunities: Number(activeFunnelRaw.opportunities || 0),
    progress_actions: Number(activeFunnelRaw.progress_actions || 0),
    conversions: Number(activeFunnelRaw.conversions || 0),
    stalls: Number(activeFunnelRaw.stalls || 0),
  };

  const activeExplainRaw: Dict =
    selectedSide === "global"
      ? (globalExplain || {})
      : ((bySideExplain[selectedSide]?.conversion_path_counts || {}) as Dict);

  const explain: ExplainData = {
    converted_after_progress: Number(activeExplainRaw.converted_after_progress || 0),
    converted_without_progress: Number(activeExplainRaw.converted_without_progress || 0),
    progressed_but_not_converted: Number(activeExplainRaw.progressed_but_not_converted || 0),
    stalled_and_not_converted: Number(activeExplainRaw.stalled_and_not_converted || 0),
  };

  if (!funnel.opportunities && !funnel.progress_actions && !funnel.conversions) {
    return null;
  }

  // Conversion rates
  const oppToProgressRate = funnel.opportunities > 0
    ? (funnel.progress_actions / funnel.opportunities) * 100
    : 0;
  const progressToConvRate = funnel.progress_actions > 0
    ? (funnel.conversions / funnel.progress_actions) * 100
    : 0;
  const overallConvRate = funnel.opportunities > 0
    ? (funnel.conversions / funnel.opportunities) * 100
    : 0;
  const stallRate = funnel.opportunities > 0
    ? (funnel.stalls / funnel.opportunities) * 100
    : 0;

  return (
    <div
      style={{
        margin: "18px 0",
        padding: "16px",
        background: "#1e293b",
        border: "1px solid #334155",
        borderRadius: "8px",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12, flexWrap: "wrap", gap: 8 }}>
        <div>
          <h3 style={{ margin: 0, fontSize: "15px", color: "#38bdf8", display: "flex", alignItems: "center", gap: 6 }}>
            <span>🎯</span> Embudo de Conversión de Objetivos (VP Progress & Capture Funnel)
          </h3>
          <div className="muted" style={{ marginTop: 2, fontSize: "11px" }}>
            Telemetría XAI: Transición desde la detección de hexágono objetivo hasta la captura consolidada.
          </div>
        </div>

        {availableScopes.length > 1 && (
          <div style={{ display: "flex", gap: 6, background: "#0f172a", padding: "3px", borderRadius: "6px" }}>
            {availableScopes.map((scope) => (
              <button
                key={scope}
                onClick={() => setSelectedSide(scope)}
                style={{
                  fontSize: "11px",
                  padding: "4px 8px",
                  borderRadius: "4px",
                  background: selectedSide === scope ? "#0284c7" : "transparent",
                  color: selectedSide === scope ? "#ffffff" : "#94a3b8",
                  border: "none",
                  fontWeight: selectedSide === scope ? 700 : 500,
                  cursor: "pointer",
                  textTransform: "uppercase",
                }}
              >
                {scope}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Visual Funnel Stage Bars */}
      <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 16 }}>
        {/* Stage 1: Opportunities */}
        <div style={{ background: "#0f172a", borderRadius: "6px", padding: "10px 14px", border: "1px solid #1e293b" }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px", marginBottom: 6 }}>
            <span style={{ fontWeight: 600, color: "#93c5fd" }}>1. Oportunidades de Captura Detectadas</span>
            <span style={{ fontWeight: 700, color: "#f8fafc" }}>
              {funnel.opportunities.toLocaleString()} <span className="muted" style={{ fontWeight: 400 }}>(100.0%)</span>
            </span>
          </div>
          <div style={{ background: "#334155", borderRadius: "4px", height: "14px", overflow: "hidden" }}>
            <div
              style={{
                width: "100%",
                height: "100%",
                background: "linear-gradient(90deg, #3b82f6, #60a5fa)",
                borderRadius: "4px",
                transition: "width 0.4s ease",
              }}
            />
          </div>
        </div>

        {/* Stage 2: Progress Actions */}
        <div style={{ background: "#0f172a", borderRadius: "6px", padding: "10px 14px", border: "1px solid #1e293b" }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px", marginBottom: 6 }}>
            <div>
              <span style={{ fontWeight: 600, color: "#fcd34d" }}>2. Acciones de Avance / Reducción de Distancia</span>
              <span style={{ marginLeft: 8, fontSize: "11px", color: "#fbbf24" }}>
                ({oppToProgressRate.toFixed(1)}% de oportunidades)
              </span>
            </div>
            <span style={{ fontWeight: 700, color: "#f8fafc" }}>
              {funnel.progress_actions.toLocaleString()}
            </span>
          </div>
          <div style={{ background: "#334155", borderRadius: "4px", height: "14px", overflow: "hidden", display: "flex" }}>
            <div
              style={{
                width: `${Math.min(100, Math.max(2, oppToProgressRate))}%`,
                height: "100%",
                background: "linear-gradient(90deg, #f59e0b, #fbbf24)",
                borderRadius: "4px 0 0 4px",
                transition: "width 0.4s ease",
              }}
            />
            <div
              style={{
                width: `${Math.min(100 - oppToProgressRate, Math.max(0, stallRate))}%`,
                height: "100%",
                background: "rgba(244, 63, 94, 0.45)",
                borderRadius: "0 4px 4px 0",
              }}
              title={`Atascos / Inacción: ${funnel.stalls.toLocaleString()} (${stallRate.toFixed(1)}%)`}
            />
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11px", marginTop: 4 }}>
            <span className="muted">Avance proactivo hacia VP</span>
            <span style={{ color: "#f43f5e" }}>
              Atascos / Inacción: {funnel.stalls.toLocaleString()} ({stallRate.toFixed(1)}%)
            </span>
          </div>
        </div>

        {/* Stage 3: Conversions */}
        <div style={{ background: "#0f172a", borderRadius: "6px", padding: "10px 14px", border: "1px solid #1e293b" }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px", marginBottom: 6 }}>
            <div>
              <span style={{ fontWeight: 600, color: "#6ee7b7" }}>3. Conversiones Exitosas (VP Capturado)</span>
              <span style={{ marginLeft: 8, fontSize: "11px", color: "#34d399" }}>
                ({progressToConvRate.toFixed(1)}% de avances | {overallConvRate.toFixed(2)}% global)
              </span>
            </div>
            <span style={{ fontWeight: 700, color: "#34d399" }}>
              {funnel.conversions.toLocaleString()}
            </span>
          </div>
          <div style={{ background: "#334155", borderRadius: "4px", height: "14px", overflow: "hidden" }}>
            <div
              style={{
                width: `${Math.min(100, Math.max(funnel.conversions > 0 ? 3 : 0, overallConvRate))}%`,
                height: "100%",
                background: "linear-gradient(90deg, #10b981, #34d399)",
                borderRadius: "4px",
                transition: "width 0.4s ease",
              }}
            />
          </div>
        </div>
      </div>

      {/* Conversion Path Breakdown Cards */}
      <div style={{ marginTop: 14 }}>
        <div style={{ fontSize: "12px", fontWeight: 600, color: "#cbd5e1", marginBottom: 8 }}>
          Rutas de Decisión Explicadas (Explainability Path Breakdown)
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 8 }}>
          <div style={{ background: "#0f172a", padding: "8px 12px", borderRadius: "6px", borderLeft: "3px solid #10b981" }}>
            <div className="muted" style={{ fontSize: "11px" }}>Convertidos tras avance metódico</div>
            <div style={{ fontSize: "14px", fontWeight: 700, color: "#34d399", marginTop: 2 }}>
              {explain.converted_after_progress.toLocaleString()}
            </div>
          </div>
          <div style={{ background: "#0f172a", padding: "8px 12px", borderRadius: "6px", borderLeft: "3px solid #38bdf8" }}>
            <div className="muted" style={{ fontSize: "11px" }}>Convertidos de inmediato (contacto directo)</div>
            <div style={{ fontSize: "14px", fontWeight: 700, color: "#38bdf8", marginTop: 2 }}>
              {explain.converted_without_progress.toLocaleString()}
            </div>
          </div>
          <div style={{ background: "#0f172a", padding: "8px 12px", borderRadius: "6px", borderLeft: "3px solid #f59e0b" }}>
            <div className="muted" style={{ fontSize: "11px" }}>Avanzaron pero disputados / interceptados</div>
            <div style={{ fontSize: "14px", fontWeight: 700, color: "#fbbf24", marginTop: 2 }}>
              {explain.progressed_but_not_converted.toLocaleString()}
            </div>
          </div>
          <div style={{ background: "#0f172a", padding: "8px 12px", borderRadius: "6px", borderLeft: "3px solid #f43f5e" }}>
            <div className="muted" style={{ fontSize: "11px" }}>Atascados / Parálisis táctica sin conversión</div>
            <div style={{ fontSize: "14px", fontWeight: 700, color: "#f43f5e", marginTop: 2 }}>
              {explain.stalled_and_not_converted.toLocaleString()}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
