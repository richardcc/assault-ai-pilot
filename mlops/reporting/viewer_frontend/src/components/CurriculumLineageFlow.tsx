import React from "react";
import type { CurriculumStepMetric } from "../curriculumMetrics";

export interface CanonicalPhaseDef {
  phaseKey: string;
  phaseTitle: string;
  phaseNumber: number;
  stageName: string;
  stageNumber: 1 | 2;
  targetWinRate?: number;
  targetCapturedAvg?: number;
  targetVpTakeRate?: number;
  description?: string;
}

export const FULL_ASSAULT_CAMPAIGN_PHASES: CanonicalPhaseDef[] = [
  // Stage 1: VP Acceleration & Objective Doctrine (5 Phases)
  {
    phaseKey: "phase1_vp_sprint_unoccupied",
    phaseTitle: "Vp Sprint Unoccupied",
    phaseNumber: 1,
    stageName: "Stage 1: Objective Doctrine",
    stageNumber: 1,
    targetWinRate: 0.80,
    targetCapturedAvg: 0.90,
    targetVpTakeRate: 0.12,
    description: "1 US vs 1 VP unoccupied at distance 3",
  },
  {
    phaseKey: "phase2_vp_assault_suppressed",
    phaseTitle: "Vp Assault Suppressed",
    phaseNumber: 2,
    stageName: "Stage 1: Objective Doctrine",
    stageNumber: 1,
    targetWinRate: 0.75,
    targetCapturedAvg: 0.90,
    targetVpTakeRate: 0.10,
    description: "Base of Fire (81mm Mortar) + Combined Assault",
  },
  {
    phaseKey: "phase3_vp_race_2v2",
    phaseTitle: "Vp Race 2v2",
    phaseNumber: 3,
    stageName: "Stage 1: Objective Doctrine",
    stageNumber: 1,
    targetWinRate: 0.30,
    targetCapturedAvg: 0.85,
    targetVpTakeRate: 0.035,
    description: "Simultaneous 2v2 sprint race to disputed VPs",
  },
  {
    phaseKey: "phase4_tactical_gela_mastery",
    phaseTitle: "Tactical Gela Mastery",
    phaseNumber: 4,
    stageName: "Stage 1: Objective Doctrine",
    stageNumber: 1,
    targetWinRate: 0.45,
    targetCapturedAvg: 2.00,
    targetVpTakeRate: 0.04,
    description: "Full tactical mastery in Gela (14 units, 5 VPs)",
  },
  {
    phaseKey: "phase5_urban_assault_pure_offensive",
    phaseTitle: "Urban Assault Pure Offensive",
    phaseNumber: 5,
    stageName: "Stage 1: Objective Doctrine",
    stageNumber: 1,
    targetWinRate: 0.45,
    targetCapturedAvg: 2.20,
    targetVpTakeRate: 0.02,
    description: "Attacker breakthrough in Battaglia Cittadina (T=10)",
  },

  // Stage 2: Multi-Scenario Progressive Self-Play vs Random (8 Phases)
  {
    phaseKey: "phase1_bootstrap",
    phaseTitle: "Bootstrap Multi-Map",
    phaseNumber: 6,
    stageName: "Stage 2: Multi-Scenario Self-Play",
    stageNumber: 2,
    targetWinRate: 0.60,
    targetCapturedAvg: 2.50,
    targetVpTakeRate: 0.08,
    description: "Gela (80%) + Mettete (20%) dual-scenario adaptation",
  },
  {
    phaseKey: "phase1_channel_adapt",
    phaseTitle: "Channel Adapt 38Ch",
    phaseNumber: 7,
    stageName: "Stage 2: Multi-Scenario Self-Play",
    stageNumber: 2,
    targetWinRate: 0.60,
    targetCapturedAvg: 2.55,
    targetVpTakeRate: 0.09,
    description: "38-channel sensory expansion adaptation",
  },
  {
    phaseKey: "phase1_refine_aggressive",
    phaseTitle: "Refine Aggressive",
    phaseNumber: 8,
    stageName: "Stage 2: Multi-Scenario Self-Play",
    stageNumber: 2,
    targetWinRate: 0.60,
    targetCapturedAvg: 2.60,
    targetVpTakeRate: 0.10,
    description: "Tactical aggressiveness refinement",
  },
  {
    phaseKey: "phase2_mix_70_30",
    phaseTitle: "Mix 70% Self / 30% Random",
    phaseNumber: 9,
    stageName: "Stage 2: Multi-Scenario Self-Play",
    stageNumber: 2,
    targetWinRate: 0.60,
    targetCapturedAvg: 2.65,
    targetVpTakeRate: 0.11,
    description: "Selfplay introduction (70/30 ratio)",
  },
  {
    phaseKey: "phase3_mix_50_50",
    phaseTitle: "Mix 50% Self / 50% Random",
    phaseNumber: 10,
    stageName: "Stage 2: Multi-Scenario Self-Play",
    stageNumber: 2,
    targetWinRate: 0.60,
    targetCapturedAvg: 2.70,
    targetVpTakeRate: 0.12,
    description: "Balanced selfplay & heuristic exploration",
  },
  {
    phaseKey: "phase4_mix_30_70",
    phaseTitle: "Mix 30% Self / 70% Random",
    phaseNumber: 11,
    stageName: "Stage 2: Multi-Scenario Self-Play",
    stageNumber: 2,
    targetWinRate: 0.62,
    targetCapturedAvg: 2.75,
    targetVpTakeRate: 0.13,
    description: "Advanced selfplay consolidation",
  },
  {
    phaseKey: "phase5_self_dominant_90_10",
    phaseTitle: "Self Dominant 90/10",
    phaseNumber: 12,
    stageName: "Stage 2: Multi-Scenario Self-Play",
    stageNumber: 2,
    targetWinRate: 0.64,
    targetCapturedAvg: 2.80,
    targetVpTakeRate: 0.14,
    description: "90% Selfplay domination",
  },
  {
    phaseKey: "phase6_self_only_stabilize",
    phaseTitle: "Self-Play Stabilization 100%",
    phaseNumber: 13,
    stageName: "Stage 2: Multi-Scenario Self-Play",
    stageNumber: 2,
    targetWinRate: 0.66,
    targetCapturedAvg: 2.85,
    targetVpTakeRate: 0.15,
    description: "100% Pure symmetric selfplay stabilization",
  },
];

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
  if (!steps || steps.length === 0) return null;

  const [viewMode, setViewMode] = React.useState<"canonical" | "chronological">("canonical");

  // Filter chosen steps (one per phase group marked with isPhaseSelected, fallback to all if none)
  const chosenSteps = steps.filter((s) => s.isPhaseSelected);
  const chronologicalDisplayNodes = chosenSteps.length > 0 ? chosenSteps : steps;

  const peakElo = Math.max(...steps.map((s) => s.elo ?? 0), 0);
  const initialStep = steps[0];
  const latestStep = steps[steps.length - 1];
  const netEloGain = (latestStep?.elo ?? 0) - (initialStep?.elo ?? 0);

  // Helper: Match a phase name to the canonical index (0 to 12)
  function matchCanonicalPhase(phaseName: string): number {
    const rawLower = phaseName.toLowerCase();
    const cleanLower = rawLower.replace(/^phase\d*_?/, "").replace(/_v\d+.*$/, "");
    return FULL_ASSAULT_CAMPAIGN_PHASES.findIndex((p) => {
      const pKeyLower = p.phaseKey.toLowerCase();
      const pClean = pKeyLower.replace(/^phase\d*_?/, "");
      return rawLower.includes(pKeyLower) || cleanLower.includes(pClean) || pKeyLower.includes(cleanLower);
    });
  }

  // Canonical mapping: Map each of the 13 canonical phases 1-to-1
  const canonicalItems = FULL_ASSAULT_CAMPAIGN_PHASES.map((def, cIdx) => {
    const matchingSteps = steps.filter((s) => matchCanonicalPhase(s.phaseName) === cIdx);
    if (matchingSteps.length === 0) {
      return {
        isExecuted: false as const,
        canonicalDef: def,
        step: null as CurriculumStepMetric | null,
        cyclesCount: 0,
        allMatchingSteps: [] as CurriculumStepMetric[],
      };
    }

    // Pick best representative step for this canonical phase:
    // 1. Any cycle that passed the gate
    // 2. Any cycle explicitly marked isPhaseSelected
    // 3. Highest ELO
    // 4. Latest evaluated cycle
    const passed = matchingSteps.find((s) => s.gateStatus === "PASS" || s.promotionDecision === "promote");
    const selected = matchingSteps.find((s) => s.isPhaseSelected);
    const highestElo = [...matchingSteps].sort((a, b) => (b.elo ?? 0) - (a.elo ?? 0))[0];
    const representative = passed || selected || highestElo || matchingSteps[matchingSteps.length - 1];

    return {
      isExecuted: true as const,
      canonicalDef: def,
      step: representative,
      cyclesCount: matchingSteps.length,
      allMatchingSteps: matchingSteps,
    };
  });

  const canonicalExecutedCount = canonicalItems.filter((item) => item.isExecuted).length;
  const canonicalPendingCount = FULL_ASSAULT_CAMPAIGN_PHASES.length - canonicalExecutedCount;

  // Group canonical items by sub-curriculum (Stage 1 and Stage 2)
  const canonicalStages = React.useMemo(() => {
    const stageMap = new Map<number, {
      stageNumber: number;
      stageName: string;
      stageDescription: string;
      stageIcon: string;
      accentColor: string;
      items: typeof canonicalItems;
    }>();

    canonicalItems.forEach((item) => {
      const sNum = item.canonicalDef.stageNumber;
      if (!stageMap.has(sNum)) {
        const isStage1 = sNum === 1;
        stageMap.set(sNum, {
          stageNumber: sNum,
          stageName: isStage1 ? "Sub-Curriculum 1: Objective Doctrine & VP Acceleration" : "Sub-Curriculum 2: Multi-Scenario Self-Play vs Random",
          stageDescription: isStage1
            ? "Fundamental VP sprint, suppression, race & tactical urban assault (Phases 1–5)"
            : "Multi-scenario generalization (Gela + Mettete), 38Ch sensory adaptation & progressive selfplay (Phases 6–13)",
          stageIcon: isStage1 ? "🎯" : "⚔️",
          accentColor: isStage1 ? "#f59e0b" : "#38bdf8",
          items: [],
        });
      }
      stageMap.get(sNum)!.items.push(item);
    });

    return Array.from(stageMap.values()).sort((a, b) => a.stageNumber - b.stageNumber);
  }, [canonicalItems]);

  // Helper to match a chronological step to its stage number
  function getStepStageNumber(phaseName: string): number {
    const cIdx = matchCanonicalPhase(phaseName);
    if (cIdx >= 0 && cIdx < FULL_ASSAULT_CAMPAIGN_PHASES.length) {
      return FULL_ASSAULT_CAMPAIGN_PHASES[cIdx].stageNumber;
    }
    if (/phase[1-5]_/i.test(phaseName)) return 1;
    return 2;
  }

  // Group chronological execution nodes by sub-curriculum
  const chronologicalStages = React.useMemo(() => {
    const stage1Nodes = chronologicalDisplayNodes.filter((n) => getStepStageNumber(n.phaseName) === 1);
    const stage2Nodes = chronologicalDisplayNodes.filter((n) => getStepStageNumber(n.phaseName) === 2);

    return [
      {
        stageNumber: 1,
        stageName: "Sub-Curriculum 1: Objective Doctrine & VP Acceleration",
        stageDescription: "Executed runs in VP sprint, suppression, race & tactical urban assault (Phases 1–5)",
        stageIcon: "🎯",
        accentColor: "#f59e0b",
        nodes: stage1Nodes,
      },
      {
        stageNumber: 2,
        stageName: "Sub-Curriculum 2: Multi-Scenario Self-Play vs Random",
        stageDescription: "Executed runs in multi-scenario selfplay progression (Phases 6–13)",
        stageIcon: "⚔️",
        accentColor: "#38bdf8",
        nodes: stage2Nodes,
      },
    ];
  }, [chronologicalDisplayNodes]);

  // Render executed active node card
  const renderExecutedCard = (
    item: { canonicalDef?: CanonicalPhaseDef; cyclesCount?: number },
    node: CurriculumStepMetric,
    keyPrefix: string,
    phaseBadgeText: string,
    displayTitle?: string,
  ) => {
    const isPeak = (node.elo ?? 0) === peakElo && peakElo > 0;
    const isSelected = selectedRunId === node.runId;
    const isPromoted =
      node.gateStatus === "PASS" ||
      node.promotionDecision === "promote" ||
      node.promotionDecision === "promote_best_of_cycles";
    const isHeld =
      node.gateStatus === "FAIL" ||
      node.promotionDecision === "hold";

    const title = displayTitle || item.canonicalDef?.phaseTitle || node.phaseName.replace(/^phase\d+_/i, "").replace(/_/g, " ");
    const cyclesCount = item.cyclesCount ?? 1;

    return (
      <div
        key={`${keyPrefix}-${node.runId}`}
        onClick={() => onSelectRunId?.(node.runId)}
        style={{
          minWidth: 210,
          maxWidth: 245,
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
            {phaseBadgeText}
          </span>
          <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
            {cyclesCount > 1 && (
              <span
                style={{
                  fontSize: 9,
                  fontWeight: 700,
                  background: "#33415550",
                  border: "1px solid #47556950",
                  color: "#cbd5e1",
                  padding: "0 4px",
                  borderRadius: 3,
                }}
                title={`${cyclesCount} reinforcement/eval cycles executed for this phase`}
              >
                🔁 {cyclesCount} Cycles
              </span>
            )}
            <span style={{ fontSize: 10, color: "#64748b" }}>
              C{node.cycleInPhase}/{node.totalCyclesInPhase}
            </span>
          </div>
        </div>

        {/* Stage Tag */}
        <div style={{ fontSize: 9, fontWeight: 700, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.4px", marginBottom: 2 }}>
          {item.canonicalDef?.stageName || (getStepStageNumber(node.phaseName) === 1 ? "Stage 1: Objective Doctrine" : "Stage 2: Multi-Scenario Self-Play")}
        </div>

        {/* Phase Name & Run ID */}
        <div style={{ fontWeight: 700, fontSize: 12, color: "#f8fafc", marginBottom: 2, textTransform: "capitalize" }}>
          {title}
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

        {/* Win Rate & Target Goal */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 11, marginBottom: 2 }}>
          <span className="muted">Win Rate:</span>
          <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <span style={{ fontWeight: 700, color: (node.winRate ?? 0) >= (node.targetWinRate ?? 0.5) ? "#34d399" : "#f87171" }}>
              {node.winRate !== null ? `${(node.winRate * 100).toFixed(1)}%` : "-"}
            </span>
            {node.targetWinRate !== null && (
              <span style={{ fontSize: 9, color: (node.winRate ?? 0) >= node.targetWinRate ? "#10b981aa" : "#94a3b8" }}>
                (🎯 &gt;={(node.targetWinRate * 100).toFixed(0)}%)
              </span>
            )}
          </div>
        </div>

        {/* VPs Controlled vs Goal */}
        {(node.capturedAvg !== null || node.targetCapturedAvg !== null) && (
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 11, marginBottom: 2 }}>
            <span className="muted">VPs Avg:</span>
            <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <span style={{ fontWeight: 700, color: (node.capturedAvg ?? 0) >= (node.targetCapturedAvg ?? 0) ? "#34d399" : "#f87171" }}>
                {node.capturedAvg !== null ? node.capturedAvg.toFixed(2) : "-"}
              </span>
              {node.targetCapturedAvg !== null && (
                <span style={{ fontSize: 9, color: (node.capturedAvg ?? 0) >= node.targetCapturedAvg ? "#10b981aa" : "#94a3b8" }}>
                  (🎯 &gt;={node.targetCapturedAvg.toFixed(2)})
                </span>
              )}
            </div>
          </div>
        )}

        {/* VP Take Rate vs Goal */}
        {(node.vpTakeRate !== null || node.targetVpTakeRate !== null) && (
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 10, marginBottom: 2 }}>
            <span className="muted">Take Rate:</span>
            <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <span style={{ fontWeight: 600, color: (node.vpTakeRate ?? 0) >= (node.targetVpTakeRate ?? 0) ? "#34d399" : "#f87171" }}>
                {node.vpTakeRate !== null ? node.vpTakeRate.toFixed(3) : "-"}
              </span>
              {node.targetVpTakeRate !== null && (
                <span style={{ fontSize: 9, color: (node.vpTakeRate ?? 0) >= node.targetVpTakeRate ? "#10b981aa" : "#94a3b8" }}>
                  (🎯 &gt;={node.targetVpTakeRate.toFixed(3)})
                </span>
              )}
            </div>
          </div>
        )}

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
    );
  };

  // Render ghost / upcoming pending canonical phase card
  const renderPendingCard = (pending: CanonicalPhaseDef, keyPrefix: string) => {
    const isStageTransition = pending.phaseNumber === 6;
    return (
      <div
        key={`${keyPrefix}-${pending.phaseKey}`}
        style={{
          minWidth: 210,
          maxWidth: 245,
          flexShrink: 0,
          background: isStageTransition ? "rgba(15, 23, 42, 0.45)" : "rgba(11, 18, 32, 0.35)",
          border: isStageTransition ? "1px dashed rgba(56, 189, 248, 0.55)" : "1px dashed rgba(100, 116, 139, 0.45)",
          borderRadius: 8,
          padding: "10px 12px",
          opacity: 0.55,
          position: "relative",
          filter: "grayscale(25%)",
          transition: "all 0.2s ease-in-out",
        }}
        title={`Upcoming canonical phase: ${pending.phaseTitle} (Not started yet)`}
        onMouseEnter={(e) => {
          e.currentTarget.style.opacity = "0.90";
          e.currentTarget.style.border = "1px dashed rgba(56, 189, 248, 0.85)";
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.opacity = "0.55";
          e.currentTarget.style.border = isStageTransition ? "1px dashed rgba(56, 189, 248, 0.55)" : "1px dashed rgba(100, 116, 139, 0.45)";
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
          <span
            style={{
              fontSize: 10,
              fontWeight: 700,
              textTransform: "uppercase",
              color: isStageTransition ? "#38bdf8" : "#94a3b8",
              background: isStageTransition ? "#0284c720" : "#1e293b60",
              padding: "1px 5px",
              borderRadius: 3,
            }}
          >
            Phase {pending.phaseNumber}
          </span>
          <span
            style={{
              fontSize: 9,
              fontWeight: 700,
              color: isStageTransition ? "#38bdf8" : "#94a3b8",
              background: "#33415540",
              border: "1px solid #47556940",
              padding: "1px 6px",
              borderRadius: 3,
              display: "inline-flex",
              alignItems: "center",
              gap: 3,
            }}
          >
            ⏳ PENDING
          </span>
        </div>

        <div style={{ fontSize: 9, fontWeight: 700, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.4px", marginBottom: 2 }}>
          {pending.stageName}
        </div>

        <div style={{ fontWeight: 700, fontSize: 12, color: "#cbd5e1", marginBottom: 3, textTransform: "capitalize" }}>
          {pending.phaseTitle}
        </div>

        <div
          style={{
            fontSize: 10,
            color: "#64748b",
            marginBottom: 8,
            lineHeight: "1.3",
            minHeight: 24,
          }}
        >
          {pending.description || "Awaiting previous phase completion"}
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 3, padding: "6px 8px", background: "#060b1340", borderRadius: 4, marginBottom: 8, border: "1px solid #1e293b40" }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "#94a3b8" }}>
            <span>Goal Win Rate:</span>
            <strong style={{ color: "#38bdf8" }}>
              {pending.targetWinRate !== undefined ? `≥${(pending.targetWinRate * 100).toFixed(0)}%` : "-"}
            </strong>
          </div>
          {pending.targetCapturedAvg !== undefined && (
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "#94a3b8" }}>
              <span>Goal VPs Avg:</span>
              <strong style={{ color: "#38bdf8" }}>
                ≥{pending.targetCapturedAvg.toFixed(2)}
              </strong>
            </div>
          )}
          {pending.targetVpTakeRate !== undefined && (
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "#94a3b8" }}>
              <span>Goal Take Rate:</span>
              <strong style={{ color: "#38bdf8" }}>
                ≥{pending.targetVpTakeRate.toFixed(3)}
              </strong>
            </div>
          )}
        </div>

        <div style={{ paddingTop: 4, borderTop: "1px dashed #1e293b", display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 9 }}>
          <span style={{ color: "#64748b", fontWeight: 600 }}>
            ⚪ NOT STARTED
          </span>
          <span style={{ color: "#475569" }}>
            Upcoming
          </span>
        </div>
      </div>
    );
  };

  // Render arrow connector between nodes
  const renderConnector = (key: string, label: string = "Weights", isHighlight: boolean = false) => (
    <div
      key={key}
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 2,
        flexShrink: 0,
        padding: "0 2px",
      }}
    >
      <span style={{ fontSize: 18, color: isHighlight ? "#38bdf8" : "#f59e0b" }}>➔</span>
      <span
        style={{
          fontSize: 8,
          color: isHighlight ? "#38bdf8" : "#64748b",
          textTransform: "uppercase",
          letterSpacing: "0.4px",
          fontWeight: isHighlight ? 800 : 700,
        }}
      >
        {label}
      </span>
    </div>
  );

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
          marginBottom: 14,
          flexWrap: "wrap",
          gap: 10,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <span style={{ fontSize: 14, fontWeight: 700, color: "#f59e0b", display: "flex", alignItems: "center", gap: 6 }}>
            <span>🗺️</span> Full Assault Campaign Pipeline (13 Phases across 2 Sub-Curriculums)
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
            ★ {canonicalExecutedCount} / {FULL_ASSAULT_CAMPAIGN_PHASES.length} Campaign Phases Executed
          </span>
          {canonicalPendingCount > 0 && (
            <span
              style={{
                fontSize: 11,
                background: "#1e293b95",
                border: "1px dashed #64748b",
                color: "#cbd5e1",
                padding: "2px 8px",
                borderRadius: 4,
                fontWeight: 600,
                display: "inline-flex",
                alignItems: "center",
                gap: 4,
              }}
            >
              ⏳ {canonicalPendingCount} Remaining to Full Mastery (Stage 2)
            </span>
          )}
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

        {/* View Switcher Toggle */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 4,
            background: "#0b1329",
            border: "1px solid #1e293b",
            borderRadius: 6,
            padding: 2,
          }}
        >
          <button
            onClick={() => setViewMode("canonical")}
            style={{
              background: viewMode === "canonical" ? "#f59e0b" : "transparent",
              color: viewMode === "canonical" ? "#000000" : "#94a3b8",
              fontWeight: 700,
              fontSize: 11,
              padding: "3px 9px",
              border: "none",
              borderRadius: 4,
              cursor: "pointer",
              transition: "all 0.15s",
            }}
            title="Show the true 13-Phase Campaign Roadmap organized in dedicated Sub-Curriculum rows"
          >
            ★ 13-Phase Campaign Rows ({canonicalExecutedCount}/13)
          </button>
          <button
            onClick={() => setViewMode("chronological")}
            style={{
              background: viewMode === "chronological" ? "#0284c7" : "transparent",
              color: viewMode === "chronological" ? "#ffffff" : "#94a3b8",
              fontWeight: 700,
              fontSize: 11,
              padding: "3px 9px",
              border: "none",
              borderRadius: 4,
              cursor: "pointer",
              transition: "all 0.15s",
            }}
            title="Show every historical phase group and re-training cycle organized by sub-curriculum rows"
          >
            All Execution Runs ({chronologicalDisplayNodes.length} Phases)
          </button>
        </div>
      </div>

      {/* Sub-Curriculum Rows Container */}
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {/* ============================================================== */}
        {/* VIEW MODE 1: CANONICAL SUB-CURRICULUM ROWS                     */}
        {/* ============================================================== */}
        {viewMode === "canonical" &&
          canonicalStages.map((stage, stageIdx) => {
            const stageExecuted = stage.items.filter((it) => it.isExecuted).length;
            const stageTotal = stage.items.length;
            const isStageCompleted = stageExecuted === stageTotal;
            const isStageActive = stageExecuted > 0 && !isStageCompleted;

            return (
              <React.Fragment key={`stage-row-${stage.stageNumber}`}>
                {/* Inter-Stage Breakthrough Transition Bridge (Between Row 1 and Row 2) */}
                {stageIdx > 0 && (
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: 12,
                      margin: "4px 0",
                      padding: "8px 14px",
                      background: "linear-gradient(90deg, rgba(245, 158, 11, 0.08), rgba(56, 189, 248, 0.14), rgba(245, 158, 11, 0.08))",
                      border: "1px dashed rgba(56, 189, 248, 0.4)",
                      borderRadius: 6,
                      flexWrap: "wrap",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ fontSize: 15 }}>⬇️</span>
                      <span style={{ fontSize: 12, fontWeight: 800, color: "#38bdf8", letterSpacing: "0.5px" }}>
                        STAGE TRANSITION BREAKTHROUGH:
                      </span>
                      <span style={{ fontSize: 11, color: "#cbd5e1" }}>
                        Weights from Stage {stage.stageNumber - 1} Promoted Checkpoint initialize Stage {stage.stageNumber} Base Model
                      </span>
                    </div>
                    <span
                      style={{
                        fontSize: 10,
                        fontWeight: 700,
                        background: "#0f172a",
                        border: "1px solid #0284c760",
                        color: "#7dd3fc",
                        padding: "2px 8px",
                        borderRadius: 4,
                      }}
                    >
                      Phase 5 (Urban Assault) ➔ Phase 6 (Bootstrap Multi-Map)
                    </span>
                  </div>
                )}

                {/* Sub-Curriculum Card Row Container */}
                <div
                  style={{
                    background: "#060b16",
                    border: "1px solid #1e293b",
                    borderRadius: 7,
                    padding: "10px 12px",
                  }}
                >
                  {/* Row Header Bar */}
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      marginBottom: 10,
                      paddingBottom: 6,
                      borderBottom: "1px solid #1e293b80",
                      flexWrap: "wrap",
                      gap: 8,
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                      <span
                        style={{
                          fontSize: 12,
                          fontWeight: 800,
                          color: stage.accentColor,
                          display: "flex",
                          alignItems: "center",
                          gap: 6,
                        }}
                      >
                        <span>{stage.stageIcon}</span>
                        {stage.stageName.toUpperCase()}
                      </span>
                      <span style={{ fontSize: 11, color: "#64748b" }}>
                        • {stage.stageDescription}
                      </span>
                    </div>

                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span
                        style={{
                          fontSize: 10,
                          fontWeight: 700,
                          background: isStageCompleted ? "#065f46" : isStageActive ? "#78350f" : "#1e293b",
                          color: isStageCompleted ? "#34d399" : isStageActive ? "#fde047" : "#94a3b8",
                          padding: "2px 8px",
                          borderRadius: 4,
                          border: `1px solid ${isStageCompleted ? "#10b98150" : isStageActive ? "#f59e0b50" : "#334155"}`,
                        }}
                      >
                        {stageExecuted} / {stageTotal} Phases {isStageCompleted ? "Completed ✓" : isStageActive ? "In Progress" : "Pending ⏳"}
                      </span>
                    </div>
                  </div>

                  {/* Horizontal Flow of Phases in This Sub-Curriculum Row */}
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 10,
                      overflowX: "auto",
                      paddingBottom: 4,
                      paddingTop: 2,
                    }}
                  >
                    {stage.items.map((item, idx) => (
                      <React.Fragment key={`canonical-${item.canonicalDef.phaseKey}`}>
                        {item.isExecuted && item.step
                          ? renderExecutedCard(item, item.step, "canonical", `Phase ${item.canonicalDef.phaseNumber}`)
                          : renderPendingCard(item.canonicalDef, "canonical")}
                        {idx < stage.items.length - 1 && renderConnector(`canonical-conn-${item.canonicalDef.phaseKey}`)}
                      </React.Fragment>
                    ))}
                  </div>
                </div>
              </React.Fragment>
            );
          })}

        {/* ============================================================== */}
        {/* VIEW MODE 2: CHRONOLOGICAL EXECUTION RUNS BY SUB-CURRICULUM     */}
        {/* ============================================================== */}
        {viewMode === "chronological" &&
          chronologicalStages.map((stage, stageIdx) => {
            const hasRuns = stage.nodes.length > 0;

            return (
              <React.Fragment key={`chrono-row-${stage.stageNumber}`}>
                {stageIdx > 0 && (
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      gap: 8,
                      margin: "4px 0",
                      padding: "6px 12px",
                      background: "rgba(30, 41, 59, 0.3)",
                      border: "1px dashed #334155",
                      borderRadius: 6,
                    }}
                  >
                    <span style={{ fontSize: 11, color: "#64748b", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.5px" }}>
                      ⬇️ Sub-Curriculum Transition: Stage {stage.stageNumber - 1} ➔ Stage {stage.stageNumber} ⬇️
                    </span>
                  </div>
                )}

                <div
                  style={{
                    background: "#060b16",
                    border: "1px solid #1e293b",
                    borderRadius: 7,
                    padding: "10px 12px",
                  }}
                >
                  {/* Row Header */}
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      marginBottom: 10,
                      paddingBottom: 6,
                      borderBottom: "1px solid #1e293b80",
                      flexWrap: "wrap",
                      gap: 8,
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                      <span
                        style={{
                          fontSize: 12,
                          fontWeight: 800,
                          color: stage.accentColor,
                          display: "flex",
                          alignItems: "center",
                          gap: 6,
                        }}
                      >
                        <span>{stage.stageIcon}</span>
                        {stage.stageName.toUpperCase()}
                      </span>
                      <span style={{ fontSize: 11, color: "#64748b" }}>
                        • {stage.stageDescription}
                      </span>
                    </div>

                    <span
                      style={{
                        fontSize: 10,
                        fontWeight: 700,
                        background: hasRuns ? "#0284c725" : "#1e293b",
                        color: hasRuns ? "#38bdf8" : "#64748b",
                        padding: "2px 8px",
                        borderRadius: 4,
                        border: `1px solid ${hasRuns ? "#0284c750" : "#334155"}`,
                      }}
                    >
                      {stage.nodes.length} Runs Recorded
                    </span>
                  </div>

                  {/* Horizontal Flow or Empty State */}
                  {hasRuns ? (
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 10,
                        overflowX: "auto",
                        paddingBottom: 4,
                        paddingTop: 2,
                      }}
                    >
                      {stage.nodes.map((node, idx) => (
                        <React.Fragment key={`chrono-${node.runId}`}>
                          {renderExecutedCard(
                            {},
                            node,
                            "chrono",
                            `Run ${idx + 1}`,
                            node.phaseName.replace(/^phase\d+_/i, "").replace(/_v\d+.*$/i, "").replace(/_/g, " "),
                          )}
                          {idx < stage.nodes.length - 1 && renderConnector(`chrono-conn-${node.runId}`)}
                        </React.Fragment>
                      ))}
                    </div>
                  ) : (
                    <div style={{ padding: "14px 10px", textAlign: "center", color: "#64748b", fontSize: 11, fontStyle: "italic" }}>
                      No execution runs recorded yet in this sub-curriculum.
                    </div>
                  )}
                </div>
              </React.Fragment>
            );
          })}
      </div>
    </div>
  );
}
