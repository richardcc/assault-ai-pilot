import { useEffect, useMemo, useState } from "react";

import {

  deleteModelExperiment,

  fetchCatalog,

  fetchCurriculumCompareLatest,

  fetchModel,

  fetchModelTacticalQuality,

  fetchTraceability,

  fetchTrainSummary,

} from "../api";

import { calculateDurationSeconds, formatDuration, formatDurationDetailed, formatLocalDate } from "../dateUtils";

import {

  buildCurriculumProgression,

  extractStepTraceMetrics,

  type CurriculumStepMetric,

} from "../curriculumMetrics";

import type { Dict, EvalResultRow, EvalRow, ModelPayload, TrainRow } from "../types";

import { NetworkTopologyTab } from "./model-tabs/NetworkTopologyTab";

import { CurriculumLineageFlow } from "../components/CurriculumLineageFlow";



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



type MetricMode = "elo" | "winRate" | "capturedAvg" | "vpTakeRate";

interface MetricConfig {
  key: MetricMode;
  label: string;
  shortLabel: string;
  unit: string;
  getValue: (s: CurriculumStepMetric) => number | null;
  getTarget: (s: CurriculumStepMetric) => number | null;
  formatValue: (v: number) => string;
}

const METRIC_CONFIGS: Record<MetricMode, MetricConfig> = {
  elo: {
    key: "elo",
    label: "📈 ELO Curve",
    shortLabel: "ELO",
    unit: " pts",
    getValue: (s) => s.elo,
    getTarget: () => null,
    formatValue: (v) => `${Math.round(v)}`,
  },
  winRate: {
    key: "winRate",
    label: "🎯 Win Rate vs. Goal",
    shortLabel: "Win Rate",
    unit: "%",
    getValue: (s) => (s.winRate !== null ? s.winRate * 100 : null),
    getTarget: (s) => (s.targetWinRate !== null ? s.targetWinRate * 100 : null),
    formatValue: (v) => `${v.toFixed(1)}%`,
  },
  capturedAvg: {
    key: "capturedAvg",
    label: "🚩 Captured VPs vs. Goal",
    shortLabel: "Captured VPs",
    unit: "",
    getValue: (s) => s.capturedAvg,
    getTarget: (s) => s.targetCapturedAvg,
    formatValue: (v) => v.toFixed(2),
  },
  vpTakeRate: {
    key: "vpTakeRate",
    label: "⚡ VP Take Rate vs. Goal",
    shortLabel: "Take Rate",
    unit: "%",
    getValue: (s) => (s.vpTakeRate !== null ? s.vpTakeRate * 100 : null),
    getTarget: (s) => (s.targetVpTakeRate !== null ? s.targetVpTakeRate * 100 : null),
    formatValue: (v) => `${v.toFixed(1)}%`,
  },
};

function CurriculumProgressionChart({ steps }: { steps: CurriculumStepMetric[] }) {
  const [selectedMetric, setSelectedMetric] = useState<MetricMode>("elo");

  const cfg = METRIC_CONFIGS[selectedMetric];

  // Filter steps that have a value for the selected metric
  const validSteps = steps.filter((s) => cfg.getValue(s) !== null);

  if (validSteps.length === 0) {
    if (selectedMetric !== "elo") {
      const eloSteps = steps.filter((s) => s.elo !== null);
      if (eloSteps.length === 0) return null;
    } else {
      return null;
    }
  }

  // Calculate dynamic scale bounds based on actual values and targets
  const allValues = validSteps.map((s) => cfg.getValue(s)!).filter((v) => !isNaN(v));
  const allTargets = validSteps.map((s) => cfg.getTarget(s)).filter((t): t is number => t !== null && !isNaN(t));
  const allPointsToFit = [...allValues, ...allTargets];

  let minY = 0;
  let maxY = 100;
  let rangeY = 100;

  if (selectedMetric === "elo") {
    minY = Math.min(...allValues) - 70;
    maxY = Math.max(...allValues) + 75;
    rangeY = Math.max(130, maxY - minY);
  } else if (selectedMetric === "winRate" || selectedMetric === "vpTakeRate") {
    const rawMin = allPointsToFit.length > 0 ? Math.min(...allPointsToFit) : 0;
    const rawMax = allPointsToFit.length > 0 ? Math.max(...allPointsToFit) : 100;
    minY = Math.max(0, Math.floor(rawMin - 10));
    maxY = Math.min(100, Math.ceil(rawMax + 12));
    rangeY = Math.max(25, maxY - minY);
  } else if (selectedMetric === "capturedAvg") {
    const rawMax = allPointsToFit.length > 0 ? Math.max(...allPointsToFit) : 3;
    minY = 0;
    maxY = Math.max(3, Math.ceil(rawMax + 1.0));
    rangeY = Math.max(2, maxY - minY);
  }

  const width = Math.max(860, validSteps.length * 82);
  const height = 300;
  const padX = 58;
  const padY = 46;
  const chartW = width - padX * 2;
  const chartH = height - padY - 42;

  const points = validSteps.map((s, idx) => {
    const val = cfg.getValue(s)!;
    const tgt = cfg.getTarget(s);
    const x = padX + (validSteps.length > 1 ? (idx / (validSteps.length - 1)) * chartW : chartW / 2);
    const y = padY + chartH - ((val - minY) / rangeY) * chartH;
    const isMet = tgt !== null ? val >= tgt : true;
    return { x, y, val, tgt, isMet, step: s, idx };
  });

  const pathD = points.map((p, idx) => `${idx === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ");

  const selectedPoints = points.filter((p) => p.step.isPhaseSelected);
  const selectedPathD = selectedPoints
    .map((p, idx) => `${idx === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`)
    .join(" ");

  // Compute contiguous phase groups on the chart for visual grouping bands
  const phaseBands: Array<{
    phaseName: string;
    groupIdx: number;
    startX: number;
    endX: number;
    targetVal: number | null;
  }> = [];

  points.forEach((p) => {
    const stepSpacing = validSteps.length > 1 ? chartW / (validSteps.length - 1) : 60;
    const halfStep = Math.min(38, stepSpacing * 0.44);
    const last = phaseBands[phaseBands.length - 1];
    if (!last || last.groupIdx !== p.step.phaseGroupIndex) {
      phaseBands.push({
        phaseName: p.step.phaseName,
        groupIdx: p.step.phaseGroupIndex,
        startX: p.x - halfStep,
        endX: p.x + halfStep,
        targetVal: p.tgt,
      });
    } else {
      last.endX = p.x + halfStep;
      if (last.targetVal === null && p.tgt !== null) {
        last.targetVal = p.tgt;
      }
    }
  });

  const latest = validSteps[validSteps.length - 1];
  const first = validSteps[0];
  const deltaTotal = (latest && first) ? latest.elo! - first.elo! : 0;
  const peakVal = Math.max(...validSteps.map((s) => cfg.getValue(s)!));
  const avgVal = validSteps.reduce((acc, s) => acc + cfg.getValue(s)!, 0) / Math.max(1, validSteps.length);
  const targetMetCount = points.filter((p) => p.tgt !== null && p.isMet).length;
  const targetTotalCount = points.filter((p) => p.tgt !== null).length;

  return (
    <div
      style={{
        background: "#0b1220",
        border: "1px solid #1e293b",
        borderRadius: 8,
        padding: "12px 16px",
        marginBottom: 16,
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 12,
          flexWrap: "wrap",
          gap: 12,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          {/* Mode Switch Tabs */}
          <div style={{ display: "flex", background: "#0f172a", padding: "2px 4px", borderRadius: 6, border: "1px solid #334155", gap: 3 }}>
            {(["elo", "winRate", "capturedAvg", "vpTakeRate"] as MetricMode[]).map((mode) => {
              const item = METRIC_CONFIGS[mode];
              const isActive = selectedMetric === mode;
              return (
                <button
                  key={mode}
                  type="button"
                  onClick={() => setSelectedMetric(mode)}
                  style={{
                    background: isActive ? "#0284c7" : "transparent",
                    color: isActive ? "#ffffff" : "#94a3b8",
                    border: "none",
                    borderRadius: 4,
                    padding: "3px 8px",
                    fontSize: 11,
                    fontWeight: isActive ? 700 : 500,
                    cursor: "pointer",
                    transition: "all 0.15s ease",
                  }}
                >
                  {item.label}
                </button>
              );
            })}
          </div>

          <span
            style={{
              fontSize: 11,
              background: "#0284c725",
              border: "1px solid #0284c750",
              color: "#38bdf8",
              padding: "1px 6px",
              borderRadius: 4,
              fontWeight: 600,
            }}
          >
            {validSteps.length} Cycles ({phaseBands.length} Phases)
          </span>

          <span
            style={{
              fontSize: 11,
              background: "#451a0390",
              border: "1px solid #f59e0b80",
              color: "#fde047",
              padding: "1px 7px",
              borderRadius: 4,
              fontWeight: 700,
              display: "inline-flex",
              alignItems: "center",
              gap: 4,
            }}
            title="The cycle with highest quality/ELO or passing the Gate in each phase is marked with ★ and connected by the golden line"
          >
            ★ Selected per Phase ({selectedPoints.length})
          </span>
        </div>

        {/* Dynamic Summary Stats based on selected metric */}
        <div style={{ display: "flex", gap: 14, fontSize: 12, flexWrap: "wrap", alignItems: "center" }}>
          {selectedMetric === "elo" ? (
            <>
              <div>
                <span className="muted">Initial ELO:</span>{" "}
                <strong style={{ color: "#e2e8f0" }}>{first.elo}</strong>
              </div>
              <div>
                <span className="muted">Current ELO:</span>{" "}
                <strong style={{ color: "#38bdf8" }}>{latest.elo}</strong>
              </div>
              <div>
                <span className="muted">Peak ELO:</span>{" "}
                <strong style={{ color: "#fde047" }}>★ {peakVal}</strong>
              </div>
              <div>
                <span className="muted">Average Win Rate:</span>{" "}
                <strong style={{ color: "#34d399" }}>
                  {(
                    (validSteps.filter((s) => s.winRate !== null).reduce((acc, s) => acc + s.winRate!, 0) /
                      Math.max(1, validSteps.filter((s) => s.winRate !== null).length)) *
                    100
                  ).toFixed(1)}
                  %
                </strong>
              </div>
              <div
                style={{
                  background: deltaTotal >= 0 ? "#10b98118" : "#ef444418",
                  border: `1px solid ${deltaTotal >= 0 ? "#10b98140" : "#ef444440"}`,
                  padding: "2px 8px",
                  borderRadius: 4,
                }}
              >
                <span className="muted">Global Δ:</span>{" "}
                <strong style={{ color: deltaTotal >= 0 ? "#34d399" : "#f87171" }}>
                  {deltaTotal >= 0 ? `▲ +${deltaTotal}` : `▼ ${deltaTotal}`} pts
                </strong>
              </div>
            </>
          ) : (
            <>
              <div>
                <span className="muted">Current:</span>{" "}
                <strong style={{ color: latest && points[points.length - 1]?.isMet ? "#34d399" : "#f87171" }}>
                  {latest ? cfg.formatValue(cfg.getValue(latest)!) : "-"}
                </strong>
              </div>
              <div>
                <span className="muted">Average:</span>{" "}
                <strong style={{ color: "#38bdf8" }}>{cfg.formatValue(avgVal)}</strong>
              </div>
              <div>
                <span className="muted">Peak:</span>{" "}
                <strong style={{ color: "#fde047" }}>★ {cfg.formatValue(peakVal)}</strong>
              </div>
              {targetTotalCount > 0 && (
                <div
                  style={{
                    background: targetMetCount === targetTotalCount ? "#10b98118" : "#f59e0b18",
                    border: `1px solid ${targetMetCount === targetTotalCount ? "#10b98140" : "#f59e0b40"}`,
                    padding: "2px 8px",
                    borderRadius: 4,
                  }}
                >
                  <span className="muted">Goal Met:</span>{" "}
                  <strong style={{ color: targetMetCount === targetTotalCount ? "#34d399" : "#fbbf24" }}>
                    {targetMetCount}/{targetTotalCount} ({((targetMetCount / targetTotalCount) * 100).toFixed(0)}%)
                  </strong>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      <div style={{ width: "100%", overflowX: "auto" }}>
        <svg
          viewBox={`0 0 ${width} ${height}`}
          style={{ width: "100%", minWidth: 660, height, display: "block" }}
        >
          <defs>
            <linearGradient id="chartAreaGrad" x1="0" y1="0" x2="0" y2="1">
              <stop
                offset="0%"
                stopColor={selectedMetric === "elo" ? "#38bdf8" : "#10b981"}
                stopOpacity={0.24}
              />
              <stop
                offset="100%"
                stopColor={selectedMetric === "elo" ? "#38bdf8" : "#10b981"}
                stopOpacity={0.0}
              />
            </linearGradient>
          </defs>

          {/* Phase group background bands */}
          {phaseBands.map((band, bIdx) => (
            <rect
              key={`band-${bIdx}`}
              x={band.startX}
              y={padY - 24}
              width={Math.max(24, band.endX - band.startX)}
              height={chartH + 46}
              rx={5}
              fill={bIdx % 2 === 0 ? "#1e293b38" : "#0f172a45"}
              stroke={bIdx % 2 === 0 ? "#33415555" : "#1e293b55"}
              strokeWidth="1"
            />
          ))}

          {/* Grid lines */}
          <line x1={padX} y1={padY} x2={width - padX} y2={padY} stroke="#1e293b" strokeDasharray="3 3" />
          <line
            x1={padX}
            y1={padY + chartH / 2}
            x2={width - padX}
            y2={padY + chartH / 2}
            stroke="#1e293b"
            strokeDasharray="3 3"
          />
          <line x1={padX} y1={padY + chartH} x2={width - padX} y2={padY + chartH} stroke="#1e293b" />

          {/* Target Lines per Phase Band (When metric is not ELO) */}
          {selectedMetric !== "elo" &&
            phaseBands.map((band, bIdx) => {
              if (band.targetVal === null) return null;
              const targetY = padY + chartH - ((band.targetVal - minY) / rangeY) * chartH;
              const clampedTargetY = Math.max(padY - 8, Math.min(padY + chartH, targetY));
              const bandW = Math.max(24, band.endX - band.startX);
              return (
                <g key={`target-band-${bIdx}`}>
                  {/* Goal dashed threshold line */}
                  <line
                    x1={band.startX + 2}
                    y1={clampedTargetY}
                    x2={band.endX - 2}
                    y2={clampedTargetY}
                    stroke="#f59e0b"
                    strokeWidth="1.8"
                    strokeDasharray="4 3"
                    opacity={0.95}
                  />
                  {/* Goal label badge */}
                  <rect
                    x={band.startX + bandW / 2 - 34}
                    y={clampedTargetY - 14}
                    width={68}
                    height={13}
                    rx={3}
                    fill="#451a03e6"
                    stroke="#f59e0b80"
                    strokeWidth="1"
                  />
                  <text
                    x={band.startX + bandW / 2}
                    y={clampedTargetY - 4}
                    textAnchor="middle"
                    fill="#fde047"
                    fontSize={8.5}
                    fontWeight={800}
                  >
                    🎯 ≥{cfg.formatValue(band.targetVal)}
                  </text>
                </g>
              );
            })}

          {/* Area fill */}
          {points.length > 1 && (
            <path
              d={`${pathD} L ${points[points.length - 1].x.toFixed(1)} ${(padY + chartH).toFixed(1)} L ${points[0].x.toFixed(1)} ${(padY + chartH).toFixed(1)} Z`}
              fill="url(#chartAreaGrad)"
            />
          )}

          {/* All-cycles curve */}
          {points.length > 1 && (
            <path
              d={pathD}
              fill="none"
              stroke={selectedMetric === "elo" ? "#38bdf8" : "#22c55e"}
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
              opacity={0.8}
            />
          )}

          {/* Chosen-per-phase gold trendline */}
          {selectedPoints.length > 1 && (
            <path
              d={selectedPathD}
              fill="none"
              stroke="#f59e0b"
              strokeWidth="2.2"
              strokeDasharray="6 4"
              strokeLinecap="round"
              strokeLinejoin="round"
              opacity={0.95}
            />
          )}

          {/* Points & Labels */}
          {points.map((p, idx) => {
            const isChosen = p.step.isPhaseSelected;
            const isPeak = p.val === peakVal;
            const cleanPhaseName = p.step.phaseName.replace(/^phase\d*_?/, "");
            const shortPhase = cleanPhaseName.length > 12 ? `${cleanPhaseName.slice(0, 10)}..` : cleanPhaseName;
            const cycleTag = p.step.totalCyclesInPhase > 1 ? ` C${p.step.cycleInPhase}` : "";

            const displayValue = cfg.formatValue(p.val);
            const badgeText = isChosen ? `★ ${displayValue}` : displayValue;
            const badgeWidth = Math.max(34, badgeText.length * 6.5 + 8);

            // Node colors based on mode and goal achievement
            let nodeFill = "#0284c7";
            let badgeBg = "#1e293b";
            let badgeBorder = "#334155";
            let badgeTextColor = "#cbd5e1";

            if (selectedMetric === "elo") {
              nodeFill = isChosen ? "#fbbf24" : isPeak ? "#a855f7" : "#0284c7";
              if (isChosen) {
                badgeBg = "#451a03";
                badgeBorder = "#f59e0b";
                badgeTextColor = "#fef08a";
              }
            } else {
              // Target-oriented metrics
              if (p.tgt !== null) {
                if (p.isMet) {
                  nodeFill = isChosen ? "#fbbf24" : "#10b981";
                  badgeBg = "#064e3b";
                  badgeBorder = "#10b981";
                  badgeTextColor = "#6ee7b7";
                } else {
                  nodeFill = "#ef4444";
                  badgeBg = "#450a0a";
                  badgeBorder = "#ef4444";
                  badgeTextColor = "#fca5a5";
                }
              } else {
                nodeFill = isChosen ? "#fbbf24" : "#0284c7";
              }
            }

            return (
              <g key={idx}>
                <title>
                  {`${p.step.phaseName} (Cycle ${p.step.cycleInPhase}/${p.step.totalCyclesInPhase})${
                    isChosen ? " — ★ PHASE SELECTED" : ""
                  }
Run: ${p.step.runId}
${cfg.shortLabel}: ${displayValue}${
                    p.tgt !== null ? ` (Target: ≥${cfg.formatValue(p.tgt)})` : ""
                  }
Gate Status: ${p.step.gateStatus || "-"}
ELO: ${p.step.elo ?? "-"}
Win Rate: ${
                    p.step.winRate !== null ? (p.step.winRate * 100).toFixed(1) + "%" : "-"
                  }`}
                </title>

                {/* Connecting vertical tick */}
                <line
                  x1={p.x}
                  y1={p.y}
                  x2={p.x}
                  y2={padY + chartH}
                  stroke={isChosen ? "#f59e0b" : p.tgt !== null ? (p.isMet ? "#10b981" : "#ef4444") : "#334155"}
                  strokeWidth={isChosen ? "1.5" : "1"}
                  strokeDasharray="2 2"
                  opacity={isChosen ? 0.85 : 0.45}
                />

                {/* Outer glowing ring for chosen cycle of phase */}
                {isChosen && (
                  <circle
                    cx={p.x}
                    cy={p.y}
                    r={9.5}
                    fill="#f59e0b28"
                    stroke="#fbbf24"
                    strokeWidth="1.6"
                  />
                )}

                {/* Point */}
                <circle
                  cx={p.x}
                  cy={p.y}
                  r={isChosen ? 5.5 : 4}
                  fill={nodeFill}
                  stroke="#0f172a"
                  strokeWidth="2"
                />

                {/* Pill background for value badge */}
                <rect
                  x={p.x - badgeWidth / 2}
                  y={p.y - 24}
                  width={badgeWidth}
                  height={15}
                  rx={4}
                  fill={badgeBg}
                  stroke={badgeBorder}
                  strokeWidth="1"
                />

                {/* Value badge label */}
                <text
                  x={p.x}
                  y={p.y - 13}
                  textAnchor="middle"
                  fill={badgeTextColor}
                  fontSize={10}
                  fontWeight={isChosen ? 800 : 700}
                >
                  {badgeText}
                </text>

                {/* Subtext: secondary metric (ELO when in other views, Win Rate when in ELO) */}
                {selectedMetric === "elo" ? (
                  p.step.winRate !== null && (
                    <text
                      x={p.x}
                      y={p.y + 18}
                      textAnchor="middle"
                      fill={isChosen ? "#4ade80" : "#34d399"}
                      fontSize={9.5}
                      fontWeight={isChosen ? 700 : 600}
                    >
                      {(p.step.winRate * 100).toFixed(0)}%
                    </text>
                  )
                ) : (
                  p.step.elo !== null && (
                    <text
                      x={p.x}
                      y={p.y + 18}
                      textAnchor="middle"
                      fill="#94a3b8"
                      fontSize={9}
                      fontWeight={600}
                    >
                      {p.step.elo}
                    </text>
                  )
                )}

                {/* Cycle & Phase bottom label */}
                <text
                  x={p.x}
                  y={height - 15}
                  textAnchor="middle"
                  fill={isChosen ? "#fde047" : "#94a3b8"}
                  fontSize={9.5}
                  fontWeight={isChosen ? 700 : 500}
                >
                  {shortPhase}
                </text>
                <text
                  x={p.x}
                  y={height - 4}
                  textAnchor="middle"
                  fill={isChosen ? "#fbbf24" : "#64748b"}
                  fontSize={8.5}
                  fontWeight={isChosen ? 800 : 600}
                >
                  {isChosen ? `★${cycleTag || " Selected"}` : cycleTag.trim() || `F${p.step.stepIndex}`}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
}


export function CatalogPage() {

  const [catalog, setCatalog] = useState<Dict | null>(null);

  const [traceRows, setTraceRows] = useState<Dict[]>([]);

  const [selectedCurriculumFilter, setSelectedCurriculumFilter] = useState("all");



  const availableCurriculums = useMemo(() => {

    const set = new Set<string>();

    for (const r of traceRows) {

      const name = String(r.curriculum_name || r.curriculum || "").trim();

      if (name) set.add(name);

    }

    return Array.from(set).sort();

  }, [traceRows]);



  const latestActiveCurriculum = useMemo(() => {

    if (!traceRows || traceRows.length === 0) return "";

    for (let i = 0; i < traceRows.length; i++) {

      const name = String(traceRows[i].curriculum_name || traceRows[i].curriculum || "").trim();

      if (name) return name;

    }

    return "";

  }, [traceRows]);



  const filteredTraceRows = useMemo(() => {

    if (selectedCurriculumFilter === "all") return traceRows;

    return traceRows.filter((r) => {

      const name = String(r.curriculum_name || r.curriculum || "").trim();

      return name === selectedCurriculumFilter;

    });

  }, [traceRows, selectedCurriculumFilter]);



  const traceByTrainRun = useMemo(() => {

    const map = new Map<string, Dict>();

    for (const r of traceRows) {

      const tid = String(r.train_run_id || "").trim();

      if (tid) map.set(tid, r);

    }

    return map;

  }, [traceRows]);



  const curriculumDurationStats = useMemo(() => {

    let totalSec = 0;

    let totalTrainSec = 0;

    let totalBenchSec = 0;

    let count = 0;

    let maxSec = 0;

    let maxRow: Dict | null = null;

    for (const r of filteredTraceRows) {

      const dur = calculateDurationSeconds(

        r.phase_started_at as string | undefined,

        r.phase_finished_at as string | undefined

      );

      if (dur !== null && dur >= 0) {

        totalSec += dur;

        count += 1;

        if (dur > maxSec) {

          maxSec = dur;

          maxRow = r;

        }

      }

      if (typeof r.train_duration_seconds === "number") totalTrainSec += r.train_duration_seconds;

      if (typeof r.bench_duration_seconds === "number") totalBenchSec += r.bench_duration_seconds;

    }

    const avgSec = count > 0 ? totalSec / count : null;

    return { totalSec, totalTrainSec, totalBenchSec, count, avgSec, maxSec, maxRow };

  }, [filteredTraceRows]);



  const [selectedEngine, setSelectedEngine] = useState("");

  const [selectedModel, setSelectedModel] = useState("");

  const [modelDetail, setModelDetail] = useState<ModelPayload | null>(null);

  const [tacticalQuality, setTacticalQuality] = useState<Dict | null>(null);
  const [showDetailedMeta, setShowDetailedMeta] = useState(false);

  const [compareRows, setCompareRows] = useState<Dict[]>([]);

  const [compareProfileFilter, setCompareProfileFilter] = useState("all");

  const [compareSideFilter, setCompareSideFilter] = useState("all");

  const [compareEngineFilter, setCompareEngineFilter] = useState("all");

  const [error, setError] = useState("");

  const [summaryTab, setSummaryTab] = useState<"overview" | "topology" | "curriculum" | "compare">("overview");

  const [deletingModelId, setDeletingModelId] = useState("");



  // Horizontal resizability for the 3 panels with local storage persistence

  const DEFAULT_PANEL1_WIDTH = 190;

  const DEFAULT_PANEL2_WIDTH = 290;



  const [panel1Width, setPanel1Width] = useState<number>(() => {

    try {

      const saved = localStorage.getItem("assault_viewer_panel1_width");

      if (saved) {

        const val = parseInt(saved, 10);

        if (!isNaN(val) && val >= 130 && val <= 600) return val;

      }

    } catch {}

    return DEFAULT_PANEL1_WIDTH;

  });



  const [panel2Width, setPanel2Width] = useState<number>(() => {

    try {

      const saved = localStorage.getItem("assault_viewer_panel2_width");

      if (saved) {

        const val = parseInt(saved, 10);

        if (!isNaN(val) && val >= 180 && val <= 750) return val;

      }

    } catch {}

    return DEFAULT_PANEL2_WIDTH;

  });



  const [isDraggingP1, setIsDraggingP1] = useState(false);

  const [isDraggingP2, setIsDraggingP2] = useState(false);



  const handleMouseDownP1 = (e: React.MouseEvent) => {

    e.preventDefault();

    setIsDraggingP1(true);

    const startX = e.clientX;

    const startW = panel1Width;



    document.body.style.cursor = "col-resize";

    document.body.style.userSelect = "none";



    const onMouseMove = (ev: MouseEvent) => {

      const delta = ev.clientX - startX;

      const newW = Math.max(130, Math.min(500, startW + delta));

      setPanel1Width(newW);

    };



    const onMouseUp = (ev: MouseEvent) => {

      setIsDraggingP1(false);

      const delta = ev.clientX - startX;

      const finalW = Math.max(130, Math.min(500, startW + delta));

      setPanel1Width(finalW);

      try {

        localStorage.setItem("assault_viewer_panel1_width", String(finalW));

      } catch {}

      document.body.style.cursor = "";

      document.body.style.userSelect = "";

      window.removeEventListener("mousemove", onMouseMove);

      window.removeEventListener("mouseup", onMouseUp);

    };



    window.addEventListener("mousemove", onMouseMove);

    window.addEventListener("mouseup", onMouseUp);

  };



  const handleMouseDownP2 = (e: React.MouseEvent) => {

    e.preventDefault();

    setIsDraggingP2(true);

    const startX = e.clientX;

    const startW = panel2Width;



    document.body.style.cursor = "col-resize";

    document.body.style.userSelect = "none";



    const onMouseMove = (ev: MouseEvent) => {

      const delta = ev.clientX - startX;

      const newW = Math.max(180, Math.min(750, startW + delta));

      setPanel2Width(newW);

    };



    const onMouseUp = (ev: MouseEvent) => {

      setIsDraggingP2(false);

      const delta = ev.clientX - startX;

      const finalW = Math.max(180, Math.min(750, startW + delta));

      setPanel2Width(finalW);

      try {

        localStorage.setItem("assault_viewer_panel2_width", String(finalW));

      } catch {}

      document.body.style.cursor = "";

      document.body.style.userSelect = "";

      window.removeEventListener("mousemove", onMouseMove);

      window.removeEventListener("mouseup", onMouseUp);

    };



    window.addEventListener("mousemove", onMouseMove);

    window.addEventListener("mouseup", onMouseUp);

  };



  const handleResetP1 = () => {

    setPanel1Width(DEFAULT_PANEL1_WIDTH);

    try {

      localStorage.setItem("assault_viewer_panel1_width", String(DEFAULT_PANEL1_WIDTH));

    } catch {}

  };



  const handleResetP2 = () => {

    setPanel2Width(DEFAULT_PANEL2_WIDTH);

    try {

      localStorage.setItem("assault_viewer_panel2_width", String(DEFAULT_PANEL2_WIDTH));

    } catch {}

  };



  async function handleDeleteModel(targetModelId: string) {

    if (!targetModelId) return;

    const ok = window.confirm(

      `Are you sure you want to COMPLETELY DELETE experiment:\n"${targetModelId}"?\n\nThis action will delete all its checkpoints, self-play files, logs, and database records in DuckDB and Parquet.`

    );

    if (!ok) return;



    setDeletingModelId(targetModelId);

    try {

      const res = await deleteModelExperiment(targetModelId, selectedEngine);

      alert(

        `✅ Experimento eliminado con éxito:\n${targetModelId}\nEspacio liberado: ${res.freed_mb ?? 0} MB (${(res.deleted_directories as string[])?.length ?? 0} directorios)`

      );

      await load();

      if (selectedModel === targetModelId) {

        setSelectedModel("");

      }

    } catch (err: any) {

      alert(`❌ Failed to delete experiment: ${err.message || err}`);

    } finally {

      setDeletingModelId("");

    }

  }



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



  const [loadingModelDetail, setLoadingModelDetail] = useState(false);



  // Fetch full model detail whenever selectedEngine & selectedModel change

  useEffect(() => {

    setTrainSummary(null);

    setTacticalQuality(null);

    if (!selectedEngine || !selectedModel) {

      setModelDetail(null);

      setLoadingModelDetail(false);

      return;

    }

    let cancelled = false;

    setLoadingModelDetail(true);

    async function fetchDetail() {

      try {

        const [m, q] = await Promise.all([

          fetchModel(selectedEngine, selectedModel),

          fetchModelTacticalQuality(selectedEngine, selectedModel).catch(() => null),

        ]);

        if (!cancelled) {

          setModelDetail(m);

          setTacticalQuality(q);

          setLoadingModelDetail(false);

        }

      } catch {

        if (!cancelled) {

          setModelDetail(null);

          setTacticalQuality(null);

          setLoadingModelDetail(false);

        }

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



  const modelTrainDurationStats = useMemo(() => {

    let totalSec = 0;

    let totalTrainSec = 0;

    let totalBenchSec = 0;

    let count = 0;

    for (const t of trains) {

      const tid = String(t.run_id || "").trim();

      const trace = traceByTrainRun.get(tid);

      let dur = typeof t.duration_seconds === "number" ? t.duration_seconds : null;

      if (dur === null || dur === undefined) {

        dur = calculateDurationSeconds(

          (trace?.phase_started_at || t.phase_started_at) as string | undefined,

          (trace?.phase_finished_at || t.phase_finished_at) as string | undefined

        );

      }

      if (dur !== null && dur !== undefined && dur >= 0) {

        totalSec += dur;

        count += 1;

      }

      if (typeof trace?.train_duration_seconds === "number") {

        totalTrainSec += trace.train_duration_seconds;

      }

      if (typeof trace?.bench_duration_seconds === "number") {

        totalBenchSec += trace.bench_duration_seconds;

      }

    }

    return { totalSec, totalTrainSec, totalBenchSec, count };

  }, [trains, traceByTrainRun]);



  const curriculumProgression = useMemo(

    () => buildCurriculumProgression(trains, traceByTrainRun),

    [trains, traceByTrainRun]

  );



  const stepMetricByRunId = useMemo(() => {

    const map = new Map<string, CurriculumStepMetric>();

    for (const step of curriculumProgression) {

      map.set(step.runId, step);

    }

    return map;

  }, [curriculumProgression]);



  const [trainSummary, setTrainSummary] = useState<Dict | null>(null);

  const [selectedTrainRunId, setSelectedTrainRunId] = useState("");



  useEffect(() => {

    if (!trains.length) {

      setSelectedTrainRunId("");

      return;

    }

    setSelectedTrainRunId(String(trains[0].run_id || ""));

  }, [trains]);



  const activeTrainRow = useMemo(() => {

    if (!trains.length) return null;

    return trains.find((t) => String(t.run_id || "") === selectedTrainRunId) || trains[0];

  }, [trains, selectedTrainRunId]);



  useEffect(() => {

    const activeRunId = activeTrainRow?.run_id ? String(activeTrainRow.run_id) : "";

    if (!activeRunId) {

      setTrainSummary(null);

      return;

    }

    let cancelled = false;

    async function fetchSummary() {

      try {

        const s = await fetchTrainSummary(activeRunId);

        if (!cancelled) setTrainSummary(s);

      } catch {

        if (!cancelled) setTrainSummary(null);

      }

    }

    void fetchSummary();

    return () => {

      cancelled = true;

    };

  }, [activeTrainRow]);

  const { trainCounts, evalCounts, scenariosSeen } = useMemo(() => {

    const tCounts: Record<string, number> = {};

    const eCounts: Record<string, number> = {};



    const unpack = (key: string, count: number, target: Record<string, number>) => {

      let s = String(key || "").trim();

      if (!s) return;

      if (s.startsWith("multi:")) s = s.substring(6).trim();

      const parts = s.includes("|") ? s.split("|").map((p) => p.trim()).filter(Boolean) : [s];

      for (const p of parts) {

        if (!p) continue;

        target[p] = (target[p] || 0) + count;

      }

    };



    const rawT = (modelDetail?.scenario_train_counts || {}) as Record<string, number>;

    const rawE = (modelDetail?.scenario_eval_counts || {}) as Record<string, number>;



    for (const [k, v] of Object.entries(rawT)) unpack(k, v, tCounts);

    for (const [k, v] of Object.entries(rawE)) unpack(k, v, eCounts);



    const sSet = new Set<string>([...Object.keys(tCounts), ...Object.keys(eCounts)]);

    for (const s of (modelDetail?.scenarios_seen || [])) {

      let cleaned = String(s || "").trim();

      if (!cleaned) continue;

      if (cleaned.startsWith("multi:")) cleaned = cleaned.substring(6).trim();

      const parts = cleaned.includes("|") ? cleaned.split("|").map((p) => p.trim()).filter(Boolean) : [cleaned];

      for (const p of parts) {

        if (p) sSet.add(p);

      }

    }



    return {

      trainCounts: tCounts,

      evalCounts: eCounts,

      scenariosSeen: Array.from(sSet).sort(),

    };

  }, [modelDetail]);



  return (

    <div className="wrap">

      <div className="bar" style={{ justifyContent: "space-between" }}>

        <h1 style={{ margin: 0, fontSize: 18 }}>Curriculum Reporting Viewer</h1>

        <div className="bar" style={{ gap: 8 }}>

          <button
            onClick={() => window.open("/docs/", "_blank")}
            style={{
              background: "#0284c7",
              color: "#ffffff",
              border: "none",
              borderRadius: 4,
              padding: "4px 10px",
              fontSize: 12,
              fontWeight: 700,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: 5,
            }}
            title="Open Interactive Technical Documentation Hub"
          >
            <span>📚</span> Documentation
          </button>
          <button
            onClick={() => window.open("http://127.0.0.1:8780", "_blank")}
            style={{
              background: "#065f46",
              color: "#6ee7b7",
              border: "1px solid #10b981",
              borderRadius: 4,
              padding: "4px 10px",
              fontSize: 12,
              fontWeight: 700,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: 5,
            }}
            title="Open Tactical Unit & Formation Catalog Editor (Port 8780)"
          >
            <span>🎖️</span> Unit Editor (8780)
          </button>
          <button
            onClick={() => window.open("http://127.0.0.1:8001/docs", "_blank")}
            style={{
              background: "#1e293b",
              color: "#fde047",
              border: "1px solid #eab308",
              borderRadius: 4,
              padding: "4px 10px",
              fontSize: 12,
              fontWeight: 700,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: 5,
            }}
            title="Open FastAPI Swagger Interactive Docs (Port 8001)"
          >
            <span>⚡</span> Swagger API (8001)
          </button>

          <button onClick={() => void load()}>Reload</button>

          <span className="muted">

            schema={String(catalog?.schema_version || "")} | source={String(catalog?.catalog_source || "")}

          </span>

          {error ? <span className="muted" style={{ color: "#fca5a5" }}>error: {error}</span> : null}

        </div>

      </div>



      <div className="grid">

        {/* Engines Panel */}

        <section

          className="panel"

          style={{

            width: panel1Width,

            minWidth: 130,

            maxWidth: 500,

            flexShrink: 0,

            boxSizing: "border-box",

          }}

        >

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

                  <b style={{ fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={e.engine}>

                    {e.engine}

                  </b>

                  <button

                    onClick={(ev) => {

                      ev.stopPropagation();

                      window.open(

                        `/elo?engine=${encodeURIComponent(e.engine)}&model=${encodeURIComponent(selectedModel || "__all__")}`,

                        "_blank",

                        "noopener,noreferrer"

                      );

                    }}

                    style={{ fontSize: 11, padding: "2px 6px", flexShrink: 0 }}

                  >

                    ELO

                  </button>

                </div>

                <div className="muted">{e.models?.length ?? 0} models</div>

              </div>

            ))}

          </div>

        </section>



        {/* Resizer Divider 1 */}

        <div

          className={`resizer-col ${isDraggingP1 ? "dragging" : ""}`}

          onMouseDown={handleMouseDownP1}

          onDoubleClick={handleResetP1}

          title="Arrastrar para redimensionar Engines | Doble clic para restablecer ancho (190px)"

        />



        {/* Models Panel */}

        <section

          className="panel"

          style={{

            width: panel2Width,

            minWidth: 180,

            maxWidth: 750,

            flexShrink: 0,

            boxSizing: "border-box",

          }}

        >

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

                  <div className="bar" style={{ justifyContent: "space-between", alignItems: "center", gap: 6 }}>

                    <b style={{ fontSize: 12, wordBreak: "break-all" }}>{m.model_id}</b>

                    <div style={{ display: "flex", gap: 4, alignItems: "center", flexShrink: 0 }}>

                      <button

                        onClick={(ev) => {

                          ev.stopPropagation();

                          window.open(

                            `/model?engine=${encodeURIComponent(selectedEngine)}&model=${encodeURIComponent(m.model_id)}`,

                            "_blank",

                            "noopener,noreferrer"

                          );

                        }}

                        style={{ fontSize: 11, padding: "2px 6px", whiteSpace: "nowrap" }}

                      >

                        View Detail

                      </button>

                      <button

                        onClick={(ev) => {

                          ev.stopPropagation();

                          void handleDeleteModel(m.model_id);

                        }}

                        disabled={deletingModelId === m.model_id}

                        style={{

                          fontSize: 11,

                          padding: "2px 6px",

                          whiteSpace: "nowrap",

                          background: "#dc2626",

                          color: "#ffffff",

                          border: "none",

                          borderRadius: 4,

                          cursor: "pointer",

                          fontWeight: 600,

                        }}

                        title="Delete this experiment and all its files on disk"

                      >

                        {deletingModelId === m.model_id ? "Borrando..." : "🗑️ Borrar"}

                      </button>

                    </div>

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



        {/* Resizer Divider 2 */}

        <div

          className={`resizer-col ${isDraggingP2 ? "dragging" : ""}`}

          onMouseDown={handleMouseDownP2}

          onDoubleClick={handleResetP2}

          title="Arrastrar para redimensionar Models y Summary | Doble clic para restablecer ancho (290px)"

        />



        {/* Summary Panel with 3 Tabs */}

        <section

          className="panel"

          style={{

            flex: 1,

            minWidth: 320,

            minHeight: 0,

            boxSizing: "border-box",

          }}

        >

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
                  {/* Ultra-compact Executive Header & Action Bar */}
                  <div
                    style={{
                      background: "#0f172a",
                      border: "1px solid #334155",
                      borderRadius: 6,
                      padding: "8px 12px",
                      marginBottom: 10,
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      flexWrap: "wrap",
                      gap: 8,
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                      <span style={{ fontSize: 13, fontWeight: 700, color: "#38bdf8" }}>
                        {catalogModel.model_id}
                      </span>
                      <span
                        style={{
                          background: "#1e293b",
                          border: "1px solid #475569",
                          borderRadius: 4,
                          padding: "2px 6px",
                          fontSize: 11,
                          color: "#94a3b8",
                        }}
                      >
                        {selectedEngine} / {String((modelDetail as Dict)?.algorithm || selectedEngine)}
                      </span>
                      <span style={{ fontSize: 11, color: "#cbd5e1" }}>
                        <b>{catalogModel.train_runs_count ?? trains.length}</b> trains · <b>{catalogModel.eval_history_total_count ?? evals.length}</b> evals
                      </span>
                      {modelTrainDurationStats.totalSec > 0 && (
                        <span
                          style={{
                            fontSize: 11,
                            color: "#38bdf8",
                            background: "#0369a120",
                            border: "1px solid #0284c740",
                            padding: "2px 6px",
                            borderRadius: 4,
                          }}
                          title={`Training duration: ${formatDurationDetailed(modelTrainDurationStats.totalSec)}`}
                        >
                          ⏱️ Train: {formatDuration(modelTrainDurationStats.totalSec)}
                        </span>
                      )}
                      {curriculumDurationStats.totalSec > 0 && (
                        <span
                          style={{
                            fontSize: 11,
                            color: "#c084fc",
                            background: "#7e22ce20",
                            border: "1px solid #9333ea40",
                            padding: "2px 6px",
                            borderRadius: 4,
                          }}
                          title={`Curriculum duration: ${formatDurationDetailed(curriculumDurationStats.totalSec)}`}
                        >
                          ⏱️ Curr: {formatDuration(curriculumDurationStats.totalSec)}
                        </span>
                      )}
                    </div>

                    <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                      <button
                        type="button"
                        onClick={() => setShowDetailedMeta(!showDetailedMeta)}
                        style={{
                          background: showDetailedMeta ? "#334155" : "#1e293b",
                          color: "#cbd5e1",
                          fontSize: 11,
                          padding: "4px 8px",
                          borderRadius: 4,
                          border: "1px solid #475569",
                          cursor: "pointer",
                        }}
                        title="Toggle full metadata drawer"
                      >
                        {showDetailedMeta ? "Metadata ▲" : "Metadata ▼"}
                      </button>
                      <button
                        type="button"
                        onClick={() => window.open(detailUrl, "_blank", "noopener,noreferrer")}
                        style={{
                          background: "#0ea5e9",
                          color: "#0f172a",
                          fontWeight: "bold",
                          fontSize: 11,
                          padding: "4px 10px",
                          borderRadius: 4,
                          border: "none",
                          cursor: "pointer",
                        }}
                      >
                        → Full Detail
                      </button>
                      <button
                        type="button"
                        onClick={() => window.open(eloUrl, "_blank", "noopener,noreferrer")}
                        style={{
                          fontSize: 11,
                          padding: "4px 10px",
                          borderRadius: 4,
                          cursor: "pointer",
                        }}
                      >
                        ELO Leaderboard
                      </button>
                      <button
                        type="button"
                        onClick={() => void handleDeleteModel(catalogModel.model_id)}
                        disabled={deletingModelId === catalogModel.model_id}
                        style={{
                          background: "#dc2626",
                          color: "#ffffff",
                          border: "none",
                          fontWeight: "bold",
                          fontSize: 11,
                          padding: "4px 10px",
                          borderRadius: 4,
                          cursor: "pointer",
                        }}
                        title="Delete this experiment and all its files on disk"
                      >
                        {deletingModelId === catalogModel.model_id ? "Deleting..." : "🗑️ Delete"}
                      </button>
                    </div>
                  </div>

                  {/* Collapsible Detailed Metadata */}
                  {showDetailedMeta && (
                    <div
                      className="kpi-grid"
                      style={{
                        marginBottom: 10,
                        background: "#0f172a",
                        border: "1px solid #334155",
                        borderRadius: 6,
                        padding: 8,
                      }}
                    >
                      <div className="kpi">
                        <div className="k">latest_train_run_id</div>
                        <div className="v" style={{ wordBreak: "break-all", fontSize: 11 }}>
                          {catalogModel.latest_train_run_id || "-"}
                        </div>
                      </div>
                      <div className="kpi">
                        <div className="k">config_fingerprint</div>
                        <div className="v" style={{ fontSize: 11 }}>{String(modelDetail?.config_fingerprint || "-")}</div>
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
                  )}

                  {/* Slim Tactical Quality & Asymmetric Balance Bar */}
                  {tacticalQuality && tacticalQuality.status === "ok" ? (
                    <div
                      style={{
                        marginBottom: 10,
                        background: "#0b1220",
                        border: "1px solid #334155",
                        borderRadius: 6,
                        padding: "6px 12px",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        flexWrap: "wrap",
                        gap: 10,
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{ fontSize: 12, fontWeight: 700, color: "#38bdf8" }}>
                          🎯 Tactical Quality
                        </span>
                        <span
                          style={{
                            background:
                              (tacticalQuality.quality_gate as Dict)?.status === "PASS"
                                ? "#22c55e20"
                                : (tacticalQuality.quality_gate as Dict)?.status === "WARN"
                                ? "#f59e0b20"
                                : "#ef444420",
                            border: `1px solid ${
                              (tacticalQuality.quality_gate as Dict)?.status === "PASS"
                                ? "#22c55e"
                                : (tacticalQuality.quality_gate as Dict)?.status === "WARN"
                                ? "#f59e0b"
                                : "#ef4444"
                            }`,
                            color:
                              (tacticalQuality.quality_gate as Dict)?.status === "PASS"
                                ? "#4ade80"
                                : (tacticalQuality.quality_gate as Dict)?.status === "WARN"
                                ? "#fbbf24"
                                : "#f87171",
                            padding: "1px 6px",
                            borderRadius: 4,
                            fontSize: 10,
                            fontWeight: 700,
                          }}
                        >
                          {String((tacticalQuality.quality_gate as Dict)?.status || "EVAL")}
                        </span>
                        <span style={{ fontSize: 11, color: "#94a3b8" }}>
                          Grade: <strong style={{ color: "#38bdf8" }}>{String(tacticalQuality.tactical_grade || "-")}</strong>
                        </span>
                      </div>

                      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", fontSize: 11 }}>
                        <span title="Tactical Quality Score (0-100 composite)">
                          <span style={{ color: "#94a3b8" }}>TQS: </span>
                          <strong style={{ color: "#38bdf8" }}>{Number(tacticalQuality.tactical_quality_score || 0).toFixed(1)}</strong>
                        </span>
                        <span title="Bradley-Terry Calibrated Anchor ELO">
                          <span style={{ color: "#94a3b8" }}>Anchor ELO: </span>
                          <strong style={{ color: "#93c5fd" }}>{Number(tacticalQuality.anchor_elo || 1200).toFixed(0)}</strong>
                        </span>
                        <span title="Balanced Mirror Win Rate vs Random (cancels side bias)">
                          <span style={{ color: "#94a3b8" }}>Mirror WR: </span>
                          <strong style={{ color: "#34d399" }}>{(Number(tacticalQuality.global_mirror_score_vs_random || 0) * 100).toFixed(1)}%</strong>
                        </span>
                        <span title="Mean Asymmetry Gap (disfavored side vulnerability)">
                          <span style={{ color: "#94a3b8" }}>Asymm Gap: </span>
                          <strong style={{ color: "#fcd34d" }}>{(Number(tacticalQuality.mean_asymmetry_gap || 0) * 100).toFixed(1)}%</strong>
                        </span>
                        <span title="Combat Exchange Ratio (CER: kills / losses)">
                          <span style={{ color: "#94a3b8" }}>CER: </span>
                          <strong style={{ color: "#fb7185" }}>{Number(tacticalQuality.combat_exchange_ratio || 1.0).toFixed(2)}x</strong>
                        </span>
                        <span title="Net Victory Points average">
                          <span style={{ color: "#94a3b8" }}>VP Net: </span>
                          <strong style={{ color: "#c084fc" }}>
                            {Number(tacticalQuality.vp_net_avg || 0) > 0 ? "+" : ""}
                            {Number(tacticalQuality.vp_net_avg || 0).toFixed(2)}
                          </strong>
                        </span>
                      </div>

                      {Array.isArray((tacticalQuality.quality_gate as Dict)?.reasons) &&
                        ((tacticalQuality.quality_gate as Dict).reasons as string[]).length > 0 && (
                          <div style={{ width: "100%", marginTop: 2, fontSize: 10, color: "#fca5a5" }}>
                            ⚠️ {((tacticalQuality.quality_gate as Dict).reasons as string[]).join(" • ")}
                          </div>
                        )}
                    </div>
                  ) : !loadingModelDetail ? (
                    <div
                      style={{
                        marginBottom: 10,
                        background: "#0b1220",
                        border: "1px dashed #334155",
                        borderRadius: 6,
                        padding: "6px 12px",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        flexWrap: "wrap",
                        gap: 8,
                        fontSize: 11,
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <span style={{ fontWeight: 700, color: "#94a3b8" }}>🎯 Tactical Quality</span>
                        <span style={{ fontSize: 9, background: "#1e293b", border: "1px solid #475569", color: "#94a3b8", padding: "1px 5px", borderRadius: 3 }}>
                          EVALUATION PENDING
                        </span>
                      </div>
                      <span className="muted" style={{ fontSize: 10 }}>
                        TQS, Anchor ELO, and Side Asymmetry Gap will calculate automatically once benchmark evaluations run.
                      </span>
                    </div>
                  ) : null}

                  {/* Loading indicator */}
                  {loadingModelDetail && (
                    <div style={{ padding: "8px 0", color: "#38bdf8", fontSize: 12, display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ display: "inline-block", width: 12, height: 12, border: "2px solid #555", borderTopColor: "#38bdf8", borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
                      Loading execution history and scenario details...
                    </div>
                  )}

                  {/* Ultra-compact horizontal Scenarios Chip Strip */}
                  {scenariosSeen.length > 0 && (
                    <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 10, flexWrap: "wrap", fontSize: 11 }}>
                      <span style={{ fontWeight: 700, color: "#94a3b8" }}>🗺️ Scenarios ({scenariosSeen.length}):</span>
                      {scenariosSeen.map((s) => {
                        const tc = trainCounts[s] ?? 0;
                        const ec = evalCounts[s] ?? 0;
                        return (
                          <span
                            key={s}
                            style={{
                              background: "#0f172a",
                              border: "1px solid #334155",
                              padding: "2px 8px",
                              borderRadius: 4,
                              display: "inline-flex",
                              alignItems: "center",
                              gap: 6,
                            }}
                            title={`Scenario: ${s} | Train runs: ${tc} | Eval runs: ${ec}`}
                          >
                            <code style={{ fontSize: 11, color: "#38bdf8", fontWeight: 600 }}>{s}</code>
                            <span style={{ color: "#60a5fa", fontWeight: 700, fontSize: 10 }}>T:{tc}</span>
                            <span style={{ color: "#475569" }}>|</span>
                            <span style={{ color: "#34d399", fontWeight: 700, fontSize: 10 }}>E:{ec}</span>
                          </span>
                        );
                      })}
                    </div>
                  )}

                  {/* Curriculum Progression Chart & Lineage Flow */}
                  <div style={{ marginBottom: 14 }}>
                    {curriculumProgression.length > 0 && (
                      <>
                        <CurriculumProgressionChart steps={curriculumProgression} />

                        <CurriculumLineageFlow
                          steps={curriculumProgression}
                          selectedRunId={selectedTrainRunId}
                          onSelectRunId={(runId) => setSelectedTrainRunId(runId)}
                        />
                      </>
                    )}

                    {/* Detailed Scenarios Trained & Evaluated Table (positioned below progression flow) */}
                    {scenariosSeen.length > 0 && (
                      <div style={{ marginBottom: 14 }}>
                        <h4 style={{ margin: "0 0 6px 0", fontSize: 12, color: "#94a3b8", display: "flex", alignItems: "center", gap: 6 }}>
                          <span>🗺️</span> Scenarios Trained & Evaluated ({scenariosSeen.length})
                        </h4>
                        <div className="scroll-table-container" style={{ maxHeight: 200, border: "1px solid #334155", borderRadius: 6 }}>
                          <table style={{ margin: 0 }}>
                            <thead>
                              <tr>
                                <th style={{ background: "#0f172a", textAlign: "left", padding: "6px 12px" }}>scenario_id</th>
                                <th style={{ background: "#0f172a", textAlign: "center", width: 140, padding: "6px 12px" }}>train_count</th>
                                <th style={{ background: "#0f172a", textAlign: "center", width: 140, padding: "6px 12px" }}>eval_count</th>
                              </tr>
                            </thead>
                            <tbody>
                              {scenariosSeen.map((s) => {
                                const tc = trainCounts[s] ?? 0;
                                const ec = evalCounts[s] ?? 0;
                                return (
                                  <tr key={s} style={{ lineHeight: 1.6 }}>
                                    <td style={{ padding: "6px 12px" }}>
                                      <code style={{ fontSize: 12, color: "#38bdf8", fontWeight: 600 }}>{s}</code>
                                    </td>
                                    <td style={{ textAlign: "center", padding: "6px 12px" }}>
                                      <span
                                        style={{
                                          background: tc > 0 ? "#172554" : "#1e293b",
                                          color: tc > 0 ? "#60a5fa" : "#64748b",
                                          padding: "2px 8px",
                                          borderRadius: 4,
                                          fontWeight: 700,
                                          fontSize: 12,
                                          border: `1px solid ${tc > 0 ? "#1d4ed8" : "#334155"}`,
                                        }}
                                      >
                                        {tc}
                                      </span>
                                    </td>
                                    <td style={{ textAlign: "center", padding: "6px 12px" }}>
                                      <span
                                        style={{
                                          background: ec > 0 ? "#064e3b" : "#1e293b",
                                          color: ec > 0 ? "#34d399" : "#64748b",
                                          padding: "2px 8px",
                                          borderRadius: 4,
                                          fontWeight: 700,
                                          fontSize: 12,
                                          border: `1px solid ${ec > 0 ? "#059669" : "#334155"}`,
                                        }}
                                      >
                                        {ec}
                                      </span>
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}

                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6, flexWrap: "wrap", gap: 8 }}>

                      <h3 style={{ margin: 0, fontSize: 13 }}>Training Runs & Curriculum Progress ({trains.length})</h3>

                      <span className="muted" style={{ fontSize: 11 }}>

                        Bradley-Terry calibrated ELO, Win Rate, and Gate evaluation metrics by curriculum phase.

                      </span>

                    </div>



                    {trains.length > 0 ? (

                      <>

                        <div className="scroll-table-container" style={{ maxHeight: 420 }}>

                          <table>

                            <thead>

                              <tr>

                                <th>run_id</th>

                                <th>curriculum phase</th>

                                <th title="Total phase wall time and detailed split between Training (Self-play + Updates) and Benchmark evaluation">⏱️ Duration (Train / Bench)</th>

                                <th title="Bradley-Terry Anchor ELO and delta vs previous phase">🎯 Calibrated ELO (Δ)</th>

                                <th title="Win rate in resolved non-timeout matches">⚔️ Win Rate</th>

                                <th title="Promotion gate status and reinforcement cycle decision">🚪 Gate / Decision</th>

                                <th title="Average net victory points and enemy attrition">📊 VP Net / Losses</th>

                                <th>scenario</th>

                                <th>created_at</th>

                                <th>git_commit</th>

                                <th>checkpoint</th>

                              </tr>

                            </thead>

                            <tbody>

                              {trains.map((t) => {

                                const tid = String(t.run_id || "").trim();

                                const trace = traceByTrainRun.get(tid);

                                const sm = stepMetricByRunId.get(tid);

                                const phaseName = String(trace?.phase_name || t.curriculum_phase || "-");

                                let dur = typeof t.duration_seconds === "number" ? t.duration_seconds : null;

                                if (dur === null || dur === undefined) {

                                  dur = calculateDurationSeconds(

                                    (trace?.phase_started_at || t.phase_started_at) as string | undefined,

                                    (trace?.phase_finished_at || t.phase_finished_at) as string | undefined

                                  );

                                }

                                return (

                                  <tr

                                    key={String(t.run_id || Math.random())}

                                    style={

                                      sm?.isPhaseSelected

                                        ? {

                                            background: "#451a0325",

                                            borderLeft: "3px solid #f59e0b",

                                          }

                                        : undefined

                                    }

                                  >

                                    <td><b>{String(t.run_id || "-")}</b></td>

                                    <td>

                                      {phaseName !== "-" ? (

                                        <div style={{ display: "inline-flex", alignItems: "center", gap: 5, flexWrap: "wrap" }}>

                                          <span

                                            style={{

                                              background: sm?.isPhaseSelected ? "#451a0390" : "#0284c720",

                                              border: `1px solid ${sm?.isPhaseSelected ? "#f59e0b80" : "#0284c740"}`,

                                              color: sm?.isPhaseSelected ? "#fde047" : "#38bdf8",

                                              padding: "2px 6px",

                                              borderRadius: 4,

                                              fontSize: 11,

                                              fontWeight: 700,

                                            }}

                                          >

                                            {phaseName}

                                            {sm && sm.totalCyclesInPhase > 1

                                              ? ` (C${sm.cycleInPhase}/${sm.totalCyclesInPhase})`

                                              : ""}

                                          </span>

                                          {sm?.isPhaseSelected && (

                                            <span

                                              style={{

                                                background: "#f59e0b25",

                                                border: "1px solid #f59e0b90",

                                                color: "#fbbf24",

                                                padding: "1px 5px",

                                                borderRadius: 3,

                                                fontSize: 9.5,

                                                fontWeight: 800,

                                                whiteSpace: "nowrap",

                                              }}

                                              title="Best cycle selected from this phase to promote to the next phase"

                                            >

                                              ★ SELECTED

                                            </span>

                                          )}

                                        </div>

                                      ) : (

                                        <span className="muted">-</span>

                                      )}

                                    </td>

                                    <td>

                                      {(() => {

                                        const trainSec = sm?.trainDurationSeconds ?? (typeof trace?.train_duration_seconds === "number" ? trace.train_duration_seconds : null);

                                        const benchSec = sm?.benchDurationSeconds ?? (typeof trace?.bench_duration_seconds === "number" ? trace.bench_duration_seconds : null);

                                        const selfplaySec = sm?.selfplayDurationSeconds ?? (typeof trace?.selfplay_duration_seconds === "number" ? trace.selfplay_duration_seconds : null);

                                        const optSec = sm?.optDurationSeconds ?? (typeof trace?.opt_duration_seconds === "number" ? trace.opt_duration_seconds : null);



                                        if (dur === null || dur === undefined || dur < 0) {

                                          return <span className="muted">-</span>;

                                        }



                                        const hasSplit = trainSec !== null && benchSec !== null && (trainSec > 0 || benchSec > 0);
                                        const sumTiming = (trainSec || 0) + (benchSec || 0);
                                        const totalWall = (dur && dur > sumTiming) ? dur : sumTiming;
                                        const overheadSec = Math.max(0, totalWall - sumTiming);

                                        const trainPct = totalWall > 0 ? ((trainSec || 0) / totalWall) * 100 : 0;
                                        const benchPct = totalWall > 0 ? ((benchSec || 0) / totalWall) * 100 : 0;
                                        const overheadPct = totalWall > 0 ? Math.max(0, 100 - trainPct - benchPct) : 0;

                                        return (
                                          <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                                            <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                                              <span
                                                style={{
                                                  background: "#10b98118",
                                                  border: "1px solid #10b98140",
                                                  color: "#34d399",
                                                  padding: "1px 5px",
                                                  borderRadius: 4,
                                                  fontSize: 11,
                                                  fontWeight: 700,
                                                  whiteSpace: "nowrap",
                                                }}
                                                title={formatDurationDetailed(dur)}
                                              >
                                                ⏱️ {formatDuration(dur)}
                                              </span>
                                            </div>

                                            {hasSplit && (
                                              <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                                                <div
                                                  style={{
                                                    display: "flex",
                                                    width: "100%",
                                                    maxWidth: 120,
                                                    height: 4,
                                                    borderRadius: 2,
                                                    overflow: "hidden",
                                                    background: "#1e293b",
                                                  }}
                                                  title={`Total Cycle: ${formatDuration(totalWall)} | Train: ${formatDuration(trainSec!)} (${Math.round(trainPct)}%) | Bench: ${formatDuration(benchSec!)} (${Math.round(benchPct)}%)${overheadSec > 2 ? ` | Overhead/IO: ${formatDuration(overheadSec)} (${Math.round(overheadPct)}%)` : ""}`}
                                                >
                                                  <div style={{ width: `${trainPct}%`, background: "#38bdf8" }} />
                                                  <div style={{ width: `${benchPct}%`, background: "#f59e0b" }} />
                                                  {overheadPct > 0.5 && <div style={{ width: `${overheadPct}%`, background: "#64748b" }} />}
                                                </div>

                                                <div style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 10, color: "#94a3b8", whiteSpace: "nowrap" }}>
                                                  <span title={`Self-Play: ${formatDuration(selfplaySec || 0)} | Updates: ${formatDuration(optSec || 0)}`}>
                                                    <span style={{ color: "#38bdf8", fontWeight: 600 }}>Train:</span> {formatDuration(trainSec!)}
                                                  </span>
                                                  <span>•</span>
                                                  <span>
                                                    <span style={{ color: "#fbbf24", fontWeight: 600 }}>Bench:</span> {formatDuration(benchSec!)}
                                                  </span>
                                                  {overheadSec > 3 && (
                                                    <span style={{ color: "#64748b", fontSize: 9 }} title="Cycle initialization, checkpoint saves, quality gate evaluation, and DuckDB telemetry sync">
                                                      (+{formatDuration(overheadSec)})
                                                    </span>
                                                  )}
                                                </div>
                                              </div>
                                            )}
                                          </div>
                                        );

                                      })()}

                                    </td>

                                    <td>

                                      {sm?.elo !== null && sm?.elo !== undefined ? (

                                        <div style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>

                                          <span

                                            style={{

                                              background: sm.isPhaseSelected ? "#451a0390" : "#0284c725",

                                              border: `1px solid ${sm.isPhaseSelected ? "#f59e0b90" : "#0284c760"}`,

                                              color: sm.isPhaseSelected ? "#fde047" : "#38bdf8",

                                              padding: "2px 7px",

                                              borderRadius: 4,

                                              fontSize: 12,

                                              fontWeight: 700,

                                            }}

                                          >

                                            {sm.isPhaseSelected ? `★ ${sm.elo}` : sm.elo}

                                          </span>

                                          {sm.deltaElo !== null && (

                                            <span

                                              style={{

                                                fontSize: 10,

                                                fontWeight: 700,

                                                color: sm.deltaElo > 0 ? "#34d399" : sm.deltaElo < 0 ? "#f87171" : "#94a3b8",

                                              }}

                                              title={`Delta vs previous phase: ${sm.deltaElo >= 0 ? "+" : ""}${sm.deltaElo} pts`}

                                            >

                                              {sm.deltaElo > 0 ? `▲+${sm.deltaElo}` : sm.deltaElo < 0 ? `▼${sm.deltaElo}` : "=0"}

                                            </span>

                                          )}

                                        </div>

                                      ) : (

                                        <span className="muted">-</span>

                                      )}

                                    </td>

                                    <td>

                                      {sm?.winRate !== null && sm?.winRate !== undefined ? (

                                        <span

                                          style={{

                                            background: sm.winRate >= 0.85 ? "#10b98120" : sm.winRate >= 0.6 ? "#0284c720" : "#f59e0b20",

                                            border: `1px solid ${sm.winRate >= 0.85 ? "#10b98150" : sm.winRate >= 0.6 ? "#0284c750" : "#f59e0b50"}`,

                                            color: sm.winRate >= 0.85 ? "#34d399" : sm.winRate >= 0.6 ? "#38bdf8" : "#fbbf24",

                                            padding: "2px 6px",

                                            borderRadius: 4,

                                            fontSize: 11,

                                            fontWeight: 700,

                                          }}

                                          title={`Win Rate: ${(sm.winRate * 100).toFixed(1)}% | Score: ${sm.score !== null ? (sm.score * 100).toFixed(1) + '%' : '-'}`}

                                        >

                                          {(sm.winRate * 100).toFixed(1)}%

                                        </span>

                                      ) : (

                                        <span className="muted">-</span>

                                      )}

                                    </td>

                                    <td>

                                      {sm?.gateStatus ? (

                                        <div style={{ display: "inline-flex", flexDirection: "column", gap: 2 }}>

                                          <span

                                            style={{

                                              background: sm.gateStatus === "PASS" || sm.gateStatus === "PASSED" ? "#10b98125" : "#ef444425",

                                              border: `1px solid ${sm.gateStatus === "PASS" || sm.gateStatus === "PASSED" ? "#10b98160" : "#ef444460"}`,

                                              color: sm.gateStatus === "PASS" || sm.gateStatus === "PASSED" ? "#34d399" : "#f87171",

                                              padding: "1px 6px",

                                              borderRadius: 3,

                                              fontSize: 10,

                                              fontWeight: 700,

                                              textAlign: "center",

                                            }}

                                            title={sm.gateFailReasons.length ? sm.gateFailReasons.join("\n") : "Cumple los criterios de pase del Gate"}

                                          >

                                            {sm.gateStatus}

                                          </span>

                                          {sm.promotionDecision && (

                                            <span

                                              style={{

                                                fontSize: 9.5,

                                                color: sm.promotionDecision === "promoted" ? "#34d399" : "#fbbf24",

                                                fontWeight: 600,

                                                textTransform: "uppercase",

                                                textAlign: "center",

                                              }}

                                            >

                                              {sm.promotionDecision}

                                            </span>

                                          )}

                                        </div>

                                      ) : (

                                        <span className="muted">-</span>

                                      )}

                                    </td>

                                    <td>

                                      {sm?.capturedAvg !== null || sm?.vpNet !== null ? (

                                        <div style={{ fontSize: 11, whiteSpace: "nowrap" }}>

                                          <span style={{ color: "#38bdf8", fontWeight: 600 }} title="Average casualties inflicted per match">

                                            🎯 {sm.capturedAvg !== null ? sm.capturedAvg.toFixed(1) : "-"} kills

                                          </span>

                                          {sm.vpNet !== null && (

                                            <span

                                              style={{

                                                marginLeft: 6,

                                                color: sm.vpNet > 0 ? "#34d399" : sm.vpNet < 0 ? "#f87171" : "#94a3b8",

                                                fontWeight: 600,

                                              }}

                                              title="Saldo neto promedio de puntos de victoria"

                                            >

                                              ({sm.vpNet > 0 ? `+${sm.vpNet.toFixed(2)}` : sm.vpNet.toFixed(2)} VP)

                                            </span>

                                          )}

                                        </div>

                                      ) : (

                                        <span className="muted">-</span>

                                      )}

                                    </td>

                                    <td>{String(t.scenario_id || "-")}</td>

                                    <td>{formatLocalDate(t.created_at_utc)}</td>

                                    <td><code>{String(t.git_commit || "-").slice(0, 8)}</code></td>

                                    <td className="muted" style={{ fontSize: 11 }}>{String(t.latest_checkpoint || "-")}</td>

                                  </tr>

                                );

                              })}

                            </tbody>

                          </table>

                        </div>

                        <div

                          style={{

                            marginTop: 6,

                            padding: "6px 12px",

                            background: "#0f172a",

                            borderRadius: 4,

                            border: "1px solid #1e293b",

                            display: "flex",

                            justifyContent: "space-between",

                            alignItems: "center",

                            fontSize: 12,

                            flexWrap: "wrap",

                            gap: 6,

                          }}

                        >

                          <span className="muted">

                            Showing all {trains.length} training runs (scrollable)

                          </span>

                          <span style={{ fontWeight: 600, color: "#e2e8f0", display: "inline-flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>

                            <span>

                              ⏱️ Total Time:{" "}

                              <strong style={{ color: "#34d399" }}>

                                {modelTrainDurationStats.totalSec > 0

                                  ? formatDurationDetailed(modelTrainDurationStats.totalSec)

                                  : "N/A"}

                              </strong>

                            </span>

                            {modelTrainDurationStats.totalTrainSec > 0 && modelTrainDurationStats.totalBenchSec > 0 && (

                              <span style={{ fontSize: 11, color: "#94a3b8" }}>

                                (🏋️ <span style={{ color: "#38bdf8", fontWeight: 700 }}>Train:</span>{" "}

                                {formatDurationDetailed(modelTrainDurationStats.totalTrainSec)} [

                                {Math.round((modelTrainDurationStats.totalTrainSec / (modelTrainDurationStats.totalTrainSec + modelTrainDurationStats.totalBenchSec)) * 100)}%] • 🎯{" "}

                                <span style={{ color: "#fbbf24", fontWeight: 700 }}>Bench:</span>{" "}

                                {formatDurationDetailed(modelTrainDurationStats.totalBenchSec)} [

                                {Math.round((modelTrainDurationStats.totalBenchSec / (modelTrainDurationStats.totalTrainSec + modelTrainDurationStats.totalBenchSec)) * 100)}%])

                              </span>

                            )}

                          </span>

                        </div>

                      </>

                    ) : (

                      <div className="muted" style={{ fontSize: 12 }}>No training runs found in DuckDB catalog.</div>

                    )}

                  </div>



                  {/* Recent Evaluations */}

                  <div>

                    <h3 style={{ margin: "0 0 6px 0", fontSize: 13 }}>Evaluation Runs ({evals.length})</h3>

                    {evals.length > 0 ? (

                      <>

                        <div className="scroll-table-container" style={{ maxHeight: 380 }}>

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

                              {evals.map((ev) => {

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

                        <div

                          style={{

                            marginTop: 6,

                            padding: "6px 12px",

                            background: "#0f172a",

                            borderRadius: 4,

                            border: "1px solid #1e293b",

                            display: "flex",

                            justifyContent: "space-between",

                            alignItems: "center",

                            fontSize: 12,

                            flexWrap: "wrap",

                            gap: 6,

                          }}

                        >

                          <span className="muted">

                            Showing all {evals.length} evaluation runs

                          </span>

                        </div>

                      </>

                    ) : (

                      <div className="muted" style={{ fontSize: 12 }}>No evaluation runs found in index.</div>

                    )}

                  </div>

                </div>

              ) : (

                <div className="muted">Select an engine and model to view summary.</div>

              )}

            </>

          )}



          {/* TAB: NETWORK TOPOLOGY */}

          {summaryTab === "topology" && (

            <div>

              <div className="bar" style={{ marginBottom: 12, justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>

                <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>

                  <span style={{ fontSize: 13, fontWeight: 700, color: "#38bdf8" }}>

                    Topología Dinámica del Modelo: {catalogModel?.model_id || selectedModel}

                  </span>

                  {trains.length > 1 && (

                    <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12 }}>

                      <span className="muted">Run/Cycle:</span>

                      <select

                        value={selectedTrainRunId}

                        onChange={(e) => setSelectedTrainRunId(e.target.value)}

                        style={{ padding: "2px 6px", fontSize: 11, background: "#1e293b", color: "#e2e8f0", border: "1px solid #334155", borderRadius: 4 }}

                      >

                        {trains.map((t) => (

                          <option key={String(t.run_id)} value={String(t.run_id)}>

                            {String(t.run_id)} ({formatLocalDate(t.created_at_utc)})

                          </option>

                        ))}

                      </select>

                    </div>

                  )}

                </div>

                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>

                  <button

                    onClick={() => window.open(detailUrl, "_blank", "noopener,noreferrer")}

                    style={{ background: "#0ea5e9", color: "#0f172a", fontWeight: "bold", fontSize: 11, padding: "4px 8px" }}

                  >

                    Abrir Detalle Completo ➔

                  </button>

                  <button

                    onClick={() => void handleDeleteModel(catalogModel?.model_id || selectedModel)}

                    disabled={deletingModelId === (catalogModel?.model_id || selectedModel)}

                    style={{

                      background: "#ef444420",

                      border: "1px solid #ef444480",

                      color: "#fca5a5",

                      fontWeight: "bold",

                      fontSize: 11,

                      padding: "4px 8px",

                      borderRadius: 4,

                      cursor: "pointer",

                    }}

                    title="Delete this experiment and all its files on disk"

                  >

                    {deletingModelId === (catalogModel?.model_id || selectedModel) ? "Deleting..." : "🗑️ Delete"}

                  </button>

                </div>

              </div>

              <NetworkTopologyTab

                trainRow={activeTrainRow}

                trainSummary={trainSummary}

                evalRows={evals}

              />

            </div>

          )}



          {/* TAB 2: CURRICULUM TRACEABILITY */}

          {summaryTab === "curriculum" && (

            <div>

              <div

                style={{

                  display: "flex",

                  justifyContent: "space-between",

                  alignItems: "center",

                  flexWrap: "wrap",

                  gap: 12,

                  marginBottom: 12,

                  background: "#0f172a",

                  padding: "10px 14px",

                  borderRadius: 6,

                  border: "1px solid #334155",

                }}

              >

                <div>

                  <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>

                    <h3 style={{ margin: 0, fontSize: 14 }}>Curriculum Phase Traceability</h3>

                    <div style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>

                      <span className="muted" style={{ fontSize: 11, fontWeight: 600 }}>Active curriculum:</span>

                      <span

                        style={{

                          background: "#0284c7",

                          color: "#ffffff",

                          fontSize: 12,

                          fontWeight: 700,

                          padding: "2px 8px",

                          borderRadius: 4,

                          fontFamily: "monospace",

                          border: "1px solid #38bdf8",

                        }}

                      >

                        {selectedCurriculumFilter === "all"

                          ? (latestActiveCurriculum || "All curriculums")

                          : selectedCurriculumFilter}

                      </span>

                    </div>

                  </div>

                  <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>

                    Phase history, hard promotion gates, decisions, and tactical curriculum metrics.

                  </div>

                </div>



                {availableCurriculums.length > 1 && (

                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>

                    <span className="muted" style={{ fontSize: 11, fontWeight: 600 }}>Filter curriculum:</span>

                    <select

                      value={selectedCurriculumFilter}

                      onChange={(e) => setSelectedCurriculumFilter(e.target.value)}

                      style={{

                        padding: "3px 8px",

                        fontSize: 12,

                        background: "#1e293b",

                        color: "#e2e8f0",

                        border: "1px solid #475569",

                        borderRadius: 4,

                        fontWeight: 600,

                      }}

                    >

                      <option value="all">All ({traceRows.length} records)</option>

                      {availableCurriculums.map((c) => (

                        <option key={c} value={c}>

                          {c} ({traceRows.filter((r) => String(r.curriculum_name || r.curriculum || "").trim() === c).length})

                        </option>

                      ))}

                    </select>

                  </div>

                )}

              </div>



              {/* KPI Summary for Curriculum Times */}

              <div

                className="kpi-grid"

                style={{

                  marginBottom: 14,

                  gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",

                }}

              >

                <div className="kpi" style={{ borderLeft: "3px solid #38bdf8" }}>

                  <div className="k">⏱️ TOTAL TIME CONSUMED</div>

                  <div className="v" style={{ color: "#38bdf8", fontWeight: 700, fontSize: 16 }}>

                    {curriculumDurationStats.totalSec > 0

                      ? formatDurationDetailed(curriculumDurationStats.totalSec)

                      : "-"}

                  </div>

                  <div className="muted" style={{ fontSize: 10, marginTop: 2 }}>

                    {curriculumDurationStats.totalTrainSec > 0 && curriculumDurationStats.totalBenchSec > 0 ? (

                      <span>

                        <span style={{ color: "#38bdf8", fontWeight: 600 }}>Train:</span> {formatDuration(curriculumDurationStats.totalTrainSec)} •{" "}

                        <span style={{ color: "#fbbf24", fontWeight: 600 }}>Bench:</span> {formatDuration(curriculumDurationStats.totalBenchSec)}

                      </span>

                    ) : (

                      `Sum across ${curriculumDurationStats.count} recorded phases`

                    )}

                  </div>

                </div>



                <div className="kpi" style={{ borderLeft: "3px solid #34d399" }}>

                  <div className="k">📊 AVERAGE PER PHASE</div>

                  <div className="v" style={{ color: "#34d399", fontWeight: 700, fontSize: 16 }}>

                    {curriculumDurationStats.avgSec !== null

                      ? formatDuration(curriculumDurationStats.avgSec)

                      : "-"}

                  </div>

                  <div className="muted" style={{ fontSize: 10, marginTop: 2 }}>

                    Mean wall time per executed phase

                  </div>

                </div>



                <div className="kpi" style={{ borderLeft: "3px solid #f59e0b" }}>

                  <div className="k">🚀 LONGEST PHASE</div>

                  <div className="v" style={{ color: "#fbbf24", fontWeight: 700, fontSize: 12, wordBreak: "break-all" }}>

                    {curriculumDurationStats.maxRow

                      ? `${String(curriculumDurationStats.maxRow.phase_name || "")} (${formatDuration(curriculumDurationStats.maxSec)})`

                      : "-"}

                  </div>

                  <div className="muted" style={{ fontSize: 10, marginTop: 2 }}>

                    Peak duration in curriculum run

                  </div>

                </div>



                <div className="kpi" style={{ borderLeft: "3px solid #a78bfa" }}>

                  <div className="k">🏁 TRACKED PHASES</div>

                  <div className="v" style={{ color: "#c084fc", fontWeight: 700, fontSize: 16 }}>

                    {filteredTraceRows.length} phases

                  </div>

                  <div className="muted" style={{ fontSize: 10, marginTop: 2 }}>

                    {curriculumDurationStats.count} timed cycles

                  </div>

                </div>

              </div>



              <table>

                <thead>

                  <tr>

                    <th>curriculum</th>

                    <th>phase</th>

                    <th title="Total duration and split between training and evaluation">⏱️ Duration (Train / Bench)</th>

                    <th title="Bradley-Terry Anchor ELO">🎯 Calibrated ELO</th>

                    <th title="Win rate in resolved non-timeout matches">⚔️ Win Rate</th>

                    <th title="Average net victory points and enemy attrition">📊 VP / Losses</th>

                    <th>scenario_mix</th>

                    <th>train_run_id</th>

                    <th>recorded_at</th>

                    <th>gate_status</th>

                    <th>hard_gate</th>

                    <th>diagnostic</th>

                    <th>promotion_decision</th>

                  </tr>

                </thead>

                <tbody>

                  {!filteredTraceRows.length ? (

                    <tr>

                      <td colSpan={13} className="muted">No traceability records for this curriculum.</td>

                    </tr>

                  ) : (

                    filteredTraceRows.slice(0, 50).map((r, idx) => {

                      const sm = extractStepTraceMetrics(r);

                      const scenarioIds = Array.isArray(r.scenario_mix_ids) ? (r.scenario_mix_ids as string[]) : [];

                      const cleanedScenarios = scenarioIds

                        .map((s) => String(s).replace(/^multi:/, "").split("|"))

                        .flat()

                        .filter(Boolean);

                      const scenarioDisplay = cleanedScenarios.length

                        ? cleanedScenarios

                            .map((s) => s.replace("battaglia_cittadina_2_1", "battaglia").replace("mettete_i_piedi_terra_1", "mettete"))

                            .join(" + ")

                        : "-";



                      const dur = calculateDurationSeconds(

                        r.phase_started_at as string | undefined,

                        r.phase_finished_at as string | undefined

                      );



                      return (

                        <tr key={idx}>

                          <td>

                            <code style={{ color: "#38bdf8", fontSize: 11 }}>

                              {String(r.curriculum_name || r.curriculum || "-")}

                            </code>

                          </td>

                          <td><b>{String(r.phase_name || "-")}</b></td>

                          <td>

                            {(() => {

                              const trainSec = typeof r.train_duration_seconds === "number" ? r.train_duration_seconds : null;

                              const benchSec = typeof r.bench_duration_seconds === "number" ? r.bench_duration_seconds : null;



                              if (dur === null || dur === undefined || dur < 0) {

                                return <span className="muted">-</span>;

                              }



                              const hasSplit = trainSec !== null && benchSec !== null && (trainSec > 0 || benchSec > 0);
                              const sumTiming = (trainSec || 0) + (benchSec || 0);
                              const totalWall = (dur && dur > sumTiming) ? dur : sumTiming;
                              const overheadSec = Math.max(0, totalWall - sumTiming);

                              const trainPct = totalWall > 0 ? ((trainSec || 0) / totalWall) * 100 : 0;
                              const benchPct = totalWall > 0 ? ((benchSec || 0) / totalWall) * 100 : 0;
                              const overheadPct = totalWall > 0 ? Math.max(0, 100 - trainPct - benchPct) : 0;

                              return (
                                <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                                  <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                                    <span
                                      style={{
                                        background: "#0284c718",
                                        border: "1px solid #0284c740",
                                        color: "#38bdf8",
                                        padding: "1px 5px",
                                        borderRadius: 4,
                                        fontSize: 11,
                                        fontWeight: 700,
                                        whiteSpace: "nowrap",
                                      }}
                                      title={formatDurationDetailed(dur)}
                                    >
                                      ⏱️ {formatDuration(dur)}
                                    </span>
                                  </div>

                                  {hasSplit && (
                                    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                                      <div
                                        style={{
                                          display: "flex",
                                          width: "100%",
                                          maxWidth: 110,
                                          height: 3,
                                          borderRadius: 2,
                                          overflow: "hidden",
                                          background: "#1e293b",
                                        }}
                                        title={`Total Cycle: ${formatDuration(totalWall)} | Train: ${formatDuration(trainSec!)} (${Math.round(trainPct)}%) | Bench: ${formatDuration(benchSec!)} (${Math.round(benchPct)}%)${overheadSec > 2 ? ` | Overhead/IO: ${formatDuration(overheadSec)} (${Math.round(overheadPct)}%)` : ""}`}
                                      >
                                        <div style={{ width: `${trainPct}%`, background: "#38bdf8" }} />
                                        <div style={{ width: `${benchPct}%`, background: "#f59e0b" }} />
                                        {overheadPct > 0.5 && <div style={{ width: `${overheadPct}%`, background: "#64748b" }} />}
                                      </div>

                                      <div style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 9.5, color: "#94a3b8", whiteSpace: "nowrap" }}>
                                        <span><span style={{ color: "#38bdf8", fontWeight: 600 }}>T:</span> {formatDuration(trainSec!)}</span>
                                        <span>•</span>
                                        <span><span style={{ color: "#fbbf24", fontWeight: 600 }}>B:</span> {formatDuration(benchSec!)}</span>
                                        {overheadSec > 3 && <span style={{ color: "#64748b", fontSize: 9 }} title="Pipeline overhead / IO">(+{formatDuration(overheadSec)})</span>}
                                      </div>
                                    </div>
                                  )}
                                </div>
                              );

                            })()}

                          </td>

                          <td>

                            {sm.elo !== null ? (

                              <span

                                style={{

                                  fontWeight: 700,

                                  color: "#38bdf8",

                                  background: "#0284c725",

                                  border: "1px solid #0284c750",

                                  padding: "2px 6px",

                                  borderRadius: 4,

                                  fontSize: 11,

                                }}

                              >

                                {sm.elo}

                              </span>

                            ) : (

                              <span className="muted">-</span>

                            )}

                          </td>

                          <td>

                            {sm.winRate !== null ? (

                              <span

                                style={{

                                  fontWeight: 700,

                                  color: sm.winRate >= 0.85 ? "#34d399" : "#38bdf8",

                                  fontSize: 11,

                                }}

                              >

                                {(sm.winRate * 100).toFixed(1)}%

                              </span>

                            ) : (

                              <span className="muted">-</span>

                            )}

                          </td>

                          <td>

                            {sm.capturedAvg !== null || sm.vpNet !== null ? (

                              <span style={{ fontSize: 11, whiteSpace: "nowrap" }}>

                                {sm.capturedAvg !== null ? `${sm.capturedAvg.toFixed(1)} kills` : ""}

                                {sm.vpNet !== null ? ` (${sm.vpNet > 0 ? "+" : ""}${sm.vpNet.toFixed(2)} VP)` : ""}

                              </span>

                            ) : (

                              <span className="muted">-</span>

                            )}

                          </td>

                          <td style={{ fontSize: 11 }} title={cleanedScenarios.join(", ")}>

                            {scenarioDisplay}

                          </td>

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

                      );

                    })

                  )}

                </tbody>

              </table>



              <div

                style={{

                  marginTop: 8,

                  padding: "8px 12px",

                  background: "#0f172a",

                  borderRadius: 4,

                  border: "1px solid #334155",

                  display: "flex",

                  justifyContent: "space-between",

                  alignItems: "center",

                  fontSize: 12,

                  flexWrap: "wrap",

                  gap: 8,

                }}

              >

                <span className="muted">

                  Showing {Math.min(filteredTraceRows.length, 50)} of {filteredTraceRows.length} recorded phases

                </span>

                <span style={{ fontWeight: 600, color: "#e2e8f0", display: "inline-flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>

                  <span>

                    ⏱️ Total Curriculum Time:{" "}

                    <strong style={{ color: "#38bdf8", fontSize: 13 }}>

                      {curriculumDurationStats.totalSec > 0

                        ? formatDurationDetailed(curriculumDurationStats.totalSec)

                        : "N/A"}

                    </strong>

                  </span>

                  {curriculumDurationStats.totalTrainSec > 0 && curriculumDurationStats.totalBenchSec > 0 && (

                    <span style={{ fontSize: 11, color: "#94a3b8" }}>

                      (🏋️ <span style={{ color: "#38bdf8", fontWeight: 700 }}>Train:</span>{" "}

                      {formatDurationDetailed(curriculumDurationStats.totalTrainSec)} [

                      {Math.round((curriculumDurationStats.totalTrainSec / (curriculumDurationStats.totalTrainSec + curriculumDurationStats.totalBenchSec)) * 100)}%] • 🎯{" "}

                      <span style={{ color: "#fbbf24", fontWeight: 700 }}>Bench:</span>{" "}

                      {formatDurationDetailed(curriculumDurationStats.totalBenchSec)} [

                      {Math.round((curriculumDurationStats.totalBenchSec / (curriculumDurationStats.totalTrainSec + curriculumDurationStats.totalBenchSec)) * 100)}%])

                    </span>

                  )}

                </span>

              </div>

            </div>

          )}



          {/* TAB 3: CURRICULUM COMPARE */}

          {summaryTab === "compare" && (() => {

            const compareProfiles = Array.from(new Set(compareRows.map((r) => String(r.profile || "")).filter(Boolean))).sort();

            const compareEngines = Array.from(

              new Set([

                "efficientzero_v2",

                ...compareRows.map((r) => String(r.engine || "")).filter((e) => e && e !== "muzero"),

              ])

            );



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

                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 6 }}>

                  <h3 style={{ margin: 0, fontSize: 13 }}>Curriculum Compare (Latest)</h3>

                  {availableCurriculums.length > 0 && (

                    <div style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>

                      <span className="muted" style={{ fontSize: 11, fontWeight: 600 }}>Curriculum:</span>

                      <span

                        style={{

                          background: "#0284c7",

                          color: "#ffffff",

                          fontSize: 11,

                          fontWeight: 700,

                          padding: "2px 8px",

                          borderRadius: 4,

                          fontFamily: "monospace",

                          border: "1px solid #38bdf8",

                        }}

                      >

                        {latestActiveCurriculum || availableCurriculums[0]}

                      </span>

                    </div>

                  )}

                </div>

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

                    <span>🔍</span> Filters:

                  </span>



                  {/* Side Filter */}

                  <div style={{ display: "flex", alignItems: "center", gap: 5 }}>

                    <label style={{ fontSize: 11, color: "#94a3b8", fontWeight: 600 }}>Side:</label>

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

                      <option value="all">All sides</option>

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

                      <option value="all">All engines</option>

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

                      <option value="all">All types ({compareProfiles.length})</option>

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

                          No comparison records match the selected filters.

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

