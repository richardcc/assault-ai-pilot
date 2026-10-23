import React, { useState } from "react";
import type { Dict } from "../types";

interface ForensicSitRepModalProps {
  isOpen: boolean;
  onClose: () => void;
  sitrepData: Dict | null;
  isLoading: boolean;
  onJumpToStep?: (stepIndex: number) => void;
  onRecompute?: () => void;
}

export const ForensicSitRepModal: React.FC<ForensicSitRepModalProps> = ({
  isOpen,
  onClose,
  sitrepData,
  isLoading,
  onJumpToStep,
  onRecompute,
}) => {
  const [activeTab, setActiveTab] = useState<"executive" | "correlations" | "turning_points" | "doctrine">("executive");

  if (!isOpen) return null;

  const sitrep = (sitrepData?.sitrep || sitrepData) as Dict | null;
  const isOk = Boolean(sitrepData?.ok ?? true);
  const errorMsg = sitrepData?.error ? String(sitrepData.error) : null;

  const turningPoints = (sitrep?.turning_points as Array<Dict>) || [];
  const phases = (sitrep?.operational_phases as Array<Dict>) || [];
  const headCorrs = (sitrep?.head_correlations as Dict) || {};
  const citations = (sitrep?.doctrinal_citations as Array<Dict>) || [];
  const recommendations = (sitrep?.tactical_recommendations as Array<string>) || [];

  const threat = (headCorrs.threat_map as Dict) || {};
  const morale = (headCorrs.morale as Dict) || {};
  const objective = (headCorrs.objective_intent as Dict) || {};

  const getSeverityBadge = (sev: string) => {
    switch (String(sev || "").toUpperCase()) {
      case "CRITICAL":
        return { bg: "rgba(239, 68, 68, 0.2)", border: "#ef4444", color: "#fca5a5" };
      case "HIGH":
        return { bg: "rgba(245, 158, 11, 0.2)", border: "#f59e0b", color: "#fcd34d" };
      default:
        return { bg: "rgba(59, 130, 246, 0.2)", border: "#3b82f6", color: "#93c5fd" };
    }
  };

  const getEventBadge = (type: string) => {
    switch (String(type || "").toUpperCase()) {
      case "VP_CAPTURE":
        return { label: "VP CAPTURE", icon: "🚩", color: "#4ade80" };
      case "UNIT_ELIMINATION":
        return { label: "KILL", icon: "☠️", color: "#f87171" };
      case "HEAVY_ATTRITION":
        return { label: "ATTRITION", icon: "💥", color: "#fb923c" };
      case "SURPRISE_DAMAGE":
        return { label: "AMBUSH", icon: "⚠️", color: "#e879f9" };
      case "MORALE_FAILURE":
        return { label: "SUPPRESSION", icon: "🛑", color: "#fbbf24" };
      default:
        return { label: "TACTICAL EVENT", icon: "🎯", color: "#38bdf8" };
    }
  };

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        width: "100vw",
        height: "100vh",
        backgroundColor: "rgba(10, 15, 29, 0.85)",
        backdropFilter: "blur(6px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 9999,
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: "92vw",
          maxWidth: 1060,
          maxHeight: "90vh",
          backgroundColor: "#0f172a",
          border: "1px solid #334155",
          borderRadius: 10,
          display: "flex",
          flexDirection: "column",
          boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.75)",
          color: "#f8fafc",
          overflow: "hidden",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          style={{
            padding: "16px 20px",
            borderBottom: "1px solid #1e293b",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            background: "linear-gradient(90deg, #0f172a 0%, #1e293b 100%)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <span style={{ fontSize: 22 }}>🎖️</span>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <h3 style={{ margin: 0, fontSize: 17, fontWeight: 700, color: "#f8fafc" }}>
                  Operational Situation Report (SitRep) & Causal Profiler
                </h3>
                <span
                  style={{
                    fontSize: 10,
                    fontWeight: 700,
                    padding: "2px 6px",
                    borderRadius: 4,
                    background: "rgba(14, 165, 233, 0.2)",
                    border: "1px solid #0284c7",
                    color: "#38bdf8",
                  }}
                >
                  AUTONOMOUS FORENSICS
                </span>
                {sitrep?.cached && (
                  <span
                    style={{
                      fontSize: 10,
                      fontWeight: 600,
                      padding: "2px 6px",
                      borderRadius: 4,
                      background: "rgba(100, 116, 139, 0.2)",
                      border: "1px solid #475569",
                      color: "#94a3b8",
                    }}
                  >
                    CACHED
                  </span>
                )}
              </div>
              <div style={{ fontSize: 12, color: "#94a3b8", marginTop: 2 }}>
                Scenario: <code>{String(sitrep?.scenario_id || "N/A")}</code> | Episode: <code>{String(sitrep?.episode_id || "episode_0")}</code> | Matchup: {String(sitrep?.attacker_side || "US")} vs {String(sitrep?.defender_side || "IT")}
              </div>
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            {onRecompute && (
              <button
                onClick={onRecompute}
                disabled={isLoading}
                style={{
                  background: "rgba(255, 255, 255, 0.05)",
                  border: "1px solid #475569",
                  color: "#cbd5e1",
                  padding: "5px 10px",
                  borderRadius: 4,
                  fontSize: 11,
                  fontWeight: 600,
                  cursor: isLoading ? "not-allowed" : "pointer",
                  display: "flex",
                  alignItems: "center",
                  gap: 4,
                }}
                title="Force full recomputation of turning points and causal metrics"
              >
                <span>🔄</span>
                <span>Re-Profile</span>
              </button>
            )}
            <button
              onClick={onClose}
              style={{
                background: "transparent",
                border: "none",
                color: "#94a3b8",
                fontSize: 20,
                cursor: "pointer",
                padding: "4px 8px",
              }}
            >
              ✕
            </button>
          </div>
        </div>

        {/* Tab Navigation */}
        <div
          style={{
            display: "flex",
            borderBottom: "1px solid #1e293b",
            background: "#0b1329",
            padding: "0 16px",
            gap: 4,
          }}
        >
          <button
            onClick={() => setActiveTab("executive")}
            style={{
              padding: "10px 16px",
              background: "transparent",
              border: "none",
              borderBottom: activeTab === "executive" ? "2px solid #38bdf8" : "2px solid transparent",
              color: activeTab === "executive" ? "#38bdf8" : "#94a3b8",
              fontWeight: activeTab === "executive" ? 700 : 500,
              fontSize: 12,
              cursor: "pointer",
            }}
          >
            📋 Executive Assessment & Phases
          </button>
          <button
            onClick={() => setActiveTab("correlations")}
            style={{
              padding: "10px 16px",
              background: "transparent",
              border: "none",
              borderBottom: activeTab === "correlations" ? "2px solid #38bdf8" : "2px solid transparent",
              color: activeTab === "correlations" ? "#38bdf8" : "#94a3b8",
              fontWeight: activeTab === "correlations" ? 700 : 500,
              fontSize: 12,
              cursor: "pointer",
            }}
          >
            🧠 Tactical Head Forensics
          </button>
          <button
            onClick={() => setActiveTab("turning_points")}
            style={{
              padding: "10px 16px",
              background: "transparent",
              border: "none",
              borderBottom: activeTab === "turning_points" ? "2px solid #38bdf8" : "2px solid transparent",
              color: activeTab === "turning_points" ? "#38bdf8" : "#94a3b8",
              fontWeight: activeTab === "turning_points" ? 700 : 500,
              fontSize: 12,
              cursor: "pointer",
            }}
          >
            ⚡ Turning Points ({turningPoints.length})
          </button>
          <button
            onClick={() => setActiveTab("doctrine")}
            style={{
              padding: "10px 16px",
              background: "transparent",
              border: "none",
              borderBottom: activeTab === "doctrine" ? "2px solid #38bdf8" : "2px solid transparent",
              color: activeTab === "doctrine" ? "#38bdf8" : "#94a3b8",
              fontWeight: activeTab === "doctrine" ? 700 : 500,
              fontSize: 12,
              cursor: "pointer",
            }}
          >
            📖 Doctrinal Grounding (RAG) ({citations.length})
          </button>
        </div>

        {/* Content Body */}
        <div style={{ flex: 1, overflowY: "auto", padding: 20 }}>
          {isLoading ? (
            <div style={{ textAlign: "center", padding: "60px 0", color: "#94a3b8" }}>
              <div style={{ fontSize: 32, marginBottom: 12 }}>⚡</div>
              <div style={{ fontSize: 15, fontWeight: 600 }}>Analyzing Match Timeline & Causal Heads...</div>
              <div style={{ fontSize: 12, marginTop: 4 }}>Correlating threat predictions, morale fragility, and VP conversion velocity...</div>
            </div>
          ) : !isOk || errorMsg ? (
            <div style={{ padding: 20, background: "rgba(239, 68, 68, 0.1)", border: "1px solid #ef4444", borderRadius: 8 }}>
              <div style={{ fontWeight: 700, color: "#f87171", fontSize: 14 }}>Unable to generate Forensic SitRep</div>
              <div style={{ fontSize: 12, color: "#fca5a5", marginTop: 4 }}>{errorMsg || "Unknown analysis error"}</div>
            </div>
          ) : (
            <>
              {/* TAB 1: EXECUTIVE ASSESSMENT */}
              {activeTab === "executive" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
                  {/* Executive Summary Card */}
                  <div
                    style={{
                      background: "rgba(30, 41, 59, 0.6)",
                      border: "1px solid #334155",
                      borderRadius: 8,
                      padding: 16,
                      borderLeft: "4px solid #38bdf8",
                    }}
                  >
                    <div style={{ fontSize: 11, fontWeight: 700, color: "#38bdf8", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 6 }}>
                      Executive Operational Summary
                    </div>
                    <div style={{ fontSize: 13, lineHeight: 1.6, color: "#e2e8f0" }}>
                      {String(sitrep?.executive_summary || "No executive summary available.")}
                    </div>
                  </div>

                  {/* Operational Phases */}
                  <div>
                    <h4 style={{ margin: "0 0 10px 0", fontSize: 14, fontWeight: 700, color: "#f1f5f9" }}>
                      Operational Timeline Breakdown
                    </h4>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
                      {phases.map((p, idx) => (
                        <div
                          key={idx}
                          style={{
                            background: "#1e293b",
                            border: "1px solid #334155",
                            borderRadius: 6,
                            padding: 12,
                            display: "flex",
                            flexDirection: "column",
                            justifyContent: "space-between",
                          }}
                        >
                          <div>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                              <span style={{ fontSize: 12, fontWeight: 700, color: "#38bdf8" }}>{String(p.phase)}</span>
                              <span style={{ fontSize: 10, color: "#94a3b8" }}>{String(p.turns)}</span>
                            </div>
                            <div style={{ fontSize: 11, lineHeight: 1.5, color: "#cbd5e1", marginTop: 8 }}>
                              {String(p.assessment)}
                            </div>
                          </div>
                          <div style={{ marginTop: 10, fontSize: 10, color: "#64748b" }}>
                            Turning points: <strong style={{ color: "#94a3b8" }}>{Number(p.turning_points_count ?? 0)}</strong>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Tactical Recommendations */}
                  {recommendations.length > 0 && (
                    <div style={{ background: "rgba(245, 158, 11, 0.08)", border: "1px solid rgba(245, 158, 11, 0.3)", borderRadius: 8, padding: 14 }}>
                      <div style={{ fontSize: 12, fontWeight: 700, color: "#fbbf24", marginBottom: 8, display: "flex", alignItems: "center", gap: 6 }}>
                        <span>💡</span>
                        <span>Tactical Doctrine & Policy Tuning Recommendations</span>
                      </div>
                      <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, color: "#fde68a", lineHeight: 1.6 }}>
                        {recommendations.map((rec, rIdx) => (
                          <li key={rIdx}>{rec}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}

              {/* TAB 2: TACTICAL HEAD FORENSICS */}
              {activeTab === "correlations" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                  <div style={{ fontSize: 12, color: "#94a3b8" }}>
                    Mathematical correlation between neural auxiliary head predictions and real ground truth game outcomes.
                  </div>

                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 14 }}>
                    {/* Threat Map Card */}
                    <div style={{ background: "#1e293b", border: "1px solid #334155", borderRadius: 8, padding: 14 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <span style={{ fontSize: 13, fontWeight: 700, color: "#f87171" }}>🎯 Threat Map</span>
                        <span
                          style={{
                            fontSize: 10,
                            fontWeight: 700,
                            padding: "2px 6px",
                            borderRadius: 4,
                            background: "rgba(239, 68, 68, 0.15)",
                            color: "#fca5a5",
                            border: "1px solid #ef4444",
                          }}
                        >
                          {String(threat.reliability_rating || "N/A")}
                        </span>
                      </div>
                      <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 6 }}>
                        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11 }}>
                          <span style={{ color: "#94a3b8" }}>Anticipation Accuracy:</span>
                          <strong style={{ color: "#f8fafc" }}>{((Number(threat.anticipation_accuracy ?? 0)) * 100).toFixed(1)}%</strong>
                        </div>
                        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11 }}>
                          <span style={{ color: "#94a3b8" }}>Correlation (Pearson r):</span>
                          <strong style={{ color: "#f8fafc" }}>{Number(threat.correlation_pearson ?? 0).toFixed(2)}</strong>
                        </div>
                        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11 }}>
                          <span style={{ color: "#94a3b8" }}>Surprise Ambushes:</span>
                          <strong style={{ color: Number(threat.surprise_damage_count ?? 0) > 0 ? "#f87171" : "#4ade80" }}>
                            {Number(threat.surprise_damage_count ?? 0)}
                          </strong>
                        </div>
                        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11 }}>
                          <span style={{ color: "#94a3b8" }}>Mitigated Hazards:</span>
                          <strong style={{ color: "#38bdf8" }}>{Number(threat.damage_avoidance_count ?? 0)}</strong>
                        </div>
                      </div>
                      <div style={{ marginTop: 12, borderTop: "1px solid #334155", paddingTop: 8 }}>
                        {(threat.observations as Array<string> || []).map((obs, oi) => (
                          <div key={oi} style={{ fontSize: 10, color: "#cbd5e1", marginTop: 4, lineHeight: 1.4 }}>
                            • {obs}
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Morale Card */}
                    <div style={{ background: "#1e293b", border: "1px solid #334155", borderRadius: 8, padding: 14 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <span style={{ fontSize: 13, fontWeight: 700, color: "#fbbf24" }}>🛑 Morale / Fragility</span>
                        <span
                          style={{
                            fontSize: 10,
                            fontWeight: 700,
                            padding: "2px 6px",
                            borderRadius: 4,
                            background: "rgba(245, 158, 11, 0.15)",
                            color: "#fcd34d",
                            border: "1px solid #f59e0b",
                          }}
                        >
                          {String(morale.reliability_rating || "N/A")}
                        </span>
                      </div>
                      <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 6 }}>
                        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11 }}>
                          <span style={{ color: "#94a3b8" }}>Anticipation Accuracy:</span>
                          <strong style={{ color: "#f8fafc" }}>{((Number(morale.anticipation_accuracy ?? 0)) * 100).toFixed(1)}%</strong>
                        </div>
                        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11 }}>
                          <span style={{ color: "#94a3b8" }}>Suppression Crises:</span>
                          <strong style={{ color: "#f8fafc" }}>{Number(morale.suppression_incidents ?? 0)}</strong>
                        </div>
                        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11 }}>
                          <span style={{ color: "#94a3b8" }}>Predicted Fragility Hits:</span>
                          <strong style={{ color: "#fbbf24" }}>{Number(morale.predicted_fragility_conversions ?? 0)}</strong>
                        </div>
                      </div>
                      <div style={{ marginTop: 12, borderTop: "1px solid #334155", paddingTop: 8 }}>
                        {(morale.observations as Array<string> || []).map((obs, oi) => (
                          <div key={oi} style={{ fontSize: 10, color: "#cbd5e1", marginTop: 4, lineHeight: 1.4 }}>
                            • {obs}
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Objective Intent Card */}
                    <div style={{ background: "#1e293b", border: "1px solid #334155", borderRadius: 8, padding: 14 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <span style={{ fontSize: 13, fontWeight: 700, color: "#4ade80" }}>🚩 Objective Intent</span>
                        <span
                          style={{
                            fontSize: 10,
                            fontWeight: 700,
                            padding: "2px 6px",
                            borderRadius: 4,
                            background: "rgba(74, 222, 128, 0.15)",
                            color: "#86efac",
                            border: "1px solid #22c55e",
                          }}
                        >
                          {String(objective.conversion_efficiency_rating || "N/A")}
                        </span>
                      </div>
                      <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 6 }}>
                        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11 }}>
                          <span style={{ color: "#94a3b8" }}>Conversion Rate:</span>
                          <strong style={{ color: "#4ade80" }}>{((Number(objective.conversion_rate ?? 0)) * 100).toFixed(1)}%</strong>
                        </div>
                        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11 }}>
                          <span style={{ color: "#94a3b8" }}>VPs Targeted / Secured:</span>
                          <strong style={{ color: "#f8fafc" }}>
                            {Number(objective.vps_captured_count ?? 0)} / {Number(objective.total_vps_targeted ?? 0)}
                          </strong>
                        </div>
                        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11 }}>
                          <span style={{ color: "#94a3b8" }}>Conversion Latency:</span>
                          <strong style={{ color: "#f8fafc" }}>{Number(objective.mean_conversion_latency_steps ?? 0)} steps</strong>
                        </div>
                        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11 }}>
                          <span style={{ color: "#94a3b8" }}>Target Oscillation:</span>
                          <strong style={{ color: Number(objective.target_switches ?? 0) >= 4 ? "#fbbf24" : "#cbd5e1" }}>
                            {Number(objective.target_switches ?? 0)} switches
                          </strong>
                        </div>
                      </div>
                      <div style={{ marginTop: 12, borderTop: "1px solid #334155", paddingTop: 8 }}>
                        {(objective.observations as Array<string> || []).map((obs, oi) => (
                          <div key={oi} style={{ fontSize: 10, color: "#cbd5e1", marginTop: 4, lineHeight: 1.4 }}>
                            • {obs}
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* TAB 3: DECISIVE TURNING POINTS */}
              {activeTab === "turning_points" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  <div style={{ fontSize: 12, color: "#94a3b8" }}>
                    Chronological audit of decisive moments that dictated victory margin. Click "Seek Step" to inspect that point in the replay board.
                  </div>
                  {turningPoints.length === 0 ? (
                    <div style={{ padding: 20, textAlign: "center", color: "#64748b" }}>
                      No critical turning points detected (match had low attrition or short duration).
                    </div>
                  ) : (
                    turningPoints.map((tp, idx) => {
                      const sevBadge = getSeverityBadge(String(tp.severity));
                      const evtBadge = getEventBadge(String(tp.event_type));
                      return (
                        <div
                          key={idx}
                          style={{
                            background: "#1e293b",
                            border: `1px solid ${sevBadge.border}`,
                            borderRadius: 8,
                            padding: 14,
                            display: "flex",
                            flexDirection: "column",
                            gap: 8,
                          }}
                        >
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                              <span style={{ fontSize: 16 }}>{evtBadge.icon}</span>
                              <span style={{ fontSize: 13, fontWeight: 700, color: evtBadge.color }}>
                                {String(tp.title)}
                              </span>
                              <span
                                style={{
                                  fontSize: 10,
                                  fontWeight: 700,
                                  padding: "2px 6px",
                                  borderRadius: 4,
                                  background: sevBadge.bg,
                                  border: `1px solid ${sevBadge.border}`,
                                  color: sevBadge.color,
                                }}
                              >
                                {String(tp.severity)}
                              </span>
                            </div>
                            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                              <span style={{ fontSize: 11, color: "#94a3b8" }}>
                                Turn {Number(tp.turn)} | Step {Number(tp.step)}
                              </span>
                              {onJumpToStep && (
                                <button
                                  onClick={() => {
                                    onJumpToStep(Number(tp.step));
                                    onClose();
                                  }}
                                  style={{
                                    background: "rgba(14, 165, 233, 0.2)",
                                    border: "1px solid #0284c7",
                                    color: "#38bdf8",
                                    fontSize: 11,
                                    fontWeight: 600,
                                    padding: "3px 8px",
                                    borderRadius: 4,
                                    cursor: "pointer",
                                  }}
                                  title="Jump replay timeline directly to this decisive event"
                                >
                                  ▶ Seek Step
                                </button>
                              )}
                            </div>
                          </div>

                          <div style={{ fontSize: 12, color: "#cbd5e1", lineHeight: 1.5 }}>
                            {String(tp.description)}
                          </div>

                          {Boolean(tp.causal_impact) && (
                            <div
                              style={{
                                fontSize: 11,
                                color: "#93c5fd",
                                background: "rgba(59, 130, 246, 0.1)",
                                padding: "6px 10px",
                                borderRadius: 4,
                                borderLeft: "3px solid #3b82f6",
                              }}
                            >
                              <strong>Causal Impact:</strong> {String(tp.causal_impact)}
                            </div>
                          )}
                        </div>
                      );
                    })
                  )}
                </div>
              )}

              {/* TAB 4: DOCTRINAL GROUNDING (RAG) */}
              {activeTab === "doctrine" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                  <div style={{ fontSize: 12, color: "#94a3b8" }}>
                    Automated citations retrieved from official Assault rulebooks via <code>assault_rag</code> explaining tactical resolution rules.
                  </div>

                  {citations.length === 0 ? (
                    <div style={{ padding: 20, textAlign: "center", color: "#64748b" }}>
                      No doctrinal citations retrieved for this episode.
                    </div>
                  ) : (
                    citations.map((cite, cIdx) => (
                      <div
                        key={cIdx}
                        style={{
                          background: "#1e293b",
                          border: "1px solid #334155",
                          borderRadius: 8,
                          padding: 14,
                          display: "flex",
                          flexDirection: "column",
                          gap: 6,
                        }}
                      >
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                          <span style={{ fontSize: 13, fontWeight: 700, color: "#38bdf8" }}>
                            {String(cite.topic || cite.rule_id)}
                          </span>
                          <span style={{ fontSize: 10, color: "#64748b" }}>
                            Source: <code>{String(cite.source || "Rulebook")}</code>
                          </span>
                        </div>
                        <div style={{ fontSize: 11, color: "#fbbf24", fontStyle: "italic" }}>
                          {String(cite.relevance_reason)}
                        </div>
                        <div
                          style={{
                            fontSize: 11,
                            color: "#cbd5e1",
                            background: "rgba(0, 0, 0, 0.2)",
                            padding: "8px 10px",
                            borderRadius: 4,
                            fontFamily: "monospace",
                            whiteSpace: "pre-wrap",
                            lineHeight: 1.4,
                          }}
                        >
                          {String(cite.text_snippet)}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div
          style={{
            padding: "12px 20px",
            borderTop: "1px solid #1e293b",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            background: "#0b1329",
            fontSize: 11,
            color: "#64748b",
          }}
        >
          <div>Assault Forensic Engine v2.5.19 | Strictly grounded in ground-truth telemetry</div>
          <button
            onClick={onClose}
            style={{
              background: "#334155",
              border: "none",
              color: "#f8fafc",
              padding: "6px 14px",
              borderRadius: 4,
              fontSize: 12,
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Close SitRep
          </button>
        </div>
      </div>
    </div>
  );
};
