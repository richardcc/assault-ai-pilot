import React, { useState } from "react";
import type { CurriculumStepMetric } from "../curriculumMetrics";

interface CurriculumLineageFlowProps {
  steps: CurriculumStepMetric[];
  selectedRunId?: string;
  onSelectRunId?: (runId: string) => void;
}

export function CurriculumLineageFlow({
  steps,
  selectedRunId,
  onSelectRunId,
}: CurriculumLineageFlowProps) {
  const [showMilestones, setShowMilestones] = useState(true);

  if (!steps || steps.length === 0) return null;

  // Filter chosen steps (one per phase marked with isPhaseSelected, fallback to all if none)
  const chosenSteps = steps.filter((s) => s.isPhaseSelected);
  const displayNodes = chosenSteps.length > 0 ? chosenSteps : steps;

  const peakElo = Math.max(...steps.map((s) => s.elo ?? 0), 0);
  const initialStep = displayNodes[0];
  const latestStep = displayNodes[displayNodes.length - 1];
  const netEloGain = (latestStep?.elo ?? 0) - (initialStep?.elo ?? 0);

  return (
    <div
      style={{
        background: "#080e1a",
        border: "1px solid #1e293b",
        borderRadius: 8,
        padding: "14px 16px",
        marginBottom: 16,
        boxShadow: "0 4px 16px rgba(0, 0, 0, 0.4)",
      }}
    >
      {/* Header Bar */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 12,
          flexWrap: "wrap",
          gap: 10,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <span style={{ fontSize: 14, fontWeight: 700, color: "#f59e0b", display: "flex", alignItems: "center", gap: 6 }}>
            <span>🗺️</span> Curriculum Lineage Pipeline Flow
          </span>
          <span
            style={{
              fontSize: 11,
              background: "#451a03",
              border: "1px solid #f59e0b80",
              color: "#fde047",
              padding: "2px 8px",
              borderRadius: 4,
              fontWeight: 700,
            }}
          >
            ★ {displayNodes.length} Golden Path Checkpoints
          </span>
          <span
            style={{
              fontSize: 11,
              background: "#0284c725",
              border: "1px solid #0284c750",
              color: "#38bdf8",
              padding: "2px 8px",
              borderRadius: 4,
              fontWeight: 600,
            }}
          >
            Δ Global: {netEloGain >= 0 ? `+${netEloGain}` : netEloGain} pts ELO
          </span>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <button
            onClick={() => setShowMilestones((v) => !v)}
            style={{
              fontSize: 11,
              background: showMilestones ? "#3b82f625" : "#1e293b",
              border: `1px solid ${showMilestones ? "#3b82f6" : "#334155"}`,
              color: showMilestones ? "#93c5fd" : "#94a3b8",
              padding: "4px 10px",
              borderRadius: 4,
              cursor: "pointer",
              fontWeight: 600,
              display: "flex",
              alignItems: "center",
              gap: 4,
            }}
          >
            <span>📖</span> {showMilestones ? "Hide Tactical Milestones" : "View Tactical Milestones"}
          </button>
        </div>
      </div>

      {/* Visual Pipeline Flowchart (Horizontal Scrollable Nodes) */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          overflowX: "auto",
          paddingBottom: 10,
          paddingTop: 4,
        }}
      >
        {displayNodes.map((node, idx) => {
          const isPeak = (node.elo ?? 0) === peakElo && peakElo > 0;
          const isSelected = selectedRunId === node.runId;
          const cleanPhase = node.phaseName
            .replace(/^phase\d+_/i, "")
            .replace(/_v\d+.*$/i, "")
            .replace(/_/g, " ");

          const isPromoted =
            node.gateStatus === "PASS" ||
            node.promotionDecision === "promote" ||
            node.promotionDecision === "promote_best_of_cycles";

          const isHeld =
            node.gateStatus === "FAIL" ||
            node.promotionDecision === "hold";

          return (
            <React.Fragment key={node.runId}>
              {/* Node Card */}
              <div
                onClick={() => onSelectRunId?.(node.runId)}
                style={{
                  minWidth: 200,
                  maxWidth: 240,
                  flexShrink: 0,
                  background: isPeak
                    ? "linear-gradient(145deg, #1f1604, #0b1220)"
                    : isSelected
                    ? "#13233c"
                    : "#0c1527",
                  border: isPeak
                    ? "2px solid #f59e0b"
                    : isSelected
                    ? "2px solid #38bdf8"
                    : "1px solid #1e293b",
                  borderRadius: 8,
                  padding: "10px 12px",
                  cursor: "pointer",
                  boxShadow: isPeak
                    ? "0 0 14px rgba(245, 158, 11, 0.35)"
                    : isSelected
                    ? "0 0 12px rgba(56, 189, 248, 0.3)"
                    : "none",
                  transition: "all 0.15s ease-in-out",
                  position: "relative",
                }}
                title={`Click to inspect run ${node.runId}`}
              >
                {/* Peak Badge */}
                {isPeak && (
                  <div
                    style={{
                      position: "absolute",
                      top: -10,
                      right: 10,
                      background: "#f59e0b",
                      color: "#000000",
                      fontSize: 9,
                      fontWeight: 800,
                      padding: "1px 6px",
                      borderRadius: 3,
                      boxShadow: "0 2px 4px rgba(0,0,0,0.5)",
                      letterSpacing: "0.5px",
                    }}
                  >
                    ★ ALL-TIME PEAK
                  </div>
                )}

                {/* Node Phase & Step Index */}
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                  <span
                    style={{
                      fontSize: 10,
                      fontWeight: 700,
                      textTransform: "uppercase",
                      color: isPeak ? "#fde047" : "#38bdf8",
                      background: isPeak ? "#78350f50" : "#0284c725",
                      padding: "1px 5px",
                      borderRadius: 3,
                    }}
                  >
                    Phase {node.phaseGroupIndex + 1}
                  </span>
                  <span style={{ fontSize: 10, color: "#64748b" }}>
                    C{node.cycleInPhase}/{node.totalCyclesInPhase}
                  </span>
                </div>

                {/* Phase Name & Run ID */}
                <div style={{ fontWeight: 700, fontSize: 12, color: "#f8fafc", marginBottom: 2, textTransform: "capitalize" }}>
                  {cleanPhase}
                </div>
                <div
                  style={{
                    fontSize: 10,
                    fontFamily: "monospace",
                    color: isSelected ? "#38bdf8" : "#94a3b8",
                    marginBottom: 8,
                  }}
                >
                  {node.runId.length > 20 ? node.runId.substring(0, 20) + "…" : node.runId}
                </div>

                {/* ELO & Delta Pill */}
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                  <span className="muted" style={{ fontSize: 11 }}>Calibrated ELO:</span>
                  <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <span style={{ fontWeight: 800, fontSize: 13, color: isPeak ? "#fde047" : "#e2e8f0" }}>
                      {node.elo ?? "-"}
                    </span>
                    {node.deltaElo !== null && node.deltaElo !== 0 && (
                      <span
                        style={{
                          fontSize: 10,
                          fontWeight: 700,
                          color: node.deltaElo > 0 ? "#34d399" : "#f87171",
                        }}
                      >
                        {node.deltaElo > 0 ? `+${node.deltaElo}` : node.deltaElo}
                      </span>
                    )}
                  </div>
                </div>

                {/* Win Rate & Net VP */}
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 11 }}>
                  <span className="muted">Win Rate:</span>
                  <span style={{ fontWeight: 700, color: (node.winRate ?? 0) >= 0.5 ? "#34d399" : "#cbd5e1" }}>
                    {node.winRate !== null ? `${(node.winRate * 100).toFixed(1)}%` : "-"}
                  </span>
                </div>

                {/* Status indicator */}
                <div style={{ marginTop: 6, paddingTop: 6, borderTop: "1px solid #1e293b", display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 10 }}>
                  {isPromoted ? (
                    <span style={{ color: "#10b981", fontWeight: 700 }}>
                      ★ PROMOTED
                    </span>
                  ) : isHeld ? (
                    <span style={{ color: "#f87171", fontWeight: 700 }}>
                      ⚠️ GATE FAILED (HOLD)
                    </span>
                  ) : (
                    <span style={{ color: "#94a3b8", fontWeight: 600 }}>
                      EVALUATED
                    </span>
                  )}
                  <span style={{ color: "#64748b" }}>
                    {node.checkpoint && node.checkpoint !== "-" ? "Checkpoint OK" : "In Progress"}
                  </span>
                </div>
              </div>

              {/* Arrow Connector between nodes */}
              {idx < displayNodes.length - 1 && (
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    gap: 2,
                    flexShrink: 0,
                    padding: "0 2px",
                  }}
                >
                  <span style={{ fontSize: 18, color: "#f59e0b" }}>➔</span>
                  <span style={{ fontSize: 8, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.4px" }}>
                    Weights
                  </span>
                </div>
              )}
            </React.Fragment>
          );
        })}
      </div>

      {/* Dynamic Key Progression Milestones Cards */}
      {showMilestones && (
        <div style={{ marginTop: 16, paddingTop: 14, borderTop: "1px solid #1e293b" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 10 }}>
            <span style={{ fontSize: 13, fontWeight: 700, color: "#e2e8f0" }}>
              🏆 Key Tactical Progression Milestones
            </span>
            <span className="muted" style={{ fontSize: 11 }}>
              (Forensic analysis of doctrinal transitions and bottleneck resolutions)
            </span>
          </div>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
              gap: 12,
            }}
          >
            {/* Milestone 1 */}
            <div
              style={{
                background: "#0c1527",
                border: "1px solid #1e3a5f",
                borderRadius: 6,
                padding: "10px 12px",
                display: "flex",
                flexDirection: "column",
                gap: 6,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 6 }}>
                <span style={{ fontWeight: 700, fontSize: 12, color: "#38bdf8", display: "flex", alignItems: "center", gap: 5 }}>
                  <span>🚀</span> 1. Tactical Leap (Phase 1 ➔ Phase 2)
                </span>
                <span
                  style={{
                    fontSize: 10,
                    fontWeight: 700,
                    background: "#065f46",
                    color: "#a7f3d0",
                    padding: "1px 6px",
                    borderRadius: 3,
                    whiteSpace: "nowrap",
                  }}
                >
                  +541 ELO (484 ➔ 1025)
                </span>
              </div>
              <p style={{ margin: 0, fontSize: 11, color: "#cbd5e1", lineHeight: 1.4 }}>
                Transitioning from simple approach to coordinated mortar assault (<code>ROLE_FIRE_SUPPORT</code>), the
                agent learned not to stall in open terrain, raising calibrated ELO from 484 to 1025 in cycle 1 (<code>47512000</code>).
              </p>
            </div>

            {/* Milestone 2 */}
            <div
              style={{
                background: "#0c1527",
                border: "1px solid #1e3a5f",
                borderRadius: 6,
                padding: "10px 12px",
                display: "flex",
                flexDirection: "column",
                gap: 6,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 6 }}>
                <span style={{ fontWeight: 700, fontSize: 12, color: "#a78bfa", display: "flex", alignItems: "center", gap: 5 }}>
                  <span>⚔️</span> 2. Symmetric Contest (Phase 3)
                </span>
                <span
                  style={{
                    fontSize: 10,
                    fontWeight: 700,
                    background: "#4c1d95",
                    color: "#ddd6fe",
                    padding: "1px 6px",
                    borderRadius: 3,
                    whiteSpace: "nowrap",
                  }}
                >
                  +59 ELO (50.0% WR)
                </span>
              </div>
              <p style={{ margin: 0, fontSize: 11, color: "#cbd5e1", lineHeight: 1.4 }}>
                In the competitive 2v2 race, cycle 3 (<code>60a00b81</code>) achieved 50% win rate against bot,
                establishing the <code>ASSAULT_VP</code> posture and reaching 1117 ELO.
              </p>
            </div>

            {/* Milestone 3 */}
            <div
              style={{
                background: "linear-gradient(145deg, #1c1505, #0c1527)",
                border: "1px solid #b45309",
                borderRadius: 6,
                padding: "10px 12px",
                display: "flex",
                flexDirection: "column",
                gap: 6,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 6 }}>
                <span style={{ fontWeight: 700, fontSize: 12, color: "#fde047", display: "flex", alignItems: "center", gap: 5 }}>
                  <span>🏆</span> 3. Absolute Historical Peak (Phase 4 Gela)
                </span>
                <span
                  style={{
                    fontSize: 10,
                    fontWeight: 800,
                    background: "#f59e0b",
                    color: "#000000",
                    padding: "1px 6px",
                    borderRadius: 3,
                    whiteSpace: "nowrap",
                  }}
                >
                  ★ 1435 ELO (93.3% WR)
                </span>
              </div>
              <p style={{ margin: 0, fontSize: 11, color: "#fef08a", lineHeight: 1.4 }}>
                In Gela cycle 1 (<code>17d36438</code>), the model reached a record 1435 ELO and 93.3% win rate,
                consolidating as the top performing checkpoint (<code>runs/efficientzero_v2_17d36438/checkpoints/final.pt</code>).
              </p>
            </div>

            {/* Milestone 4 */}
            <div
              style={{
                background: "#0c1527",
                border: "1px solid #334155",
                borderRadius: 6,
                padding: "10px 12px",
                display: "flex",
                flexDirection: "column",
                gap: 6,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 6 }}>
                <span style={{ fontWeight: 700, fontSize: 12, color: "#f472b6", display: "flex", alignItems: "center", gap: 5 }}>
                  <span>🛡️</span> 4. Multi-Scenario Expansion & Timeout Tuning
                </span>
                <span
                  style={{
                    fontSize: 10,
                    fontWeight: 700,
                    background: "#831843",
                    color: "#fbcfe8",
                    padding: "1px 6px",
                    borderRadius: 3,
                    whiteSpace: "nowrap",
                  }}
                >
                  1369 ➔ 1140 ➔ RESOLVED
                </span>
              </div>
              <p style={{ margin: 0, fontSize: 11, color: "#cbd5e1", lineHeight: 1.4 }}>
                When introducing <code>mettete_i_piedi_terra_1</code> (12 turns), previous evaluation hit step limits early.
                With calibrated settings (<code>max_steps: 120/180</code> and self-play scaling with <code>vp_potential_weight: 1.5</code>),
                episodes complete naturally and convert contested positions into decisive victories.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
