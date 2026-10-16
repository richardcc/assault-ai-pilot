import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import type { Dict, ReplayMetaPayload, ReplayStepRow, ReplayUnitSnapshot } from "../../types";

function parseSuppressed(val: unknown): boolean | null {
  if (val === null || val === undefined || val === "") return null;
  if (typeof val === "boolean") return val;
  if (typeof val === "number") return val !== 0;
  const s = String(val).trim().toLowerCase();
  if (["1", "true", "yes", "on"].includes(s)) return true;
  if (["0", "false", "no", "off"].includes(s)) return false;
  return null;
}

export function MatchReplayTab({
  selectedEvalSourcePath,
  replayMeta,
  replaySteps,
  stepIndex,
  onStepIndexChange,
}: {
  selectedEvalSourcePath: string;
  replayMeta: ReplayMetaPayload | null;
  replaySteps: Dict | null;
  stepIndex: number;
  onStepIndexChange: (idx: number | ((prev: number) => number)) => void;
}) {
  const [isPlaying, setIsPlaying] = useState(false);
  const [playSpeed, setPlaySpeed] = useState<number>(1);
  const [hoveredUnitId, setHoveredUnitId] = useState("");
  const [selectedUnitId, setSelectedUnitId] = useState("");
  const [activeTab, setActiveTab] = useState<"decision" | "units" | "telemetry">("decision");
  const [mctsFilter, setMctsFilter] = useState<"all" | "visited" | "unvisited">("all");
  const [mctsSearch, setMctsSearch] = useState("");
  const [mctsSortBy, setMctsSortBy] = useState<"visits" | "q_value" | "prior" | "rank">("visits");

  // Map display layer toggles
  const [showVps, setShowVps] = useState(true);
  const [showHpBars, setShowHpBars] = useState(true);
  const [showCoords, setShowCoords] = useState(true);
  const [showVectors, setShowVectors] = useState(true);
  const [zoomLevel, setZoomLevel] = useState(1.0);

  // Canvas hover & tooltip state
  const [hoveredHex, setHoveredHex] = useState<{ q: number; r: number; x: number; y: number } | null>(null);

  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  const steps = useMemo(
    () => (Array.isArray(replaySteps?.steps) ? (replaySteps!.steps as ReplayStepRow[]) : []),
    [replaySteps]
  );
  const clamped = Math.max(0, Math.min(stepIndex, Math.max(0, steps.length - 1)));
  const currentStep = steps[clamped] || {};

  // Units list for current step
  const units = useMemo(() => {
    if (Array.isArray(currentStep.units) && currentStep.units.length > 0) {
      return currentStep.units as ReplayUnitSnapshot[];
    }
    if (Array.isArray(currentStep.unit_positions) && currentStep.unit_positions.length > 0) {
      const hpMap = (currentStep.unit_hp_map || {}) as Record<string, number>;
      const aliveMap = (currentStep.unit_alive_map || {}) as Record<string, boolean>;
      const suppMap = (currentStep.unit_suppressed_map || {}) as Record<string, unknown>;
      return (currentStep.unit_positions as Dict[]).map((p) => {
        const uid = String(p.unit_id || "");
        return {
          unit_id: uid,
          side: String(p.side || (uid.split("_")[0] || "")),
          q: Number(p.q),
          r: Number(p.r),
          hp: hpMap[uid] !== undefined ? Number(hpMap[uid]) : 4.0,
          alive: aliveMap[uid] !== undefined ? Boolean(aliveMap[uid]) : true,
          suppressed: Boolean(suppMap[uid]),
        } as ReplayUnitSnapshot;
      });
    }
    return [];
  }, [currentStep]);

  // Controller mapping by side
  const controllerMap = useMemo(() => {
    return (currentStep.controller_by_side || currentStep.side_controller_map || {}) as Record<string, string>;
  }, [currentStep]);

  // VP Map for current step
  const vpMap = useMemo(() => {
    const raw = (currentStep.vp_map || {}) as Record<string, string>;
    const list: Array<{ q: number; r: number; owner: string; key: string }> = [];
    for (const [k, v] of Object.entries(raw)) {
      const parts = k.split(",");
      if (parts.length === 2) {
        list.push({
          q: Number(parts[0]),
          r: Number(parts[1]),
          owner: String(v || "NEUTRAL").toUpperCase(),
          key: k,
        });
      }
    }
    return list;
  }, [currentStep.vp_map]);

  // VP tally counts
  const vpTally = useMemo(() => {
    const tally: Record<string, number> = { US: 0, IT: 0, GE: 0, NEUTRAL: 0 };
    for (const vp of vpMap) {
      tally[vp.owner] = (tally[vp.owner] || 0) + 1;
    }
    return tally;
  }, [vpMap]);

  // Parse Action vector and targets
  const actionVector = useMemo(() => {
    const actionId = String(currentStep.action_id || "");
    const parts = actionId.split(":");
    const kind = parts[0] || "";
    const actorId = parts[1] || String(currentStep.unit_id || "");

    const actorUnit = units.find((u) => u.unit_id === actorId);

    let fromQ: number | null = actorUnit ? actorUnit.q : null;
    let fromR: number | null = actorUnit ? actorUnit.r : null;
    let toQ: number | null = null;
    let toR: number | null = null;
    let targetUnitId: string | null = null;
    let isFire = kind.includes("FIRE") || kind.includes("ATTACK");
    let isMove = kind.includes("MOVE") || kind.includes("ASSAULT");

    if (isMove && parts.length >= 4) {
      toQ = Number(parts[2]);
      toR = Number(parts[3]);
    } else if (Number.isFinite(Number(currentStep.target_q)) && Number.isFinite(Number(currentStep.target_r))) {
      toQ = Number(currentStep.target_q);
      toR = Number(currentStep.target_r);
    } else if (isFire && parts.length >= 3) {
      targetUnitId = parts[2];
      const targetUnit = units.find((u) => u.unit_id === targetUnitId);
      if (targetUnit) {
        toQ = targetUnit.q;
        toR = targetUnit.r;
      }
    }

    return {
      actionId,
      kind,
      actorId,
      targetUnitId,
      fromQ,
      fromR,
      toQ,
      toR,
      isFire,
      isMove,
    };
  }, [currentStep, units]);

  const getStepDetails = useCallback((s: ReplayStepRow, idx: number) => {
    const actionParts = String(s.action_id || "").split(":");
    const inferredUnitId = String(s.unit_id || actionParts[1] || "-");
    const inferredSide = String(s.to_play || s.unit_side || (inferredUnitId !== "-" ? inferredUnitId.split("_")[0] : "-")).toUpperCase();
    const inferredTurn = s.game_turn ?? s.turn ?? (Math.floor(idx / 14) + 1);
    const oppSide = inferredSide === "IT" ? "US" : inferredSide === "US" ? "IT" : inferredSide === "GE" ? "US" : "-";
    const flag = inferredSide === "US" ? "🇺🇸" : inferredSide === "IT" ? "🇮🇹" : inferredSide === "GE" ? "🇩🇪" : "";
    const oppFlag = oppSide === "US" ? "🇺🇸" : oppSide === "IT" ? "🇮🇹" : oppSide === "GE" ? "🇩🇪" : "";
    return {
      stepIndex: idx,
      gameTurn: inferredTurn,
      toPlay: inferredSide,
      flag,
      opponentSide: oppSide,
      oppFlag,
      unitId: inferredUnitId,
      actionId: String(s.action_id || "-"),
      actionKind: String(s.action_kind || actionParts[0] || "-"),
      reward: Number(s.reward || 0),
      damage: Number(s.damage_dealt || 0),
      kills: Number(s.kills_dealt || 0),
    };
  }, []);

  const currentDetails = useMemo(() => getStepDetails(currentStep, clamped), [currentStep, clamped, getStepDetails]);

  // MCTS Action Candidates
  const rawCandidates = useMemo(() => {
    return Array.isArray(currentStep.mcts_action_candidates)
      ? (currentStep.mcts_action_candidates as Dict[])
      : [];
  }, [currentStep.mcts_action_candidates]);

  const totalCandidatesCount = rawCandidates.length;
  const visitedCandidatesCount = useMemo(
    () => rawCandidates.filter((c) => Number(c.visit_count || 0) > 0).length,
    [rawCandidates]
  );
  const unvisitedCandidatesCount = totalCandidatesCount - visitedCandidatesCount;
  const totalMctsVisits = Number(currentStep.mcts_total_visits || 0);

  const filteredCandidates = useMemo(() => {
    let list = [...rawCandidates];
    if (mctsFilter === "visited") {
      list = list.filter((c) => Number(c.visit_count || 0) > 0);
    } else if (mctsFilter === "unvisited") {
      list = list.filter((c) => Number(c.visit_count || 0) === 0);
    }
    if (mctsSearch.trim()) {
      const q = mctsSearch.trim().toLowerCase();
      list = list.filter((c) => String(c.action_id || "").toLowerCase().includes(q));
    }
    list.sort((a, b) => {
      if (mctsSortBy === "visits") {
        return Number(b.visit_count || 0) - Number(a.visit_count || 0);
      }
      if (mctsSortBy === "q_value") {
        return Number(b.mcts_q_value ?? -999) - Number(a.mcts_q_value ?? -999);
      }
      if (mctsSortBy === "prior") {
        return Number(b.policy_prior ?? 0) - Number(a.policy_prior ?? 0);
      }
      if (mctsSortBy === "rank") {
        return Number(a.decision_rank ?? 999) - Number(b.decision_rank ?? 999);
      }
      return 0;
    });
    return list;
  }, [rawCandidates, mctsFilter, mctsSearch, mctsSortBy]);

  // Auto-play timer
  useEffect(() => {
    if (!isPlaying) return;
    const baseInterval = 500 / playSpeed;
    const interval = setInterval(() => {
      onStepIndexChange((prev: number) => {
        if (prev >= steps.length - 1) {
          setIsPlaying(false);
          return prev;
        }
        return prev + 1;
      });
    }, baseInterval);
    return () => clearInterval(interval);
  }, [isPlaying, playSpeed, steps.length, onStepIndexChange]);

  const unitPoints = useMemo(
    () =>
      units
        .map((u) => ({
          q: Number(u.q),
          r: Number(u.r),
          unit_id: String(u.unit_id || ""),
          side: String(u.side || "").toUpperCase(),
          alive: Boolean(u.alive),
          hp: Number(u.hp || 0),
          suppressed: Boolean(u.suppressed),
        }))
        .filter((u) => Number.isFinite(u.q) && Number.isFinite(u.r)),
    [units]
  );

  // Units grouped by faction
  const usUnits = useMemo(() => units.filter((u) => u.side?.toUpperCase() === "US"), [units]);
  const itUnits = useMemo(() => units.filter((u) => u.side?.toUpperCase() === "IT" || u.side?.toUpperCase() === "GE"), [units]);

  // High-DPI Hex Grid Canvas Renderer
  useEffect(() => {
    const c = canvasRef.current;
    if (!c) return;
    const ctx = c.getContext("2d");
    if (!ctx) return;

    // High-DPI scaling
    const dpr = window.devicePixelRatio || 1;
    const rect = c.getBoundingClientRect();
    const cssWidth = rect.width || 800;
    const cssHeight = rect.height || 420;

    if (c.width !== Math.floor(cssWidth * dpr) || c.height !== Math.floor(cssHeight * dpr)) {
      c.width = Math.floor(cssWidth * dpr);
      c.height = Math.floor(cssHeight * dpr);
    }

    ctx.save();
    ctx.scale(dpr, dpr);

    // Dark tactical background
    ctx.clearRect(0, 0, cssWidth, cssHeight);
    const grad = ctx.createLinearGradient(0, 0, cssWidth, cssHeight);
    grad.addColorStop(0, "#090d16");
    grad.addColorStop(1, "#0f172a");
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, cssWidth, cssHeight);

    // Compute coordinate bounding box
    const qs = unitPoints.map((p) => p.q);
    const rs = unitPoints.map((p) => p.r);
    for (const vp of vpMap) {
      qs.push(vp.q);
      rs.push(vp.r);
    }
    if (actionVector.toQ !== null && actionVector.toR !== null) {
      qs.push(actionVector.toQ);
      rs.push(actionVector.toR);
    }

    const minQ = Math.max(0, (qs.length ? Math.min(...qs) : 0) - 2);
    const maxQ = Math.min(18, (qs.length ? Math.max(...qs) : 16) + 2);
    const minR = Math.max(0, (rs.length ? Math.min(...rs) : 0) - 2);
    const maxR = Math.min(12, (rs.length ? Math.max(...rs) : 10) + 2);

    // Odd-r Pointy-Topped Hexagon Geometry
    const oddRRaw = (q: number, r: number) => ({
      x: Math.sqrt(3) * (q + 0.5 * (r % 2)) + Math.sqrt(3) / 2,
      y: 1.5 * r + 1.0,
    });

    const raws: Array<{ x: number; y: number; q: number; r: number }> = [];
    for (let r = minR; r <= maxR; r += 1) {
      for (let q = minQ; q <= maxQ; q += 1) {
        raws.push({ ...oddRRaw(q, r), q, r });
      }
    }

    const minX = Math.min(...raws.map((p) => p.x));
    const maxX = Math.max(...raws.map((p) => p.x));
    const minY = Math.min(...raws.map((p) => p.y));
    const maxY = Math.max(...raws.map((p) => p.y));

    const spanX = Math.max(1e-6, maxX - minX + Math.sqrt(3));
    const spanY = Math.max(1e-6, maxY - minY + 2.0);
    const pad = 16;
    const baseScaleX = (cssWidth - pad * 2) / spanX;
    const baseScaleY = (cssHeight - pad * 2) / spanY;
    const scale = Math.max(8, Math.min(baseScaleX, baseScaleY) * zoomLevel);

    const boardPixelW = spanX * scale;
    const boardPixelH = spanY * scale;
    const offsetX = (cssWidth - boardPixelW) / 2 + (Math.sqrt(3) / 2) * scale;
    const offsetY = (cssHeight - boardPixelH) / 2 + 1.0 * scale;

    const toPixel = (q: number, r: number) => {
      const p = oddRRaw(q, r);
      return {
        x: offsetX + (p.x - minX) * scale,
        y: offsetY + (p.y - minY) * scale,
      };
    };

    const drawHex = (x: number, y: number, size: number, stroke: string, fill: string, lineWidth = 1) => {
      ctx.beginPath();
      for (let i = 0; i < 6; i += 1) {
        const a = (Math.PI / 180) * (60 * i - 30);
        const xx = x + size * Math.cos(a);
        const yy = y + size * Math.sin(a);
        if (i === 0) ctx.moveTo(xx, yy);
        else ctx.lineTo(xx, yy);
      }
      ctx.closePath();
      ctx.fillStyle = fill;
      ctx.fill();
      ctx.strokeStyle = stroke;
      ctx.lineWidth = lineWidth;
      ctx.stroke();
    };

    // 1. Draw Board Hex Grid Cells
    for (const cell of raws) {
      const p = toPixel(cell.q, cell.r);
      const isHovered = hoveredHex && hoveredHex.q === cell.q && hoveredHex.r === cell.r;

      drawHex(
        p.x,
        p.y,
        scale * 0.95,
        isHovered ? "#38bdf8" : "#243247",
        isHovered ? "rgba(56, 189, 248, 0.18)" : "rgba(15, 23, 42, 0.70)",
        isHovered ? 2 : 1
      );

      // Coordinates text
      if (showCoords) {
        ctx.fillStyle = isHovered ? "#38bdf8" : "#64748b";
        ctx.font = `${Math.max(8, Math.floor(scale * 0.32))}px monospace`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(`${cell.q},${cell.r}`, p.x, p.y - scale * 0.42);
      }
    }

    // 2. Draw Victory Points (VPs)
    if (showVps) {
      for (const vp of vpMap) {
        const p = toPixel(vp.q, vp.r);
        const ownerColor =
          vp.owner === "US"
            ? "#3b82f6"
            : vp.owner === "IT"
            ? "#10b981"
            : vp.owner === "GE"
            ? "#a855f7"
            : "#f59e0b";

        // VP Hex Outer Glowing Ring
        drawHex(p.x, p.y, scale * 0.98, ownerColor, "rgba(0, 0, 0, 0.25)", 2.5);

        // VP Star / Diamond marker
        ctx.beginPath();
        ctx.arc(p.x, p.y, scale * 0.38, 0, Math.PI * 2);
        ctx.fillStyle = `${ownerColor}33`;
        ctx.fill();
        ctx.strokeStyle = ownerColor;
        ctx.lineWidth = 1.5;
        ctx.stroke();

        // VP Text Label
        ctx.fillStyle = "#ffffff";
        ctx.font = `bold ${Math.max(8, Math.floor(scale * 0.32))}px sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(`★ ${vp.owner}`, p.x, p.y + (scale * 0.38));
      }
    }

    // 3. Draw Target Hex Marker
    if (actionVector.toQ !== null && actionVector.toR !== null) {
      const tp = toPixel(actionVector.toQ, actionVector.toR);
      const isFire = actionVector.isFire;
      const targetStroke = isFire ? "#ef4444" : "#facc15";

      // Tactical Reticle
      drawHex(tp.x, tp.y, scale * 1.05, targetStroke, isFire ? "rgba(239, 68, 68, 0.20)" : "rgba(250, 204, 21, 0.20)", 2.5);

      // Crosshairs
      ctx.beginPath();
      ctx.strokeStyle = targetStroke;
      ctx.lineWidth = 2;
      ctx.moveTo(tp.x - scale * 0.3, tp.y);
      ctx.lineTo(tp.x + scale * 0.3, tp.y);
      ctx.moveTo(tp.x, tp.y - scale * 0.3);
      ctx.lineTo(tp.x, tp.y + scale * 0.3);
      ctx.stroke();
    }

    // 4. Draw Action Trajectory Vector (Movement Arrow or Fire Line)
    if (showVectors && actionVector.fromQ !== null && actionVector.fromR !== null && actionVector.toQ !== null && actionVector.toR !== null) {
      const pFrom = toPixel(actionVector.fromQ, actionVector.fromR);
      const pTo = toPixel(actionVector.toQ, actionVector.toR);

      ctx.save();
      if (actionVector.isFire) {
        // Red laser/bullet line for combat
        ctx.beginPath();
        ctx.moveTo(pFrom.x, pFrom.y);
        ctx.lineTo(pTo.x, pTo.y);
        ctx.strokeStyle = "#ef4444";
        ctx.lineWidth = 3;
        ctx.shadowColor = "#f87171";
        ctx.shadowBlur = 8;
        ctx.stroke();

        // Combat Impact Explosion Icon
        ctx.fillStyle = "#facc15";
        ctx.font = `${Math.max(12, Math.floor(scale * 0.6))}px sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText("💥", pTo.x, pTo.y);
      } else {
        // Cyan dashed arrow for movement
        ctx.beginPath();
        ctx.setLineDash([6, 4]);
        ctx.moveTo(pFrom.x, pFrom.y);
        ctx.lineTo(pTo.x, pTo.y);
        ctx.strokeStyle = "#38bdf8";
        ctx.lineWidth = 2.5;
        ctx.shadowColor = "#38bdf8";
        ctx.shadowBlur = 6;
        ctx.stroke();
        ctx.setLineDash([]);

        // Arrow head
        const angle = Math.atan2(pTo.y - pFrom.y, pTo.x - pFrom.x);
        const headLen = Math.max(6, scale * 0.25);
        ctx.beginPath();
        ctx.moveTo(pTo.x, pTo.y);
        ctx.lineTo(pTo.x - headLen * Math.cos(angle - Math.PI / 6), pTo.y - headLen * Math.sin(angle - Math.PI / 6));
        ctx.lineTo(pTo.x - headLen * Math.cos(angle + Math.PI / 6), pTo.y - headLen * Math.sin(angle + Math.PI / 6));
        ctx.fillStyle = "#38bdf8";
        ctx.fill();
      }
      ctx.restore();
    }

    // 5. Draw Tactical Unit Counters
    for (const u of unitPoints) {
      const p = toPixel(u.q, u.r);
      const isHovered = hoveredUnitId === u.unit_id || (hoveredHex && hoveredHex.q === u.q && hoveredHex.r === u.r);
      const isSelected = selectedUnitId === u.unit_id;
      const isActing = String(currentStep.unit_id || actionVector.actorId) === u.unit_id;
      const isEliminated = !u.alive || u.hp <= 0;

      const unitRadius = Math.max(6, scale * (isActing || isHovered || isSelected ? 0.48 : 0.42));

      // Active Unit Beacon Aura
      if (isActing) {
        ctx.beginPath();
        ctx.arc(p.x, p.y, unitRadius * 1.5, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(250, 204, 21, 0.22)";
        ctx.fill();
        ctx.strokeStyle = "#facc15";
        ctx.lineWidth = 2;
        ctx.stroke();

        // Arrow indicator pointing down to active unit
        ctx.fillStyle = "#facc15";
        ctx.beginPath();
        ctx.moveTo(p.x, p.y - unitRadius * 1.6);
        ctx.lineTo(p.x - 5, p.y - unitRadius * 1.6 - 7);
        ctx.lineTo(p.x + 5, p.y - unitRadius * 1.6 - 7);
        ctx.closePath();
        ctx.fill();
      }

      // Unit Body Token
      ctx.beginPath();
      ctx.arc(p.x, p.y, unitRadius, 0, Math.PI * 2);

      const fillColor = isEliminated
        ? "#334155"
        : u.side === "IT"
        ? "#064e3b"
        : u.side === "GE"
        ? "#4c1d95"
        : "#1e3a8a";

      const strokeColor = isEliminated
        ? "#64748b"
        : isActing
        ? "#facc15"
        : isHovered || isSelected
        ? "#ffffff"
        : u.side === "IT"
        ? "#34d399"
        : u.side === "GE"
        ? "#c084fc"
        : "#60a5fa";

      ctx.fillStyle = fillColor;
      ctx.fill();
      ctx.strokeStyle = strokeColor;
      ctx.lineWidth = isActing ? 3 : isHovered ? 2.5 : 1.5;
      ctx.stroke();

      // Unit Role Icon / Text
      ctx.fillStyle = isEliminated ? "#94a3b8" : "#ffffff";
      ctx.font = `bold ${Math.max(7, Math.floor(scale * 0.28))}px sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";

      const roleIcon = isEliminated
        ? "☠️"
        : u.unit_id.includes("MORTAR") || u.unit_id.includes("MG") || u.unit_id.includes("4") || u.unit_id.includes("5")
        ? "🎯"
        : "🪖";

      ctx.fillText(roleIcon, p.x, p.y - 2);

      // Unit ID Pill Underneath
      ctx.fillStyle = "#0f172a";
      const nameW = Math.max(26, scale * 0.7);
      const nameH = Math.max(10, scale * 0.26);
      ctx.fillRect(p.x - nameW / 2, p.y + unitRadius * 0.65, nameW, nameH);
      ctx.strokeStyle = strokeColor;
      ctx.lineWidth = 1;
      ctx.strokeRect(p.x - nameW / 2, p.y + unitRadius * 0.65, nameW, nameH);

      ctx.fillStyle = isActing ? "#facc15" : "#f8fafc";
      ctx.font = `bold ${Math.max(7, Math.floor(scale * 0.22))}px sans-serif`;
      ctx.fillText(u.unit_id, p.x, p.y + unitRadius * 0.65 + nameH / 2);

      // HP Gauge Bar
      if (showHpBars && !isEliminated) {
        const maxHp = 4.0;
        const hpFrac = Math.max(0, Math.min(1, u.hp / maxHp));
        const barW = Math.max(22, scale * 0.6);
        const barH = 3.5;
        const barX = p.x - barW / 2;
        const barY = p.y - unitRadius - 5;

        // Background
        ctx.fillStyle = "rgba(15, 23, 42, 0.85)";
        ctx.fillRect(barX, barY, barW, barH);

        // Health fill
        ctx.fillStyle = hpFrac > 0.6 ? "#22c55e" : hpFrac > 0.3 ? "#f59e0b" : "#ef4444";
        ctx.fillRect(barX, barY, barW * hpFrac, barH);

        ctx.strokeStyle = "#334155";
        ctx.lineWidth = 0.5;
        ctx.strokeRect(barX, barY, barW, barH);
      }

      // Suppressed Badge
      if (u.suppressed && !isEliminated) {
        ctx.fillStyle = "#ea580c";
        ctx.font = `bold ${Math.max(7, Math.floor(scale * 0.20))}px sans-serif`;
        ctx.fillText("PIN", p.x + unitRadius * 0.7, p.y - unitRadius * 0.7);
      }
    }

    ctx.restore();
  }, [
    unitPoints,
    vpMap,
    actionVector,
    currentStep,
    hoveredUnitId,
    selectedUnitId,
    hoveredHex,
    showVps,
    showHpBars,
    showCoords,
    showVectors,
    zoomLevel,
  ]);

  // Canvas Mouse Move Event
  const handleCanvasMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const c = canvasRef.current;
    if (!c) return;
    const rect = c.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    // Inverse odd-r hex picking
    const qs = unitPoints.map((p) => p.q);
    const rs = unitPoints.map((p) => p.r);
    for (const vp of vpMap) {
      qs.push(vp.q);
      rs.push(vp.r);
    }
    const minQ = Math.max(0, (qs.length ? Math.min(...qs) : 0) - 2);
    const maxQ = Math.min(18, (qs.length ? Math.max(...qs) : 16) + 2);
    const minR = Math.max(0, (rs.length ? Math.min(...rs) : 0) - 2);
    const maxR = Math.min(12, (rs.length ? Math.max(...rs) : 10) + 2);

    const oddRRaw = (q: number, r: number) => ({
      x: Math.sqrt(3) * (q + 0.5 * (r % 2)) + Math.sqrt(3) / 2,
      y: 1.5 * r + 1.0,
    });

    const raws: Array<{ x: number; y: number; q: number; r: number }> = [];
    for (let r = minR; r <= maxR; r += 1) {
      for (let q = minQ; q <= maxQ; q += 1) {
        raws.push({ ...oddRRaw(q, r), q, r });
      }
    }

    const minX = Math.min(...raws.map((p) => p.x));
    const maxX = Math.max(...raws.map((p) => p.x));
    const minY = Math.min(...raws.map((p) => p.y));
    const maxY = Math.max(...raws.map((p) => p.y));

    const spanX = Math.max(1e-6, maxX - minX + Math.sqrt(3));
    const spanY = Math.max(1e-6, maxY - minY + 2.0);
    const pad = 16;
    const baseScaleX = (rect.width - pad * 2) / spanX;
    const baseScaleY = (rect.height - pad * 2) / spanY;
    const scale = Math.max(8, Math.min(baseScaleX, baseScaleY) * zoomLevel);

    const boardPixelW = spanX * scale;
    const boardPixelH = spanY * scale;
    const offsetX = (rect.width - boardPixelW) / 2 + (Math.sqrt(3) / 2) * scale;
    const offsetY = (rect.height - boardPixelH) / 2 + 1.0 * scale;

    let closestCell: { q: number; r: number; dist: number } | null = null;
    for (const cell of raws) {
      const px = offsetX + (cell.x - minX) * scale;
      const py = offsetY + (cell.y - minY) * scale;
      const dist = Math.hypot(px - x, py - y);
      if (!closestCell || dist < closestCell.dist) {
        closestCell = { q: cell.q, r: cell.r, dist };
      }
    }

    if (closestCell && closestCell.dist < scale * 0.95) {
      setHoveredHex({ q: closestCell.q, r: closestCell.r, x, y });
    } else {
      setHoveredHex(null);
    }
  };

  const handleCanvasMouseLeave = () => {
    setHoveredHex(null);
    setHoveredUnitId("");
  };

  const handleCanvasClick = () => {
    if (hoveredHex) {
      const unitOnHex = units.find((u) => u.q === hoveredHex.q && u.r === hoveredHex.r);
      if (unitOnHex) {
        setSelectedUnitId(unitOnHex.unit_id);
        setActiveTab("units");
      }
    }
  };

  if (!selectedEvalSourcePath) {
    return <div className="muted" style={{ padding: 20 }}>Selecciona una evaluación para ver el Match Replay.</div>;
  }

  const suppressedMap = (currentStep.unit_suppressed_map || {}) as Record<string, unknown>;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {/* 1. Header & Interactive VCR Playback Console */}
      <div
        style={{
          background: "linear-gradient(180deg, #1e293b, #0f172a)",
          border: "1px solid #334155",
          borderRadius: 8,
          padding: "10px 14px",
          display: "flex",
          flexDirection: "column",
          gap: 8,
          boxShadow: "0 4px 12px rgba(0,0,0,0.3)",
        }}
      >
        {/* Scrubber Range Slider */}
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 11, fontWeight: 700, color: "#38bdf8", minWidth: 60 }}>
            Paso {clamped} / {Math.max(0, steps.length - 1)}
          </span>
          <input
            type="range"
            min={0}
            max={Math.max(0, steps.length - 1)}
            value={clamped}
            onChange={(e) => onStepIndexChange(Number(e.target.value || 0))}
            style={{ flex: 1, accentColor: "#38bdf8", cursor: "pointer" }}
          />
          <span style={{ fontSize: 11, fontWeight: 700, color: "#a855f7", minWidth: 60, textAlign: "right" }}>
            Turno {currentDetails.gameTurn}
          </span>
        </div>

        {/* Controls Bar */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
          {/* VCR Playback Buttons */}
          <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <button
              onClick={() => onStepIndexChange(0)}
              title="Primer paso (t=0)"
              style={{ padding: "4px 8px", fontSize: 12, background: "#1e293b", border: "1px solid #475569", borderRadius: 4, cursor: "pointer" }}
            >
              ⏮ Inicio
            </button>
            <button
              onClick={() => onStepIndexChange((prev) => Math.max(0, prev - 1))}
              title="Paso anterior"
              style={{ padding: "4px 8px", fontSize: 12, background: "#1e293b", border: "1px solid #475569", borderRadius: 4, cursor: "pointer" }}
            >
              ◀ Ant
            </button>
            <button
              onClick={() => setIsPlaying(!isPlaying)}
              style={{
                padding: "4px 14px",
                fontSize: 12,
                fontWeight: 700,
                background: isPlaying ? "#0ea5e9" : "#0284c7",
                color: "#ffffff",
                border: "none",
                borderRadius: 4,
                cursor: "pointer",
                minWidth: 84,
              }}
            >
              {isPlaying ? "⏸ Pausa" : "▶ Play"}
            </button>
            <button
              onClick={() => onStepIndexChange((prev) => Math.min(steps.length - 1, prev + 1))}
              title="Paso siguiente"
              style={{ padding: "4px 8px", fontSize: 12, background: "#1e293b", border: "1px solid #475569", borderRadius: 4, cursor: "pointer" }}
            >
              Sig ▶
            </button>
            <button
              onClick={() => onStepIndexChange(Math.max(0, steps.length - 1))}
              title="Último paso"
              style={{ padding: "4px 8px", fontSize: 12, background: "#1e293b", border: "1px solid #475569", borderRadius: 4, cursor: "pointer" }}
            >
              Fin ⏭
            </button>

            {/* Playback Speed selector */}
            <div style={{ display: "flex", gap: 2, marginLeft: 6, background: "#0f172a", padding: 2, borderRadius: 4 }}>
              {[0.5, 1, 2, 4].map((spd) => (
                <button
                  key={spd}
                  onClick={() => setPlaySpeed(spd)}
                  style={{
                    padding: "2px 6px",
                    fontSize: 10,
                    fontWeight: playSpeed === spd ? 700 : 500,
                    background: playSpeed === spd ? "#38bdf8" : "transparent",
                    color: playSpeed === spd ? "#0f172a" : "#94a3b8",
                    border: "none",
                    borderRadius: 3,
                    cursor: "pointer",
                  }}
                >
                  {spd}x
                </button>
              ))}
            </div>
          </div>

          {/* Turn Jump Dropdown */}
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontSize: 11, color: "#94a3b8" }}>Ir a:</span>
            <select
              value={clamped}
              onChange={(e) => onStepIndexChange(Number(e.target.value || 0))}
              style={{
                padding: "3px 8px",
                background: "#0f172a",
                border: "1px solid #334155",
                borderRadius: 4,
                color: "#f8fafc",
                fontSize: 11,
                maxWidth: 240,
              }}
            >
              {steps.map((st, i) => {
                const d = getStepDetails(st, i);
                return (
                  <option key={i} value={i}>
                    P{i} (T{d.gameTurn}) | {d.flag} {d.toPlay} ➔ {d.actionId}
                  </option>
                );
              })}
            </select>
          </div>

          {/* VP Tally Badges */}
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 5,
                background: "rgba(37, 99, 235, 0.15)",
                border: "1px solid #2563eb",
                padding: "2px 8px",
                borderRadius: 4,
                fontSize: 11,
              }}
            >
              <span>🇺🇸 US:</span>
              <b style={{ color: "#60a5fa" }}>{vpTally.US || 0} VPs</b>
            </div>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 5,
                background: "rgba(5, 150, 105, 0.15)",
                border: "1px solid #059669",
                padding: "2px 8px",
                borderRadius: 4,
                fontSize: 11,
              }}
            >
              <span>🇮🇹 IT:</span>
              <b style={{ color: "#34d399" }}>{vpTally.IT || 0} VPs</b>
            </div>
          </div>
        </div>
      </div>

      {/* 2. Main Split Tactical Arena (Left Map, Right Inspector) */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(480px, 680px) minmax(420px, 1fr)",
          gap: 14,
          alignItems: "start",
        }}
      >
        {/* LEFT COLUMN: Tactical Map & Event Feed */}
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {/* Map Controls Toolbar */}
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              background: "#1e293b",
              border: "1px solid #334155",
              borderRadius: 6,
              padding: "4px 10px",
              flexWrap: "wrap",
              gap: 6,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ fontSize: 11, fontWeight: 700, color: "#38bdf8" }}>Capas del Mapa:</span>
              <button
                onClick={() => setShowVps(!showVps)}
                style={{
                  fontSize: 10,
                  padding: "2px 6px",
                  borderRadius: 3,
                  background: showVps ? "#065f46" : "#0f172a",
                  color: showVps ? "#34d399" : "#64748b",
                  border: "1px solid #334155",
                  cursor: "pointer",
                }}
              >
                ★ VPs ({vpMap.length})
              </button>
              <button
                onClick={() => setShowHpBars(!showHpBars)}
                style={{
                  fontSize: 10,
                  padding: "2px 6px",
                  borderRadius: 3,
                  background: showHpBars ? "#1e3a8a" : "#0f172a",
                  color: showHpBars ? "#60a5fa" : "#64748b",
                  border: "1px solid #334155",
                  cursor: "pointer",
                }}
              >
                ❤️ Barras HP
              </button>
              <button
                onClick={() => setShowCoords(!showCoords)}
                style={{
                  fontSize: 10,
                  padding: "2px 6px",
                  borderRadius: 3,
                  background: showCoords ? "#3730a3" : "#0f172a",
                  color: showCoords ? "#a5b4fc" : "#64748b",
                  border: "1px solid #334155",
                  cursor: "pointer",
                }}
              >
                🌐 Coordenadas
              </button>
              <button
                onClick={() => setShowVectors(!showVectors)}
                style={{
                  fontSize: 10,
                  padding: "2px 6px",
                  borderRadius: 3,
                  background: showVectors ? "#7c2d12" : "#0f172a",
                  color: showVectors ? "#fb923c" : "#64748b",
                  border: "1px solid #334155",
                  cursor: "pointer",
                }}
              >
                🎯 Vectores Acción
              </button>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <button
                onClick={() => setZoomLevel((z) => Math.max(0.7, z - 0.1))}
                title="Alejar mapa"
                style={{ padding: "2px 6px", fontSize: 11, background: "#0f172a", border: "1px solid #334155", color: "#f8fafc", borderRadius: 3, cursor: "pointer" }}
              >
                -
              </button>
              <span style={{ fontSize: 10, color: "#94a3b8", minWidth: 32, textAlign: "center" }}>
                {(zoomLevel * 100).toFixed(0)}%
              </span>
              <button
                onClick={() => setZoomLevel((z) => Math.min(1.8, z + 0.1))}
                title="Acercar mapa"
                style={{ padding: "2px 6px", fontSize: 11, background: "#0f172a", border: "1px solid #334155", color: "#f8fafc", borderRadius: 3, cursor: "pointer" }}
              >
                +
              </button>
              <button
                onClick={() => setZoomLevel(1.0)}
                title="Restablecer zoom"
                style={{ padding: "2px 6px", fontSize: 10, background: "#0f172a", border: "1px solid #334155", color: "#94a3b8", borderRadius: 3, cursor: "pointer" }}
              >
                100%
              </button>
            </div>
          </div>

          {/* Tactical Map Canvas with Relative Hover HUD */}
          <div style={{ position: "relative" }}>
            <canvas
              ref={canvasRef}
              onMouseMove={handleCanvasMouseMove}
              onMouseLeave={handleCanvasMouseLeave}
              onClick={handleCanvasClick}
              style={{
                width: "100%",
                height: 480,
                border: "1px solid #334155",
                borderRadius: 8,
                display: "block",
                cursor: hoveredHex ? "pointer" : "default",
                boxShadow: "inset 0 0 20px rgba(0,0,0,0.6)",
              }}
            />

            {/* Hover Tooltip Overlay */}
            {hoveredHex && (
              <div
                style={{
                  position: "absolute",
                  left: hoveredHex.x > 460 ? hoveredHex.x - 175 : hoveredHex.x + 14,
                  top: Math.max(10, hoveredHex.y - 40),
                  background: "rgba(15, 23, 42, 0.95)",
                  border: "1px solid #38bdf8",
                  borderRadius: 6,
                  padding: "6px 10px",
                  fontSize: 11,
                  color: "#f8fafc",
                  pointerEvents: "none",
                  boxShadow: "0 4px 14px rgba(0,0,0,0.5)",
                  zIndex: 20,
                  minWidth: 150,
                }}
              >
                <div style={{ fontWeight: 700, color: "#38bdf8", marginBottom: 2 }}>
                  Casilla Hex ({hoveredHex.q}, {hoveredHex.r})
                </div>
                {vpMap.find((v) => v.q === hoveredHex.q && v.r === hoveredHex.r) && (
                  <div style={{ color: "#facc15", fontSize: 10, fontWeight: 600 }}>
                    ★ Punto de Victoria ({vpMap.find((v) => v.q === hoveredHex.q && v.r === hoveredHex.r)?.owner})
                  </div>
                )}
                {units.filter((u) => u.q === hoveredHex.q && u.r === hoveredHex.r).map((u) => (
                  <div key={u.unit_id} style={{ marginTop: 2, display: "flex", justifyContent: "space-between", gap: 8 }}>
                    <span style={{ color: u.side === "US" ? "#60a5fa" : "#34d399", fontWeight: 700 }}>
                      {u.unit_id} ({u.side})
                    </span>
                    <span style={{ color: u.alive ? "#22c55e" : "#ef4444" }}>
                      {u.alive ? `${u.hp.toFixed(1)} HP` : "Eliminada"}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Tactical Action Event Banner */}
          <div
            style={{
              background: actionVector.isFire
                ? "linear-gradient(90deg, rgba(159, 18, 57, 0.3), rgba(15, 23, 42, 0.9))"
                : actionVector.isMove
                ? "linear-gradient(90deg, rgba(2, 132, 199, 0.25), rgba(15, 23, 42, 0.9))"
                : "linear-gradient(90deg, rgba(30, 41, 59, 0.4), rgba(15, 23, 42, 0.9))",
              border: `1px solid ${actionVector.isFire ? "#f43f5e" : actionVector.isMove ? "#38bdf8" : "#475569"}`,
              borderRadius: 6,
              padding: "10px 14px",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              gap: 8,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ fontSize: 20 }}>
                {actionVector.isFire ? "💥" : actionVector.isMove ? "🏃" : "🛡️"}
              </span>
              <div>
                <div style={{ fontSize: 10, textTransform: "uppercase", color: "#94a3b8", fontWeight: 700 }}>
                  Acción Ejecutada en Paso {clamped}
                </div>
                <div style={{ fontSize: 13, fontWeight: 700, color: "#f8fafc" }}>
                  <span style={{ color: currentDetails.toPlay === "US" ? "#60a5fa" : "#34d399" }}>
                    {currentDetails.flag} {currentDetails.unitId}
                  </span>{" "}
                  ➔ <code style={{ color: "#facc15" }}>{currentDetails.actionId}</code>
                </div>
              </div>
            </div>

            <div style={{ display: "flex", gap: 10 }}>
              <div style={{ textAlign: "right" }}>
                <div className="muted" style={{ fontSize: 10 }}>Daño Causado</div>
                <div style={{ fontSize: 12, fontWeight: 700, color: currentDetails.damage > 0 ? "#ef4444" : "#cbd5e1" }}>
                  {currentDetails.damage.toFixed(2)} dmg
                </div>
              </div>
              <div style={{ textAlign: "right" }}>
                <div className="muted" style={{ fontSize: 10 }}>Bajas</div>
                <div style={{ fontSize: 12, fontWeight: 700, color: currentDetails.kills > 0 ? "#ef4444" : "#cbd5e1" }}>
                  {currentDetails.kills}
                </div>
              </div>
              <div style={{ textAlign: "right" }}>
                <div className="muted" style={{ fontSize: 10 }}>Recompensa</div>
                <div style={{ fontSize: 12, fontWeight: 700, color: currentDetails.reward >= 0 ? "#22c55e" : "#ef4444" }}>
                  {currentDetails.reward.toFixed(4)}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN: Tactical Inspector Tabs */}
        <div
          style={{
            background: "#1e293b",
            border: "1px solid #334155",
            borderRadius: 8,
            padding: 12,
            display: "flex",
            flexDirection: "column",
            gap: 12,
            minHeight: 520,
          }}
        >
          {/* Tab Selector Header */}
          <div style={{ display: "flex", gap: 4, background: "#0f172a", padding: 3, borderRadius: 6 }}>
            <button
              onClick={() => setActiveTab("decision")}
              style={{
                flex: 1,
                fontSize: 11,
                padding: "6px 8px",
                borderRadius: 4,
                background: activeTab === "decision" ? "#0284c7" : "transparent",
                color: activeTab === "decision" ? "#ffffff" : "#94a3b8",
                border: "none",
                fontWeight: activeTab === "decision" ? 700 : 500,
                cursor: "pointer",
              }}
            >
              🎯 MCTS & Decisión
            </button>
            <button
              onClick={() => setActiveTab("units")}
              style={{
                flex: 1,
                fontSize: 11,
                padding: "6px 8px",
                borderRadius: 4,
                background: activeTab === "units" ? "#0284c7" : "transparent",
                color: activeTab === "units" ? "#ffffff" : "#94a3b8",
                border: "none",
                fontWeight: activeTab === "units" ? 700 : 500,
                cursor: "pointer",
              }}
            >
              👥 Tropas ({units.length})
            </button>
            <button
              onClick={() => setActiveTab("telemetry")}
              style={{
                flex: 1,
                fontSize: 11,
                padding: "6px 8px",
                borderRadius: 4,
                background: activeTab === "telemetry" ? "#0284c7" : "transparent",
                color: activeTab === "telemetry" ? "#ffffff" : "#94a3b8",
                border: "none",
                fontWeight: activeTab === "telemetry" ? 700 : 500,
                cursor: "pointer",
              }}
            >
              📊 VPs & Telemetría
            </button>
          </div>

          {/* TAB 1: MCTS & DECISIÓN */}
          {activeTab === "decision" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {/* Selected Decision Card */}
              <div
                style={{
                  background: "#0f172a",
                  border: "1px solid #1e3a8a",
                  borderRadius: 6,
                  padding: 10,
                  display: "flex",
                  flexDirection: "column",
                  gap: 6,
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: 10, color: "#60a5fa", fontWeight: 700, textTransform: "uppercase" }}>
                    Decisión Monte Carlo Tree Search
                  </span>
                  {currentStep.policy_overridden_by_mcts ? (
                    <span style={{ fontSize: 10, background: "rgba(14, 165, 233, 0.2)", color: "#38bdf8", padding: "1px 5px", borderRadius: 3, fontWeight: 700 }}>
                      ⚡ MCTS corrigió la Policy
                    </span>
                  ) : (
                    <span style={{ fontSize: 10, background: "rgba(34, 197, 94, 0.15)", color: "#22c55e", padding: "1px 5px", borderRadius: 3 }}>
                      ✓ Policy mantenida
                    </span>
                  )}
                </div>

                <div style={{ fontSize: 12, fontWeight: 700, color: "#facc15" }}>
                  <code>{currentDetails.actionId}</code>
                </div>

                {Boolean(currentStep.why_action_vs_vp_text) && (
                  <div style={{ fontSize: 11, color: "#cbd5e1", fontStyle: "italic", background: "rgba(255,255,255,0.03)", padding: 6, borderRadius: 4 }}>
                    "{String(currentStep.why_action_vs_vp_text)}"
                  </div>
                )}

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, marginTop: 2 }}>
                  <div style={{ background: "#1e293b", padding: "4px 8px", borderRadius: 4 }}>
                    <div className="muted" style={{ fontSize: 9 }}>MCTS Visitas N</div>
                    <div style={{ fontSize: 12, fontWeight: 700, color: "#38bdf8" }}>
                      {currentStep.mcts_total_visits ?? "N/A"}
                    </div>
                  </div>
                  <div style={{ background: "#1e293b", padding: "4px 8px", borderRadius: 4 }}>
                    <div className="muted" style={{ fontSize: 9 }}>Valor Esperado Q(s,a)</div>
                    <div style={{ fontSize: 12, fontWeight: 700, color: Number(currentStep.mcts_q_value) >= 0 ? "#22c55e" : "#ef4444" }}>
                      {Number.isFinite(Number(currentStep.mcts_q_value)) ? Number(currentStep.mcts_q_value).toFixed(3) : "-"}
                    </div>
                  </div>
                </div>
              </div>

              {/* MCTS Candidates Tree Explorer */}
              {totalCandidatesCount > 0 ? (
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                    <span style={{ fontSize: 11, fontWeight: 700, color: "#38bdf8" }}>
                      Candidatas en la Raíz ({totalCandidatesCount})
                    </span>
                    <div style={{ display: "flex", gap: 4 }}>
                      <button
                        onClick={() => setMctsFilter("all")}
                        style={{ fontSize: 10, padding: "1px 5px", borderRadius: 3, background: mctsFilter === "all" ? "#0284c7" : "#0f172a", border: "none", color: "#fff", cursor: "pointer" }}
                      >
                        Todas
                      </button>
                      <button
                        onClick={() => setMctsFilter("visited")}
                        style={{ fontSize: 10, padding: "1px 5px", borderRadius: 3, background: mctsFilter === "visited" ? "#0284c7" : "#0f172a", border: "none", color: "#22c55e", cursor: "pointer" }}
                      >
                        N &gt; 0 ({visitedCandidatesCount})
                      </button>
                      <button
                        onClick={() => setMctsFilter("unvisited")}
                        style={{ fontSize: 10, padding: "1px 5px", borderRadius: 3, background: mctsFilter === "unvisited" ? "#ef4444" : "#0f172a", border: "none", color: "#ef4444", cursor: "pointer" }}
                      >
                        N = 0 ({unvisitedCandidatesCount})
                      </button>
                    </div>
                  </div>

                  <div style={{ display: "flex", gap: 6, marginBottom: 6 }}>
                    <input
                      type="text"
                      placeholder="Filtrar acción..."
                      value={mctsSearch}
                      onChange={(e) => setMctsSearch(e.target.value)}
                      style={{ flex: 1, fontSize: 11, padding: "3px 6px", background: "#0f172a", border: "1px solid #334155", borderRadius: 4, color: "#fff" }}
                    />
                    <select
                      value={mctsSortBy}
                      onChange={(e) => setMctsSortBy(e.target.value as "visits" | "q_value" | "prior" | "rank")}
                      style={{ fontSize: 10, padding: "2px 4px", background: "#0f172a", border: "1px solid #334155", color: "#fff" }}
                    >
                      <option value="visits">Por Visitas N</option>
                      <option value="q_value">Por Valor Q</option>
                      <option value="prior">Por Prior Policy</option>
                      <option value="rank">Por Rango</option>
                    </select>
                  </div>

                  <div style={{ maxHeight: 260, overflowY: "auto", border: "1px solid #334155", borderRadius: 6 }}>
                    <table style={{ margin: 0, fontSize: 11 }}>
                      <thead>
                        <tr>
                          <th>Acción</th>
                          <th style={{ width: 80 }}>Visitas N</th>
                          <th style={{ width: 50 }}>Q</th>
                          <th style={{ width: 50 }}>Prior</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filteredCandidates.map((c, idx) => {
                          const isSelected = Boolean(c.selected_action || String(c.action_id || "") === String(currentStep.action_id || ""));
                          const visits = Number(c.visit_count || 0);
                          const qVal = Number(c.mcts_q_value);
                          const prior = Number(c.policy_prior);
                          const visitPct = totalMctsVisits > 0 ? (visits * 100) / totalMctsVisits : 0;

                          return (
                            <tr key={idx} style={{ background: isSelected ? "rgba(250, 204, 21, 0.12)" : undefined }}>
                              <td>
                                <code style={{ color: isSelected ? "#facc15" : "#e2e8f0", fontWeight: isSelected ? 700 : 400 }}>
                                  {isSelected ? "★ " : ""}{String(c.action_id || "-")}
                                </code>
                              </td>
                              <td>
                                <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                                  <span style={{ fontWeight: isSelected ? 700 : 400, width: 20, textAlign: "right" }}>{visits}</span>
                                  <div style={{ flex: 1, background: "#0f172a", height: 4, borderRadius: 2, overflow: "hidden" }}>
                                    <div style={{ width: `${Math.min(100, visitPct)}%`, height: "100%", background: isSelected ? "#facc15" : "#38bdf8" }} />
                                  </div>
                                </div>
                              </td>
                              <td style={{ color: Number.isFinite(qVal) ? (qVal > 0 ? "#22c55e" : qVal < 0 ? "#f87171" : undefined) : undefined }}>
                                {Number.isFinite(qVal) ? qVal.toFixed(2) : "-"}
                              </td>
                              <td>{Number.isFinite(prior) ? prior.toFixed(2) : "-"}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : (
                <div className="muted" style={{ fontSize: 11, textAlign: "center", padding: 20 }}>
                  No se registraron ramas MCTS para este paso.
                </div>
              )}
            </div>
          )}

          {/* TAB 2: ROSTER DE UNIDADES */}
          {activeTab === "units" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div style={{ fontSize: 11, color: "#94a3b8" }}>
                Haz clic en una escuadra para enfocarla en el mapa táctico.
              </div>

              {/* US Troops */}
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, color: "#60a5fa", marginBottom: 4, display: "flex", alignItems: "center", gap: 4 }}>
                  <span>🇺🇸</span> Tropas de EE.UU. ({usUnits.length} escuadras)
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 4, maxHeight: 180, overflowY: "auto" }}>
                  {usUnits.map((u) => {
                    const isActing = String(currentStep.unit_id) === u.unit_id;
                    const isSelected = selectedUnitId === u.unit_id;
                    return (
                      <div
                        key={u.unit_id}
                        onClick={() => setSelectedUnitId(u.unit_id)}
                        onMouseEnter={() => setHoveredUnitId(u.unit_id)}
                        onMouseLeave={() => setHoveredUnitId("")}
                        style={{
                          background: isSelected ? "#1e3a8a" : isActing ? "rgba(250, 204, 21, 0.15)" : "#0f172a",
                          border: `1px solid ${isSelected ? "#38bdf8" : isActing ? "#facc15" : "#334155"}`,
                          borderRadius: 4,
                          padding: "4px 8px",
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          cursor: "pointer",
                          fontSize: 11,
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                          <span style={{ fontWeight: 700, color: "#f8fafc" }}>{u.unit_id}</span>
                          <span className="muted" style={{ fontSize: 10 }}>({u.q},{u.r})</span>
                          {isActing && <span style={{ fontSize: 9, color: "#facc15", fontWeight: 700 }}>ACTIVA</span>}
                        </div>
                        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                          <span style={{ color: u.alive ? (u.hp >= 3.0 ? "#22c55e" : "#f59e0b") : "#ef4444", fontWeight: 700 }}>
                            {u.alive ? `${u.hp.toFixed(1)} HP` : "BAJA"}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* IT/Opponent Troops */}
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, color: "#34d399", marginBottom: 4, display: "flex", alignItems: "center", gap: 4 }}>
                  <span>🇮🇹</span> Tropas del Eje ({itUnits.length} escuadras)
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 4, maxHeight: 180, overflowY: "auto" }}>
                  {itUnits.map((u) => {
                    const isActing = String(currentStep.unit_id) === u.unit_id;
                    const isSelected = selectedUnitId === u.unit_id;
                    return (
                      <div
                        key={u.unit_id}
                        onClick={() => setSelectedUnitId(u.unit_id)}
                        onMouseEnter={() => setHoveredUnitId(u.unit_id)}
                        onMouseLeave={() => setHoveredUnitId("")}
                        style={{
                          background: isSelected ? "#064e3b" : isActing ? "rgba(250, 204, 21, 0.15)" : "#0f172a",
                          border: `1px solid ${isSelected ? "#34d399" : isActing ? "#facc15" : "#334155"}`,
                          borderRadius: 4,
                          padding: "4px 8px",
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          cursor: "pointer",
                          fontSize: 11,
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                          <span style={{ fontWeight: 700, color: "#f8fafc" }}>{u.unit_id}</span>
                          <span className="muted" style={{ fontSize: 10 }}>({u.q},{u.r})</span>
                          {isActing && <span style={{ fontSize: 9, color: "#facc15", fontWeight: 700 }}>ACTIVA</span>}
                        </div>
                        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                          <span style={{ color: u.alive ? (u.hp >= 3.0 ? "#22c55e" : "#f59e0b") : "#ef4444", fontWeight: 700 }}>
                            {u.alive ? `${u.hp.toFixed(1)} HP` : "BAJA"}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}

          {/* TAB 3: VPs & TELEMETRÍA */}
          {activeTab === "telemetry" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: "#38bdf8" }}>
                Puntos de Victoria en Disputa ({vpMap.length} hexágonos)
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {vpMap.map((vp) => (
                  <div
                    key={vp.key}
                    style={{
                      background: "#0f172a",
                      border: "1px solid #334155",
                      borderRadius: 4,
                      padding: "6px 10px",
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      fontSize: 11,
                    }}
                  >
                    <div>
                      <b style={{ color: "#f8fafc" }}>Hex ({vp.q}, {vp.r})</b>
                      <span className="muted" style={{ fontSize: 10, marginLeft: 6 }}>2 Puntos</span>
                    </div>
                    <div>
                      <span
                        style={{
                          background: vp.owner === "US" ? "#1e3a8a" : vp.owner === "IT" ? "#064e3b" : "#334155",
                          color: vp.owner === "US" ? "#60a5fa" : vp.owner === "IT" ? "#34d399" : "#facc15",
                          padding: "2px 8px",
                          borderRadius: 3,
                          fontWeight: 700,
                          fontSize: 10,
                        }}
                      >
                        {vp.owner}
                      </span>
                    </div>
                  </div>
                ))}
              </div>

              <div style={{ fontSize: 11, fontWeight: 700, color: "#38bdf8", marginTop: 8 }}>
                Controladores por Bando
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {Object.entries(controllerMap).map(([side, ctrl]) => (
                  <div
                    key={side}
                    style={{
                      background: "#0f172a",
                      border: "1px solid #334155",
                      borderRadius: 4,
                      padding: "6px 10px",
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      fontSize: 11,
                    }}
                  >
                    <b style={{ color: side === "US" ? "#60a5fa" : "#34d399" }}>{side}</b>
                    <code style={{ fontSize: 11, color: "#cbd5e1" }}>{ctrl}</code>
                  </div>
                ))}
              </div>

              <div style={{ fontSize: 11, fontWeight: 700, color: "#38bdf8", marginTop: 8 }}>
                Estado de Telemetría MLOps
              </div>
              <div style={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 4, padding: 8, fontSize: 11 }}>
                <div>Estado de cobertura: <b>{String(currentStep.telemetry_coverage_status ?? "normal")}</b></div>
                <div className="muted" style={{ fontSize: 10, marginTop: 4 }}>
                  Decision Rank: <b>{String(currentStep.decision_score_selected ?? "N/A")}</b>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
