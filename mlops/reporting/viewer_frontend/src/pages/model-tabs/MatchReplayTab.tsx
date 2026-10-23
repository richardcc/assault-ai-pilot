import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import type { Dict, ReplayMetaPayload, ReplayStepRow, ReplayUnitSnapshot } from "../../types";
import { fetchCausalSitrep, fetchExplainStep, fetchStepTacticalHeads } from "../../api";
import { ExplainabilityModal } from "../../components/ExplainabilityModal";
import { ForensicSitRepModal } from "../../components/ForensicSitRepModal";

function parseSuppressed(val: unknown): boolean | null {
  if (val === null || val === undefined || val === "") return null;
  if (typeof val === "boolean") return val;
  if (typeof val === "number") return val !== 0;
  const s = String(val).trim().toLowerCase();
  if (["1", "true", "yes", "on"].includes(s)) return true;
  if (["0", "false", "no", "off"].includes(s)) return false;
  return null;
}

function getFortificationLabel(type: string): string {
  switch (type.toLowerCase()) {
    case "bunker":
      return "Reinforced Bunker";
    case "casemate":
      return "Armored Casemate";
    case "pillbox":
      return "Pillbox Emplacement";
    case "gun_emplacement":
      return "Gun Emplacement";
    case "trench":
      return "Trench Line";
    case "barbed_wire":
      return "Barbed Wire";
    case "sandbag":
      return "Sandbag Position";
    case "tank_barricades":
      return "Anti-Tank Barricades";
    case "minefield":
      return "Minefield";
    default:
      return type.replace(/_/g, " ");
  }
}

function getFortificationShort(type: string): string {
  switch (type.toLowerCase()) {
    case "bunker":
      return "BK";
    case "casemate":
      return "CS";
    case "pillbox":
      return "PB";
    case "gun_emplacement":
      return "GN";
    case "trench":
      return "TR";
    case "barbed_wire":
      return "WR";
    case "sandbag":
      return "SB";
    case "tank_barricades":
      return "TB";
    case "minefield":
      return "MN";
    default:
      return type.slice(0, 2).toUpperCase();
  }
}

const HEX_UNIT_OFFSETS = [
  { dx: 0.8660254037844386, dy: -0.5 },
  { dx: 0.8660254037844386, dy: 0.5 },
  { dx: 0, dy: 1 },
  { dx: -0.8660254037844386, dy: 0.5 },
  { dx: -0.8660254037844386, dy: -0.5 },
  { dx: 0, dy: -1 },
];

interface ControllerBadgeInfo {
  label: string;
  icon: string;
  bg: string;
  color: string;
  border: string;
}

function getControllerBadgeInfo(rawCtrl: string): ControllerBadgeInfo {
  const norm = String(rawCtrl || "").toLowerCase();
  if (norm.includes("random")) {
    return {
      label: "Random Baseline",
      icon: "🎲",
      bg: "rgba(245, 158, 11, 0.18)",
      color: "#fbbf24",
      border: "rgba(245, 158, 11, 0.45)",
    };
  }
  if (norm.includes("human")) {
    return {
      label: "Human Player",
      icon: "👤",
      bg: "rgba(59, 130, 246, 0.18)",
      color: "#60a5fa",
      border: "rgba(59, 130, 246, 0.45)",
    };
  }
  if (norm.includes("selfplay") || norm.includes("self-play")) {
    return {
      label: "EfficientZeroV2 (Self-Play)",
      icon: "🤖",
      bg: "rgba(168, 85, 247, 0.2)",
      color: "#c084fc",
      border: "rgba(168, 85, 247, 0.5)",
    };
  }
  return {
    label: "EfficientZeroV2 (AI)",
    icon: "🤖",
    bg: "rgba(99, 102, 241, 0.2)",
    color: "#a5b4fc",
    border: "rgba(99, 102, 241, 0.5)",
  };
}

interface UnitTacticalRoleInfo {
  role: string;
  label: string;
  icon: string;
  color: string;
  desc: string;
  isMutated: boolean;
  mutationReason: string;
  priorBoost: number;
}

function getUnitTacticalRole(
  unit: ReplayUnitSnapshot,
  step: ReplayStepRow,
  _posture: string,
  _targetVpId: string
): UnitTacticalRoleInfo {
  const unitRec = unit as Record<string, unknown>;
  const stepRec = step as Record<string, unknown>;
  const isActing = String(step.unit_id) === String(unit.unit_id);

  const explicitRole = String(
    unitRec.role_assigned ||
    unitRec.active_role ||
    unitRec.doctrine_role ||
    unitRec.unit_macro_role ||
    unitRec.role ||
    unitRec.macro_role ||
    (isActing ? (stepRec.role_assigned || step.unit_macro_role) : "") ||
    ""
  ).trim();

  const isMutated = Boolean(
    unitRec.role_is_mutated ??
    (isActing ? stepRec.role_is_mutated : false)
  );

  const mutationReason = String(
    unitRec.role_mutation_reason ||
    (isActing ? stepRec.role_mutation_reason : "") ||
    ""
  ).trim();

  const priorBoost = Number(
    unitRec.prior_boost_applied ??
    (isActing ? (stepRec.prior_boost_applied ?? 0) : 0)
  ) || 0;

  if (explicitRole.includes("FIRE_SUPPORT")) {
    return {
      role: "ROLE_FIRE_SUPPORT",
      label: "Fire Support",
      icon: "🎯",
      color: "#f97316",
      desc: "Heavy weapons securing fire lanes and suppression.",
      isMutated,
      mutationReason,
      priorBoost,
    };
  }
  if (explicitRole.includes("CLOSE_DEFENSE")) {
    return {
      role: "ROLE_CLOSE_DEFENSE",
      label: "Close Defense",
      icon: "🛡️",
      color: "#a855f7",
      desc: "Flanked heavy weapon assuming close-quarters self-defense.",
      isMutated,
      mutationReason,
      priorBoost,
    };
  }
  if (explicitRole.includes("RECON")) {
    return {
      role: "ROLE_RECON",
      label: "Reconnaissance",
      icon: "🔭",
      color: "#06b6d4",
      desc: "Forward scouting, detection, and sector surveillance.",
      isMutated,
      mutationReason,
      priorBoost,
    };
  }
  if (explicitRole.includes("DEFENDER") || explicitRole.includes("OBJECTIVE_DEFENDER")) {
    return {
      role: "ROLE_OBJECTIVE_DEFENDER",
      label: "VP Defender",
      icon: "🏰",
      color: "#38bdf8",
      desc: "Entrenched in perimeter securing VP control.",
      isMutated,
      mutationReason,
      priorBoost,
    };
  }
  if (explicitRole.includes("SCREEN") || explicitRole.includes("FLANK")) {
    return {
      role: "ROLE_FLANK_SCREEN",
      label: "Flank Screen",
      icon: "👁️",
      color: "#10b981",
      desc: "Sector surveillance and flank screening.",
      isMutated,
      mutationReason,
      priorBoost,
    };
  }
  if (explicitRole.includes("TACTICAL_RESERVE") || explicitRole.includes("RESERVE")) {
    return {
      role: "ROLE_TACTICAL_RESERVE",
      label: "Tactical Reserve",
      icon: "⏱️",
      color: "#8b5cf6",
      desc: "Rearguard element holding cohesion until decisive engagement.",
      isMutated,
      mutationReason,
      priorBoost,
    };
  }
  if (explicitRole.includes("RECOVER")) {
    return {
      role: "ROLE_RECOVER",
      label: "Recovery",
      icon: "🩹",
      color: "#eab308",
      desc: "Unit under morale degradation or damage falling back in good order.",
      isMutated,
      mutationReason,
      priorBoost,
    };
  }
  if (explicitRole.includes("SPEARHEAD")) {
    return {
      role: "ROLE_SPEARHEAD",
      label: "Spearhead",
      icon: "⚡",
      color: "#ef4444",
      desc: "Shock vanguard designated for direct objective assault.",
      isMutated,
      mutationReason,
      priorBoost,
    };
  }
  if (explicitRole) {
    return {
      role: explicitRole,
      label: explicitRole.replace("ROLE_", ""),
      icon: "🎖️",
      color: "#94a3b8",
      desc: `Tactical role assigned: ${explicitRole}`,
      isMutated,
      mutationReason,
      priorBoost,
    };
  }
  return {
    role: "",
    label: "",
    icon: "",
    color: "#64748b",
    desc: "No tactical role assigned in trace.",
    isMutated: false,
    mutationReason: "",
    priorBoost: 0,
  };
}

const MAP_PIECE_OVERRIDES: Record<string, string[]> = {
  S1: ["/art/maps/Map S1.png", "/art/maps/map_s1.png"],
  S2: ["/art/maps/Map S2.png", "/art/maps/map_s2.png"],
  S3: ["/art/maps/Map S3.png", "/art/maps/map_s3.png"],
  S4: ["/art/maps/Map S4.png", "/art/maps/map_s4.png"],
  S5: ["/art/maps/Map S5.png", "/art/maps/map_s5.png"],
  S6: ["/art/maps/Map S6.png", "/art/maps/map_s6.png"],
  S7: ["/art/maps/Map S7.png", "/art/maps/map_s7.png"],
  S8: ["/art/maps/Map S8.png", "/art/maps/map_s8.png"],
  Z1: ["/art/maps/Map Z1.png", "/art/maps/map_z1.png"],
  Z2: ["/art/maps/Map Z2.png", "/art/maps/map_z2.png"],
  Z3: ["/art/maps/Map Z3.png", "/art/maps/map_z3.png"],
  Z4: ["/art/maps/Map Z4.png", "/art/maps/map_z4.png"],
  P1: ["/art/maps/Map P1.png", "/art/maps/map_p1.png"],
  P2: ["/art/maps/Map P2.png", "/art/maps/map_p2.png"],
  P3: ["/art/maps/Map P3.png", "/art/maps/map_p3.png"],
};

function getMapPieceCandidates(pieceId: string): string[] {
  const id = String(pieceId || "").toUpperCase();
  const found = MAP_PIECE_OVERRIDES[id];
  if (found && found.length) return found;
  return [`/art/maps/Map ${id}.png`, `/art/maps/map_${id.toLowerCase()}.png`];
}

const FORTIFICATION_CONFIG: Record<string, { label: string; short: string; art: string }> = {
  trench: { label: "Trench Line", short: "TR", art: "/art/terrain/Terrain Trenches.png" },
  bunker: { label: "Reinforced Bunker", short: "BK", art: "/art/terrain/Terrain Bunker.png" },
  casemate: { label: "Armored Casemate", short: "CS", art: "/art/terrain/Terrain Pillbox.png" },
  pillbox: { label: "Pillbox Emplacement", short: "PB", art: "/art/terrain/Terrain Pillbox.png" },
  gun_emplacement: { label: "Gun Emplacement", short: "GN", art: "/art/terrain/Terrain Gun Emplacement.png" },
  barbed_wire: { label: "Wire Obstacle", short: "WR", art: "/art/terrain/Terrain Barbed Wire.png" },
  sandbag: { label: "Sandbag Position", short: "SB", art: "/art/terrain/Terrain Sandbag Position.png" },
  tank_barricades: { label: "Anti-Tank Barricades", short: "TB", art: "/art/terrain/Terrain Tank Barricades.png" },
  minefield: { label: "Minefield", short: "MN", art: "" },
};

function getFortificationArt(type: string): string {
  const norm = String(type || "").toLowerCase().replace(/ /g, "_");
  const def = FORTIFICATION_CONFIG[norm];
  if (def && def.art) return def.art;
  switch (norm) {
    case "bunker":
      return "/art/terrain/Terrain Bunker.png";
    case "casemate":
    case "pillbox":
      return "/art/terrain/Terrain Pillbox.png";
    case "gun_emplacement":
      return "/art/terrain/Terrain Gun Emplacement.png";
    case "trench":
      return "/art/terrain/Terrain Trenches.png";
    case "barbed_wire":
      return "/art/terrain/Terrain Barbed Wire.png";
    case "sandbag":
      return "/art/terrain/Terrain Sandbag Position.png";
    case "tank_barricades":
      return "/art/terrain/Terrain Tank Barricades.png";
    default:
      return "";
  }
}

function getFortificationIconEmoji(type: string): string {
  const norm = String(type || "").toLowerCase().replace(/ /g, "_");
  switch (norm) {
    case "bunker":
      return "🛡️";
    case "casemate":
    case "pillbox":
      return "🏰";
    case "gun_emplacement":
      return "🎯";
    case "trench":
      return "⛏️";
    case "barbed_wire":
      return "🪤";
    case "sandbag":
      return "🧱";
    case "tank_barricades":
      return "🚧";
    case "minefield":
      return "💣";
    default:
      return "🛡️";
  }
}

const SIDE_MARKERS: Record<string, string> = {
  US: "/art/markers/Markers USA.png",
  IT: "/art/markers/Markers Italy.png",
  GE: "/art/markers/Markers Germany.png",
  UK: "/art/markers/Markers UK.png",
};

const UNIT_IMAGES: Record<string, { label: string; full: string; half?: string }> = {
  GE_RIFLES_43: {
    label: "GE Rifles 43",
    full: "/art/counters/GE Rifles 43.png",
    half: "/art/counters/GE Rifles 43b.png",
  },
  GE_FJ_RIFLES_43: {
    label: "GE FJ Rifles 43",
    full: "/art/counters/GE FJ Rifles 43.png",
    half: "/art/counters/GE FJ Rifles 43b.png",
  },
  GE_HEAVY_MG_42: {
    label: "GE Heavy MG 42",
    full: "/art/counters/GE HMG 42.png",
    half: "/art/counters/GE HMG 42b.png",
  },
  GE_50MM_MORTAR: {
    label: "GE 50mm Mortar",
    full: "/art/counters/GE 50mm Mortar.png",
    half: "/art/counters/GE 50mm Mortarb.png",
  },
  IT_RIFLES_43: {
    label: "IT Rifles 43",
    full: "/art/counters/IT Rifles 43.png",
    half: "/art/counters/IT Rifles 43b.png",
  },
  IT_LMG_SQUAD_43: {
    label: "IT LMG Squad 43",
    full: "/art/counters/IT LMG Squad 43.png",
    half: "/art/counters/IT LMG Squad 43b.png",
  },
  IT_SOLOTHURN_ATR_43: {
    label: "IT Solothurn ATR 43",
    full: "/art/counters/IT Solothurn ATR 43.png",
    half: "/art/counters/IT Solothurn ATR 43b.png",
  },
  IT_20MM_BREDA_AA_43: {
    label: "IT 20mm Breda AA 43",
    full: "/art/counters/IT 20mm Breda AA 43.png",
    half: "/art/counters/IT 20mm Breda AAb.png",
  },
  IT_BREDA_MMG: {
    label: "IT Breda MMG",
    full: "/art/counters/IT Breda MMG.png",
    half: "/art/counters/IT Breda MMG.png",
  },
  IT_SNIPER_43: {
    label: "IT Sniper 43",
    full: "/art/counters/IT Sniper 43.png",
    half: "/art/counters/IT Sniper 43b.png",
  },
  IT_45MM_BRIXIA: {
    label: "IT 45mm Brixia",
    full: "/art/counters/IT 45mm Brixia Team.png",
    half: "/art/counters/IT 45mm Brixia Teamb.png",
  },
  US_RIFLES_43: {
    label: "US Rifles 43",
    full: "/art/counters/US Rifles 43.png",
    half: "/art/counters/US Rifles 43b.png",
  },
  US_RANGERS_43: {
    label: "US Rangers 43",
    full: "/art/counters/US Rangers 43.png",
    half: "/art/counters/US Rangers 43b.png",
  },
  US_SNIPER_43: {
    label: "US Sniper 43",
    full: "/art/counters/US Sniper 43.png",
    half: "/art/counters/US Sniper 43b.png",
  },
  US_BAZOOKA_TEAM: {
    label: "US Bazooka Team 43",
    full: "/art/counters/US Bazooka Team 43.png",
    half: "/art/counters/US Bazooka Team 43b.png",
  },
  US_81MM_MORTAR: {
    label: "US 81mm Mortar",
    full: "/art/counters/US 81mm Mortar.png",
    half: "/art/counters/US 81mm Mortarb.png",
  },
};

const DEFAULT_UNIT_KEYS: Record<string, string> = {
  IT_1: "IT_RIFLES_43",
  IT_2: "IT_RIFLES_43",
  IT_3: "IT_LMG_SQUAD_43",
  IT_4: "IT_LMG_SQUAD_43",
  IT_5: "IT_45MM_BRIXIA",
  IT_6: "IT_BREDA_MMG",
  IT_7: "IT_SNIPER_43",
  US_1: "US_RIFLES_43",
  US_2: "US_RIFLES_43",
  US_3: "US_RIFLES_43",
  US_4: "US_RIFLES_43",
  US_5: "US_BAZOOKA_TEAM",
  US_6: "US_SNIPER_43",
  US_7: "US_81MM_MORTAR",
};

function getUnitCounterArt(unitKey: string, hp?: number): string {
  const normKey = String(unitKey || "").toUpperCase();
  const def = UNIT_IMAGES[normKey];
  if (!def) return "";
  if (hp !== undefined && hp <= 2 && def.half) {
    return def.half;
  }
  return def.full;
}

function axialToLabel(q: number, r: number): string {
  return `${String.fromCharCode(65 + q)}${r + 1}`;
}



function getTerrainColorCss(t: string): string {
  switch (t.toLowerCase()) {
    case "building_single":
      return "#5c3a21";
    case "building_multi":
      return "#4a2a14";
    case "light_forest":
      return "#1e3d20";
    case "heavy_forest":
      return "#142e16";
    case "olive_vine_grove":
      return "#2d4420";
    case "brush":
      return "#383f1e";
    case "rocky":
      return "#3a3d45";
    case "water":
      return "#1e3a5f";
    default:
      return "rgba(15, 23, 42, 0.70)";
  }
}

function getTerrainLabel(t: string): string {
  switch (t.toLowerCase()) {
    case "building_single":
      return "Edificio Simple";
    case "building_multi":
      return "Edificio Robusto";
    case "light_forest":
      return "Bosque Ligero";
    case "heavy_forest":
      return "Bosque Denso";
    case "olive_vine_grove":
      return "Olivar / Viñedo";
    case "brush":
      return "Matorral";
    case "rocky":
      return "Terreno Rocoso";
    case "water":
      return "Agua / Río";
    case "clear":
      return "Campo Abierto";
    default:
      return t;
  }
}

function getTerrainShort(t: string): string {
  switch (t.toLowerCase()) {
    case "building_single":
      return "ED";
    case "building_multi":
      return "ED+";
    case "light_forest":
      return "BQ";
    case "heavy_forest":
      return "B+";
    case "olive_vine_grove":
      return "OL";
    case "brush":
      return "MT";
    case "rocky":
      return "RC";
    case "water":
      return "AG";
    default:
      return "";
  }
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
  const [showForts, setShowForts] = useState(true);
  const [showTerrain, setShowTerrain] = useState(true);
  const [showBriefing, setShowBriefing] = useState(true);
  const [theaterMode, setTheaterMode] = useState(false);
  const [mapHeight, setMapHeight] = useState(680);
  const [zoomLevel, setZoomLevel] = useState(1.0);
  const [panOffset, setPanOffset] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const dragStartRef = useRef<{ clientX: number; clientY: number; startPanX: number; startPanY: number; hasMoved: boolean }>({
    clientX: 0,
    clientY: 0,
    startPanX: 0,
    startPanY: 0,
    hasMoved: false,
  });
  const [imgLoadVersion, setImgLoadVersion] = useState(0);

  // Steps and clamped navigation index (declared early so all hooks have access)
  const steps = useMemo(
    () => (Array.isArray(replaySteps?.steps) ? (replaySteps!.steps as ReplayStepRow[]) : []),
    [replaySteps]
  );
  const clamped = Math.max(0, Math.min(stepIndex, Math.max(0, steps.length - 1)));
  const currentStep = steps[clamped] || {};
  const prevStep = clamped > 0 ? (steps[clamped - 1] || null) : null;


  // Cache loaded PNG assets for 2D canvas drawing
  const imageCacheRef = useRef<Map<string, HTMLImageElement>>(new Map());
  const getLoadedImage = useCallback((src: string): HTMLImageElement | null => {
    if (!src) return null;
    let img = imageCacheRef.current.get(src);
    if (img) {
      return img.complete && img.naturalWidth > 0 ? img : null;
    }
    img = new Image();
    img.src = src;
    img.onload = () => {
      setImgLoadVersion((v) => v + 1);
    };
    img.onerror = () => {
      // avoid infinite reload
    };
    imageCacheRef.current.set(src, img);
    return null;
  }, []);

  // Canvas hover & tooltip state
  const [hoveredHex, setHoveredHex] = useState<{ q: number; r: number } | null>(null);
  const [mousePos, setMousePos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  // Explainability Modal (IGNH / Grad-CAM)
  const [isExplainModalOpen, setIsExplainModalOpen] = useState(false);
  const [explainData, setExplainData] = useState<Dict | null>(null);
  const [isExplaining, setIsExplaining] = useState(false);
  const [explainHeatmapLayer, setExplainHeatmapLayer] = useState<string | null>(null);
  const [explainHeatmapHexes, setExplainHeatmapHexes] = useState<Array<{ q: number; r: number; value: number }>>([]);

  const handleExplainAction = async () => {
    const epId = String(replaySteps?.episode_id || "episode_0");
    const stp = Number(currentStep.step ?? clamped);
    const actId = String(currentStep.action_id || currentStep.chosen_action || "");
    setIsExplainModalOpen(true);
    setIsExplaining(true);
    try {
      const resp = await fetchExplainStep(selectedEvalSourcePath, epId, stp, actId);
      setExplainData(resp);
    } catch (err: any) {
      setExplainData({ ok: false, error: String(err?.message || err) });
    } finally {
      setIsExplaining(false);
    }
  };

  const explainHeatmapMap = useMemo(() => {
    const m = new Map<string, number>();
    for (const item of explainHeatmapHexes) {
      m.set(`${item.q},${item.r}`, item.value);
    }
    return m;
  }, [explainHeatmapHexes]);

  // Tactical Threat Head Overlay State (Auxiliary heads visualization)
  const [showThreatHead, setShowThreatHead] = useState(false);
  const [tacticalHeadsByStep, setTacticalHeadsByStep] = useState<Map<number, Dict>>(new Map());
  const [isLoadingTacticalHeads, setIsLoadingTacticalHeads] = useState(false);

  useEffect(() => {
    if (!showThreatHead || !selectedEvalSourcePath) return;
    const stepIdx = clamped;
    if (tacticalHeadsByStep.has(stepIdx)) return;

    let isMounted = true;
    setIsLoadingTacticalHeads(true);
    const epId = String(replaySteps?.episode_id || "episode_0");
    fetchStepTacticalHeads(selectedEvalSourcePath, epId, stepIdx)
      .then((data) => {
        if (!isMounted) return;
        if (data && data.ok) {
          setTacticalHeadsByStep((prev) => {
            const next = new Map(prev);
            next.set(stepIdx, (data.tactical_heads as Dict) || {});
            return next;
          });
        }
      })
      .catch((err) => {
        console.warn("Could not fetch step tactical heads:", err);
      })
      .finally(() => {
        if (isMounted) setIsLoadingTacticalHeads(false);
      });

    return () => {
      isMounted = false;
    };
  }, [showThreatHead, clamped, selectedEvalSourcePath, replaySteps?.episode_id, tacticalHeadsByStep]);

  const currentTacticalHeads = useMemo(() => {
    return tacticalHeadsByStep.get(clamped) || null;
  }, [tacticalHeadsByStep, clamped]);

  // IPB Topography Overlay State (Roadmap Task 4.3)
  const [showIpbTopography, setShowIpbTopography] = useState(false);
  const [topographyProfile, setTopographyProfile] = useState<Dict | null>(null);
  const [isLoadingTopography, setIsLoadingTopography] = useState(false);

  useEffect(() => {
    if (!showIpbTopography || !selectedEvalSourcePath) return;
    if (topographyProfile) return;
    let isMounted = true;
    setIsLoadingTopography(true);
    const scenId = String(replaySteps?.scenario_id || "");
    const epId = String(replaySteps?.episode_id || "episode_0");
    const params = new URLSearchParams({
      scenario_id: scenId,
      eval_source_path: selectedEvalSourcePath,
      episode_id: epId,
    });
    fetch(`/api/v2/replay/topography?${params.toString()}`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!isMounted) return;
        if (data && data.ok && data.topography) {
          setTopographyProfile(data.topography as Dict);
        }
      })
      .catch((err) => console.warn("Failed to fetch IPB topography:", err))
      .finally(() => {
        if (isMounted) setIsLoadingTopography(false);
      });
    return () => {
      isMounted = false;
    };
  }, [showIpbTopography, selectedEvalSourcePath, replaySteps?.scenario_id, replaySteps?.episode_id, topographyProfile]);

  const topographyMap = useMemo(() => {
    const map = new Map<string, { classification: string; cover_rating: number; los_exposure: number; elevation: number; chokepoint: number }>();
    if (!topographyProfile || !Array.isArray(topographyProfile.hex_profiles)) return map;
    for (const hp of topographyProfile.hex_profiles) {
      if (!hp) continue;
      map.set(`${hp.q},${hp.r}`, {
        classification: String(hp.classification || ""),
        cover_rating: Number(hp.cover_rating || 0),
        los_exposure: Number(hp.los_exposure || 0),
        elevation: Number(hp.elevation_dominance || 0),
        chokepoint: Number(hp.chokepoint_bottleneck || 0),
      });
    }
    return map;
  }, [topographyProfile]);

  // Forensic SitRep and Causal Profiler Modal State
  const [isSitrepOpen, setIsSitrepOpen] = useState(false);
  const [sitrepData, setSitrepData] = useState<Dict | null>(null);
  const [isSitrepLoading, setIsSitrepLoading] = useState(false);

  const handleOpenSitrep = async (force = false) => {
    setIsSitrepOpen(true);
    if (!force && sitrepData && !sitrepData.error) return;
    setIsSitrepLoading(true);
    try {
      const epId = replaySteps?.episode_id || selectedEpisodeId || "episode_0";
      const data = await fetchCausalSitrep(selectedEvalSourcePath, epId, force);
      setSitrepData(data);
    } catch (err: any) {
      setSitrepData({ ok: false, error: String(err?.message || err) });
    } finally {
      setIsSitrepLoading(false);
    }
  };

  const threatHeadHexMap = useMemo(() => {
    const m = new Map<string, number>();
    const threatList = Array.isArray(currentTacticalHeads?.threat_map)
      ? (currentTacticalHeads!.threat_map as Array<{ q: number; r: number; value: number }>)
      : [];
    for (const h of threatList) {
      if (h && Number.isFinite(h.q) && Number.isFinite(h.r)) {
        m.set(`${h.q},${h.r}`, Number(h.value || 0));
      }
    }
    return m;
  }, [currentTacticalHeads]);

  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  // Smooth mouse wheel zoom anchored to cursor
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const handleWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = canvas.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;

      const zoomFactor = e.deltaY < 0 ? 1.15 : 0.87;
      setZoomLevel((prevZoom) => {
        const nextZoom = Math.max(0.6, Math.min(4.5, Number((prevZoom * zoomFactor).toFixed(2))));
        if (nextZoom === prevZoom) return prevZoom;

        const ratio = nextZoom / prevZoom;
        const centerX = rect.width / 2;
        const centerY = rect.height / 2;

        // Mathematically exact zoom anchoring to the mouse cursor position
        setPanOffset((prevPan) => ({
          x: Math.round((mouseX - centerX) - (mouseX - centerX - prevPan.x) * ratio),
          y: Math.round((mouseY - centerY) - (mouseY - centerY - prevPan.y) * ratio),
        }));

        return nextZoom;
      });
    };

    canvas.addEventListener("wheel", handleWheel, { passive: false });
    return () => {
      canvas.removeEventListener("wheel", handleWheel);
    };
  }, []);

  // Active Scenario Overlay (prefers per-episode overlay from replaySteps if available, falls back to replayMeta)
  const activeOverlay = useMemo(() => {
    return (replaySteps?.scenario_overlay || replayMeta?.scenario_overlay || {}) as Dict;
  }, [replaySteps?.scenario_overlay, replayMeta?.scenario_overlay]);

  // Scenario Units definitions (unit_id -> unit_key mapping)
  const scenarioUnitMap = useMemo(() => {
    const raw = (activeOverlay?.scenario_units as unknown[]) || [];
    const map = new Map<string, { unit_key: string; side: string }>();
    if (Array.isArray(raw)) {
      for (const u of raw as Dict[]) {
        if (u && u.unit_id) {
          map.set(String(u.unit_id), {
            unit_key: String(u.unit_key || ""),
            side: String(u.side || ""),
          });
        }
      }
    }
    return map;
  }, [activeOverlay]);

  // Units list for current step
  const units = useMemo(() => {
    if (Array.isArray(currentStep.units) && currentStep.units.length > 0) {
      return (currentStep.units as Dict[]).map((u) => {
        const uid = String(u.unit_id || "");
        const su = scenarioUnitMap.get(uid);
        return {
          ...u,
          unit_id: uid,
          unit_key: String(u.unit_key || su?.unit_key || DEFAULT_UNIT_KEYS[uid] || ""),
          side: String(u.side || su?.side || (uid.split("_")[0] || "")),
        } as ReplayUnitSnapshot;
      });
    }
    if (Array.isArray(currentStep.unit_positions) && currentStep.unit_positions.length > 0) {
      const hpMap = (currentStep.unit_hp_map || {}) as Record<string, number>;
      const aliveMap = (currentStep.unit_alive_map || {}) as Record<string, boolean>;
      const suppMap = (currentStep.unit_suppressed_map || {}) as Record<string, unknown>;
      return (currentStep.unit_positions as Dict[]).map((p) => {
        const uid = String(p.unit_id || "");
        const su = scenarioUnitMap.get(uid);
        const ukey = String(p.unit_key || su?.unit_key || DEFAULT_UNIT_KEYS[uid] || "");
        return {
          unit_id: uid,
          unit_key: ukey,
          side: String(p.side || su?.side || (uid.split("_")[0] || "")),
          q: Number(p.q),
          r: Number(p.r),
          hp: hpMap[uid] !== undefined ? Number(hpMap[uid]) : 4.0,
          alive: aliveMap[uid] !== undefined ? Boolean(aliveMap[uid]) : true,
          suppressed: Boolean(suppMap[uid]),
        } as ReplayUnitSnapshot;
      });
    }
    return [];
  }, [currentStep, scenarioUnitMap]);

  // Current episode metadata from replayMeta
  const currentEpisodeMeta = useMemo(() => {
    const eps = Array.isArray(replayMeta?.episodes_meta) ? replayMeta.episodes_meta : [];
    const currentEpId = String(replaySteps?.episode_id || "episode_0");
    return (eps.find((e: Dict) => String(e.episode_id) === currentEpId) || eps[0] || null) as Dict | null;
  }, [replayMeta, replaySteps?.episode_id]);

  // Controller mapping by side (100% dynamic, multi-tier fallback ensuring never empty)
  const controllerMap = useMemo(() => {
    const fromStep = (currentStep.controller_by_side || currentStep.side_controller_map) as Record<string, string> | undefined;
    if (fromStep && Object.keys(fromStep).length > 0) return fromStep;

    const fromStepsPayload = (replaySteps?.controller_by_side || replaySteps?.side_controller_map) as Record<string, string> | undefined;
    if (fromStepsPayload && Object.keys(fromStepsPayload).length > 0) return fromStepsPayload;

    const fromMeta = currentEpisodeMeta?.controller_by_side as Record<string, string> | undefined;
    if (fromMeta && Object.keys(fromMeta).length > 0) return fromMeta;

    const fromOverlay = (activeOverlay?.side_controller_map || activeOverlay?.controller_by_side) as Record<string, string> | undefined;
    if (fromOverlay && Object.keys(fromOverlay).length > 0) return fromOverlay;

    // Dynamic resolution based on matchup profile and agent name
    const matchup = String(currentEpisodeMeta?.matchup || replaySteps?.matchup || "").toLowerCase();
    const agentName = String(currentEpisodeMeta?.agent_name || replaySteps?.agent_name || "").toLowerCase();
    const attacker = String(activeOverlay?.attacker_side || "US").toUpperCase();
    const defender = String(activeOverlay?.defender_side || (attacker === "US" ? "IT" : "US")).toUpperCase();

    const result: Record<string, string> = {};
    if (matchup === "vs_random_atk") {
      result[attacker] = "EfficientZeroV2 (AI)";
      result[defender] = "Random Baseline";
    } else if (matchup === "vs_random_def") {
      result[defender] = "EfficientZeroV2 (AI)";
      result[attacker] = "Random Baseline";
    } else if (matchup.includes("selfplay")) {
      result[attacker] = "EfficientZeroV2 (Self-Play)";
      result[defender] = "EfficientZeroV2 (Self-Play)";
    } else if (agentName.includes("random_us")) {
      result["US"] = "Random Baseline";
      result[defender] = "EfficientZeroV2 (AI)";
    } else if (agentName.includes("random_it") || agentName.includes("random_ge")) {
      result["IT"] = "Random Baseline";
      result["GE"] = "Random Baseline";
      result["US"] = "EfficientZeroV2 (AI)";
    } else if (agentName.includes("random")) {
      result[attacker] = "EfficientZeroV2 (AI)";
      result[defender] = "Random Baseline";
    } else {
      result[attacker] = "EfficientZeroV2 (AI)";
      result[defender] = "EfficientZeroV2 (AI)";
    }
    return result;
  }, [currentStep, replaySteps, currentEpisodeMeta, activeOverlay]);

  // VP Map for current step (strictly based on the active scenario definition)
  const vpMap = useMemo(() => {
    const raw = (currentStep.vp_map || {}) as Record<string, string>;
    const overlayVps = activeOverlay?.vp_hexes as Array<{ q: number; r: number; initial_owner?: string; value?: number }> | undefined;

    if (Array.isArray(overlayVps) && overlayVps.length > 0) {
      return overlayVps.map((v) => {
        const k = `${v.q},${v.r}`;
        const stepOwner = raw[k];
        const owner = String(stepOwner || v.initial_owner || "NEUTRAL").toUpperCase();
        return {
          q: v.q,
          r: v.r,
          owner,
          key: k,
          value: Number(v.value || 2),
        };
      });
    }

    const list: Array<{ q: number; r: number; owner: string; key: string; value: number }> = [];
    for (const [k, stepOwner] of Object.entries(raw)) {
      const parts = k.split(",");
      if (parts.length === 2) {
        list.push({
          q: Number(parts[0]),
          r: Number(parts[1]),
          owner: String(stepOwner || "NEUTRAL").toUpperCase(),
          key: k,
          value: 2,
        });
      }
    }
    return list;
  }, [currentStep.vp_map, activeOverlay]);

  // VP tally counts
  const vpTally = useMemo(() => {
    const tally: Record<string, number> = { US: 0, IT: 0, GE: 0, NEUTRAL: 0 };
    for (const vp of vpMap) {
      tally[vp.owner] = (tally[vp.owner] || 0) + 1;
    }
    return tally;
  }, [vpMap]);

  // Scenario Shape bounds [width, height] strictly from the authentic scenario definition
  const scenarioShape = useMemo(() => {
    if (Array.isArray(activeOverlay?.shape) && activeOverlay.shape.length >= 2) {
      return [Number(activeOverlay.shape[0]) || 18, Number(activeOverlay.shape[1]) || 12] as [number, number];
    }
    return [18, 12] as [number, number];
  }, [activeOverlay]);

  // Scenario Max Turns
  const maxTurns = useMemo(() => {
    const raw = activeOverlay?.max_turns;
    if (raw !== undefined && Number(raw) > 0) return Number(raw);
    return 8;
  }, [activeOverlay]);

  // Exact optimal pixel width of the map so no horizontal space is wasted
  const optimalMapWidth = useMemo(() => {
    const [shapeW, shapeH] = scenarioShape;
    const sX = Math.sqrt(3) * (shapeW + 0.5);
    const sY = 1.5 * Math.max(1, shapeH - 1) + 2.0;
    const pad = 24;
    return Math.round((mapHeight - pad) * (sX / sY) + pad);
  }, [scenarioShape, mapHeight]);

  // Scenario Map Pieces (Illustrated boards with buildings, streets, etc.)
  const mapPieces = useMemo(() => {
    const raw = activeOverlay?.pieces;
    if (Array.isArray(raw) && raw.length > 0) {
      return raw as Array<{ id: string; origin: [number, number]; rotation?: number; shape: [number, number] }>;
    }
    return [];
  }, [activeOverlay]);

  // Scenario Fortifications (Bunkers, Pillboxes, Trenches, Wire, etc.)
  const fortifications = useMemo(() => {
    const list: Array<{
      q: number;
      r: number;
      type: string;
      orientation?: number;
      vertex_start?: number;
      vertex_end?: number;
      side?: string;
      label?: string;
    }> = [];
    const seen = new Set<string>();

    // 1. From activeOverlay
    const overlayForts = activeOverlay?.fortifications;
    if (Array.isArray(overlayForts) && overlayForts.length > 0) {
      for (const f of overlayForts as Dict[]) {
        if (f && Number.isFinite(Number(f.q)) && Number.isFinite(Number(f.r))) {
          const q = Number(f.q);
          const r = Number(f.r);
          const ftype = String(f.type || "bunker");
          const key = `${q},${r}:${ftype}`;
          if (!seen.has(key)) {
            seen.add(key);
            list.push({
              q,
              r,
              type: ftype,
              orientation: f.orientation !== undefined ? Number(f.orientation) : undefined,
              vertex_start: f.vertex_start !== undefined ? Number(f.vertex_start) : undefined,
              vertex_end: f.vertex_end !== undefined ? Number(f.vertex_end) : undefined,
              side: f.side ? String(f.side) : undefined,
              label: f.label ? String(f.label) : undefined,
            });
          }
        }
      }
    }

    // 2. From current step if present
    const stepForts = (currentStep.obs_fortification_type_map || currentStep.fortifications_map || {}) as Record<string, string>;
    for (const [k, v] of Object.entries(stepForts)) {
      const parts = k.split(",");
      if (parts.length === 2 && v) {
        const q = Number(parts[0]);
        const r = Number(parts[1]);
        const key = `${q},${r}:${v}`;
        if (!seen.has(key)) {
          seen.add(key);
          list.push({ q, r, type: String(v) });
        }
      }
    }
    return list;
  }, [activeOverlay, currentStep.obs_fortification_type_map, currentStep.fortifications_map]);

  // Scenario Terrain Map (Buildings, woods, olive groves, etc.)
  const terrainMap = useMemo(() => {
    const map = new Map<string, string>();
    // 1. From activeOverlay map_cells (array or record)
    const overlayCells = activeOverlay?.map_cells;
    if (Array.isArray(overlayCells)) {
      for (const cell of overlayCells as Dict[]) {
        if (cell && Number.isFinite(Number(cell.q)) && Number.isFinite(Number(cell.r)) && cell.terrain) {
          map.set(`${cell.q},${cell.r}`, String(cell.terrain));
        }
      }
    } else if (overlayCells && typeof overlayCells === "object") {
      for (const [coord, cellData] of Object.entries(overlayCells as Record<string, Dict>)) {
        if (cellData?.terrain) {
          map.set(coord, String(cellData.terrain));
        }
      }
    }
    // 2. From step if present
    const stepTerrain = (currentStep.obs_terrain_type_map || currentStep.terrain_map || {}) as Record<string, string>;
    for (const [coord, t] of Object.entries(stepTerrain)) {
      if (t) {
        map.set(coord, String(t));
      }
    }
    return map;
  }, [activeOverlay, currentStep.obs_terrain_type_map, currentStep.terrain_map]);

  // Fortifications text summary
  const fortSummary = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const f of fortifications) {
      const t = String(f.type || "").toLowerCase();
      counts[t] = (counts[t] || 0) + 1;
    }
    const parts: string[] = [];
    if (counts["bunker"]) parts.push(`${counts["bunker"]} Bunker${counts["bunker"] > 1 ? "s" : ""}`);
    if (counts["casemate"]) parts.push(`${counts["casemate"]} Casemate${counts["casemate"] > 1 ? "s" : ""}`);
    if (counts["gun_emplacement"]) parts.push(`${counts["gun_emplacement"]} Gun Emplacement${counts["gun_emplacement"] > 1 ? "s" : ""}`);
    if (counts["trench"]) parts.push(`${counts["trench"]} Trench${counts["trench"] > 1 ? "es" : ""}`);
    if (counts["barbed_wire"]) parts.push(`${counts["barbed_wire"]} Wire Obstacle${counts["barbed_wire"] > 1 ? "s" : ""}`);
    if (counts["minefield"]) parts.push(`${counts["minefield"]} Minefield${counts["minefield"] > 1 ? "s" : ""}`);
    return parts.join(", ");
  }, [fortifications]);

  // Scenario & Tactical Forces Briefing Data (100% Dynamic, strictly driven by active scenario overlay)
  const scenarioBriefing = useMemo(() => {
    const rawId = String(
      activeOverlay?.scenario_id ||
      replaySteps?.scenario_id ||
      (replayMeta?.scenario_id && !String(replayMeta.scenario_id).startsWith("multi:") ? replayMeta.scenario_id : "") ||
      ""
    ).toLowerCase();

    const shape = scenarioShape;

    // Units inventory
    const rawScenarioUnits = (activeOverlay?.scenario_units as Dict[]) || [];
    const sourceUnits = rawScenarioUnits.length > 0 ? rawScenarioUnits : (units as Dict[]);

    const unitsBySide: Record<string, { total: number; alive: number; keys: Record<string, number> }> = {};

    // Alive lookup from current step units
    const aliveMap = new Map<string, boolean>();
    for (const u of units) {
      const uid = String(u.unit_id || "");
      const isAlive = u.alive !== false && (u.hp === undefined || Number(u.hp) > 0);
      aliveMap.set(uid, isAlive);
    }

    for (const su of sourceUnits) {
      const uid = String(su.unit_id || "");
      const side = String(su.side || (uid.startsWith("US") ? "US" : uid.startsWith("GE") ? "GE" : uid.startsWith("IT") ? "IT" : "UNKNOWN")).toUpperCase();
      if (!unitsBySide[side]) {
        unitsBySide[side] = { total: 0, alive: 0, keys: {} };
      }
      unitsBySide[side].total += 1;

      const isAlive = aliveMap.has(uid) ? aliveMap.get(uid)! : true;
      if (isAlive) {
        unitsBySide[side].alive += 1;
      }

      const ukey = String(su.unit_key || su.unit_id || "Unit")
        .replace(/^(US_|GE_|IT_)/i, "")
        .replace(/_/g, " ");
      unitsBySide[side].keys[ukey] = (unitsBySide[side].keys[ukey] || 0) + 1;
    }

    // Scheduled Reinforcements inventory
    const rawReinforcements = (activeOverlay?.reinforcements as Dict[]) || [];
    const reinforcementsBySide: Record<
      string,
      { count: number; waves: { turn: number; phase: string; count: number; keys: Record<string, number> }[] }
    > = {};

    for (const rw of rawReinforcements) {
      const rSide = String(rw.side || "US").toUpperCase();
      const rTurn = Number(rw.turn || 1);
      const rPhase = String(rw.phase || "organization");
      const rUnits = (rw.units as Dict[]) || [];
      const waveKeys: Record<string, number> = {};
      for (const ru of rUnits) {
        const ukey = String(ru.unit_key || ru.unit_id || "Unit")
          .replace(/^(US_|GE_|IT_)/i, "")
          .replace(/_/g, " ");
        waveKeys[ukey] = (waveKeys[ukey] || 0) + 1;
      }
      if (!reinforcementsBySide[rSide]) {
        reinforcementsBySide[rSide] = { count: 0, waves: [] };
      }
      reinforcementsBySide[rSide].count += rUnits.length;
      reinforcementsBySide[rSide].waves.push({
        turn: rTurn,
        phase: rPhase,
        count: rUnits.length,
        keys: waveKeys,
      });
    }

    const attackerSide = String(activeOverlay?.attacker_side || "US").toUpperCase();
    const defenderSide = String(activeOverlay?.defender_side || (attackerSide === "US" ? "IT" : "US")).toUpperCase();

    // Purely dynamic Title, Subtitle, Description from activeOverlay
    const title = String(
      activeOverlay?.name ||
      activeOverlay?.title ||
      (rawId ? rawId.replace(/_/g, " ").toUpperCase() : "Tactical Scenario")
    );
    const subtitle = String(
      activeOverlay?.subtitle ||
      `Tactical Scenario (${shape[0]}×${shape[1]} Hexes)`
    );
    const desc = String(
      activeOverlay?.description ||
      `Tactical combat between ${attackerSide} and ${defenderSide} contesting objective VPs.`
    );
    const idLabel = String(activeOverlay?.scenario_id || rawId || "scenario");

    return {
      title,
      subtitle,
      idLabel,
      desc,
      attackerSide,
      defenderSide,
      shapeText: `${shape[0]}×${shape[1]} hex`,
      totalVps: vpMap.length,
      unitsBySide,
      reinforcementsBySide,
      victoryOutcomes: (activeOverlay?.victory_outcomes || {}) as Dict,
      maxTurns: Number(activeOverlay?.max_turns || maxTurns || 8),
    };
  }, [activeOverlay, replaySteps?.scenario_id, replayMeta?.scenario_id, scenarioShape, units, vpMap, maxTurns]);

  const factions = useMemo(() => {
    const sides = Object.keys(scenarioBriefing.unitsBySide);
    const sideList = sides.length > 0 ? sides : ["US", scenarioBriefing.defenderSide || "IT"];

    // Dynamic Victory Requirements from victory_outcomes
    const vo = scenarioBriefing.victoryOutcomes as Dict;
    const voTable = Array.isArray(vo.table) ? (vo.table as Dict[]) : [];
    const totalVps = scenarioBriefing.totalVps || 5;
    const maxT = scenarioBriefing.maxTurns || 8;

    let victoryThreshold = 0;
    let majorVictoryThreshold = 0;
    for (const row of voTable) {
      const cls = String(row.outcome_class || "").toLowerCase();
      const cap = (row.captured || {}) as Dict;
      const minCap = Number(cap.min ?? cap.max ?? 0);
      if (cls === "total_victory") majorVictoryThreshold = minCap;
      if (cls === "victory" && victoryThreshold === 0) victoryThreshold = minCap;
    }
    if (victoryThreshold === 0) {
      victoryThreshold = Math.ceil(totalVps * 0.6);
    }
    const defenderHoldThreshold = totalVps - victoryThreshold + 1;

    return sideList.map((side) => {
      const isUS = side === "US";
      const isGE = side === "GE";
      const isIT = side === "IT";
      const isAttacker = side === scenarioBriefing.attackerSide;

      const flag = isUS ? "🇺🇸" : isGE ? "🇩🇪" : isIT ? "🇮🇹" : "🚩";
      const name = isUS
        ? "United States (US Army)"
        : isGE
        ? "Germany (Wehrmacht / FJ)"
        : isIT
        ? "Italy (Regio Esercito)"
        : `Faction ${side}`;

      const roleBadge = isAttacker ? "ATTACKER" : "DEFENDER";
      const roleColor = isAttacker ? "#38bdf8" : "#34d399";
      const borderColor = isAttacker ? "rgba(56, 189, 248, 0.45)" : "rgba(52, 211, 153, 0.45)";
      const bgGrad = isAttacker
        ? "linear-gradient(135deg, rgba(30, 58, 138, 0.35), rgba(15, 23, 42, 0.65))"
        : isGE
        ? "linear-gradient(135deg, rgba(127, 29, 29, 0.35), rgba(15, 23, 42, 0.65))"
        : "linear-gradient(135deg, rgba(6, 78, 59, 0.35), rgba(15, 23, 42, 0.65))";

      const ctrlRaw = controllerMap[side] || controllerMap[side.toUpperCase()] || "";
      const controller = getControllerBadgeInfo(ctrlRaw);

      let mission = "";
      if (isAttacker) {
        if (majorVictoryThreshold > 0 && majorVictoryThreshold !== victoryThreshold) {
          mission = `Assault & capture: Control ≥ ${victoryThreshold} of ${totalVps} VPs within ${maxT} turns (≥ ${majorVictoryThreshold} for Total Victory).`;
        } else {
          mission = `Assault & capture: Control ≥ ${victoryThreshold} of ${totalVps} VPs within ${maxT} turns.`;
        }
      } else {
        mission = `Sector defense: Retain ≥ ${defenderHoldThreshold} of ${totalVps} VPs through turn ${maxT} to deny Allied objectives.`;
      }

      const data = scenarioBriefing.unitsBySide[side] || { total: 0, alive: 0, keys: {} };
      const keyBreakdown = Object.entries(data.keys).map(([k, count]) => `${count}x ${k}`).join(" · ");

      const rData = (scenarioBriefing.reinforcementsBySide || {})[side];
      const reinforcementsCount = rData ? rData.count : 0;
      const initialTotal = data.total;
      const totalForces = initialTotal + reinforcementsCount;

      let reinforcementsInfo = "";
      if (rData && rData.waves.length > 0) {
        reinforcementsInfo = rData.waves
          .map((w) => {
            const wBreakdown = Object.entries(w.keys).map(([k, count]) => `${count}x ${k}`).join(" · ");
            return `+${w.count} units on Turn ${w.turn} (${wBreakdown})`;
          })
          .join("; ");
      }

      return {
        side,
        flag,
        name,
        roleBadge,
        roleColor,
        borderColor,
        bgGrad,
        controller,
        mission,
        total: data.total,
        alive: data.alive,
        initialTotal,
        reinforcementsCount,
        reinforcementsInfo,
        totalForces,
        keyBreakdown: keyBreakdown || `${data.total} units`,
        fortifications: !isAttacker && fortSummary ? fortSummary : null,
      };
    });
  }, [scenarioBriefing, fortSummary, controllerMap]);

  // Parse Action vector and targets with pre/post status resolution
  const actionVector = useMemo(() => {
    const actionId = String(currentStep.action_id || "");
    const parts = actionId.split(":");
    const kind = parts[0] || "";
    const actorId = parts[1] || String(currentStep.unit_id || "");

    const actorUnit = units.find((u) => u.unit_id === actorId);

    // Look up previous step units to find exact origin and pre-action health
    const prevUnits = prevStep && Array.isArray(prevStep.units) ? (prevStep.units as Dict[]) : [];
    const prevActor = prevUnits.find((u) => String(u.unit_id) === actorId);

    // Initial scenario units fallback if step 0
    const rawScenarioUnits = (activeOverlay?.scenario_units as Dict[]) || [];
    const initialActor = rawScenarioUnits.find((u) => String(u.unit_id) === actorId);

    // Determine fromQ, fromR (Origin position BEFORE this step action was executed)
    let fromQ: number | null = null;
    let fromR: number | null = null;

    if (prevActor && Number.isFinite(prevActor.q) && Number.isFinite(prevActor.r)) {
      fromQ = Number(prevActor.q);
      fromR = Number(prevActor.r);
    } else if (initialActor && Number.isFinite(initialActor.q) && Number.isFinite(initialActor.r)) {
      fromQ = Number(initialActor.q);
      fromR = Number(initialActor.r);
    } else if (actorUnit && Number.isFinite(actorUnit.q) && Number.isFinite(actorUnit.r)) {
      fromQ = Number(actorUnit.q);
      fromR = Number(actorUnit.r);
    }

    let toQ: number | null = null;
    let toR: number | null = null;
    let targetUnitId: string | null = null;
    const isFire = kind.includes("FIRE") || kind.includes("ATTACK");
    const isMove = !isFire && (kind.includes("MOVE") || kind.includes("ASSAULT"));

    if (isFire) {
      // Find target unit id across tokens (e.g. OPPORTUNITY_FIRE:IT_6:US_8 or FIRE_MOVE:US_2:RANGED_DIRECT:US_2:IT_1:0:10)
      for (let i = 2; i < parts.length; i++) {
        const pStr = parts[i];
        if (pStr && pStr !== actorId && (units.some((u) => u.unit_id === pStr) || prevUnits.some((u) => u.unit_id === pStr))) {
          targetUnitId = pStr;
          break;
        }
      }
      if (!targetUnitId && parts.length >= 3 && parts[2]) {
        targetUnitId = parts[2];
      }
      if (targetUnitId) {
        const targetUnit = units.find((u) => u.unit_id === targetUnitId) || prevUnits.find((u) => u.unit_id === targetUnitId);
        if (targetUnit && Number.isFinite(targetUnit.q) && Number.isFinite(targetUnit.r)) {
          toQ = Number(targetUnit.q);
          toR = Number(targetUnit.r);
        }
      }
    } else if (isMove && parts.length >= 4) {
      const qNum = Number(parts[2]);
      const rNum = Number(parts[3]);
      if (Number.isFinite(qNum) && Number.isFinite(rNum)) {
        toQ = qNum;
        toR = rNum;
      }
    }

    if (
      toQ === null &&
      currentStep.target_q !== null &&
      currentStep.target_q !== undefined &&
      currentStep.target_r !== null &&
      currentStep.target_r !== undefined &&
      Number.isFinite(Number(currentStep.target_q)) &&
      Number.isFinite(Number(currentStep.target_r))
    ) {
      toQ = Number(currentStep.target_q);
      toR = Number(currentStep.target_r);
    }

    // If still no toQ/toR for Move, use unit current position (where it arrived)
    if (isMove && (toQ === null || toR === null) && actorUnit && Number.isFinite(actorUnit.q) && Number.isFinite(actorUnit.r)) {
      toQ = Number(actorUnit.q);
      toR = Number(actorUnit.r);
    }

    // Strict numerical sanity check
    if (toQ !== null && !Number.isFinite(toQ)) toQ = null;
    if (toR !== null && !Number.isFinite(toR)) toR = null;
    if (fromQ !== null && !Number.isFinite(fromQ)) fromQ = null;
    if (fromR !== null && !Number.isFinite(fromR)) fromR = null;

    // Acting Unit Health and Status Before and After
    const actorHpPre = prevActor ? Number(prevActor.hp ?? 4.0) : (initialActor ? Number(initialActor.hp ?? 4.0) : (actorUnit ? Number(actorUnit.hp ?? 4.0) : 4.0));
    const actorHpPost = actorUnit ? Number(actorUnit.hp ?? actorHpPre) : actorHpPre;
    const actorAlivePre = prevActor ? (prevActor.alive !== false && actorHpPre > 0) : true;
    const actorAlivePost = actorUnit ? (actorUnit.alive !== false && actorHpPost > 0) : false;

    // Target Unit Health and Status Before and After (for combat actions)
    let targetHpPre: number | null = null;
    let targetHpPost: number | null = null;
    let targetAlivePre: boolean | null = null;
    let targetAlivePost: boolean | null = null;
    let targetUnitName = "";
    let targetUnitSide = "";

    if (targetUnitId) {
      const prevTarget = prevUnits.find((u) => String(u.unit_id) === targetUnitId);
      const currTarget = units.find((u) => String(u.unit_id) === targetUnitId);
      const initTarget = rawScenarioUnits.find((u) => String(u.unit_id) === targetUnitId);

      targetHpPre = prevTarget ? Number(prevTarget.hp ?? 4.0) : (initTarget ? Number(initTarget.hp ?? 4.0) : (currTarget ? Number(currTarget.hp ?? 4.0) : 4.0));
      targetHpPost = currTarget ? Number(currTarget.hp ?? targetHpPre) : targetHpPre;
      targetAlivePre = prevTarget ? (prevTarget.alive !== false && targetHpPre > 0) : true;
      targetAlivePost = currTarget ? (currTarget.alive !== false && targetHpPost > 0) : false;

      const su = scenarioUnitMap.get(targetUnitId);
      targetUnitName = su ? su.unit_key.replace(/^(US_|GE_|IT_)/i, "").replace(/_/g, " ") : targetUnitId;
      targetUnitSide = su ? su.side : (targetUnitId.split("_")[0] || "");
    }

    const actorUnitName = actorUnit ? (scenarioUnitMap.get(actorId)?.unit_key || actorUnit.unit_key || actorId).replace(/^(US_|GE_|IT_)/i, "").replace(/_/g, " ") : actorId;
    const actorSide = actorUnit ? actorUnit.side : (actorId.split("_")[0] || "");

    // Compute distance in hexes between origin and destination
    let hexDistance = 0;
    if (fromQ !== null && fromR !== null && toQ !== null && toR !== null) {
      const dq = toQ - fromQ;
      const dr = toR - fromR;
      hexDistance = Math.max(Math.abs(dq), Math.abs(dr), Math.abs(dq + dr));
    }

    return {
      actionId,
      kind,
      actorId,
      actorSide,
      actorUnitName,
      targetUnitId,
      targetUnitSide,
      targetUnitName,
      fromQ,
      fromR,
      toQ,
      toR,
      isFire,
      isMove,
      actorHpPre,
      actorHpPost,
      actorAlivePre,
      actorAlivePost,
      targetHpPre,
      targetHpPost,
      targetAlivePre,
      targetAlivePost,
      hexDistance,
    };
  }, [currentStep, prevStep, units, activeOverlay, scenarioUnitMap]);

  const getStepDetails = useCallback((s: ReplayStepRow, idx: number) => {
    const actionParts = String(s.action_id || "").split(":");
    const unitId = String(s.unit_id || actionParts[1] || "-");
    const side = String(s.to_play || s.unit_side || (unitId !== "-" ? unitId.split("_")[0] : "-")).toUpperCase();
    const gameTurn = s.game_turn ?? s.turn ?? null;
    const oppSide = String(s.opponent_side || (side === "IT" ? "US" : side === "US" ? "IT" : side === "GE" ? "US" : "-")).toUpperCase();
    const flag = side === "US" ? "🇺🇸" : side === "IT" ? "🇮🇹" : side === "GE" ? "🇩🇪" : "";
    const oppFlag = oppSide === "US" ? "🇺🇸" : oppSide === "IT" ? "🇮🇹" : oppSide === "GE" ? "🇩🇪" : "";

    const sRec = s as Record<string, unknown>;
    const macroPosture = String(s.macro_posture || "");
    const macroTargetVpId = String(s.macro_target_vp_id || s.target_vp || "");
    const unitMacroRole = String(sRec.role_assigned || s.unit_macro_role || "");
    const roleAssigned = String(sRec.role_assigned || s.unit_macro_role || "");
    const roleIsMutated = Boolean(sRec.role_is_mutated ?? false);
    const roleMutationReason = String(sRec.role_mutation_reason || "");
    const priorBoostApplied = Number(sRec.prior_boost_applied || 0);
    const badgeLabel = String(sRec.badge_label || (unitMacroRole ? unitMacroRole.replace("ROLE_", "") : ""));

    return {
      stepIndex: idx,
      gameTurn,
      toPlay: side,
      flag,
      opponentSide: oppSide,
      oppFlag,
      unitId,
      actionId: String(s.action_id || "-"),
      actionKind: String(s.action_kind || actionParts[0] || "-"),
      reward: Number(s.reward || 0),
      damage: Number(s.damage_dealt || 0),
      kills: Number(s.kills_dealt || 0),
      macroPosture,
      macroTargetVpId,
      unitMacroRole,
      roleAssigned,
      roleIsMutated,
      roleMutationReason,
      priorBoostApplied,
      badgeLabel,
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
          unit_key: String(u.unit_key || DEFAULT_UNIT_KEYS[u.unit_id || ""] || ""),
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

  // Memoized Board Geometry for high-performance rendering and hover picking
  const boardGeometry = useMemo(() => {
    const [shapeW, shapeH] = scenarioShape;
    const minQ = 0;
    const maxQ = Math.max(1, (Number.isFinite(shapeW) ? shapeW : 18) - 1);
    const minR = 0;
    const maxR = Math.max(1, (Number.isFinite(shapeH) ? shapeH : 12) - 1);

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

    return { raws, minX, maxX, minY, maxY, spanX, spanY, oddRRaw };
  }, [scenarioShape]);

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

    const { raws, minX, minY, spanX, spanY, oddRRaw } = boardGeometry;
    const pad = 16;
    const baseScaleX = (cssWidth - pad * 2) / spanX;
    const baseScaleY = (cssHeight - pad * 2) / spanY;
    const scale = Math.max(6, Math.min(baseScaleX, baseScaleY) * zoomLevel);

    const boardPixelW = spanX * scale;
    const boardPixelH = spanY * scale;
    const offsetX = (cssWidth - boardPixelW) / 2 + (Math.sqrt(3) / 2) * scale + panOffset.x;
    const offsetY = (cssHeight - boardPixelH) / 2 + 1.0 * scale + panOffset.y;

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
        const off = HEX_UNIT_OFFSETS[i];
        const xx = x + size * off.dx;
        const yy = y + size * off.dy;
        if (i === 0) ctx.moveTo(xx, yy);
        else ctx.lineTo(xx, yy);
      }
      ctx.closePath();
      if (fill && fill !== "transparent") {
        ctx.fillStyle = fill;
        ctx.fill();
      }
      if (stroke && stroke !== "transparent") {
        ctx.strokeStyle = stroke;
        ctx.lineWidth = lineWidth;
        ctx.stroke();
      }
    };

    // 0. Draw Scenario Illustrated Map Pieces (Buildings, streets, rivers, groves)
    let hasDrawnAnyMapPiece = false;
    if (showTerrain && mapPieces.length > 0) {
      for (const piece of mapPieces) {
        const candidates = getMapPieceCandidates(piece.id);
        let img: HTMLImageElement | null = null;
        for (const c of candidates) {
          img = getLoadedImage(c);
          if (img) break;
        }
        if (!img) continue;

        const [oq, orr] = piece.origin || [0, 0];
        const [hexW, hexH] = piece.shape || [9, 4];
        const quarterTurns = (((Number(piece.rotation ?? 0) / 90) % 4) + 4) % 4;

        const pOrigin = toPixel(oq, orr);
        const hexW_px = Math.sqrt(3) * scale;
        const hexH_px = 1.5 * scale;

        // Base size for an unrotated piece image (exact assault_ai_ui formula)
        const baseWidth = (hexW + 0.5) * hexW_px;
        const baseHeight = (hexH - 1) * hexH_px + scale * 2.0;

        const topLeftX = pOrigin.x - hexW_px / 2;
        const topLeftY = pOrigin.y - scale;

        ctx.save();
        const rotOffsetX =
          quarterTurns === 1 ? baseHeight :
          quarterTurns === 2 ? baseWidth :
          0;
        const rotOffsetY =
          quarterTurns === 2 ? baseHeight :
          quarterTurns === 3 ? baseWidth :
          0;

        ctx.translate(topLeftX + rotOffsetX, topLeftY + rotOffsetY);
        ctx.rotate((quarterTurns * Math.PI) / 2);
        ctx.drawImage(img, 0, 0, baseWidth, baseHeight);
        ctx.restore();
        hasDrawnAnyMapPiece = true;
      }
    }

    // 1. Draw Board Hex Grid Cells (Tactical Grid + Coordinates)
    for (const cell of raws) {
      const p = toPixel(cell.q, cell.r);
      const isHovered = hoveredHex && hoveredHex.q === cell.q && hoveredHex.r === cell.r;
      const coordKey = `${cell.q},${cell.r}`;
      const terrainType = terrainMap.get(coordKey) || "clear";

      const terrainColor = showTerrain
        ? hasDrawnAnyMapPiece
          ? "transparent"
          : getTerrainColorCss(terrainType)
        : "rgba(15, 23, 42, 0.70)";

      const strokeColor = hasDrawnAnyMapPiece
        ? isHovered
          ? "#38bdf8"
          : "rgba(255, 255, 255, 0.35)"
        : isHovered
        ? "#38bdf8"
        : "#243247";

      drawHex(
        p.x,
        p.y,
        scale * 0.95,
        strokeColor,
        isHovered ? "rgba(56, 189, 248, 0.28)" : terrainColor,
        isHovered ? 2 : 1
      );

      // Spatial Explainability (IGNH / Grad-CAM) Heatmap Overlay
      const explainVal = explainHeatmapMap.get(coordKey);
      if (explainVal !== undefined) {
        const absVal = Math.min(1, Math.abs(explainVal));
        const alpha = Math.max(0.18, absVal * 0.70);
        const overlayFill = explainVal >= 0
          ? `rgba(34, 197, 94, ${alpha})`
          : `rgba(239, 68, 68, ${alpha})`;
        const overlayStroke = explainVal >= 0 ? "rgba(34, 197, 94, 0.9)" : "rgba(239, 68, 68, 0.9)";
        drawHex(p.x, p.y, scale * 0.95, overlayStroke, overlayFill, 2);
      }

      // Tactical Threat Head Overlay (Auxiliary Head prediction)
      if (showThreatHead) {
        const threatVal = threatHeadHexMap.get(coordKey);
        if (threatVal !== undefined && threatVal > 0.04) {
          const alpha = Math.min(0.68, Math.max(0.16, threatVal * 0.72));
          const threatColor = threatVal >= 0.70
            ? `rgba(220, 38, 38, ${alpha})`
            : threatVal >= 0.40
            ? `rgba(234, 88, 12, ${alpha})`
            : `rgba(245, 158, 11, ${alpha * 0.85})`;
          const threatBorder = threatVal >= 0.50 ? "#ef4444" : "rgba(245, 158, 11, 0.6)";
          drawHex(p.x, p.y, scale * 0.95, threatBorder, threatColor, threatVal >= 0.50 ? 2 : 1);

          // Threat numerical percentage on higher threat hexes (fast crisp text outline)
          if (threatVal >= 0.25) {
            const threatLabel = `${Math.round(threatVal * 100)}%`;
            ctx.font = `bold ${Math.max(8, Math.floor(scale * 0.28))}px sans-serif`;
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.lineWidth = 2.5;
            ctx.strokeStyle = "rgba(0, 0, 0, 0.95)";
            ctx.strokeText(threatLabel, p.x, p.y + scale * 0.36);
            ctx.fillStyle = threatVal >= 0.60 ? "#fef08a" : "#fef3c7";
            ctx.fillText(threatLabel, p.x, p.y + scale * 0.36);
          }
        }
      }

      // IPB Topography Overlay (Roadmap Task 4.3: Defilade Corridors, Killzones, Base of Fire, Chokepoints)
      if (showIpbTopography && topographyMap.size > 0) {
        const ipbProf = topographyMap.get(coordKey);
        if (ipbProf) {
          const cls = ipbProf.classification;
          if (cls === "KEY_TERRAIN") {
            drawHex(p.x, p.y, scale * 0.95, "#f59e0b", "rgba(245, 158, 11, 0.22)", 2);
          } else if (cls === "DEFILADE_CORRIDOR") {
            drawHex(p.x, p.y, scale * 0.95, "#10b981", "rgba(16, 185, 129, 0.20)", 1.5);
          } else if (cls === "KILLZONE") {
            drawHex(p.x, p.y, scale * 0.95, "#ef4444", "rgba(239, 68, 68, 0.24)", 1.5);
          } else if (cls === "CHOKEPOINT") {
            drawHex(p.x, p.y, scale * 0.95, "#a855f7", "rgba(168, 85, 247, 0.22)", 1.5);
          } else if (cls === "BASE_OF_FIRE") {
            drawHex(p.x, p.y, scale * 0.95, "#06b6d4", "rgba(6, 182, 212, 0.22)", 2);
          }
        }
      }

      // Alphanumeric Coordinate label (like A1, B2) with fast crisp outline
      if (showCoords) {
        const coordLabel = axialToLabel(cell.q, cell.r);
        ctx.font = `bold ${Math.max(7, Math.floor(scale * 0.28))}px monospace`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.lineWidth = 2;
        ctx.strokeStyle = "rgba(0, 0, 0, 0.9)";
        ctx.strokeText(coordLabel, p.x, p.y - scale * 0.44);
        ctx.fillStyle = isHovered ? "#38bdf8" : hasDrawnAnyMapPiece ? "rgba(245, 245, 245, 0.9)" : "rgba(148, 163, 184, 0.75)";
        ctx.fillText(coordLabel, p.x, p.y - scale * 0.44);
      }

      // Terrain short label if illustrated map piece is not present
      if (showTerrain && !hasDrawnAnyMapPiece && terrainType !== "clear") {
        const shortCode = getTerrainShort(terrainType);
        if (shortCode) {
          ctx.fillStyle = "rgba(255, 255, 255, 0.40)";
          ctx.font = `bold ${Math.max(7, Math.floor(scale * 0.22))}px sans-serif`;
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillText(shortCode, p.x, p.y + scale * 0.38);
        }
      }
    }

    // 2. Draw Scenario Fortifications (Bunkers, Pillboxes, Trenches, Barbed Wire, etc.)
    if (showForts && fortifications.length > 0) {
      const renderCfg = {
        scaleX: 1.7,
        scaleY: 1.5,
        edgeOffset: 0.0,
        xNudge: -0.26,
        yNudge: 0.10,
      };

      for (const fort of fortifications) {
        const p = toPixel(fort.q, fort.r);
        const artSrc = getFortificationArt(fort.type);
        const img = artSrc ? getLoadedImage(artSrc) : null;

        const orientation = fort.orientation;
        const edgeStart = fort.vertex_start;
        const edgeEnd = fort.vertex_end;
        const edgeRotation = (() => {
          if (orientation != null && orientation >= 1 && orientation <= 6) {
            return ((orientation - 1) * Math.PI) / 3;
          }
          if (edgeStart != null && edgeEnd != null) {
            const a = Math.min(edgeStart, edgeEnd);
            return ((a - 1) * Math.PI) / 3;
          }
          return 0;
        })();

        const edgeAnchorAngle = edgeRotation - Math.PI / 6;
        const nx = Math.cos(edgeAnchorAngle);
        const ny = Math.sin(edgeAnchorAngle);
        const tx = -ny;
        const ty = nx;

        const edgeDx = nx * scale * renderCfg.edgeOffset;
        const edgeDy = ny * scale * renderCfg.edgeOffset;
        const nudgeDx = tx * scale * renderCfg.xNudge + nx * scale * renderCfg.yNudge;
        const nudgeDy = ty * scale * renderCfg.xNudge + ny * scale * renderCfg.yNudge;
        const drawX = Math.round(p.x + edgeDx + nudgeDx);
        const drawY = Math.round(p.y + edgeDy + nudgeDy);

        if (img) {
          ctx.save();
          ctx.translate(drawX, drawY);
          ctx.rotate(edgeRotation);
          const fWidth = scale * renderCfg.scaleX;
          const fHeight = scale * renderCfg.scaleY;
          ctx.drawImage(img, -fWidth / 2, -fHeight / 2, fWidth, fHeight);
          ctx.restore();
        } else {
          // Tactical fortification badge fallback
          const emoji = getFortificationIconEmoji(fort.type);
          const shortCode = getFortificationShort(fort.type);

          ctx.beginPath();
          ctx.arc(drawX, drawY, scale * 0.45, 0, Math.PI * 2);
          ctx.fillStyle = "rgba(30, 41, 59, 0.85)";
          ctx.fill();
          ctx.strokeStyle = "#eab308";
          ctx.lineWidth = 1.5;
          ctx.stroke();

          ctx.font = `${Math.max(10, Math.floor(scale * 0.38))}px sans-serif`;
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillText(emoji, drawX, drawY - scale * 0.08);

          ctx.fillStyle = "#facc15";
          ctx.font = `bold ${Math.max(7, Math.floor(scale * 0.22))}px sans-serif`;
          ctx.fillText(shortCode, drawX, drawY + scale * 0.28);
        }
      }
    }

    // 3. Draw Victory Points (VPs)
    if (showVps) {
      for (const vp of vpMap) {
        const p = toPixel(vp.q, vp.r);
        const owner = String(vp.owner || "").toUpperCase();
        const ownerColor =
          owner === "US"
            ? "#3b82f6"
            : owner === "IT"
            ? "#10b981"
            : owner === "GE"
            ? "#ef4444"
            : "#f59e0b";

        // VP Hex Outer Glowing Ring
        drawHex(p.x, p.y, scale * 0.98, ownerColor, "rgba(0, 0, 0, 0.25)", 2.0);

        // VP Faction Marker badge at top-right of hex (matching assault_ai_ui)
        const markerSrc = SIDE_MARKERS[owner];
        const markerImg = markerSrc ? getLoadedImage(markerSrc) : null;
        const markerX = p.x + scale * 0.58;
        const markerY = p.y - scale * 0.62;
        const markerSize = Math.max(14, scale * 0.52);

        if (markerImg) {
          ctx.drawImage(markerImg, markerX - markerSize / 2, markerY - markerSize / 2, markerSize, markerSize);
        } else if (owner) {
          ctx.beginPath();
          ctx.arc(markerX, markerY, markerSize / 2, 0, Math.PI * 2);
          ctx.fillStyle = ownerColor;
          ctx.fill();
          ctx.strokeStyle = "#ffffff";
          ctx.lineWidth = 1;
          ctx.stroke();
          ctx.fillStyle = "#ffffff";
          ctx.font = `bold ${Math.max(6, Math.floor(markerSize * 0.45))}px sans-serif`;
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillText(owner, markerX, markerY);
        }

        // VP Point Value Banner / Star Indicator at center-bottom
        ctx.save();
        ctx.shadowColor = "rgba(0,0,0,0.8)";
        ctx.shadowBlur = 3;
        ctx.fillStyle = "#ffffff";
        ctx.font = `bold ${Math.max(8, Math.floor(scale * 0.30))}px sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(`★ ${vp.value || 2}VP`, p.x, p.y + scale * 0.40);
        ctx.restore();
      }
    }

    // 4a. Draw Origin Hex Marker (Starting position before the move/attack)
    if (
      showVectors &&
      (actionVector.isFire || actionVector.isMove) &&
      actionVector.fromQ !== null &&
      actionVector.fromR !== null &&
      actionVector.toQ !== null &&
      actionVector.toR !== null &&
      Number.isFinite(actionVector.fromQ) &&
      Number.isFinite(actionVector.fromR) &&
      !(actionVector.fromQ === actionVector.toQ && actionVector.fromR === actionVector.toR)
    ) {
      const op = toPixel(actionVector.fromQ, actionVector.fromR);
      const isFire = actionVector.isFire;
      const originStroke = isFire ? "#f59e0b" : "#0284c7";
      const originFill = isFire ? "rgba(245, 158, 11, 0.25)" : "rgba(2, 132, 199, 0.25)";

      // Origin Hex Border & Shading
      drawHex(op.x, op.y, scale * 1.05, originStroke, originFill, 2.5);

      // Origin Marker Pin Circle
      ctx.save();
      ctx.beginPath();
      ctx.arc(op.x, op.y, scale * 0.22, 0, Math.PI * 2);
      ctx.fillStyle = originStroke;
      ctx.shadowColor = originStroke;
      ctx.shadowBlur = 6;
      ctx.fill();

      // Inner white dot
      ctx.beginPath();
      ctx.arc(op.x, op.y, scale * 0.09, 0, Math.PI * 2);
      ctx.fillStyle = "#ffffff";
      ctx.fill();

      // Tactical Badge Pill at top of hex: "📍 START" or "🎯 FIRER"
      const labelText = isFire ? "🎯 FIRER" : "📍 START";
      ctx.font = `bold ${Math.max(8, Math.floor(scale * 0.26))}px sans-serif`;
      const textMetrics = ctx.measureText(labelText);
      const pillW = textMetrics.width + 10;
      const pillH = Math.max(13, scale * 0.32);
      const pillY = op.y - scale * 0.65;

      ctx.fillStyle = "rgba(15, 23, 42, 0.88)";
      ctx.strokeStyle = originStroke;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.roundRect(op.x - pillW / 2, pillY - pillH / 2, pillW, pillH, 3);
      ctx.fill();
      ctx.stroke();

      ctx.fillStyle = "#ffffff";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(labelText, op.x, pillY);
      ctx.restore();
    }

    // 4b. Draw Target / Destination Hex Marker
    if (
      showVectors &&
      (actionVector.isFire || actionVector.isMove) &&
      actionVector.toQ !== null &&
      actionVector.toR !== null &&
      Number.isFinite(actionVector.toQ) &&
      Number.isFinite(actionVector.toR)
    ) {
      const tp = toPixel(actionVector.toQ, actionVector.toR);
      const isFire = actionVector.isFire;
      const targetStroke = isFire ? "#ef4444" : "#22c55e";
      const targetFill = isFire ? "rgba(239, 68, 68, 0.25)" : "rgba(34, 197, 94, 0.22)";

      // Tactical Reticle
      drawHex(tp.x, tp.y, scale * 1.05, targetStroke, targetFill, 2.5);

      ctx.save();
      if (isFire) {
        // Crosshairs for combat target
        ctx.beginPath();
        ctx.strokeStyle = targetStroke;
        ctx.lineWidth = 2.5;
        ctx.shadowColor = "#f87171";
        ctx.shadowBlur = 6;
        ctx.moveTo(tp.x - scale * 0.35, tp.y);
        ctx.lineTo(tp.x + scale * 0.35, tp.y);
        ctx.moveTo(tp.x, tp.y - scale * 0.35);
        ctx.lineTo(tp.x, tp.y + scale * 0.35);
        ctx.stroke();

        ctx.beginPath();
        ctx.arc(tp.x, tp.y, scale * 0.20, 0, Math.PI * 2);
        ctx.stroke();
      } else {
        // Bullseye target concentric circle for movement destination
        ctx.beginPath();
        ctx.strokeStyle = targetStroke;
        ctx.lineWidth = 2;
        ctx.arc(tp.x, tp.y, scale * 0.25, 0, Math.PI * 2);
        ctx.stroke();
      }

      // Tactical Badge Pill at bottom of hex: "🏁 DEST" or "💥 TARGET"
      const labelText = isFire ? "💥 TARGET" : "🏁 DEST";
      ctx.font = `bold ${Math.max(8, Math.floor(scale * 0.26))}px sans-serif`;
      const textMetrics = ctx.measureText(labelText);
      const pillW = textMetrics.width + 10;
      const pillH = Math.max(13, scale * 0.32);
      const pillY = tp.y + scale * 0.65;

      ctx.fillStyle = "rgba(15, 23, 42, 0.88)";
      ctx.strokeStyle = targetStroke;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.roundRect(tp.x - pillW / 2, pillY - pillH / 2, pillW, pillH, 3);
      ctx.fill();
      ctx.stroke();

      ctx.fillStyle = "#ffffff";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(labelText, tp.x, pillY);
      ctx.restore();
    }

    // 5. Draw Action Trajectory Vector (Movement Arrow or Combat Ballistic Line)
    if (
      showVectors &&
      (actionVector.isFire || actionVector.isMove) &&
      actionVector.fromQ !== null &&
      actionVector.fromR !== null &&
      actionVector.toQ !== null &&
      actionVector.toR !== null &&
      Number.isFinite(actionVector.fromQ) &&
      Number.isFinite(actionVector.fromR) &&
      Number.isFinite(actionVector.toQ) &&
      Number.isFinite(actionVector.toR) &&
      !(actionVector.fromQ === actionVector.toQ && actionVector.fromR === actionVector.toR)
    ) {
      const pFrom = toPixel(actionVector.fromQ, actionVector.fromR);
      const pTo = toPixel(actionVector.toQ, actionVector.toR);

      ctx.save();
      const angle = Math.atan2(pTo.y - pFrom.y, pTo.x - pFrom.x);
      const headLen = Math.max(12, scale * 0.35);

      if (actionVector.isFire) {
        // Red laser trajectory for combat
        ctx.beginPath();
        ctx.moveTo(pFrom.x, pFrom.y);
        ctx.lineTo(pTo.x, pTo.y);
        ctx.strokeStyle = "#ef4444";
        ctx.lineWidth = 3.5;
        ctx.shadowColor = "#f87171";
        ctx.shadowBlur = 10;
        ctx.stroke();

        // Arrowhead pointing into target hex
        ctx.beginPath();
        ctx.moveTo(pTo.x, pTo.y);
        ctx.lineTo(pTo.x - headLen * Math.cos(angle - Math.PI / 6), pTo.y - headLen * Math.sin(angle - Math.PI / 6));
        ctx.lineTo(pTo.x - headLen * Math.cos(angle + Math.PI / 6), pTo.y - headLen * Math.sin(angle + Math.PI / 6));
        ctx.closePath();
        ctx.fillStyle = "#ef4444";
        ctx.fill();

        // Combat Impact Explosion Icon
        ctx.fillStyle = "#facc15";
        ctx.font = `${Math.max(14, Math.floor(scale * 0.65))}px sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText("💥", pTo.x, pTo.y);
      } else if (actionVector.isMove) {
        // Solid Glowing Cyan Vector Arrow for movement
        ctx.beginPath();
        ctx.moveTo(pFrom.x, pFrom.y);
        ctx.lineTo(pTo.x, pTo.y);
        ctx.strokeStyle = "#38bdf8";
        ctx.lineWidth = 3.5;
        ctx.shadowColor = "#0284c7";
        ctx.shadowBlur = 8;
        ctx.stroke();

        // Arrowhead
        ctx.beginPath();
        ctx.moveTo(pTo.x, pTo.y);
        ctx.lineTo(pTo.x - headLen * Math.cos(angle - Math.PI / 6), pTo.y - headLen * Math.sin(angle - Math.PI / 6));
        ctx.lineTo(pTo.x - headLen * Math.cos(angle + Math.PI / 6), pTo.y - headLen * Math.sin(angle + Math.PI / 6));
        ctx.closePath();
        ctx.fillStyle = "#38bdf8";
        ctx.fill();

        // Midpoint Distance Badge Pill
        const midX = (pFrom.x + pTo.x) / 2;
        const midY = (pFrom.y + pTo.y) / 2;
        const distText = `➔ ${actionVector.hexDistance} hex${actionVector.hexDistance > 1 ? "es" : ""}`;
        ctx.font = `bold ${Math.max(8, Math.floor(scale * 0.24))}px sans-serif`;
        const metrics = ctx.measureText(distText);
        const mW = metrics.width + 10;
        const mH = Math.max(12, scale * 0.28);

        ctx.fillStyle = "rgba(15, 23, 42, 0.90)";
        ctx.strokeStyle = "#38bdf8";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.roundRect(midX - mW / 2, midY - mH / 2, mW, mH, 3);
        ctx.fill();
        ctx.stroke();

        ctx.fillStyle = "#e0f2fe";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(distText, midX, midY);
      }
      ctx.restore();
    }

    // 6. Draw Tactical Unit Counters (Authentic WWII Counters)
    for (const u of unitPoints) {
      const p = toPixel(u.q, u.r);
      const isHovered = hoveredUnitId === u.unit_id || (hoveredHex && hoveredHex.q === u.q && hoveredHex.r === u.r);
      const isSelected = selectedUnitId === u.unit_id;
      const isActing = String(currentStep.unit_id || actionVector.actorId) === u.unit_id;
      const isEliminated = !u.alive || u.hp <= 0;

      const counterSize = Math.max(18, scale * (isActing || isHovered || isSelected ? 1.15 : 1.05));
      const counterHalf = counterSize / 2;

      // Active Unit Beacon Aura
      if (isActing) {
        ctx.save();
        ctx.beginPath();
        ctx.arc(p.x, p.y, counterSize * 0.75, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(250, 204, 21, 0.25)";
        ctx.fill();
        ctx.strokeStyle = "#facc15";
        ctx.lineWidth = 2.5;
        ctx.shadowColor = "#facc15";
        ctx.shadowBlur = 8;
        ctx.stroke();

        // Arrow indicator pointing down to active unit
        ctx.fillStyle = "#facc15";
        ctx.beginPath();
        ctx.moveTo(p.x, p.y - counterSize * 0.72);
        ctx.lineTo(p.x - 5, p.y - counterSize * 0.72 - 8);
        ctx.lineTo(p.x + 5, p.y - counterSize * 0.72 - 8);
        ctx.closePath();
        ctx.fill();
        ctx.restore();
      }

      // Unit selection / hover ring
      if (isSelected || isHovered) {
        ctx.beginPath();
        ctx.arc(p.x, p.y, counterSize * 0.70, 0, Math.PI * 2);
        ctx.strokeStyle = isSelected ? "#38bdf8" : "#ffffff";
        ctx.lineWidth = 2;
        ctx.stroke();
      }

      // Unit Counter Image (WWII wargame counter token)
      const uKey = u.unit_key || DEFAULT_UNIT_KEYS[u.unit_id] || u.unit_id;
      const counterArt = getUnitCounterArt(uKey, u.hp);
      const counterImg = counterArt ? getLoadedImage(counterArt) : null;

      if (counterImg) {
        ctx.save();
        if (isEliminated) {
          ctx.globalAlpha = 0.35;
        }
        ctx.drawImage(counterImg, p.x - counterHalf, p.y - counterHalf, counterSize, counterSize);
        ctx.restore();

        if (isEliminated) {
          ctx.fillStyle = "#ef4444";
          ctx.font = `bold ${Math.max(12, Math.floor(counterSize * 0.55))}px sans-serif`;
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillText("☠️", p.x, p.y);
        }
      } else {
        // Fallback token circle
        ctx.beginPath();
        ctx.arc(p.x, p.y, counterHalf * 0.85, 0, Math.PI * 2);
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
        ctx.lineWidth = isActing ? 2.5 : 1.5;
        ctx.stroke();

        ctx.fillStyle = isEliminated ? "#94a3b8" : "#ffffff";
        ctx.font = `bold ${Math.max(7, Math.floor(scale * 0.28))}px sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(isEliminated ? "☠️" : "🪖", p.x, p.y - 2);
      }

      // Unit ID Pill Underneath (matching assault_ai_ui addUnitLabel)
      const sideBgColor =
        u.side === "US"
          ? "rgba(0, 51, 102, 0.90)"
          : u.side === "IT"
          ? "rgba(46, 92, 46, 0.90)"
          : u.side === "GE"
          ? "rgba(102, 0, 0, 0.90)"
          : "rgba(15, 23, 42, 0.90)";

      const nameW = Math.max(28, scale * 0.72);
      const nameH = Math.max(12, scale * 0.26);
      const pillY = p.y + counterHalf * 0.55;

      ctx.save();
      ctx.fillStyle = sideBgColor;
      ctx.beginPath();
      ctx.roundRect(p.x - nameW / 2, pillY, nameW, nameH, 3);
      ctx.fill();
      ctx.strokeStyle = isActing ? "#facc15" : "rgba(255, 255, 255, 0.6)";
      ctx.lineWidth = 1;
      ctx.stroke();

      ctx.fillStyle = isActing ? "#facc15" : "#ffffff";
      ctx.font = `bold ${Math.max(7, Math.floor(scale * 0.22))}px sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(u.unit_id, p.x, pillY + nameH / 2);
      ctx.restore();

      // HP Gauge Bar
      if (showHpBars && !isEliminated) {
        const maxHp = 4.0;
        const hpFrac = Math.max(0, Math.min(1, u.hp / maxHp));
        const barW = Math.max(22, scale * 0.7);
        const barH = 3.5;
        const barX = p.x - barW / 2;
        const barY = p.y - counterHalf - 5;

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

      // Suppressed / Pinned Badge
      if (u.suppressed && !isEliminated) {
        ctx.save();
        ctx.fillStyle = "#ea580c";
        ctx.beginPath();
        ctx.roundRect(p.x + counterHalf * 0.3, p.y - counterHalf - 4, 22, 11, 2);
        ctx.fill();
        ctx.fillStyle = "#ffffff";
        ctx.font = `bold 7px sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText("PIN", p.x + counterHalf * 0.3 + 11, p.y - counterHalf + 1.5);
        ctx.restore();
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
    showForts,
    showTerrain,
    zoomLevel,
    panOffset,
    fortifications,
    terrainMap,
    mapPieces,
    scenarioShape,
    imgLoadVersion,
    mapHeight,
    getLoadedImage,
  ]);

  // Canvas Mouse Drag & Picking Handlers
  const handleCanvasMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (e.button === 0 || e.button === 1) {
      dragStartRef.current = {
        clientX: e.clientX,
        clientY: e.clientY,
        startPanX: panOffset.x,
        startPanY: panOffset.y,
        hasMoved: false,
      };
      setIsDragging(true);
    }
  };

  const handleCanvasMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const c = canvasRef.current;
    if (!c) return;

    // Handle Pan dragging
    if (isDragging) {
      const dx = e.clientX - dragStartRef.current.clientX;
      const dy = e.clientY - dragStartRef.current.clientY;
      if (!dragStartRef.current.hasMoved && Math.hypot(dx, dy) > 3) {
        dragStartRef.current.hasMoved = true;
      }
      if (dragStartRef.current.hasMoved) {
        setPanOffset({
          x: dragStartRef.current.startPanX + dx,
          y: dragStartRef.current.startPanY + dy,
        });
      }
    }

    const rect = c.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    setMousePos({ x, y });

    const { raws, minX, minY, spanX, spanY } = boardGeometry;
    const pad = 16;
    const baseScaleX = (rect.width - pad * 2) / spanX;
    const baseScaleY = (rect.height - pad * 2) / spanY;
    const scale = Math.max(6, Math.min(baseScaleX, baseScaleY) * zoomLevel);

    const boardPixelW = spanX * scale;
    const boardPixelH = spanY * scale;
    const offsetX = (rect.width - boardPixelW) / 2 + (Math.sqrt(3) / 2) * scale + panOffset.x;
    const offsetY = (rect.height - boardPixelH) / 2 + 1.0 * scale + panOffset.y;

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
      if (!hoveredHex || hoveredHex.q !== closestCell.q || hoveredHex.r !== closestCell.r) {
        setHoveredHex({ q: closestCell.q, r: closestCell.r });
      }
    } else {
      if (hoveredHex) {
        setHoveredHex(null);
      }
    }
  };

  const handleCanvasMouseUp = () => {
    setIsDragging(false);
  };

  const handleCanvasMouseLeave = () => {
    setIsDragging(false);
    setHoveredHex(null);
    setHoveredUnitId("");
  };

  const handleCanvasClick = () => {
    if (dragStartRef.current.hasMoved) {
      // User was panning, ignore click selection
      return;
    }
    if (hoveredHex) {
      const unitOnHex = units.find((u) => u.q === hoveredHex.q && u.r === hoveredHex.r);
      if (unitOnHex) {
        setSelectedUnitId(unitOnHex.unit_id);
        setActiveTab("units");
      }
    }
  };

  if (!selectedEvalSourcePath) {
    return <div className="muted" style={{ padding: 20 }}>Select an evaluation to view Match Replay.</div>;
  }

  const suppressedMap = (currentStep.unit_suppressed_map || {}) as Record<string, unknown>;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {/* 0. Dynamic Scenario & Tactical Forces Briefing Banner */}
      <div
        style={{
          background: "linear-gradient(180deg, #1e293b, #0f172a)",
          border: "1px solid #334155",
          borderRadius: 8,
          padding: "10px 14px",
          boxShadow: "0 4px 12px rgba(0,0,0,0.3)",
          display: "flex",
          flexDirection: "column",
          gap: 10,
        }}
      >
        {/* Top Summary Row */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ fontSize: 18 }}>🗺️</span>
              <span style={{ fontSize: 15, fontWeight: 800, color: "#f8fafc", letterSpacing: 0.3 }}>
                {scenarioBriefing.title}
              </span>
            </div>
            <code
              style={{
                fontSize: 11,
                background: "#0f172a",
                border: "1px solid #334155",
                padding: "2px 6px",
                borderRadius: 4,
                color: "#38bdf8",
              }}
            >
              {scenarioBriefing.idLabel}
            </code>
            <span style={{ fontSize: 12, color: "#94a3b8", fontWeight: 500 }}>
              — {scenarioBriefing.subtitle}
            </span>
            {currentEpisodeMeta?.matchup_label && (
              <span
                style={{
                  fontSize: 11,
                  color: "#c084fc",
                  background: "rgba(168, 85, 247, 0.15)",
                  padding: "2px 8px",
                  borderRadius: 4,
                  border: "1px solid rgba(168, 85, 247, 0.35)",
                  fontWeight: 600,
                }}
              >
                ⚔️ {currentEpisodeMeta.matchup_label}
              </span>
            )}
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 11, color: "#94a3b8", background: "rgba(15, 23, 42, 0.6)", padding: "2px 8px", borderRadius: 4, border: "1px solid #334155" }}>
              ⏱️ {scenarioBriefing.maxTurns} Max Turns
            </span>
            <span style={{ fontSize: 11, color: "#94a3b8", background: "rgba(15, 23, 42, 0.6)", padding: "2px 8px", borderRadius: 4, border: "1px solid #334155" }}>
              📐 {scenarioBriefing.shapeText}
            </span>
            <span style={{ fontSize: 11, color: "#facc15", background: "rgba(250, 204, 21, 0.12)", padding: "2px 8px", borderRadius: 4, border: "1px solid rgba(250, 204, 21, 0.3)" }}>
              ⭐ {scenarioBriefing.totalVps} VPs
            </span>
            <button
              onClick={() => setShowBriefing(!showBriefing)}
              style={{
                padding: "3px 8px",
                fontSize: 11,
                background: "#1e293b",
                border: "1px solid #475569",
                borderRadius: 4,
                color: "#e2e8f0",
                cursor: "pointer",
                fontWeight: 600,
              }}
            >
              {showBriefing ? "▲ Minimize" : "▼ Faction Details"}
            </button>
          </div>
        </div>

        {/* Collapsible Factions & Tactical Mission Cards */}
        {showBriefing && (
          <div style={{ display: "flex", flexDirection: "column", gap: 8, paddingTop: 4, borderTop: "1px solid #334155" }}>
            {scenarioBriefing.desc && (
              <div style={{ fontSize: 12, color: "#94a3b8", lineHeight: 1.4 }}>
                {scenarioBriefing.desc}
              </div>
            )}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(340px, 1fr))", gap: 10 }}>
              {factions.map((f) => (
                <div
                  key={f.side}
                  style={{
                    background: f.bgGrad,
                    border: `1px solid ${f.borderColor}`,
                    borderRadius: 6,
                    padding: "8px 12px",
                    display: "flex",
                    flexDirection: "column",
                    gap: 5,
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <span style={{ fontSize: 16 }}>{f.flag}</span>
                      <b style={{ color: "#f8fafc", fontSize: 13 }}>{f.name}</b>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <span
                        style={{
                          fontSize: 10,
                          fontWeight: 800,
                          padding: "1px 6px",
                          borderRadius: 4,
                          background: `${f.roleColor}25`,
                          color: f.roleColor,
                          border: `1px solid ${f.roleColor}60`,
                        }}
                      >
                        {f.roleBadge}
                      </span>
                      <span style={{ fontSize: 11, color: "#cbd5e1" }}>
                        <b>{f.alive}</b>/{f.total} active
                        {f.reinforcementsCount > 0 && (
                          <span style={{ fontSize: 10, color: "#38bdf8", marginLeft: 4 }}>
                            (+{f.reinforcementsCount} scheduled)
                          </span>
                        )}
                      </span>
                    </div>
                  </div>

                  {/* Dedicated Prominent Side Controller Badge */}
                  <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, marginTop: 1, marginBottom: 1 }}>
                    <span style={{ color: "#94a3b8", fontWeight: 600 }}>🎮 Controller:</span>
                    <span
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 5,
                        fontSize: 11,
                        fontWeight: 700,
                        padding: "2px 8px",
                        borderRadius: 4,
                        background: f.controller.bg,
                        color: f.controller.color,
                        border: `1px solid ${f.controller.border}`,
                        boxShadow: "0 1px 3px rgba(0,0,0,0.25)",
                      }}
                    >
                      <span>{f.controller.icon}</span>
                      <span>{f.controller.label}</span>
                    </span>
                  </div>

                  <div style={{ fontSize: 11, color: "#e2e8f0" }}>
                    <span style={{ color: "#94a3b8" }}>🎯 Objective: </span>
                    {f.mission}
                  </div>

                  <div style={{ fontSize: 11, color: "#cbd5e1" }}>
                    <span style={{ color: "#94a3b8" }}>⚔️ Initial Force: </span>
                    <span style={{ color: "#e2e8f0" }}>{f.keyBreakdown} ({f.initialTotal} units)</span>
                  </div>

                  {f.reinforcementsInfo && (
                    <div style={{ fontSize: 11, color: "#38bdf8" }}>
                      <span style={{ color: "#0284c7" }}>🪂 Scheduled Reinforcements: </span>
                      <span>{f.reinforcementsInfo}</span>
                    </div>
                  )}

                  {f.reinforcementsCount > 0 && (
                    <div style={{ fontSize: 11, color: "#94a3b8" }}>
                      <span>📊 Total Strength: </span>
                      <b style={{ color: "#f8fafc" }}>{f.totalForces} units</b> ({f.initialTotal} initial + {f.reinforcementsCount} reinforcements)
                    </div>
                  )}

                  {f.fortifications && (
                    <div style={{ fontSize: 11, color: "#facc15" }}>
                      <span style={{ color: "#ca8a04" }}>🛡️ Fortifications: </span>
                      {f.fortifications}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

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
        {/* Scrubber Range Slider with Prominent Turn Indicator */}
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {/* Step Pill */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 4,
              background: "rgba(14, 165, 233, 0.15)",
              border: "1px solid #0284c7",
              padding: "4px 10px",
              borderRadius: 6,
              fontSize: 12,
              fontWeight: 700,
              color: "#38bdf8",
              whiteSpace: "nowrap",
            }}
          >
            <span>Step {clamped}</span>
            <span style={{ color: "#64748b" }}>/</span>
            <span style={{ color: "#94a3b8" }}>{Math.max(0, steps.length - 1)}</span>
          </div>

          <input
            type="range"
            min={0}
            max={Math.max(0, steps.length - 1)}
            value={clamped}
            onChange={(e) => onStepIndexChange(Number(e.target.value || 0))}
            style={{ flex: 1, accentColor: "#38bdf8", cursor: "pointer", height: 6 }}
          />

          {/* Prominent High-Contrast Turn Badge */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              background: "linear-gradient(135deg, rgba(147, 51, 234, 0.35), rgba(99, 102, 241, 0.45))",
              border: "2px solid #a855f7",
              boxShadow: "0 0 14px rgba(168, 85, 247, 0.45)",
              padding: "4px 12px",
              borderRadius: 6,
              fontSize: 13,
              fontWeight: 800,
              color: "#f3e8ff",
              whiteSpace: "nowrap",
            }}
          >
            <span>⏱️ TURN</span>
            <span
              style={{
                color: "#ffffff",
                fontSize: 16,
                fontWeight: 900,
                background: "#7e22ce",
                padding: "1px 8px",
                borderRadius: 4,
                boxShadow: "0 2px 6px rgba(0,0,0,0.5)",
              }}
            >
              {currentDetails.gameTurn !== null ? currentDetails.gameTurn : "-"}
            </span>
            <span style={{ color: "#c084fc", fontSize: 11, fontWeight: 600 }}>/ {maxTurns}</span>
          </div>
        </div>

        {/* Controls Bar */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
          {/* VCR Playback Buttons */}
          <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <button
              onClick={() => onStepIndexChange(0)}
              title="First step (t=0)"
              style={{ padding: "4px 8px", fontSize: 12, background: "#1e293b", border: "1px solid #475569", borderRadius: 4, cursor: "pointer" }}
            >
              ⏮ Start
            </button>
            <button
              onClick={() => onStepIndexChange((prev) => Math.max(0, prev - 1))}
              title="Previous step"
              style={{ padding: "4px 8px", fontSize: 12, background: "#1e293b", border: "1px solid #475569", borderRadius: 4, cursor: "pointer" }}
            >
              ◀ Prev
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
              {isPlaying ? "⏸ Pause" : "▶ Play"}
            </button>
            <button
              onClick={() => onStepIndexChange((prev) => Math.min(steps.length - 1, prev + 1))}
              title="Next step"
              style={{ padding: "4px 8px", fontSize: 12, background: "#1e293b", border: "1px solid #475569", borderRadius: 4, cursor: "pointer" }}
            >
              Next ▶
            </button>
            <button
              onClick={() => onStepIndexChange(Math.max(0, steps.length - 1))}
              title="Last step"
              style={{ padding: "4px 8px", fontSize: 12, background: "#1e293b", border: "1px solid #475569", borderRadius: 4, cursor: "pointer" }}
            >
              End ⏭
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
            <span style={{ fontSize: 11, color: "#94a3b8" }}>Jump to:</span>
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
                    P{i} {d.gameTurn !== null ? `(T${d.gameTurn}) ` : ""}| {d.flag} {d.toPlay} ➔ {d.actionId}
                  </option>
                );
              })}
            </select>
          </div>

          {/* Dynamic VP Tally Badges for active sides */}
          <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
            {/* US Badge */}
            {(vpTally.US > 0 || factions.some((f) => f.side === "US")) && (
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
            )}
            {/* GE Badge */}
            {(vpTally.GE > 0 || factions.some((f) => f.side === "GE")) && (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 5,
                  background: "rgba(220, 38, 38, 0.15)",
                  border: "1px solid #dc2626",
                  padding: "2px 8px",
                  borderRadius: 4,
                  fontSize: 11,
                }}
              >
                <span>🇩🇪 GE:</span>
                <b style={{ color: "#f87171" }}>{vpTally.GE || 0} VPs</b>
              </div>
            )}
            {/* IT Badge */}
            {(vpTally.IT > 0 || factions.some((f) => f.side === "IT")) && (
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
            )}
            {/* Neutral Badge if any */}
            {(vpTally.NEUTRAL || 0) > 0 && (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 5,
                  background: "rgba(148, 163, 184, 0.15)",
                  border: "1px solid #64748b",
                  padding: "2px 8px",
                  borderRadius: 4,
                  fontSize: 11,
                }}
              >
                <span>⚪ Neutral:</span>
                <b style={{ color: "#cbd5e1" }}>{vpTally.NEUTRAL} VPs</b>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 2. Main Tactical Arena (Left Map snug-fit, Right Inspector expansive or Full Width Theater Mode) */}
      <div
        style={
          theaterMode
            ? { display: "flex", flexDirection: "column", gap: 14 }
            : {
                display: "grid",
                gridTemplateColumns: `minmax(320px, ${optimalMapWidth}px) minmax(460px, 1fr)`,
                gap: 16,
                alignItems: "start",
              }
        }
      >
        {/* LEFT COLUMN: Tactical Map & Event Feed (snug fit to map width) */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 10,
            maxWidth: theaterMode ? "100%" : `${optimalMapWidth}px`,
            width: "100%",
          }}
        >
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
              <span style={{ fontSize: 11, fontWeight: 700, color: "#38bdf8" }}>Map Layers:</span>
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
                🌐 Coordinates
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
                🎯 Action Vectors
              </button>
              <button
                onClick={() => setShowForts(!showForts)}
                title="Show / Hide scenario bunkers and fortifications"
                style={{
                  fontSize: 10,
                  padding: "2px 6px",
                  borderRadius: 3,
                  background: showForts ? "#854d0e" : "#0f172a",
                  color: showForts ? "#facc15" : "#64748b",
                  border: "1px solid #334155",
                  cursor: "pointer",
                }}
              >
                🛡️ Fortifications ({fortifications.length})
              </button>
              <button
                onClick={() => setShowTerrain(!showTerrain)}
                title="Show / Hide scenario terrain types"
                style={{
                  fontSize: 10,
                  padding: "2px 6px",
                  borderRadius: 3,
                  background: showTerrain ? "#14532d" : "#0f172a",
                  color: showTerrain ? "#4ade80" : "#64748b",
                  border: "1px solid #334155",
                  cursor: "pointer",
                }}
              >
                🏞️ Terrain
              </button>
              <button
                onClick={() => setShowThreatHead(!showThreatHead)}
                title="Show / Hide Neural Auxiliary Threat Map predictions on the hex board"
                style={{
                  fontSize: 10,
                  padding: "2px 6px",
                  borderRadius: 3,
                  background: showThreatHead ? "#991b1b" : "#0f172a",
                  color: showThreatHead ? "#fca5a5" : "#64748b",
                  border: `1px solid ${showThreatHead ? "#ef4444" : "#334155"}`,
                  cursor: "pointer",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 4,
                  fontWeight: showThreatHead ? 700 : 500,
                }}
              >
                <span>🎯 Threat Head</span>
                {isLoadingTacticalHeads && (
                  <span style={{ fontSize: 9, opacity: 0.8 }}>...</span>
                )}
              </button>
              <button
                onClick={() => setShowIpbTopography(!showIpbTopography)}
                title="Toggle Turn-0 IPB Topography Overlay (Defilade Corridors, Killzones, Base of Fire, Chokepoints)"
                style={{
                  fontSize: 10,
                  padding: "2px 8px",
                  borderRadius: 3,
                  background: showIpbTopography ? "#047857" : "rgba(16, 185, 129, 0.15)",
                  color: showIpbTopography ? "#ecfdf5" : "#34d399",
                  border: `1px solid ${showIpbTopography ? "#10b981" : "#059669"}`,
                  cursor: "pointer",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 4,
                  fontWeight: showIpbTopography ? 700 : 500,
                }}
              >
                <span>🛡️ IPB Topography</span>
                {isLoadingTopography && (
                  <span style={{ fontSize: 9, opacity: 0.8 }}>...</span>
                )}
              </button>
              <button
                onClick={() => handleOpenSitrep()}
                title="Open Autonomous Forensic Situation Report (SitRep) and Causal Profiler"
                style={{
                  fontSize: 10,
                  padding: "2px 8px",
                  borderRadius: 3,
                  background: isSitrepOpen ? "#0369a1" : "rgba(14, 165, 233, 0.15)",
                  color: isSitrepOpen ? "#f0f9ff" : "#38bdf8",
                  border: `1px solid ${isSitrepOpen ? "#38bdf8" : "#0284c7"}`,
                  cursor: "pointer",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 4,
                  fontWeight: 700,
                }}
              >
                <span>🎖️ Forensic SitRep</span>
                {isSitrepLoading && (
                  <span style={{ fontSize: 9, opacity: 0.8 }}>...</span>
                )}
              </button>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 2 }}>
                <span style={{ fontSize: 10, color: "#94a3b8" }}>Height:</span>
                {[560, 680, 800, 920, 1050].map((h) => (
                  <button
                    key={h}
                    onClick={() => {
                      setMapHeight(h);
                      if (theaterMode) setTheaterMode(false);
                    }}
                    style={{
                      fontSize: 10,
                      padding: "2px 6px",
                      borderRadius: 3,
                      background: !theaterMode && mapHeight === h ? "#0284c7" : "#0f172a",
                      color: !theaterMode && mapHeight === h ? "#ffffff" : "#94a3b8",
                      border: "1px solid #334155",
                      cursor: "pointer",
                      fontWeight: !theaterMode && mapHeight === h ? 700 : 400,
                    }}
                  >
                    {h}px
                  </button>
                ))}
              </div>
              <button
                onClick={() => setTheaterMode(!theaterMode)}
                title={theaterMode ? "Switch to split inspector view" : "Maximize map to full screen viewport"}
                style={{
                  fontSize: 10,
                  fontWeight: 700,
                  padding: "2px 10px",
                  borderRadius: 3,
                  background: theaterMode ? "#0284c7" : "#1e293b",
                  color: theaterMode ? "#ffffff" : "#38bdf8",
                  border: `1px solid ${theaterMode ? "#38bdf8" : "#0284c7"}`,
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  gap: 4,
                  boxShadow: theaterMode ? "0 0 10px rgba(2, 132, 199, 0.4)" : "none",
                }}
              >
                <span>{theaterMode ? "🗗" : "🖥️"}</span>
                <span>{theaterMode ? "Split View" : "Full Viewport"}</span>
              </button>
              {/* Zoom & Pan Toolbar Controls */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 3,
                  background: "#0f172a",
                  padding: "2px 6px",
                  borderRadius: 4,
                  border: "1px solid #334155",
                }}
              >
                <button
                  onClick={() => {
                    setZoomLevel((z) => Math.max(0.5, Number((z / 1.2).toFixed(2))));
                  }}
                  title="Alejar mapa (-)"
                  style={{
                    padding: "2px 7px",
                    fontSize: 12,
                    fontWeight: "bold",
                    background: "#1e293b",
                    border: "1px solid #475569",
                    color: "#f8fafc",
                    borderRadius: 3,
                    cursor: "pointer",
                  }}
                >
                  −
                </button>
                <span
                  style={{
                    fontSize: 10,
                    fontWeight: 700,
                    color: zoomLevel !== 1.0 || panOffset.x !== 0 || panOffset.y !== 0 ? "#38bdf8" : "#94a3b8",
                    minWidth: 38,
                    textAlign: "center",
                  }}
                  title="Nivel de zoom actual"
                >
                  {(zoomLevel * 100).toFixed(0)}%
                </span>
                <button
                  onClick={() => {
                    setZoomLevel((z) => Math.min(3.5, Number((z * 1.2).toFixed(2))));
                  }}
                  title="Acercar mapa (+)"
                  style={{
                    padding: "2px 7px",
                    fontSize: 12,
                    fontWeight: "bold",
                    background: "#1e293b",
                    border: "1px solid #475569",
                    color: "#f8fafc",
                    borderRadius: 3,
                    cursor: "pointer",
                  }}
                >
                  +
                </button>
                <button
                  onClick={() => {
                    setZoomLevel(1.0);
                    setPanOffset({ x: 0, y: 0 });
                  }}
                  title="Restablecer vista a 100% y centrar"
                  style={{
                    padding: "2px 6px",
                    fontSize: 10,
                    fontWeight: 600,
                    background: zoomLevel !== 1.0 || panOffset.x !== 0 || panOffset.y !== 0 ? "#0369a1" : "#1e293b",
                    border: `1px solid ${zoomLevel !== 1.0 || panOffset.x !== 0 || panOffset.y !== 0 ? "#38bdf8" : "#475569"}`,
                    color: "#ffffff",
                    borderRadius: 3,
                    cursor: "pointer",
                    marginLeft: 2,
                  }}
                >
                  ↺ 100%
                </button>
              </div>

              {/* Navigation Hint */}
              <span
                style={{
                  fontSize: 10,
                  color: "#64748b",
                  display: "flex",
                  alignItems: "center",
                  gap: 3,
                }}
                title="Mouse wheel to zoom anchored to cursor, click and drag to pan the map."
              >
                <span>🖱️</span> Wheel: Zoom • Drag: Pan
              </span>
            </div>
          </div>

          {/* Tactical Map Canvas with Relative Hover HUD and Permanent Turn Badge */}
          <div
            style={{
              position: "relative",
              width: "100%",
              maxWidth: theaterMode ? "100%" : `${optimalMapWidth}px`,
            }}
          >
            {explainHeatmapLayer && (
              <div
                style={{
                  position: "absolute",
                  top: 10,
                  right: 10,
                  zIndex: 20,
                  background: "rgba(15, 23, 42, 0.9)",
                  border: "1px solid #38bdf8",
                  borderRadius: 4,
                  padding: "4px 10px",
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  fontSize: 11,
                  color: "#38bdf8",
                  fontWeight: 600,
                }}
              >
                <span>Heatmap: {explainHeatmapLayer.toUpperCase()}</span>
                <button
                  onClick={() => {
                    setExplainHeatmapLayer(null);
                    setExplainHeatmapHexes([]);
                  }}
                  style={{
                    background: "transparent",
                    border: "none",
                    color: "#ef4444",
                    cursor: "pointer",
                    fontWeight: 800,
                    fontSize: 12,
                    padding: 0,
                  }}
                  title="Clear attribution heatmap"
                >
                  ✕
                </button>
              </div>
            )}

            {/* Top-Left Floating Tactical HUD: Turn, Step, and Turn to Play */}
            <div
              style={{
                position: "absolute",
                top: 10,
                left: 10,
                background: "rgba(15, 23, 42, 0.92)",
                backdropFilter: "blur(6px)",
                border: "1px solid #7c3aed",
                boxShadow: "0 4px 14px rgba(0, 0, 0, 0.6), 0 0 10px rgba(124, 58, 237, 0.35)",
                borderRadius: 6,
                padding: "5px 12px",
                display: "flex",
                alignItems: "center",
                gap: 10,
                fontSize: 12,
                color: "#f8fafc",
                pointerEvents: "none",
                zIndex: 10,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ color: "#e9d5ff", fontSize: 11, fontWeight: 700 }}>TURN</span>
                <span
                  style={{
                    color: "#ffffff",
                    fontSize: 14,
                    fontWeight: 900,
                    background: "#7e22ce",
                    padding: "1px 7px",
                    borderRadius: 3,
                  }}
                >
                  {currentDetails.gameTurn !== null ? currentDetails.gameTurn : "-"}
                </span>
                <span style={{ color: "#94a3b8", fontSize: 10 }}>/ {maxTurns}</span>
              </div>
              <div style={{ height: 14, width: 1, background: "#475569" }} />
              <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                <span style={{ color: "#38bdf8", fontWeight: 700 }}>Step {clamped}</span>
              </div>
              <div style={{ height: 14, width: 1, background: "#475569" }} />
              <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                <span>{currentDetails.flag}</span>
                <span style={{ fontWeight: 800, color: currentDetails.toPlay === "US" ? "#60a5fa" : "#34d399" }}>
                  {currentDetails.toPlay}
                </span>
                <span style={{ color: "#94a3b8", fontSize: 10 }}>to play</span>
                {(() => {
                  const activeCtrl = getControllerBadgeInfo(controllerMap[currentDetails.toPlay] || "");
                  return (
                    <span
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 3,
                        fontSize: 9,
                        fontWeight: 700,
                        padding: "1px 6px",
                        borderRadius: 3,
                        background: activeCtrl.bg,
                        color: activeCtrl.color,
                        border: `1px solid ${activeCtrl.border}`,
                        marginLeft: 4,
                      }}
                      title={`Side Controller: ${activeCtrl.label}`}
                    >
                      <span>{activeCtrl.icon}</span>
                      <span>{activeCtrl.label}</span>
                    </span>
                  );
                })()}
              </div>
            </div>

            <canvas
              ref={canvasRef}
              onMouseDown={handleCanvasMouseDown}
              onMouseMove={handleCanvasMouseMove}
              onMouseUp={handleCanvasMouseUp}
              onMouseLeave={handleCanvasMouseLeave}
              onClick={handleCanvasClick}
              style={{
                width: "100%",
                maxWidth: theaterMode ? "100%" : `${optimalMapWidth}px`,
                height: theaterMode ? "calc(100vh - 200px)" : `${mapHeight}px`,
                minHeight: theaterMode ? 760 : undefined,
                border: "1px solid #334155",
                borderRadius: 8,
                display: "block",
                cursor: isDragging ? "grabbing" : zoomLevel > 1.05 || panOffset.x !== 0 || panOffset.y !== 0 ? "grab" : hoveredHex ? "pointer" : "default",
                boxShadow: "inset 0 0 20px rgba(0,0,0,0.6)",
              }}
            />

            {/* Hover Tooltip Overlay */}
            {hoveredHex && (
              <div
                style={{
                  position: "absolute",
                  left: mousePos.x > 460 ? mousePos.x - 175 : mousePos.x + 14,
                  top: Math.max(10, mousePos.y - 40),
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
                  Hex Cell ({hoveredHex.q}, {hoveredHex.r})
                </div>
                {terrainMap.get(`${hoveredHex.q},${hoveredHex.r}`) && (
                  <div style={{ color: "#94a3b8", fontSize: 10, marginBottom: 2 }}>
                    🏞️ {getTerrainLabel(terrainMap.get(`${hoveredHex.q},${hoveredHex.r}`) || "")}
                  </div>
                )}
                {fortifications.filter((f) => f.q === hoveredHex.q && f.r === hoveredHex.r).map((f, i) => (
                  <div key={i} style={{ color: "#facc15", fontSize: 10, fontWeight: 600, marginBottom: 2 }}>
                    {getFortificationIconEmoji(f.type)} {getFortificationLabel(f.type)}
                  </div>
                ))}
                {vpMap.find((v) => v.q === hoveredHex.q && v.r === hoveredHex.r) && (
                  <div style={{ color: "#facc15", fontSize: 10, fontWeight: 600 }}>
                    ★ Victory Point ({vpMap.find((v) => v.q === hoveredHex.q && v.r === hoveredHex.r)?.owner})
                  </div>
                )}
                {showIpbTopography && topographyMap.has(`${hoveredHex.q},${hoveredHex.r}`) && (
                  <div style={{ marginTop: 4, paddingTop: 3, borderTop: "1px solid #334155", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ color: "#34d399", fontWeight: 700, fontSize: 10 }}>🛡️ IPB Sector:</span>
                    <span style={{ color: "#ecfdf5", fontWeight: 800, fontSize: 10 }}>
                      {topographyMap.get(`${hoveredHex.q},${hoveredHex.r}`)?.classification.replace(/_/g, " ")}
                    </span>
                  </div>
                )}
                {showThreatHead && threatHeadHexMap.has(`${hoveredHex.q},${hoveredHex.r}`) && (
                  <div style={{ marginTop: 4, paddingTop: 3, borderTop: "1px solid #334155", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ color: "#f87171", fontWeight: 700, fontSize: 10 }}>🎯 Threat Head:</span>
                    <span
                      style={{
                        color: (threatHeadHexMap.get(`${hoveredHex.q},${hoveredHex.r}`) || 0) >= 0.5 ? "#f87171" : "#facc15",
                        fontWeight: 800,
                        fontSize: 10,
                      }}
                    >
                      {Math.round((threatHeadHexMap.get(`${hoveredHex.q},${hoveredHex.r}`) || 0) * 100)}%
                      {(threatHeadHexMap.get(`${hoveredHex.q},${hoveredHex.r}`) || 0) >= 0.70 ? " [LETHAL]" : (threatHeadHexMap.get(`${hoveredHex.q},${hoveredHex.r}`) || 0) >= 0.40 ? " [HIGH]" : ""}
                    </span>
                  </div>
                )}
                {units.filter((u) => u.q === hoveredHex.q && u.r === hoveredHex.r).map((u) => (
                  <div key={u.unit_id} style={{ marginTop: 2, display: "flex", justifyContent: "space-between", gap: 8 }}>
                    <span style={{ color: u.side === "US" ? "#60a5fa" : "#34d399", fontWeight: 700 }}>
                      {u.unit_id} ({u.side})
                    </span>
                    <span style={{ color: u.alive ? "#22c55e" : "#ef4444" }}>
                      {u.alive ? `${u.hp.toFixed(1)} HP` : "Eliminated"}
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
                <div style={{ fontSize: 11, textTransform: "uppercase", color: "#cbd5e1", fontWeight: 700, display: "flex", alignItems: "center", gap: 6 }}>
                  <span style={{ background: "#7e22ce", color: "#ffffff", padding: "1px 6px", borderRadius: 3, fontWeight: 900, fontSize: 10 }}>
                    {currentDetails.gameTurn !== null ? `TURN ${currentDetails.gameTurn}` : `STEP ${clamped}`}
                  </span>
                  <span style={{ color: "#38bdf8" }}>STEP {clamped}</span>
                  <span style={{ color: "#64748b" }}>•</span>
                  <span>{actionVector.isFire ? "FIRE / ATTACK" : actionVector.isMove ? "MOVEMENT" : "ACTION"}</span>
                  {currentDetails.macroPosture && (
                    <>
                      <span style={{ color: "#64748b" }}>•</span>
                      <span
                        style={{
                          background: currentDetails.macroPosture === "DEFENSIVE_HOLD"
                            ? "rgba(2, 132, 199, 0.25)"
                            : currentDetails.macroPosture === "ZONE_SUPPRESS"
                            ? "rgba(139, 92, 246, 0.25)"
                            : "rgba(239, 68, 68, 0.25)",
                          border: `1px solid ${
                            currentDetails.macroPosture === "DEFENSIVE_HOLD"
                              ? "#0284c7"
                              : currentDetails.macroPosture === "ZONE_SUPPRESS"
                              ? "#8b5cf6"
                              : "#ef4444"
                          }`,
                          color: currentDetails.macroPosture === "DEFENSIVE_HOLD"
                            ? "#38bdf8"
                            : currentDetails.macroPosture === "ZONE_SUPPRESS"
                            ? "#c084fc"
                            : "#f87171",
                          padding: "1px 6px",
                          borderRadius: 3,
                          fontWeight: 800,
                          fontSize: 10,
                          display: "inline-flex",
                          alignItems: "center",
                          gap: 4,
                        }}
                        title="Level 1: Macro Strategic Posture of Turn"
                      >
                        <span>{currentDetails.macroPosture === "DEFENSIVE_HOLD" ? "🛡️" : currentDetails.macroPosture === "ZONE_SUPPRESS" ? "💥" : "⚔️"}</span>
                        <span>{currentDetails.macroPosture}</span>
                      </span>
                    </>
                  )}
                </div>
                <div style={{ fontSize: 13, fontWeight: 700, color: "#f8fafc", display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                  <span style={{ color: currentDetails.toPlay === "US" ? "#60a5fa" : "#34d399" }}>
                    {currentDetails.flag} {currentDetails.unitId}
                  </span>{" "}
                  {(() => {
                    const activeCtrl = getControllerBadgeInfo(controllerMap[currentDetails.toPlay] || "");
                    return (
                      <span
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: 3,
                          fontSize: 10,
                          fontWeight: 700,
                          padding: "1px 5px",
                          borderRadius: 3,
                          background: activeCtrl.bg,
                          color: activeCtrl.color,
                          border: `1px solid ${activeCtrl.border}`,
                        }}
                      >
                        <span>{activeCtrl.icon}</span>
                        <span>{activeCtrl.label}</span>
                      </span>
                    );
                  })()}{" "}
                  ➔ <code style={{ color: "#facc15" }}>{currentDetails.actionId}</code>
                  {(actionVector.fromQ !== null || actionVector.toQ !== null) && (
                    <span
                      style={{
                        background: "rgba(30, 41, 59, 0.8)",
                        border: "1px solid #475569",
                        padding: "1px 6px",
                        borderRadius: 3,
                        fontSize: 10,
                        fontWeight: 600,
                        color: actionVector.isFire ? "#f87171" : "#38bdf8",
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 3,
                        marginLeft: 4,
                      }}
                      title="Hex Trajectory: Origin -> Destination"
                    >
                      <span>📍 ({actionVector.fromQ ?? "?"},{actionVector.fromR ?? "?"})</span>
                      <span>➔</span>
                      <span>{actionVector.isFire ? "🎯" : "🏁"} ({actionVector.toQ ?? "?"},{actionVector.toR ?? "?"})</span>
                    </span>
                  )}
                  {currentDetails.unitMacroRole && (
                    <span
                      style={{
                        background: currentDetails.unitMacroRole.includes("FIRE_SUPPORT")
                          ? "rgba(249, 115, 22, 0.2)"
                          : currentDetails.unitMacroRole.includes("DEFENDER")
                          ? "rgba(59, 130, 246, 0.2)"
                          : currentDetails.unitMacroRole.includes("SCREEN")
                          ? "rgba(139, 92, 246, 0.2)"
                          : "rgba(234, 179, 8, 0.2)",
                        border: `1px solid ${
                          currentDetails.unitMacroRole.includes("FIRE_SUPPORT")
                            ? "#f97316"
                            : currentDetails.unitMacroRole.includes("DEFENDER")
                            ? "#3b82f6"
                            : currentDetails.unitMacroRole.includes("SCREEN")
                            ? "#8b5cf6"
                            : "#eab308"
                        }`,
                        color: currentDetails.unitMacroRole.includes("FIRE_SUPPORT")
                          ? "#fb923c"
                          : currentDetails.unitMacroRole.includes("DEFENDER")
                          ? "#60a5fa"
                          : currentDetails.unitMacroRole.includes("SCREEN")
                          ? "#c084fc"
                          : "#facc15",
                        padding: "1px 6px",
                        borderRadius: 3,
                        fontWeight: 700,
                        fontSize: 10,
                      }}
                      title={`Squad Tactical Role: ${currentDetails.unitMacroRole}`}
                    >
                      {currentDetails.unitMacroRole.includes("FIRE_SUPPORT") ? "🎯 FIRE SUPPORT" : currentDetails.unitMacroRole.includes("DEFENDER") ? "🛡️ VP DEFENDER" : currentDetails.unitMacroRole.includes("SCREEN") ? "👁️ FLANK SCREEN" : "⚡ SPEARHEAD"}
                    </span>
                  )}
                </div>
              </div>
            </div>

            <div style={{ display: "flex", gap: 10 }}>
              <div style={{ textAlign: "right" }}>
                <div className="muted" style={{ fontSize: 10 }}>Damage Dealt</div>
                <div style={{ fontSize: 12, fontWeight: 700, color: currentDetails.damage > 0 ? "#ef4444" : "#cbd5e1" }}>
                  {currentDetails.damage.toFixed(2)} dmg
                </div>
              </div>
              <div style={{ textAlign: "right" }}>
                <div className="muted" style={{ fontSize: 10 }}>Kills</div>
                <div style={{ fontSize: 12, fontWeight: 700, color: currentDetails.kills > 0 ? "#ef4444" : "#cbd5e1" }}>
                  {currentDetails.kills}
                </div>
              </div>
              <div style={{ textAlign: "right" }}>
                <div className="muted" style={{ fontSize: 10 }}>Reward</div>
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
              🎯 EZv2 Decision & MCTS
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
              👥 Troops ({units.length})
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
              📊 VPs & Telemetry
            </button>
          </div>

          {/* TAB 1: EZV2 DECISION & MCTS */}
          {activeTab === "decision" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {/* Level 1: Doctrinal Hierarchical Planner */}
              <div
                style={{
                  background: "#0b1329",
                  border: "1px solid #1e3a8a",
                  borderRadius: 6,
                  padding: "8px 10px",
                  display: "flex",
                  flexDirection: "column",
                  gap: 6,
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: 10, fontWeight: 900, color: "#93c5fd", textTransform: "uppercase", letterSpacing: 0.5, display: "flex", alignItems: "center", gap: 5 }}>
                    <span>♟️ Hierarchical Planner (Level 1)</span>
                  </span>
                  <span style={{ fontSize: 9, color: "#64748b", fontFamily: "monospace" }}>
                    MacroStrategyPlanner
                  </span>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
                  {/* Postura Macro */}
                  <div style={{ background: "#1e293b", padding: "6px 8px", borderRadius: 4, borderLeft: `3px solid ${currentDetails.macroPosture ? (currentDetails.macroPosture === "DEFENSIVE_HOLD" ? "#0284c7" : currentDetails.macroPosture === "ZONE_SUPPRESS" ? "#8b5cf6" : "#ef4444") : "#475569"}` }}>
                    <div className="muted" style={{ fontSize: 9, textTransform: "uppercase" }}>Turn Macro Posture</div>
                    <div style={{ fontSize: 11, fontWeight: 800, color: currentDetails.macroPosture ? (currentDetails.macroPosture === "DEFENSIVE_HOLD" ? "#38bdf8" : currentDetails.macroPosture === "ZONE_SUPPRESS" ? "#c084fc" : "#f87171") : "#94a3b8", display: "flex", alignItems: "center", gap: 4, marginTop: 1 }}>
                      {currentDetails.macroPosture ? (
                        <>
                          <span>{currentDetails.macroPosture === "DEFENSIVE_HOLD" ? "🛡️" : currentDetails.macroPosture === "ZONE_SUPPRESS" ? "💥" : "⚔️"}</span>
                          <span>{currentDetails.macroPosture}</span>
                        </>
                      ) : (
                        <span>- (Not emitted)</span>
                      )}
                    </div>
                    <div style={{ fontSize: 9, color: "#94a3b8", marginTop: 2, lineHeight: 1.2 }}>
                      {currentDetails.macroPosture === "DEFENSIVE_HOLD"
                        ? "VP Lead: Consolidate and entrench controlled positions."
                        : currentDetails.macroPosture === "ZONE_SUPPRESS"
                        ? "All VPs controlled. Suppression and annihilation of remnants."
                        : currentDetails.macroPosture === "ASSAULT_VP" || currentDetails.macroPosture === "ASSAULT"
                        ? "Priority assault on closest objective VP."
                        : "No explicit macro posture recorded for this step."}
                    </div>
                  </div>

                  {/* Rol Táctico Unidad */}
                  <div style={{ background: "#1e293b", padding: "6px 8px", borderRadius: 4, borderLeft: `3px solid ${currentDetails.unitMacroRole ? (currentDetails.unitMacroRole.includes("FIRE_SUPPORT") ? "#f97316" : currentDetails.unitMacroRole.includes("DEFENDER") ? "#38bdf8" : currentDetails.unitMacroRole.includes("CLOSE_DEFENSE") ? "#a855f7" : currentDetails.unitMacroRole.includes("RECON") ? "#06b6d4" : currentDetails.unitMacroRole.includes("RECOVER") ? "#eab308" : currentDetails.unitMacroRole.includes("SCREEN") ? "#10b981" : "#ef4444") : "#475569"}` }}>
                    <div className="muted" style={{ fontSize: 9, textTransform: "uppercase", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span>Squad Tactical Role</span>
                      {currentDetails.roleIsMutated && (
                        <span style={{ color: "#fca5a5", fontWeight: 700, fontSize: 8, background: "rgba(239, 68, 68, 0.25)", padding: "1px 4px", borderRadius: 3 }}>⚡ MUTADA</span>
                      )}
                    </div>
                    <div style={{ fontSize: 11, fontWeight: 800, color: currentDetails.unitMacroRole ? (currentDetails.unitMacroRole.includes("FIRE_SUPPORT") ? "#fb923c" : currentDetails.unitMacroRole.includes("DEFENDER") ? "#60a5fa" : currentDetails.unitMacroRole.includes("CLOSE_DEFENSE") ? "#c084fc" : currentDetails.unitMacroRole.includes("RECON") ? "#67e8f9" : currentDetails.unitMacroRole.includes("RECOVER") ? "#fde047" : currentDetails.unitMacroRole.includes("SCREEN") ? "#6ee7b7" : "#f87171") : "#94a3b8", display: "flex", alignItems: "center", gap: 5, marginTop: 2, flexWrap: "wrap" }}>
                      {currentDetails.unitMacroRole ? (
                        <>
                          <span>{currentDetails.unitMacroRole.includes("FIRE_SUPPORT") ? "🎯" : currentDetails.unitMacroRole.includes("DEFENDER") ? "🏰" : currentDetails.unitMacroRole.includes("CLOSE_DEFENSE") ? "🛡️" : currentDetails.unitMacroRole.includes("RECON") ? "🔭" : currentDetails.unitMacroRole.includes("RECOVER") ? "🩹" : currentDetails.unitMacroRole.includes("SCREEN") ? "👁️" : "⚡"}</span>
                          <span>{currentDetails.unitMacroRole.replace("ROLE_", "")}</span>
                          {currentDetails.priorBoostApplied > 0 && (
                            <span style={{ fontSize: 9, background: "rgba(34, 197, 94, 0.2)", color: "#86efac", border: "1px solid #22c55e", borderRadius: 3, padding: "0 4px", fontWeight: 700 }} title="Prior boost applied at EZv2 root">
                              +{Math.round(currentDetails.priorBoostApplied * 100)}% π
                            </span>
                          )}
                        </>
                      ) : (
                        <span>- (Not emitted)</span>
                      )}
                    </div>
                    <div style={{ fontSize: 9, color: "#94a3b8", marginTop: 2, lineHeight: 1.2 }}>
                      {currentDetails.roleIsMutated && currentDetails.roleMutationReason
                        ? `Regla: ${currentDetails.roleMutationReason}. `
                        : ""}
                      {currentDetails.macroTargetVpId ? `Priority Objective: VP ${currentDetails.macroTargetVpId}` : (currentDetails.unitMacroRole ? "No specific objective" : "Step has no recorded squad tactical role.")}
                    </div>
                  </div>
                </div>
              </div>

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
                  <span style={{ fontSize: 11, color: "#60a5fa", fontWeight: 800, textTransform: "uppercase", display: "flex", alignItems: "center", gap: 6 }}>
                    <span>MCTS Decision</span>
                    <span style={{ color: "#e9d5ff", background: "rgba(168, 85, 247, 0.25)", border: "1px solid #a855f7", padding: "1px 6px", borderRadius: 3, fontSize: 10, fontWeight: 800 }}>
                      {currentDetails.gameTurn !== null ? `Turn ${currentDetails.gameTurn} | ` : ""}Step {clamped}
                    </span>
                  </span>
                  {currentStep.policy_overridden_by_mcts ? (
                    <span style={{ fontSize: 10, background: "rgba(14, 165, 233, 0.2)", color: "#38bdf8", padding: "1px 5px", borderRadius: 3, fontWeight: 700 }}>
                      ⚡ MCTS corrected Policy
                    </span>
                  ) : (
                    <span style={{ fontSize: 10, background: "rgba(34, 197, 94, 0.15)", color: "#22c55e", padding: "1px 5px", borderRadius: 3 }}>
                      ✓ Policy maintained
                    </span>
                  )}
                </div>

                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 4 }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: "#facc15" }}>
                    <code>{currentDetails.actionId}</code>
                  </div>
                  <button
                    onClick={handleExplainAction}
                    style={{
                      background: "rgba(14, 165, 233, 0.15)",
                      border: "1px solid #0284c7",
                      color: "#38bdf8",
                      fontSize: 11,
                      fontWeight: 700,
                      padding: "2px 8px",
                      borderRadius: 4,
                      cursor: "pointer",
                      display: "flex",
                      alignItems: "center",
                      gap: 4,
                    }}
                    title="Compute Integrated Gradients (IGNH) & Grad-CAM attribution for this action"
                  >
                    <span>🧠 Explain (IGNH)</span>
                  </button>
                </div>

                {Boolean(currentStep.why_action_vs_vp_text) && (
                  <div style={{ fontSize: 11, color: "#cbd5e1", fontStyle: "italic", background: "rgba(255,255,255,0.03)", padding: 6, borderRadius: 4 }}>
                    "{String(currentStep.why_action_vs_vp_text)}"
                  </div>
                )}

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, marginTop: 2 }}>
                  <div style={{ background: "#1e293b", padding: "4px 8px", borderRadius: 4 }}>
                    <div className="muted" style={{ fontSize: 9 }}>MCTS Visits N</div>
                    <div style={{ fontSize: 12, fontWeight: 700, color: "#38bdf8" }}>
                      {currentStep.mcts_total_visits ?? "N/A"}
                    </div>
                  </div>
                  <div style={{ background: "#1e293b", padding: "4px 8px", borderRadius: 4 }}>
                    <div className="muted" style={{ fontSize: 9 }}>Expected Value Q(s,a)</div>
                    <div style={{ fontSize: 12, fontWeight: 700, color: Number(currentStep.mcts_q_value) >= 0 ? "#22c55e" : "#ef4444" }}>
                      {Number.isFinite(Number(currentStep.mcts_q_value)) ? Number(currentStep.mcts_q_value).toFixed(3) : "-"}
                    </div>
                  </div>
                </div>

                {/* Neural Auxiliary Heads Breakdown (Threat, Morale, Attrition) */}
                <div style={{ marginTop: 8, padding: "8px 10px", background: "rgba(15, 23, 42, 0.75)", border: "1px solid #334155", borderRadius: 4 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                    <span style={{ fontSize: 10, fontWeight: 800, color: "#38bdf8", textTransform: "uppercase", letterSpacing: "0.4px" }}>
                      Tactical Heads (EfficientZero V2)
                    </span>
                    {isLoadingTacticalHeads ? (
                      <span style={{ fontSize: 9, color: "#94a3b8" }}>Loading heads...</span>
                    ) : (
                      <span style={{ fontSize: 9, color: "#64748b" }}>
                        {currentTacticalHeads?.threat_summary?.source || "ready"}
                      </span>
                    )}
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, fontSize: 10 }}>
                    <div style={{ background: "#1e293b", padding: "5px 7px", borderRadius: 3, borderLeft: "2px solid #ef4444" }}>
                      <span className="muted" style={{ fontSize: 9, display: "block" }}>Threat Map Head:</span>
                      <div style={{ fontWeight: 700, color: (currentTacticalHeads?.threat_summary?.max_threat ?? 0) >= 0.5 ? "#f87171" : "#34d399", marginTop: 1 }}>
                        Max: {Math.round((currentTacticalHeads?.threat_summary?.max_threat ?? 0) * 100)}% | Mean: {Math.round((currentTacticalHeads?.threat_summary?.mean_threat ?? 0) * 100)}%
                      </div>
                    </div>
                    <div style={{ background: "#1e293b", padding: "5px 7px", borderRadius: 3, borderLeft: "2px solid #38bdf8" }}>
                      <span className="muted" style={{ fontSize: 9, display: "block" }}>Morale Head (Risk):</span>
                      <div style={{ fontWeight: 700, color: (currentTacticalHeads?.morale?.suppression_risk ?? 0) >= 0.5 ? "#f87171" : "#38bdf8", marginTop: 1 }}>
                        {Math.round((currentTacticalHeads?.morale?.suppression_risk ?? 0) * 100)}% ({currentTacticalHeads?.morale?.status || "STABLE"})
                      </div>
                    </div>
                    <div style={{ background: "#1e293b", padding: "5px 7px", borderRadius: 3, gridColumn: "span 2", borderLeft: "2px solid #f59e0b" }}>
                      <span className="muted" style={{ fontSize: 9, display: "block" }}>Attrition Head (Casualties):</span>
                      <div style={{ fontWeight: 700, color: "#cbd5e1", marginTop: 1 }}>
                        Ally: {currentTacticalHeads?.attrition?.predicted_friendly_casualties ?? 0.0} | Enemy: {currentTacticalHeads?.attrition?.predicted_enemy_casualties ?? 0.0}
                        {currentTacticalHeads?.attrition?.exchange_ratio !== undefined && (
                          <span style={{ marginLeft: 6, color: "#facc15" }}>
                            (Ratio: {currentTacticalHeads.attrition.exchange_ratio}x)
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Dedicated Action Execution & Combat Outcome Card */}
              <div
                style={{
                  background: "linear-gradient(180deg, #131d31 0%, #0c1424 100%)",
                  border: "1px solid #1e40af",
                  borderRadius: 6,
                  padding: "10px 12px",
                  display: "flex",
                  flexDirection: "column",
                  gap: 8,
                  boxShadow: "0 2px 8px rgba(0,0,0,0.3)",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: 11, fontWeight: 800, color: "#38bdf8", textTransform: "uppercase", letterSpacing: 0.5, display: "flex", alignItems: "center", gap: 5 }}>
                    <span>⚡ Action Execution & Combat Outcome</span>
                  </span>
                  <span
                    style={{
                      fontSize: 10,
                      fontWeight: 800,
                      padding: "2px 6px",
                      borderRadius: 4,
                      background: actionVector.isFire ? "rgba(239, 68, 68, 0.2)" : actionVector.isMove ? "rgba(14, 165, 233, 0.2)" : "rgba(148, 163, 184, 0.15)",
                      color: actionVector.isFire ? "#f87171" : actionVector.isMove ? "#38bdf8" : "#94a3b8",
                      border: `1px solid ${actionVector.isFire ? "#ef4444" : actionVector.isMove ? "#0284c7" : "#475569"}`,
                    }}
                  >
                    {actionVector.kind}
                  </span>
                </div>

                {/* Hex Trajectory Grid: Origin -> Destination */}
                <div style={{ display: "grid", gridTemplateColumns: "1fr auto 1fr", alignItems: "center", gap: 6, background: "#0b1220", padding: "8px 10px", borderRadius: 4, border: "1px solid #1e293b" }}>
                  <div>
                    <div style={{ fontSize: 9, color: "#94a3b8", textTransform: "uppercase", fontWeight: 700 }}>📍 Origin Hex</div>
                    <div style={{ fontSize: 13, fontWeight: 800, color: "#f8fafc", fontFamily: "monospace" }}>
                      {actionVector.fromQ !== null && actionVector.fromR !== null ? `(${actionVector.fromQ}, ${actionVector.fromR})` : "-"}
                    </div>
                    <div style={{ fontSize: 10, color: "#64748b" }}>
                      {actionVector.fromQ !== null && actionVector.fromR !== null ? terrainMap.get(`${actionVector.fromQ},${actionVector.fromR}`) || "clear" : ""}
                    </div>
                  </div>

                  <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 1 }}>
                    <span style={{ fontSize: 14, color: actionVector.isFire ? "#ef4444" : "#38bdf8" }}>➔</span>
                    {actionVector.hexDistance > 0 && (
                      <span style={{ fontSize: 9, color: "#94a3b8", fontWeight: 600 }}>{actionVector.hexDistance} hex{actionVector.hexDistance > 1 ? "es" : ""}</span>
                    )}
                  </div>

                  <div>
                    <div style={{ fontSize: 9, color: "#94a3b8", textTransform: "uppercase", fontWeight: 700 }}>
                      {actionVector.isFire ? "🎯 Target Hex" : "🏁 Destination Hex"}
                    </div>
                    <div style={{ fontSize: 13, fontWeight: 800, color: actionVector.isFire ? "#f87171" : "#34d399", fontFamily: "monospace" }}>
                      {actionVector.toQ !== null && actionVector.toR !== null ? `(${actionVector.toQ}, ${actionVector.toR})` : "-"}
                    </div>
                    <div style={{ fontSize: 10, color: "#64748b" }}>
                      {actionVector.toQ !== null && actionVector.toR !== null ? terrainMap.get(`${actionVector.toQ},${actionVector.toR}`) || "clear" : ""}
                    </div>
                  </div>
                </div>

                {/* Units Status (Acting Unit & Opponent Unit) */}
                <div style={{ display: "grid", gridTemplateColumns: actionVector.isFire || actionVector.targetUnitId ? "1fr 1fr" : "1fr", gap: 6 }}>
                  {/* Acting Unit Box */}
                  <div style={{ background: "#0b1220", padding: "6px 8px", borderRadius: 4, borderLeft: `3px solid ${actionVector.actorSide === "US" ? "#3b82f6" : "#10b981"}` }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={{ fontSize: 9, color: "#94a3b8", textTransform: "uppercase", fontWeight: 700 }}>Acting Unit</span>
                      <span style={{ fontSize: 10, fontWeight: 700, color: "#f8fafc" }}>{actionVector.actorSide === "US" ? "🇺🇸" : "🇮🇹"} {actionVector.actorId}</span>
                    </div>
                    <div style={{ fontSize: 11, fontWeight: 600, color: "#cbd5e1", marginTop: 1 }}>
                      {actionVector.actorUnitName}
                    </div>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 4 }}>
                      <span style={{ fontSize: 10, color: "#94a3b8" }}>Health (HP):</span>
                      <span style={{ fontSize: 11, fontWeight: 800, color: actionVector.actorHpPost < actionVector.actorHpPre ? "#ef4444" : "#22c55e" }}>
                        {actionVector.actorHpPre.toFixed(1)} ➔ {actionVector.actorHpPost.toFixed(1)} HP
                        {actionVector.actorHpPost < actionVector.actorHpPre && ` (-${(actionVector.actorHpPre - actionVector.actorHpPost).toFixed(1)})`}
                      </span>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 2 }}>
                      <span style={{ fontSize: 10, color: "#94a3b8" }}>State:</span>
                      <span style={{ fontSize: 10, fontWeight: 700, color: actionVector.actorAlivePost ? "#22c55e" : "#ef4444" }}>
                        {actionVector.actorAlivePost ? "Active / Alive" : "Eliminated 💀"}
                      </span>
                    </div>
                  </div>

                  {/* Opponent Target Unit Box (for attacks/fire) */}
                  {(actionVector.isFire || actionVector.targetUnitId) && (
                    <div style={{ background: "#0b1220", padding: "6px 8px", borderRadius: 4, borderLeft: `3px solid ${actionVector.targetUnitSide === "US" ? "#3b82f6" : "#ef4444"}` }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <span style={{ fontSize: 9, color: "#94a3b8", textTransform: "uppercase", fontWeight: 700 }}>Opponent Target</span>
                        <span style={{ fontSize: 10, fontWeight: 700, color: "#f87171" }}>
                          {actionVector.targetUnitSide === "US" ? "🇺🇸" : actionVector.targetUnitSide === "IT" ? "🇮🇹" : "🇩🇪"} {actionVector.targetUnitId || "-"}
                        </span>
                      </div>
                      <div style={{ fontSize: 11, fontWeight: 600, color: "#cbd5e1", marginTop: 1 }}>
                        {actionVector.targetUnitName || "Target"}
                      </div>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 4 }}>
                        <span style={{ fontSize: 10, color: "#94a3b8" }}>Target Health:</span>
                        <span style={{ fontSize: 11, fontWeight: 800, color: (actionVector.targetHpPost ?? 0) < (actionVector.targetHpPre ?? 0) ? "#ef4444" : "#cbd5e1" }}>
                          {actionVector.targetHpPre !== null ? actionVector.targetHpPre.toFixed(1) : "?"} ➔ {actionVector.targetHpPost !== null ? actionVector.targetHpPost.toFixed(1) : "?"} HP
                          {actionVector.targetHpPre !== null && actionVector.targetHpPost !== null && actionVector.targetHpPost < actionVector.targetHpPre && (
                            ` (-${(actionVector.targetHpPre - actionVector.targetHpPost).toFixed(1)})`
                          )}
                        </span>
                      </div>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 2 }}>
                        <span style={{ fontSize: 10, color: "#94a3b8" }}>Target State:</span>
                        <span style={{ fontSize: 10, fontWeight: 700, color: actionVector.targetAlivePost === false ? "#ef4444" : (actionVector.targetHpPost ?? 0) < (actionVector.targetHpPre ?? 0) ? "#f59e0b" : "#22c55e" }}>
                          {actionVector.targetAlivePost === false ? "Eliminated 💀" : (actionVector.targetHpPost ?? 0) < (actionVector.targetHpPre ?? 0) ? "Damaged 💥" : "Unscathed"}
                        </span>
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* MCTS Candidates Tree Explorer */}
              {totalCandidatesCount > 0 ? (
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                    <span style={{ fontSize: 11, fontWeight: 700, color: "#38bdf8" }}>
                      Root Candidates ({totalCandidatesCount})
                    </span>
                    <div style={{ display: "flex", gap: 4 }}>
                      <button
                        onClick={() => setMctsFilter("all")}
                        style={{ fontSize: 10, padding: "1px 5px", borderRadius: 3, background: mctsFilter === "all" ? "#0284c7" : "#0f172a", border: "none", color: "#fff", cursor: "pointer" }}
                      >
                        All
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
                      placeholder="Filter action..."
                      value={mctsSearch}
                      onChange={(e) => setMctsSearch(e.target.value)}
                      style={{ flex: 1, fontSize: 11, padding: "3px 6px", background: "#0f172a", border: "1px solid #334155", borderRadius: 4, color: "#fff" }}
                    />
                    <select
                      value={mctsSortBy}
                      onChange={(e) => setMctsSortBy(e.target.value as "visits" | "q_value" | "prior" | "rank")}
                      style={{ fontSize: 10, padding: "2px 4px", background: "#0f172a", border: "1px solid #334155", color: "#fff" }}
                    >
                      <option value="visits">By Visits N</option>
                      <option value="q_value">By Q Value</option>
                      <option value="prior">By Policy Prior</option>
                      <option value="rank">By Rank</option>
                    </select>
                  </div>

                  <div style={{ maxHeight: 260, overflowY: "auto", border: "1px solid #334155", borderRadius: 6 }}>
                    <table style={{ margin: 0, fontSize: 11 }}>
                      <thead>
                        <tr>
                          <th>Action</th>
                          <th style={{ width: 80 }}>Visits N</th>
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
                  No MCTS branches recorded for this step.
                </div>
              )}
            </div>
          )}

          {/* TAB 2: UNIT ROSTER */}
          {activeTab === "units" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div style={{ fontSize: 11, color: "#94a3b8" }}>
                Click on a squad to focus it on the tactical map.
              </div>

              {/* US Troops */}
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, color: "#60a5fa", marginBottom: 4, display: "flex", alignItems: "center", gap: 4 }}>
                  <span>🇺🇸</span> US Troops ({usUnits.length} squads)
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 4, maxHeight: 180, overflowY: "auto" }}>
                  {usUnits.map((u) => {
                    const isActing = String(currentStep.unit_id) === u.unit_id;
                    const isSelected = selectedUnitId === u.unit_id;
                    const roleInfo = getUnitTacticalRole(u, currentStep, currentDetails.macroPosture, currentDetails.macroTargetVpId);
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
                          {roleInfo.label && (
                            <span
                              style={{
                                background: `${roleInfo.color}22`,
                                border: `1px solid ${roleInfo.color}66`,
                                color: roleInfo.color,
                                fontSize: 9,
                                padding: "1px 5px",
                                borderRadius: 3,
                                fontWeight: 700,
                                display: "inline-flex",
                                alignItems: "center",
                                gap: 3,
                              }}
                              title={roleInfo.desc}
                            >
                              <span>{roleInfo.icon}</span>
                              <span>{roleInfo.label}</span>
                            </span>
                          )}
                          {roleInfo.isMutated && (
                            <span
                              style={{
                                background: "rgba(239, 68, 68, 0.2)",
                                border: "1px solid #ef4444",
                                color: "#fca5a5",
                                fontSize: 8,
                                padding: "1px 4px",
                                borderRadius: 3,
                                fontWeight: 700,
                              }}
                              title={`Rol mutado dinámicamente por regla: ${roleInfo.mutationReason}`}
                            >
                              ⚡ {roleInfo.mutationReason ? roleInfo.mutationReason.slice(0, 10) : "MUT"}
                            </span>
                          )}
                          {roleInfo.priorBoost > 0 && (
                            <span
                              style={{
                                background: "rgba(34, 197, 94, 0.15)",
                                border: "1px solid #22c55e",
                                color: "#86efac",
                                fontSize: 8,
                                padding: "1px 4px",
                                borderRadius: 3,
                                fontWeight: 700,
                              }}
                              title={`Prior boost doctrinal: +${Math.round(roleInfo.priorBoost * 100)}%`}
                            >
                              +{Math.round(roleInfo.priorBoost * 100)}% π
                            </span>
                          )}
                        </div>
                        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                          <span style={{ color: u.alive ? (u.hp >= 3.0 ? "#22c55e" : "#f59e0b") : "#ef4444", fontWeight: 700 }}>
                            {u.alive ? `${u.hp.toFixed(1)} HP` : "KIA"}
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
                  <span>🇩🇪</span> Axis Troops ({itUnits.length} squads)
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 4, maxHeight: 180, overflowY: "auto" }}>
                  {itUnits.map((u) => {
                    const isActing = String(currentStep.unit_id) === u.unit_id;
                    const isSelected = selectedUnitId === u.unit_id;
                    const roleInfo = getUnitTacticalRole(u, currentStep, currentDetails.macroPosture, currentDetails.macroTargetVpId);
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
                          {isActing && <span style={{ fontSize: 9, color: "#facc15", fontWeight: 700 }}>ACTING</span>}
                          {roleInfo.label && (
                            <span
                              style={{
                                background: `${roleInfo.color}22`,
                                border: `1px solid ${roleInfo.color}66`,
                                color: roleInfo.color,
                                fontSize: 9,
                                padding: "1px 5px",
                                borderRadius: 3,
                                fontWeight: 700,
                                display: "inline-flex",
                                alignItems: "center",
                                gap: 3,
                              }}
                              title={roleInfo.desc}
                            >
                              <span>{roleInfo.icon}</span>
                              <span>{roleInfo.label}</span>
                            </span>
                          )}
                          {roleInfo.isMutated && (
                            <span
                              style={{
                                background: "rgba(239, 68, 68, 0.2)",
                                border: "1px solid #ef4444",
                                color: "#fca5a5",
                                fontSize: 8,
                                padding: "1px 4px",
                                borderRadius: 3,
                                fontWeight: 700,
                              }}
                              title={`Dynamically mutated role: ${roleInfo.mutationReason}`}
                            >
                              ⚡ {roleInfo.mutationReason ? roleInfo.mutationReason.slice(0, 10) : "MUT"}
                            </span>
                          )}
                          {roleInfo.priorBoost > 0 && (
                            <span
                              style={{
                                background: "rgba(34, 197, 94, 0.15)",
                                border: "1px solid #22c55e",
                                color: "#86efac",
                                fontSize: 8,
                                padding: "1px 4px",
                                borderRadius: 3,
                                fontWeight: 700,
                              }}
                              title={`Doctrinal prior boost: +${Math.round(roleInfo.priorBoost * 100)}%`}
                            >
                              +{Math.round(roleInfo.priorBoost * 100)}% π
                            </span>
                          )}
                        </div>
                        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                          <span style={{ color: u.alive ? (u.hp >= 3.0 ? "#22c55e" : "#f59e0b") : "#ef4444", fontWeight: 700 }}>
                            {u.alive ? `${u.hp.toFixed(1)} HP` : "KIA"}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Selected Unit Forensic Doctrine Card */}
              {selectedUnitId && (() => {
                const selUnit = usUnits.concat(itUnits).find((u) => u.unit_id === selectedUnitId);
                if (!selUnit) return null;
                const rInfo = getUnitTacticalRole(selUnit, currentStep, currentDetails.macroPosture, currentDetails.macroTargetVpId);
                return (
                  <div style={{ marginTop: 8, background: "#0f172a", border: `1px solid ${rInfo.color || "#334155"}`, borderRadius: 6, padding: 10 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                      <span style={{ fontWeight: 800, color: "#f8fafc", fontSize: 12 }}>{selUnit.unit_id}</span>
                      <span style={{ background: `${rInfo.color}33`, color: rInfo.color, padding: "2px 6px", borderRadius: 4, fontWeight: 700, fontSize: 10 }}>
                        {rInfo.icon} {rInfo.label || "No Role"}
                      </span>
                    </div>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, fontSize: 10 }}>
                      <div><b>Side:</b> {selUnit.side}</div>
                      <div><b>Position:</b> ({selUnit.q}, {selUnit.r})</div>
                      <div><b>Health:</b> {selUnit.alive ? `${selUnit.hp.toFixed(1)} HP` : "KIA"}</div>
                      <div><b>Morale / Suppression:</b> {selUnit.suppressed ? "SUPPRESSED" : "STABLE"}</div>
                      <div><b>Assigned Role:</b> <code style={{ color: rInfo.color }}>{rInfo.role || "-"}</code></div>
                      <div><b>Mutation:</b> {rInfo.isMutated ? <span style={{ color: "#f87171", fontWeight: 700 }}>⚡ YES ({rInfo.mutationReason})</span> : <span style={{ color: "#34d399" }}>NO (Base Profile)</span>}</div>
                      {rInfo.priorBoost > 0 && (
                        <div style={{ gridColumn: "span 2", color: "#86efac", fontWeight: 700 }}>
                          🚀 MCTS Prior Modulation: +{Math.round(rInfo.priorBoost * 100)}%
                        </div>
                      )}
                    </div>
                  </div>
                );
              })()}
            </div>
          )}

          {/* TAB 3: VPs & TELEMETRY */}
          {activeTab === "telemetry" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: "#38bdf8" }}>
                Contested Victory Points ({vpMap.length} hexes)
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
                      <span className="muted" style={{ fontSize: 10, marginLeft: 6 }}>{vp.value || 2} VPs</span>
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
                Side Controllers
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {Object.entries(controllerMap).map(([side, ctrl]) => {
                  const badge = getControllerBadgeInfo(ctrl);
                  return (
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
                      <span
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: 4,
                          fontSize: 10,
                          fontWeight: 700,
                          padding: "2px 8px",
                          borderRadius: 3,
                          background: badge.bg,
                          color: badge.color,
                          border: `1px solid ${badge.border}`,
                        }}
                      >
                        <span>{badge.icon}</span>
                        <span>{badge.label}</span>
                      </span>
                    </div>
                  );
                })}
              </div>

              <div style={{ fontSize: 11, fontWeight: 700, color: "#38bdf8", marginTop: 8 }}>
                MLOps Telemetry Status
              </div>
              <div style={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 4, padding: 8, fontSize: 11 }}>
                <div>Coverage Status: <b>{String(currentStep.telemetry_coverage_status ?? "normal")}</b></div>
                <div className="muted" style={{ fontSize: 10, marginTop: 4 }}>
                  Decision Rank: <b>{String(currentStep.decision_score_selected ?? "N/A")}</b>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Forensic SitRep & Causal Profiler Modal */}
      <ForensicSitRepModal
        isOpen={isSitrepOpen}
        onClose={() => setIsSitrepOpen(false)}
        sitrepData={sitrepData}
        isLoading={isSitrepLoading}
        onJumpToStep={(stepIdx) => {
          setClamped(stepIdx);
        }}
        onRecompute={() => handleOpenSitrep(true)}
      />

      {/* Explainability Modal (IGNH / Grad-CAM) */}
      <ExplainabilityModal
        isOpen={isExplainModalOpen}
        onClose={() => setIsExplainModalOpen(false)}
        data={explainData}
        isLoading={isExplaining}
        onApplyHeatmapToBoard={(layerKey, hexes) => {
          setExplainHeatmapLayer(layerKey);
          setExplainHeatmapHexes(hexes);
        }}
      />
    </div>
  );
}
