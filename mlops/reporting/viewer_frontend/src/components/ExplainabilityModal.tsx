import { useState, useMemo } from "react";
import type { Dict } from "../types";

export interface ChannelAttribution {
  channel_index: number;
  channel_name: string;
  group: string;
  raw_attribution: number;
  importance: number;
  percentage: number;
  direction: "support" | "oppose";
}

export interface GroupAttribution {
  name: string;
  raw_score: number;
  importance: number;
  percentage: number;
  direction: "support" | "oppose";
}

export interface InfluentialHex {
  q: number;
  r: number;
  score: number;
  abs_score: number;
  dominant_channel: string;
  dominant_group: string;
  dominant_value: number;
  impact: "favorable" | "unfavorable";
  description: string;
}

export interface ExplainabilityPayload extends Dict {
  ok: boolean;
  error?: string;
  run_dir?: string;
  scenario_id?: string;
  episode_id?: string;
  step_index?: number;
  turn?: number;
  to_play?: string;
  unit_id?: string;
  action_id?: string;
  action_kind?: string;
  action_index?: number;
  score_target?: number;
  score_baseline?: number;
  score_delta?: number;
  total_abs_attribution?: number;
  execution_time_ms?: number;
  tactical_rationale?: string;
  group_attributions?: Record<string, GroupAttribution>;
  channel_attributions?: ChannelAttribution[];
  spatial_heatmaps?: Record<string, Array<{ q: number; r: number; value: number }>>;
  top_influential_hexes?: InfluentialHex[];
}

const GROUP_COLORS: Record<string, string> = {
  COVER_TERRAIN: "#22c55e",
  LOS_VISIBILITY: "#06b6d4",
  THREAT_MAP: "#ef4444",
  VP_PROXIMITY: "#f59e0b",
  DOCTRINE_ROLE: "#a855f7",
  UNIT_STATE_TACTICAL: "#3b82f6",
  OTHER: "#94a3b8",
};

export function ExplainabilityModal({
  isOpen,
  onClose,
  data,
  isLoading,
  onApplyHeatmapToBoard,
}: {
  isOpen: boolean;
  onClose: () => void;
  data: ExplainabilityPayload | null;
  isLoading?: boolean;
  onApplyHeatmapToBoard?: (layerKey: string, hexes: Array<{ q: number; r: number; value: number }>) => void;
}) {
  const [activeLayer, setActiveLayer] = useState<string>("composite");
  const [tableFilter, setTableFilter] = useState<string>("all");
  const [copied, setCopied] = useState<boolean>(false);

  const availableLayers = useMemo(() => {
    if (!data?.spatial_heatmaps) return [];
    return Object.keys(data.spatial_heatmaps).filter((k) => {
      const arr = data.spatial_heatmaps?.[k];
      return Array.isArray(arr) && arr.length > 0;
    });
  }, [data]);

  const filteredChannels = useMemo(() => {
    const list = data?.channel_attributions || [];
    if (tableFilter === "all") return list;
    if (tableFilter === "top10") return list.slice(0, 10);
    return list.filter((c) => c.group === tableFilter);
  }, [data, tableFilter]);

  if (!isOpen) return null;

  const handleLayerSelect = (layer: string) => {
    setActiveLayer(layer);
    if (onApplyHeatmapToBoard && data?.spatial_heatmaps?.[layer]) {
      onApplyHeatmapToBoard(layer, data.spatial_heatmaps[layer]);
    }
  };

  const handleCopyRationale = () => {
    if (data?.tactical_rationale) {
      navigator.clipboard.writeText(data.tactical_rationale);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: "rgba(15, 23, 42, 0.8)",
        backdropFilter: "blur(4px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
        padding: 16,
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        style={{
          backgroundColor: "#0f172a",
          border: "1px solid #334155",
          borderRadius: 8,
          width: "100%",
          maxWidth: 960,
          maxHeight: "92vh",
          display: "flex",
          flexDirection: "column",
          boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.5)",
          color: "#f8fafc",
          overflow: "hidden",
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: "16px 20px",
            borderBottom: "1px solid #334155",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            background: "#1e293b",
          }}
        >
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ fontSize: 18, fontWeight: 700, color: "#38bdf8" }}>
                🧠 Spatial Causal Attribution (IGNH & Grad-CAM)
              </span>
              {data?.to_play && (
                <span
                  style={{
                    fontSize: 11,
                    fontWeight: 700,
                    padding: "2px 8px",
                    borderRadius: 4,
                    background: data.to_play === "GE" || data.to_play === "AXIS" ? "#450a0a" : "#082f49",
                    color: data.to_play === "GE" || data.to_play === "AXIS" ? "#fca5a5" : "#7dd3fc",
                    border: `1px solid ${data.to_play === "GE" || data.to_play === "AXIS" ? "#dc2626" : "#0284c7"}`,
                  }}
                >
                  {data.to_play}
                </span>
              )}
              {data?.action_kind && (
                <span
                  style={{
                    fontSize: 11,
                    fontWeight: 700,
                    padding: "2px 8px",
                    borderRadius: 4,
                    background: "rgba(168, 85, 247, 0.2)",
                    color: "#c084fc",
                    border: "1px solid #a855f7",
                  }}
                >
                  {data.action_kind}
                </span>
              )}
            </div>
            <div style={{ fontSize: 12, color: "#94a3b8", marginTop: 4 }}>
              Unit: <b style={{ color: "#f8fafc" }}>{data?.unit_id || "Unknown"}</b> | Action:{" "}
              <code style={{ color: "#facc15" }}>{data?.action_id || "N/A"}</code> | Step {data?.step_index ?? "-"} (Turn{" "}
              {data?.turn ?? "-"})
            </div>
          </div>

          <button
            onClick={onClose}
            style={{
              background: "transparent",
              border: "none",
              color: "#94a3b8",
              fontSize: 22,
              cursor: "pointer",
              padding: "4px 8px",
              lineHeight: 1,
            }}
            title="Close (ESC)"
          >
            ✕
          </button>
        </div>

        {/* Content Body */}
        <div style={{ padding: 20, overflowY: "auto", flex: 1, display: "flex", flexDirection: "column", gap: 16 }}>
          {isLoading && (
            <div style={{ textAlign: "center", padding: "40px 0", color: "#38bdf8" }}>
              <div style={{ fontSize: 16, fontWeight: 600 }}>Computing Integrated Gradients on Hex Grid...</div>
              <div style={{ fontSize: 12, color: "#94a3b8", marginTop: 6 }}>
                Evaluating model policy sensitivity across sensory channel spectrum
              </div>
            </div>
          )}

          {!isLoading && data?.ok === false && (
            <div
              style={{
                background: "rgba(239, 68, 68, 0.15)",
                border: "1px solid #ef4444",
                borderRadius: 6,
                padding: 16,
                color: "#fca5a5",
              }}
            >
              <div style={{ fontWeight: 700, fontSize: 14 }}>Attribution Analysis Failed</div>
              <div style={{ fontSize: 12, marginTop: 4 }}>{data.error || "Unknown error occurred"}</div>
            </div>
          )}

          {!isLoading && data?.ok && (
            <>
              {/* Top KPI Cards */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12 }}>
                <div style={{ background: "#1e293b", padding: 12, borderRadius: 6, border: "1px solid #334155" }}>
                  <div style={{ fontSize: 11, color: "#94a3b8" }}>Target Policy Score S(a*)</div>
                  <div style={{ fontSize: 18, fontWeight: 700, color: "#38bdf8", marginTop: 2 }}>
                    {data.score_target !== undefined ? data.score_target.toFixed(3) : "-"}
                  </div>
                </div>

                <div style={{ background: "#1e293b", padding: 12, borderRadius: 6, border: "1px solid #334155" }}>
                  <div style={{ fontSize: 11, color: "#94a3b8" }}>Baseline Score S0</div>
                  <div style={{ fontSize: 18, fontWeight: 700, color: "#94a3b8", marginTop: 2 }}>
                    {data.score_baseline !== undefined ? data.score_baseline.toFixed(3) : "-"}
                  </div>
                </div>

                <div style={{ background: "#1e293b", padding: 12, borderRadius: 6, border: "1px solid #334155" }}>
                  <div style={{ fontSize: 11, color: "#94a3b8" }}>Net Activation Delta (ΔS)</div>
                  <div
                    style={{
                      fontSize: 18,
                      fontWeight: 700,
                      color: Number(data.score_delta || 0) >= 0 ? "#22c55e" : "#ef4444",
                      marginTop: 2,
                    }}
                  >
                    {data.score_delta !== undefined
                      ? `${data.score_delta >= 0 ? "+" : ""}${data.score_delta.toFixed(3)}`
                      : "-"}
                  </div>
                </div>

                <div style={{ background: "#1e293b", padding: 12, borderRadius: 6, border: "1px solid #334155" }}>
                  <div style={{ fontSize: 11, color: "#94a3b8" }}>Compute Latency</div>
                  <div style={{ fontSize: 18, fontWeight: 700, color: "#facc15", marginTop: 2 }}>
                    {data.execution_time_ms !== undefined ? `${data.execution_time_ms} ms` : "-"}
                  </div>
                </div>
              </div>

              {/* Tactical Rationale Box */}
              {data.tactical_rationale && (
                <div
                  style={{
                    background: "rgba(14, 165, 233, 0.08)",
                    border: "1px solid #0284c7",
                    borderRadius: 6,
                    padding: 12,
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "flex-start",
                    gap: 12,
                  }}
                >
                  <div>
                    <div style={{ fontSize: 11, fontWeight: 700, color: "#38bdf8", textTransform: "uppercase" }}>
                      Tactical Decision Rationale (IGNH Synthesis)
                    </div>
                    <div style={{ fontSize: 13, color: "#e2e8f0", marginTop: 4, lineHeight: 1.5 }}>
                      "{data.tactical_rationale}"
                    </div>
                  </div>
                  <button
                    onClick={handleCopyRationale}
                    style={{
                      background: "#1e293b",
                      border: "1px solid #334155",
                      color: copied ? "#22c55e" : "#94a3b8",
                      fontSize: 11,
                      padding: "4px 8px",
                      borderRadius: 4,
                      cursor: "pointer",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {copied ? "✓ Copied" : "📋 Copy"}
                  </button>
                </div>
              )}

              {/* Sensory Channel Groups Progress Breakdown */}
              <div style={{ background: "#1e293b", padding: 16, borderRadius: 6, border: "1px solid #334155" }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", marginBottom: 12 }}>
                  Sensory Channel Groups (Relative Influence)
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  {Object.entries(data.group_attributions || {}).map(([key, grp]) => {
                    const color = GROUP_COLORS[key] || "#94a3b8";
                    const isSupport = grp.direction === "support";
                    return (
                      <div key={key}>
                        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 3 }}>
                          <span style={{ fontWeight: 600, color: "#f8fafc" }}>{grp.name}</span>
                          <span style={{ color: isSupport ? "#22c55e" : "#ef4444", fontWeight: 700 }}>
                            {grp.percentage}% ({isSupport ? "+ Support" : "- Deterrent"})
                          </span>
                        </div>
                        <div style={{ height: 8, background: "#0f172a", borderRadius: 4, overflow: "hidden" }}>
                          <div
                            style={{
                              height: "100%",
                              width: `${Math.min(100, Math.max(0, grp.percentage))}%`,
                              backgroundColor: color,
                              borderRadius: 4,
                            }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Spatial Hexagonal Layer Heatmap Controls */}
              {availableLayers.length > 0 && (
                <div style={{ background: "#1e293b", padding: 16, borderRadius: 6, border: "1px solid #334155" }}>
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      marginBottom: 10,
                      flexWrap: "wrap",
                      gap: 8,
                    }}
                  >
                    <div style={{ fontSize: 12, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase" }}>
                      Spatial Hexagonal Attribution Heatmap
                    </div>
                    {onApplyHeatmapToBoard && (
                      <span style={{ fontSize: 11, color: "#38bdf8" }}>
                        Click a layer below to inspect hex overlay on replay canvas
                      </span>
                    )}
                  </div>

                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                    {availableLayers.map((layer) => {
                      const isSelected = activeLayer === layer;
                      const count = (data.spatial_heatmaps?.[layer] || []).length;
                      return (
                        <button
                          key={layer}
                          onClick={() => handleLayerSelect(layer)}
                          style={{
                            padding: "6px 12px",
                            fontSize: 11,
                            fontWeight: 600,
                            borderRadius: 4,
                            border: `1px solid ${isSelected ? "#38bdf8" : "#334155"}`,
                            background: isSelected ? "rgba(14, 165, 233, 0.2)" : "#0f172a",
                            color: isSelected ? "#38bdf8" : "#cbd5e1",
                            cursor: "pointer",
                          }}
                        >
                          {layer.toUpperCase()} ({count} hexes)
                        </button>
                      );
                    })}
                  </div>

                  {/* Summary of Active Layer */}
                  {data.spatial_heatmaps?.[activeLayer] && (
                    <div
                      style={{
                        marginTop: 12,
                        padding: 10,
                        background: "#0f172a",
                        borderRadius: 4,
                        fontSize: 11,
                        color: "#94a3b8",
                      }}
                    >
                      Layer: <b style={{ color: "#38bdf8" }}>{activeLayer}</b> | Total active hex cells:{" "}
                      <b style={{ color: "#f8fafc" }}>{data.spatial_heatmaps[activeLayer].length}</b>
                    </div>
                  )}
                </div>
              )}

              {/* Top Influential Hexes */}
              {Array.isArray(data.top_influential_hexes) && data.top_influential_hexes.length > 0 && (
                <div style={{ background: "#1e293b", padding: 16, borderRadius: 6, border: "1px solid #334155" }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", marginBottom: 10 }}>
                    Top Influential Board Hexes
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 10 }}>
                    {data.top_influential_hexes.map((hex, idx) => {
                      const isFavorable = hex.impact === "favorable";
                      return (
                        <div
                          key={idx}
                          style={{
                            background: "#0f172a",
                            border: `1px solid ${isFavorable ? "rgba(34, 197, 94, 0.3)" : "rgba(239, 68, 68, 0.3)"}`,
                            borderRadius: 6,
                            padding: 10,
                          }}
                        >
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                            <span style={{ fontWeight: 700, fontSize: 12, color: "#f8fafc" }}>
                              Hex ({hex.q}, {hex.r})
                            </span>
                            <span
                              style={{
                                fontSize: 11,
                                fontWeight: 700,
                                color: isFavorable ? "#22c55e" : "#ef4444",
                              }}
                            >
                              {hex.score >= 0 ? "+" : ""}
                              {hex.score.toFixed(3)}
                            </span>
                          </div>
                          <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 4 }}>
                            Driver: <b style={{ color: "#e2e8f0" }}>{hex.dominant_channel}</b>
                          </div>
                          <div style={{ fontSize: 10, color: "#64748b", marginTop: 2 }}>{hex.description}</div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Detailed Channels Spectrum Table */}
              <div style={{ background: "#1e293b", padding: 16, borderRadius: 6, border: "1px solid #334155" }}>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    marginBottom: 10,
                    flexWrap: "wrap",
                    gap: 8,
                  }}
                >
                  <div style={{ fontSize: 12, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase" }}>
                    Sensory Channel Spectrum ({filteredChannels.length} channels)
                  </div>
                  <div style={{ display: "flex", gap: 6 }}>
                    <select
                      value={tableFilter}
                      onChange={(e) => setTableFilter(e.target.value)}
                      style={{
                        background: "#0f172a",
                        border: "1px solid #334155",
                        color: "#f8fafc",
                        fontSize: 11,
                        padding: "4px 8px",
                        borderRadius: 4,
                      }}
                    >
                      <option value="all">All Channels</option>
                      <option value="top10">Top 10 Influential</option>
                      <option value="COVER_TERRAIN">Cover & Fortifications</option>
                      <option value="LOS_VISIBILITY">LOS & Concealment</option>
                      <option value="THREAT_MAP">Threat Field</option>
                      <option value="VP_PROXIMITY">VP Proximity</option>
                      <option value="DOCTRINE_ROLE">Doctrine Profile</option>
                      <option value="UNIT_STATE_TACTICAL">Unit State</option>
                    </select>
                  </div>
                </div>

                <div style={{ overflowX: "auto", maxHeight: 240, overflowY: "auto" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
                    <thead>
                      <tr style={{ borderBottom: "1px solid #334155", color: "#94a3b8", textAlign: "left" }}>
                        <th style={{ padding: "6px 8px" }}>Ch #</th>
                        <th style={{ padding: "6px 8px" }}>Channel Name</th>
                        <th style={{ padding: "6px 8px" }}>Group</th>
                        <th style={{ padding: "6px 8px" }}>Raw Attribution</th>
                        <th style={{ padding: "6px 8px" }}>Importance</th>
                        <th style={{ padding: "6px 8px" }}>% Impact</th>
                        <th style={{ padding: "6px 8px" }}>Direction</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredChannels.map((c) => {
                        const isSupp = c.direction === "support";
                        return (
                          <tr key={c.channel_index} style={{ borderBottom: "1px solid #1e293b" }}>
                            <td style={{ padding: "6px 8px", color: "#64748b" }}>{c.channel_index}</td>
                            <td style={{ padding: "6px 8px", fontWeight: 600, color: "#f8fafc" }}>
                              <code>{c.channel_name}</code>
                            </td>
                            <td style={{ padding: "6px 8px", color: GROUP_COLORS[c.group] || "#94a3b8" }}>
                              {c.group}
                            </td>
                            <td style={{ padding: "6px 8px", color: c.raw_attribution >= 0 ? "#22c55e" : "#ef4444" }}>
                              {c.raw_attribution >= 0 ? "+" : ""}
                              {c.raw_attribution.toFixed(4)}
                            </td>
                            <td style={{ padding: "6px 8px", color: "#cbd5e1" }}>{c.importance.toFixed(4)}</td>
                            <td style={{ padding: "6px 8px", fontWeight: 700, color: "#38bdf8" }}>
                              {c.percentage.toFixed(2)}%
                            </td>
                            <td style={{ padding: "6px 8px" }}>
                              <span
                                style={{
                                  fontSize: 10,
                                  fontWeight: 700,
                                  padding: "2px 6px",
                                  borderRadius: 3,
                                  background: isSupp ? "rgba(34, 197, 94, 0.15)" : "rgba(239, 68, 68, 0.15)",
                                  color: isSupp ? "#22c55e" : "#ef4444",
                                }}
                              >
                                {isSupp ? "+ Support" : "- Deterrent"}
                              </span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div
          style={{
            padding: "12px 20px",
            borderTop: "1px solid #334155",
            display: "flex",
            justifyContent: "flex-end",
            background: "#1e293b",
          }}
        >
          <button
            onClick={onClose}
            style={{
              background: "#334155",
              border: "none",
              color: "#f8fafc",
              padding: "6px 16px",
              borderRadius: 4,
              cursor: "pointer",
              fontWeight: 600,
              fontSize: 12,
            }}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
