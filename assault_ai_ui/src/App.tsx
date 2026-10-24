import { useState, useEffect, useRef, useMemo } from "react";
import "./App.css";
import GameCanvas from "./game/GameCanvas";
import { gameController } from "./game/gameControllerInstance";
import { UnitStatePanel } from "./game/ui/UnitStatePanel";
import { CombatPanel } from "./game/ui/CombatPanel";
import { unitImages } from "./game/config/unitImages";
import { sides } from "./game/config/sides";
import { formatCoords } from "./game/render/hexGridRenderer";
import { DispatchedOrdersPanel } from "./game/ui/DispatchedOrdersPanel";
import { RagAssistantPanel } from "./game/ui/RagAssistantPanel";
import { EfficientZeroV2TelemetryPanel } from "./game/ui/EfficientZeroV2TelemetryPanel";
import { UnitCardTooltip } from "./game/ui/UnitCardTooltip";
import { logCombatEvents } from "./game/systems/combatLog";
import { actionMarkerImages, getUnitActionMarker } from "./game/state/actionMarkers";
import { apiUrl } from "./config/backend";

const SCENARIO_LABELS: Record<string, string> = {
  addestramento_fanteria_11_1: "🎯 11.1 Addestramento Fanteria",
  battaglia_cittadina_2_1: "🏙️ 2.1 Battaglia Cittadina (Gela)",
  mettete_i_piedi_terra_1: "🌊 1.1 Mettete i piedi a terra!",
  bunker_hill_singolo: "⛰️ Bunker Hill",
  elemento_sorpresa_singolo: "⚡ Elemento Sorpresa",
  vp_phase1_unoccupied_3hex: "🏁 VP Phase 1 (Sprint)",
  vp_phase2_defended_suppressed: "🛡️ VP Phase 2 (Suppressed)",
  vp_phase3_race_2v2: "⚔️ VP Phase 3 (Race 2v2)",
};


type LogEntry = {
  type: string;
  text: string;
  time: string;
};

type Unit = {
  id: string;
  unit_key: string;
  side: string;
  hp?: number;
  max_hp?: number;
  health_pct?: number;
  tactical_role?: string;
  has_indirect_fire?: boolean;
  is_suppression_mg?: boolean;
  is_assault_squad?: boolean;
  alive?: boolean;
  q: number;
  r: number;
};

function App() {
  const [gameData, setGameData] = useState<any>(null);
  const [deadUnits, setDeadUnits] = useState<Unit[]>([]);
  const [selectedUnitId, setSelectedUnitId] = useState<string | null>(null);
  const [hoveredTargetId, setHoveredTargetId] = useState<string | null>(null);
  const [availableMoves, setAvailableMoves] = useState<any[]>([]);
  const [attackHint, setAttackHint] = useState<string | null>(null);
  const [logEvents, setLogEvents] = useState<LogEntry[]>([]);
  const [activeMode, setActiveMode] = useState<string | null>("human");
  const [scenarioList, setScenarioList] = useState<string[]>([]);
  const [selectedScenario, setSelectedScenario] = useState<string>("");
  const [scenarioSides, setScenarioSides] = useState<string[]>([]);
  const [humanSide, setHumanSide] = useState<string>("");
  const [reactionDecisionBusy, setReactionDecisionBusy] = useState(false);
  const [stickyCombatEvent, setStickyCombatEvent] = useState<any>(null);
  const [autoAdvanceAfterHuman, setAutoAdvanceAfterHuman] = useState(true);
  const [waitingForManualAdvance, setWaitingForManualAdvance] = useState(false);
  const [telemetry, setTelemetry] = useState<any>(null);

  // Tactical HUD & Drawer State
  const [hudVisible, setHudVisible] = useState(true);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [activeSidebarTab, setActiveSidebarTab] = useState<"combat" | "log" | "ai" | "rag">("combat");
  const [rosterFilterSide, setRosterFilterSide] = useState<string>("ALL");
  const [rosterStatusFilter, setRosterStatusFilter] = useState<"ALL" | "READY" | "DONE">("ALL");
  const [squadDrawerOpen, setSquadDrawerOpen] = useState(true);
  const [bottomUnitsOpen, setBottomUnitsOpen] = useState(true);
    const [squadSearchQuery, setSquadSearchQuery] = useState("");
  const [cardPreview, setCardPreview] = useState<{
    unit: Unit;
    x: number;
    y: number;
  } | null>(null);

  const fetchTelemetry = async () => {
    try {
      const res = await fetch(apiUrl("/api/game/telemetry"));
      if (res.ok) {
        const data = await res.json();
        if (data && Object.keys(data).length > 0) {
          setTelemetry(data);
        }
      }
    } catch {
      // ignore
    }
  };

  const lastTurnRef = useRef<number>(-1);
  const lastActiveSideRef = useRef<string>("");
  const lastDoneRef = useRef<boolean>(false);
  const lastReactionWindowRef = useRef<string>("");
  const prevUnitsRef = useRef<Unit[] | null>(null);

  const addLog = (type: string, text: string) => {
    const time = new Date().toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
    setLogEvents((prev) => [{ type, text, time }, ...prev].slice(0, 80));
  };

  const resetMatchUiState = () => {
    setDeadUnits([]);
    setSelectedUnitId(null);
    setHoveredTargetId(null);
    setAvailableMoves([]);
    setAttackHint(null);
    prevUnitsRef.current = null;
  };

  const buildSidesConfig = (mode: string): Record<string, string> => {
    const sidesList = scenarioSides;
    if (!sidesList.length) return {};
    const chosenHumanSide = humanSide || sidesList[0];
    const cfg: Record<string, string> = {};
    for (const s of sidesList) {
      cfg[s] = mode === "ai_vs_ai" ? "ai" : s === chosenHumanSide ? "human" : "ai";
    }
    return cfg;
  };

  // Keyboard shortcut listener: H to toggle HUD, Escape to close drawer/unselect
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
        return;
      }
      if (e.key === "h" || e.key === "H") {
        setHudVisible((prev) => !prev);
      } else if (e.key === "s" || e.key === "S" || e.key === "a" || e.key === "A") {
        setSquadDrawerOpen((prev) => !prev);
      } else if (e.key === "u" || e.key === "U") {
        setBottomUnitsOpen((prev) => !prev);
      
      } else if (e.key === "Escape") {
        if (squadDrawerOpen) {
          setSquadDrawerOpen(false);
        } else if (sidebarOpen) {
          setSidebarOpen(false);
        } else if (selectedUnitId) {
          setSelectedUnitId(null);
          setAvailableMoves([]);
        }
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [sidebarOpen, squadDrawerOpen, selectedUnitId]);

  useEffect(() => {
    (window as any).onCloseSquadDrawer = () => setSquadDrawerOpen(false);
    return () => {
      (window as any).onCloseSquadDrawer = undefined;
    };
  }, []);

  // Subscribe to game controller events
  useEffect(() => {
    const unsubscribe = gameController.subscribe((event: any) => {
      if (event.type === "turn_change") {
        addLog(
          "turn",
          `⚔️ Turn ${event.turn} // Active side: ${event.active_side || "-"} (${event.controller || "-"})`
        );
      } else if (event.type === "combat_result") {
        addLog(
          "combat",
          `💥 Attack from ${event.attacker} to ${event.defender} - Damage: ${event.damage || 0}`
        );
      }
    });

    const unsubscribeTurnFlow = gameController.subscribeTurnFlow((flowState: any) => {
      setWaitingForManualAdvance(Boolean(flowState?.waitingForManualAdvance));
      setAutoAdvanceAfterHuman(Boolean(flowState?.autoAdvanceAfterHuman));
    });

    return () => {
      unsubscribe();
      unsubscribeTurnFlow();
    };
  }, []);

  // Bridge global system logger for combat events
  useEffect(() => {
    (window as any).logSystemEvent = (type: string, text: string) => {
      addLog(type, text);
    };
    return () => {
      (window as any).logSystemEvent = undefined;
    };
  }, []);


  // Load scenarios on mount
  useEffect(() => {
    const fetchScenarios = async () => {
      try {
        const res = await fetch(apiUrl("/api/ui/scenarios"));
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        const list = Array.isArray(data?.scenarios) ? data.scenarios : [];
        setScenarioList(list);
        if (list.length > 0) {
          setSelectedScenario((prev) => prev || list[0]);
        }
      } catch (err) {
        console.error("❌ Failed to fetch scenario list", err);
        addLog("system", `❌ Failed to fetch scenario list: ${String(err)}`);
      }
    };
    fetchScenarios();
  }, []);

  // Fetch sides and automatically load scenario on map
  const lastLoadedScenarioRef = useRef<string>("");
  useEffect(() => {
    if (!selectedScenario) return;
    let cancelled = false;

    const fetchSidesAndLoad = async () => {
      try {
        const res = await fetch(apiUrl(`/api/ui/scenarios/${encodeURIComponent(selectedScenario)}`));
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (cancelled) return;

        const rawSides = Array.isArray(data?.sides) && data.sides.length > 0
          ? data.sides
          : Array.from(
              new Set(
                (data?.units || [])
                  .map((u: any) => String(u?.side || "").toUpperCase())
                  .filter((s: string) => s.length > 0)
              )
            );
        const sidesFound = rawSides.length > 0 ? rawSides : ["GE", "US"];
        setScenarioSides(sidesFound);
        const nextHumanSide = humanSide && sidesFound.includes(humanSide) ? humanSide : sidesFound[0];
        setHumanSide(nextHumanSide);

        // Auto-load scenario on map if scenario changed or not yet loaded
        if (lastLoadedScenarioRef.current !== selectedScenario) {
          lastLoadedScenarioRef.current = selectedScenario;
          const mode = activeMode || "human";
          const cfg: Record<string, string> = {};
          for (const s of sidesFound) {
            cfg[s] = mode === "ai_vs_ai" ? "ai" : s === nextHumanSide ? "human" : "ai";
          }
          (window as any).__forceInitialCameraFit = true;
          resetMatchUiState();
          addLog("system", `🗺️ Loading scenario: ${selectedScenario} (${sidesFound.join(" vs ")})`);
          await gameController.start(mode as any, selectedScenario, cfg);
        }
      } catch (err) {
        if (cancelled) return;
        console.error("❌ Failed to fetch scenario sides", err);
        setScenarioSides(["GE", "US"]);
        setHumanSide((prev) => prev || "GE");
      }
    };

    fetchSidesAndLoad();
    return () => {
      cancelled = true;
    };
  }, [selectedScenario]);

  // Keep track of active side / turn changes in battle log
  useEffect(() => {
    if (!gameData) return;
    const turn = gameData.turn;
    const activeSide = gameData.active_side;
    if (turn !== lastTurnRef.current || activeSide !== lastActiveSideRef.current) {
      lastTurnRef.current = turn;
      lastActiveSideRef.current = activeSide;

      const faction = sides[activeSide]?.label || activeSide || "Unknown";
      const controller = gameData.sides?.[activeSide] || "Unknown";

      addLog(
        "turn",
        `⚔️ TURN ${turn} // Faction active: ${activeSide} (${faction}) - Controlled by: [${controller.toUpperCase()}]`
      );
    }
  }, [gameData]);

  // End of match detection
  useEffect(() => {
    if (!gameData) return;
    const doneNow = Boolean(gameData?.done);
    if (doneNow && !lastDoneRef.current) {
      const winner = gameData?.winner ? String(gameData.winner) : "Draw";
      const reason = String(gameData?.end_reason || "completed");
      addLog("system", `🏁 Match concluded: ${winner} (${reason})`);
    }
    lastDoneRef.current = doneNow;
  }, [gameData?.done, gameData?.winner, gameData?.end_reason]);

  // Clear human selection on AI turn
  useEffect(() => {
    if (!gameData) return;
    const activeSide = gameData.active_side;
    const isHumanTurn = gameData?.sides?.[activeSide] === "human";
    if (!isHumanTurn) {
      setSelectedUnitId(null);
      setAvailableMoves([]);
      setHoveredTargetId(null);
      setAttackHint(null);
    }
  }, [gameData?.active_side, gameData?.sides]);

  // Log selections automatically
  // Auto-open left panel when unit is selected
  useEffect(() => {
    if (selectedUnitId) {
      setSquadDrawerOpen(true);
    }
  }, [selectedUnitId]);

  useEffect(() => {
    if (selectedUnitId) {
      const unit = gameData?.units?.find((u: any) => u.id === selectedUnitId);
      const label = unit ? unitImages[unit.unit_key as keyof typeof unitImages]?.label || unit.unit_key : "";
      addLog("select", `🟢 Target locked: ${selectedUnitId} [${label}]`);
    }
  }, [selectedUnitId, gameData]);

  // Combat logging
  useEffect(() => {
    logCombatEvents(gameData?.last_events, gameData?.units || []);
  }, [gameData]);

  // Auto-open or badge combat drawer when ACTION_EFFECT occurs
  useEffect(() => {
    const events = gameData?.last_events || [];
    const latest = events.slice().reverse().find((event: any) => event?.type === "ACTION_EFFECT");
    if (latest) {
      setStickyCombatEvent(latest);
      setActiveSidebarTab("combat");
      setSidebarOpen(true);
    }
  }, [gameData?.last_events]);

  // Log VP captures
  useEffect(() => {
    const events = gameData?.last_events || [];
    for (const event of events) {
      if (event?.type !== "VP_CAPTURED") continue;
      const p = event.payload || {};
      const coords =
        p.q != null && p.r != null ? formatCoords(Number(p.q), Number(p.r)) : "[?]";
      const newOwner = p.new_owner || "NONE";
      const prevOwner = p.previous_owner || "NONE";
      const value = Number(p.value || 0);
      addLog("turn", `🏁 VP ${coords} ${prevOwner} -> ${newOwner} (+${value})`);
    }
  }, [gameData?.last_events]);

  // Keep dead units in roster
  useEffect(() => {
    if (!gameData?.units) return;

    const currentUnits: Unit[] = gameData.units;
    const currentDead = currentUnits.filter((u) => u.hp != null && u.hp <= 0);
    const currentIds = new Set(currentUnits.map((u) => u.id));
    const previousUnits = prevUnitsRef.current || [];

    setDeadUnits((prev) => {
      const nextDeadMap = new Map<string, Unit>();
      for (const dead of currentDead) {
        nextDeadMap.set(dead.id, dead);
      }
      for (const d of prev) {
        if (!currentIds.has(d.id)) {
          nextDeadMap.set(d.id, d);
        }
      }
      for (const prevUnit of previousUnits) {
        if (
          !currentIds.has(prevUnit.id) &&
          !nextDeadMap.has(prevUnit.id) &&
          prevUnit.hp != null &&
          prevUnit.hp <= 0
        ) {
          nextDeadMap.set(prevUnit.id, prevUnit);
        }
      }
      return Array.from(nextDeadMap.values());
    });

    prevUnitsRef.current = currentUnits;
  }, [gameData?.units]);

  const resolveOrderTargetId = (order: any): string | null => {
    if (!order) return null;
    const actionType = String(order.type || order.kind || "").toUpperCase();
    const isAttack =
      order.kind === "attack" || /RANGED|ASSAULT|ATTACK|REACTION|COMBAT|FIRE/.test(actionType);
    if (!isAttack) return null;

    if (order.target_id) return order.target_id;

    const q = order.target_q ?? order.q;
    const r = order.target_r ?? order.r;
    if (q == null || r == null) return null;

    const unit = (gameData?.units || []).find((u: any) => u.q === q && u.r === r);
    return unit?.id ?? null;
  };

  const handleStartGame = (mode: string) => {
    if (!selectedScenario) {
      addLog("system", "❌ No scenario selected");
      return;
    }
    const sidesList = scenarioSides.length > 0 ? scenarioSides : ["GE", "US"];
    const chosenSide = humanSide && sidesList.includes(humanSide) ? humanSide : sidesList[0];
    setHumanSide(chosenSide);
    setActiveMode(mode);
    addLog(
      "system",
      `🚀 Launching match: [${mode.toUpperCase()}] // Scenario: ${selectedScenario} // Side: ${chosenSide}`
    );
    (window as any).__forceInitialCameraFit = true;
    resetMatchUiState();
    const cfg: Record<string, string> = {};
    for (const s of sidesList) {
      cfg[s] = mode === "ai_vs_ai" ? "ai" : s === chosenSide ? "human" : "ai";
    }
    lastLoadedScenarioRef.current = selectedScenario;
    gameController.start(mode as any, selectedScenario, cfg);
  };

  const handleScenarioChange = (scenarioId: string) => {
    if (!scenarioId || scenarioId === selectedScenario) return;
    setSelectedScenario(scenarioId);
    resetMatchUiState();
  };

  const handleStopGame = () => {
    addLog("system", "⛔ Terminating active session. Resetting board...");
    setTimeout(() => {
      window.location.reload();
    }, 600);
  };

  const handleStartSelectedMode = () => {
    const modeToUse = activeMode || "human";
    handleStartGame(modeToUse);
  };

  const canStartGame = Boolean(selectedScenario);

  const handleExportTrace = async () => {
    try {
      const res = await fetch(apiUrl("/api/game/trace?limit=50000"));
      if (!res.ok) throw new Error(`Trace export failed (${res.status})`);
      const payload = await res.json();
      const stamp = new Date().toISOString().replace(/[:.]/g, "-");
      const scenario = String(gameData?.scenario_name || selectedScenario || "scenario");
      const fileName = `trace_export_${scenario}_${stamp}.json`;
      const blob = new Blob([JSON.stringify(payload, null, 2)], {
        type: "application/json;charset=utf-8",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = fileName;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      addLog("system", `💾 Trace exported: ${fileName}`);
    } catch (err) {
      console.error("❌ Trace export failed", err);
      addLog("system", `❌ Trace export failed: ${String(err)}`);
    }
  };

  const handleToggleAutoAdvance = (enabled: boolean) => {
    gameController.setAutoAdvanceAfterHuman(enabled);
    addLog(
      "system",
      enabled
        ? "▶ Auto-advance enabled: AI continues automatically after player action."
        : "⏸ Auto-advance disabled: Click Advance to proceed."
    );
  };

  const handleManualAdvance = () => {
    gameController.continueAfterHumanAction();
    addLog("system", "▶ Manual advance triggered: continuing AI turn.");
  };

  // Selected unit specs
  const selectedUnit = gameData?.units?.find((u: Unit) => u.id === selectedUnitId);
  const selectedUnitSpec = selectedUnit
    ? unitImages[selectedUnit.unit_key as keyof typeof unitImages]
    : null;
  const selectedUnitActionMarker = selectedUnit ? getUnitActionMarker(selectedUnit.id) : null;
  const selectedWaitOrder = selectedUnit
    ? (availableMoves || []).find((m: any) => m?.kind === "wait" && m?.action_id)
    : null;

  const executeActionById = async (actionId: string, order?: any) => {
    const activeSideNow = gameData?.active_side;
    const isHumanTurnNow = gameData?.sides?.[activeSideNow] === "human";
    if (!isHumanTurnNow) return;
    try {
      const executed = await (window as any).onExecuteOrder?.(order || { action_id: actionId });
      if (executed) return;
      console.warn("⛔ executeActionById rejected: onExecuteOrder did not execute");
    } catch (err) {
      console.error("❌ Action by id failed", err);
    }
  };

  const panelUnits = useMemo(() => {
    const byId = new Map<string, Unit>();
    for (const u of gameData?.units || []) {
      byId.set(u.id, u);
    }
    for (const dead of deadUnits) {
      if (!byId.has(dead.id)) {
        byId.set(dead.id, { ...dead, hp: 0 });
      }
    }
    return Array.from(byId.values());
  }, [gameData?.units, deadUnits]);

  // Live activation counts for active side
  const { readyCount, doneCount } = useMemo(() => {
    if (!panelUnits) return { readyCount: 0, doneCount: 0 };
    const activatedSet = new Set(gameData?.activated_units || []);
    let ready = 0;
    let done = 0;
    for (const u of panelUnits) {
      if (u.alive === false || (u.hp != null && u.hp <= 0)) continue;
      if (u.side === gameData?.active_side) {
        if (activatedSet.has(u.id)) {
          done++;
        } else {
          ready++;
        }
      }
    }
    return { readyCount: ready, doneCount: done };
  }, [panelUnits, gameData?.activated_units, gameData?.active_side]);

  // Squads filtered for Left Squad Drawer
  const filteredSquadList = useMemo(() => {
    let list = panelUnits;
    if (rosterFilterSide !== "ALL") {
      list = list.filter((u) => u.side === rosterFilterSide);
    }
    const activatedSet = new Set(gameData?.activated_units || []);
    if (rosterStatusFilter === "READY") {
      list = list.filter((u) => {
        const dead = u.alive === false || (u.hp != null && u.hp <= 0);
        const isOwn = u.side === gameData?.active_side;
        return !dead && isOwn && !activatedSet.has(u.id);
      });
    } else if (rosterStatusFilter === "DONE") {
      list = list.filter((u) => {
        const dead = u.alive === false || (u.hp != null && u.hp <= 0);
        return !dead && activatedSet.has(u.id);
      });
    }
    if (squadSearchQuery.trim()) {
      const q = squadSearchQuery.toLowerCase().trim();
      list = list.filter((u) => {
        const def = unitImages[u.unit_key as keyof typeof unitImages];
        const label = (def?.label || u.unit_key || "").toLowerCase();
        const id = u.id.toLowerCase();
        return label.includes(q) || id.includes(q);
      });
    }
    return list;
  }, [panelUnits, rosterFilterSide, rosterStatusFilter, squadSearchQuery, gameData?.active_side, gameData?.activated_units]);

  // Units filtered for bottom dock roster
  const filteredRosterUnits = useMemo(() => {
    let list = panelUnits;
    if (rosterFilterSide !== "ALL") {
      list = list.filter((u) => u.side === rosterFilterSide);
    }
    if (rosterStatusFilter === "READY") {
      const activatedSet = new Set(gameData?.activated_units || []);
      list = list.filter((u) => {
        const dead = u.alive === false || (u.hp != null && u.hp <= 0);
        const isOwn = u.side === gameData?.active_side;
        return !dead && isOwn && !activatedSet.has(u.id);
      });
    } else if (rosterStatusFilter === "DONE") {
      const activatedSet = new Set(gameData?.activated_units || []);
      list = list.filter((u) => {
        const dead = u.alive === false || (u.hp != null && u.hp <= 0);
        return !dead && activatedSet.has(u.id);
      });
    }
    return list;
  }, [panelUnits, rosterFilterSide, rosterStatusFilter, gameData?.active_side, gameData?.activated_units]);

  // Balance of Power (VP Duel bar calculation)
  const vpScores = gameData?.vp_score_live || {};
  const sideKeys = scenarioSides.length >= 2 ? scenarioSides : Object.keys(vpScores);
  const sideA = sideKeys[0] || "US";
  const sideB = sideKeys[1] || "GE";
  const scoreA = Number(vpScores[sideA] || 0);
  const scoreB = Number(vpScores[sideB] || 0);
  const totalVp = scoreA + scoreB;
  const pctA = totalVp > 0 ? Math.round((scoreA / totalVp) * 100) : 50;
  const pctB = 100 - pctA;

  // Reaction Fire
  const pendingReaction = gameData?.pending_reaction || null;
  const pendingReactionReactor = pendingReaction?.reactor_id
    ? (gameData?.units || []).find((u: any) => String(u.id) === String(pendingReaction.reactor_id))
    : null;
  const pendingReactionTarget = pendingReaction?.target_id
    ? (gameData?.units || []).find((u: any) => String(u.id) === String(pendingReaction.target_id))
    : null;
  const pendingReactionReactorLabel = pendingReactionReactor
    ? unitImages[pendingReactionReactor.unit_key as keyof typeof unitImages]?.label ||
      pendingReactionReactor.unit_key ||
      pendingReaction.reactor_id
    : String(pendingReaction?.reactor_id || "Unknown");
  const pendingReactionTargetLabel = pendingReactionTarget
    ? unitImages[pendingReactionTarget.unit_key as keyof typeof unitImages]?.label ||
      pendingReactionTarget.unit_key ||
      pendingReaction.target_id
    : String(pendingReaction?.target_id || "Unknown");

  useEffect(() => {
    if (!pendingReaction) {
      lastReactionWindowRef.current = "";
      return;
    }
    const key = `${pendingReaction?.reactor_id || ""}->${pendingReaction?.target_id || ""}`;
    if (key && key !== lastReactionWindowRef.current) {
      addLog("combat", `⚡ Reaction fire available: ${pendingReactionReactorLabel} -> ${pendingReactionTargetLabel}`);
      lastReactionWindowRef.current = key;
    }
  }, [pendingReaction, pendingReactionReactorLabel, pendingReactionTargetLabel]);

  const handleResolveReaction = async (useReaction: boolean) => {
    if (!pendingReaction || reactionDecisionBusy) return;
    setReactionDecisionBusy(true);
    // Dismiss pending reaction immediately in local state so the grey backdrop modal disappears instantly on click
    setGameData((prev: any) => (prev ? { ...prev, pending_reaction: null } : prev));
    try {
      const res = await fetch(apiUrl("/api/game/reaction/resolve"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ use_reaction: useReaction }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(String(data?.detail || `HTTP ${res.status}`));
      }
      if (data?.state) {
        setGameData(data.state);
        if (typeof (window as any).__setGameState === "function") {
          (window as any).__setGameState(data.state);
        }
        gameController.updateState(data.state);
      }
      addLog(
        "combat",
        useReaction
          ? `⚡ Reaction Fire accepted: ${pendingReactionReactorLabel} -> ${pendingReactionTargetLabel}`
          : `⏭️ Reaction Fire skipped: ${pendingReactionReactorLabel}`
      );
    } catch (err) {
      console.error("❌ Reaction resolve failed", err);
      addLog("system", `❌ Reaction decision failed: ${String(err)}`);
    } finally {
      setReactionDecisionBusy(false);
    }
  };

  const isHumanTurn = gameData?.sides?.[gameData?.active_side] === "human";

  return (
    <div className="app">
      {/* ========================================================
          FULL BLEED CANVAS LAYER
      ======================================================== */}
      <div className="main">
        <div className="center">
          <GameCanvas
            gameData={gameData}
            setGameData={setGameData}
            selectedUnitId={selectedUnitId}
            setSelectedUnitId={setSelectedUnitId}
            availableMoves={availableMoves}
            setAvailableMoves={setAvailableMoves}
            setAttackHint={setAttackHint}
          />
        </div>
      </div>

      {/* ========================================================
          FLOATING HUD RESTORE BUTTON (WHEN HUD IS HIDDEN)
      ======================================================== */}
      {!hudVisible && (
        <button
          className="floating-hud-restore-btn"
          onClick={() => setHudVisible(true)}
          title="Restore Tactical HUD (H)"
        >
          👁 Show HUD [H]
        </button>
      )}

      {/* ========================================================
          TOP BATTLE HEADER RIBBON
      ======================================================== */}
      <header className={`battle-header-ribbon ${!hudVisible ? "hud-hidden" : ""}`}>
        {/* Ribbon Left: Brand & Match Setup */}
        <div className="ribbon-left">
          <div className="ribbon-brand">
            ⚡ ASSAULT <span>// EZv2</span>
          </div>

          <select
            className="ribbon-select"
            value={selectedScenario}
            onChange={(e) => handleScenarioChange(e.target.value)}
            title="Scenario"
            style={{ maxWidth: 210 }}
          >
            {scenarioList.map((scenarioId) => (
              <option key={scenarioId} value={scenarioId}>
                {SCENARIO_LABELS[scenarioId] || scenarioId}
              </option>
            ))}
          </select>

          <select
            className="ribbon-select"
            value={humanSide}
            onChange={(e) => setHumanSide(e.target.value)}
            title="Human Side"
            style={{ maxWidth: 125 }}
            disabled={!scenarioSides.length}
          >
            {!scenarioSides.length && <option value="">Sides...</option>}
            {scenarioSides.map((sideId) => (
              <option key={sideId} value={sideId}>
                Side: {sideId}
              </option>
            ))}
          </select>

          <button
            className={`btn-tactical ${activeMode === "human" ? "active" : ""}`}
            onClick={() => handleStartGame("human")}
            title="Human vs AI"
          >
            🎮 Human
          </button>

          <button
            className={`btn-tactical ${activeMode === "ai_vs_ai" ? "active" : ""}`}
            onClick={() => handleStartGame("ai_vs_ai")}
            title="AI vs AI Self-play"
          >
            🤖 AI vs AI
          </button>

          <button
            className={`btn-tactical ${activeMode === "replay" ? "active" : ""}`}
            onClick={() => handleStartGame("replay")}
            title="Replay Session"
          >
            🔁 Replay
          </button>

          <button
            className="btn-tactical btn-tactical-start"
            onClick={handleStartSelectedMode}
            disabled={!canStartGame}
            title="Start Match"
          >
            ▶ Start
          </button>

          <button
            className="btn-tactical btn-tactical-stop"
            onClick={handleStopGame}
            title="Reset Board"
          >
            ⛔ Stop
          </button>
        </div>

        {/* Ribbon Center: Turn, Phase, and Balance of Power */}
        <div className="ribbon-center">
          <div className="ribbon-turn-badge">
            <span>TURN</span>
            <span className="ribbon-turn-num">{gameData?.turn ?? "1"}</span>
            <span style={{ opacity: 0.4 }}>/</span>
            <div className={`ribbon-active-pill ${isHumanTurn ? "human" : "ai"}`}>
              <span className="ribbon-active-pulse" />
              <span>{gameData?.active_side || "-"} ({isHumanTurn ? "HUMAN" : "AI"})</span>
            </div>
          </div>

          {/* Tug-of-war VP Dominance bar */}
          <div
            className="ribbon-duel-vp"
            title={`Balance of Power: ${sideA} ${scoreA} VP (${pctA}%) vs ${sideB} ${scoreB} VP (${pctB}%)`}
          >
            <div className="vp-side-score side-a">
              <span className="vp-side-name">{sideA}</span>
              <span className="vp-side-val">{scoreA}</span>
            </div>
            <div className="vp-bar-track">
              <div className="vp-bar-fill-a" style={{ width: `${pctA}%` }} />
              <div className="vp-bar-fill-b" style={{ width: `${pctB}%` }} />
            </div>
            <div className="vp-side-score side-b">
              <span className="vp-side-val">{scoreB}</span>
              <span className="vp-side-name">{sideB}</span>
            </div>
          </div>

          {gameData?.victory_outcome && (
            <div style={{ fontSize: 11, color: "var(--neon-cyan)", fontFamily: "var(--font-mono)" }}>
              🚩 OBJ: {gameData.victory_outcome.captured}/{gameData.victory_outcome.objectives_total}
            </div>
          )}
        </div>

        {/* Ribbon Right: Turn Advance, Trace, Drawer Tabs & HUD Eye */}
        <div className="ribbon-right">
          <label style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 11, cursor: "pointer" }} title="Auto-advance AI turns">
            <input
              type="checkbox"
              checked={autoAdvanceAfterHuman}
              onChange={(e) => handleToggleAutoAdvance(e.target.checked)}
              style={{ accentColor: "var(--neon-cyan)" }}
            />
            <span style={{ color: "var(--text-muted)" }}>Auto</span>
          </label>

          <button
            className="btn-tactical"
            onClick={handleManualAdvance}
            disabled={autoAdvanceAfterHuman || !waitingForManualAdvance}
            title="Step next AI action"
            style={{ padding: "4px 10px", fontSize: 11 }}
          >
            ▶ Step
          </button>

          <button
            className="btn-tactical"
            onClick={handleExportTrace}
            title="Download backend match telemetry trace"
            style={{ padding: "4px 8px" }}
          >
            💾
          </button>

          {/* Drawer trigger buttons */}
          <button
            className={`ribbon-drawer-btn ${bottomUnitsOpen ? "active" : ""}`}
            onClick={() => setBottomUnitsOpen((prev) => !prev)}
            title="Toggle Bottom Units Dock [U]"
          >
            🎖️ Units ({panelUnits.length})
          </button>
          <button
            className={`ribbon-drawer-btn ${sidebarOpen && activeSidebarTab === "combat" ? "active" : ""}`}
            onClick={() => {
              if (sidebarOpen && activeSidebarTab === "combat") setSidebarOpen(false);
              else { setActiveSidebarTab("combat"); setSidebarOpen(true); }
            }}
            title="Combat & Dice Rolls"
          >
            🎲 Combat
            {stickyCombatEvent && <span className="ribbon-drawer-badge">!</span>}
          </button>

          <button
            className={`ribbon-drawer-btn ${sidebarOpen && activeSidebarTab === "log" ? "active" : ""}`}
            onClick={() => {
              if (sidebarOpen && activeSidebarTab === "log") setSidebarOpen(false);
              else { setActiveSidebarTab("log"); setSidebarOpen(true); }
            }}
            title="Battle Log"
          >
            📜 Log ({logEvents.length})
          </button>

          <button
            className={`ribbon-drawer-btn ${sidebarOpen && activeSidebarTab === "ai" ? "active" : ""}`}
            onClick={() => {
              if (sidebarOpen && activeSidebarTab === "ai") setSidebarOpen(false);
              else { setActiveSidebarTab("ai"); setSidebarOpen(true); }
            }}
            title="EfficientZero V2 Brain"
          >
            🧠 AI
          </button>

          <button
            className={`ribbon-drawer-btn ${sidebarOpen && activeSidebarTab === "rag" ? "active" : ""}`}
            onClick={() => {
              if (sidebarOpen && activeSidebarTab === "rag") setSidebarOpen(false);
              else { setActiveSidebarTab("rag"); setSidebarOpen(true); }
            }}
            title="Rules & Tactics Advisor"
          >
            📚 Rules
          </button>

          {/* Immersive HUD Eye Toggle */}
          <button
            className="hud-eye-btn"
            onClick={() => setHudVisible(false)}
            title="Hide HUD for clean map view [H]"
          >
            👁
          </button>
        </div>
      </header>


      {/* Floating Left Action Selector Toggle Button */}
      <button
        className={`left-squad-toggle-btn ${squadDrawerOpen ? "active" : ""}`}
        onClick={() => setSquadDrawerOpen((prev) => !prev)}
        title="Toggle Tactical Action Selector [A / S]"
      >
        <span style={{ fontSize: "14px" }}>⚡</span>
        <span>ACTIONS</span>
        {selectedUnit ? (
          <span className="left-squad-toggle-count">{availableMoves.length} ORDERS</span>
        ) : (
          <span className="left-squad-toggle-count">{readyCount} READY</span>
        )}
      </button>

      {/* Left Tactical Command Panel (Positioned in user's red box area) */}
      <aside className={`left-squad-drawer ${squadDrawerOpen && hudVisible ? "drawer-open" : ""}`}>
        {/* Header */}
        <div className="left-squad-header">
          {selectedUnit ? (
            <>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <span style={{ fontSize: "15px" }}>⚡</span>
                <span className="left-squad-header-title">UNIT ORDERS</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                <span
                  className={`trooper-card-status-badge badge-${
                    selectedUnit.alive === false || (selectedUnit.hp != null && selectedUnit.hp <= 0)
                      ? "dead"
                      : selectedUnit.side !== gameData?.active_side
                      ? "enemy"
                      : (gameData?.activated_units || []).includes(selectedUnit.id)
                      ? "done"
                      : "ready"
                  }`}
                >
                  {selectedUnit.alive === false || (selectedUnit.hp != null && selectedUnit.hp <= 0)
                    ? "KIA"
                    : selectedUnit.side !== gameData?.active_side
                    ? "OPFOR"
                    : (gameData?.activated_units || []).includes(selectedUnit.id)
                    ? "✓ DONE"
                    : "● READY"}
                </span>
                <button
                  className="drawer-close-btn"
                  onClick={() => setSquadDrawerOpen(false)}
                  title="Close Orders Panel [Esc]"
                >
                  ✕
                </button>
              </div>
            </>
          ) : (
            <>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <span style={{ fontSize: "16px" }}>⚡</span>
                <span className="left-squad-header-title">ACTION SELECTOR</span>
                <span className="roster-header-badge badge-ready">🟢 {readyCount} READY</span>
              </div>
              <button
                className="drawer-close-btn"
                onClick={() => setSquadDrawerOpen(false)}
                title="Close Action Selector [Esc]"
              >
                ✕
              </button>
            </>
          )}
        </div>

        {/* Panel Body */}
        {selectedUnit ? (
          /* ========================================================
             TACTICAL ACTION SELECTOR FOR ACTIVE SELECTED SQUAD
          ======================================================== */
          <div className="left-unit-command-view">
            {/* Clean Unit Intel Card (No overlapping spec-stats) */}
            <div className="left-unit-intel-card">
              <div className="left-unit-intel-row">
                <div className="left-unit-avatar-box">
                  {selectedUnitSpec?.full && (
                    <img
                      src={encodeURI(selectedUnitSpec.full)}
                      className="left-unit-avatar-img"
                      alt={selectedUnitSpec?.label || selectedUnit.unit_key}
                    />
                  )}
                  {selectedWaitOrder && isHumanTurn && !(gameData?.activated_units || []).includes(selectedUnit.id) && (
                    <button
                      className="spec-wait-btn"
                      onClick={() => {
                        void executeActionById(selectedWaitOrder.action_id, selectedWaitOrder);
                      }}
                      title="Wait / End unit activation"
                    >
                      ⏸ WAIT
                    </button>
                  )}
                </div>

                <div className="left-unit-details">
                  <div className="left-unit-name" title={selectedUnitSpec?.label || selectedUnit.unit_key}>
                    {selectedUnitSpec?.label || selectedUnit.unit_key}
                  </div>
                  <div className="left-unit-meta-row">
                    <span>ID: {selectedUnit.id}</span>
                    <span>Coords: {formatCoords(selectedUnit.q, selectedUnit.r)}</span>
                    <span
                      style={{
                        fontWeight: 700,
                        color: selectedUnit.side === "GE" ? "var(--neon-red)" : "var(--neon-cyan)",
                      }}
                    >
                      {sides[selectedUnit.side]?.label || selectedUnit.side}
                    </span>
                  </div>

                  {/* Operational Health Bar */}
                  {selectedUnit.health_pct != null && (
                    <div className="left-unit-health-wrap">
                      <div className="health-labels">
                        <span>Health:</span>
                        <strong
                          style={{
                            color:
                              selectedUnit.health_pct > 0.6
                                ? "#4ade80"
                                : selectedUnit.health_pct > 0.35
                                ? "#fbbf24"
                                : "#f87171",
                          }}
                        >
                          {Math.round(selectedUnit.health_pct * 100)}% ({selectedUnit.hp} /{" "}
                          {selectedUnit.max_hp ?? selectedUnit.hp} HP)
                        </strong>
                      </div>
                      <div className="deck-unit-health-bar">
                        <div
                          className="deck-unit-health-fill"
                          style={{
                            width: `${Math.round(selectedUnit.health_pct * 100)}%`,
                            background:
                              selectedUnit.health_pct > 0.6
                                ? "linear-gradient(90deg, #16a34a, #22c55e)"
                                : selectedUnit.health_pct > 0.35
                                ? "linear-gradient(90deg, #d97706, #f59e0b)"
                                : "linear-gradient(90deg, #dc2626, #ef4444)",
                          }}
                        />
                      </div>
                    </div>
                  )}

                  {/* Trait Badges */}
                  <div className="left-unit-traits-row">
                    {(selectedUnit.has_indirect_fire || selectedUnit.tactical_role === "indirect_mortar") && (
                      <span className="deck-unit-badge mortar">💥 Mortar</span>
                    )}
                    {(selectedUnit.is_suppression_mg || selectedUnit.tactical_role === "suppression_mg") && (
                      <span className="deck-unit-badge mg">🛡️ HMG</span>
                    )}
                    {(selectedUnit.is_assault_squad || selectedUnit.tactical_role === "assault_squad") && (
                      <span className="deck-unit-badge assault">⚔️ Assault</span>
                    )}
                  </div>
                </div>
              </div>
            </div>

            {/* Tactical Actions List */}
            <div className="left-unit-orders-container">
              <DispatchedOrdersPanel
                availableMoves={availableMoves}
                selectedUnitId={selectedUnitId}
                isHumanTurn={isHumanTurn}
                onHoverOrder={(order) => setHoveredTargetId(resolveOrderTargetId(order))}
                onLeaveOrder={() => setHoveredTargetId(null)}
              />
              {attackHint && (
                <div
                  style={{
                    marginTop: 6,
                    padding: "6px 8px",
                    fontSize: 10.5,
                    border: "1px solid rgba(255, 80, 80, 0.35)",
                    background: "rgba(255, 60, 60, 0.12)",
                    color: "#ffd6d6",
                    borderRadius: 4,
                    fontFamily: "var(--font-mono)",
                  }}
                >
                  {attackHint}
                </div>
              )}
            </div>

            <div className="left-unit-footer">
              <button
                className="left-squad-switch-btn"
                onClick={() => {
                  setSelectedUnitId(null);
                  setAvailableMoves([]);
                }}
              >
                ✕ Deselect Unit [Esc]
              </button>
            </div>
          </div>
        ) : (
          /* ========================================================
             WHEN NO UNIT IS SELECTED: CLEAN TACTICAL AWAITING VIEW
          ======================================================== */
          <div className="left-action-awaiting">
            <div className="radar-circle"></div>
            <div className="awaiting-title">⚡ ACTION SELECTOR</div>
            <div className="awaiting-subtitle">Awaiting Squad Selection</div>
            <p className="awaiting-text">
              Select any tactical unit on the battlefield map to inspect its profile and deploy tactical orders.
            </p>
            <div className="awaiting-status-box">
              <div className="awaiting-status-row">
                <span className="awaiting-status-label">Active Turn Side:</span>
                <span
                  className="awaiting-status-val"
                  style={{ color: gameData?.active_side === "GE" ? "var(--neon-red)" : "var(--neon-cyan)" }}
                >
                  {sides[gameData?.active_side]?.label || gameData?.active_side || "—"}
                </span>
              </div>
              <div className="awaiting-status-row">
                <span className="awaiting-status-label">Ready to Act:</span>
                <span className="awaiting-status-val ready">🟢 {readyCount} Squads</span>
              </div>
              <div className="awaiting-status-row">
                <span className="awaiting-status-label">Turn Completed:</span>
                <span className="awaiting-status-val done">⚪ {doneCount} Squads</span>
              </div>
            </div>
            <div className="awaiting-hint-tip">
              💡 Tip: Click any unit directly on the hexagonal map to immediately focus and open its orders.
            </div>
          </div>
        )}
      </aside>

      {/* ========================================================
          SIDE TACTICAL DRAWER (SLIDE-OUT)
      ======================================================== */}
      <aside className={`side-tactical-drawer ${sidebarOpen ? "drawer-open" : ""}`}>
        <div className="drawer-header">
          <div className="drawer-tabs">
            <button
              className={`drawer-tab-btn ${activeSidebarTab === "combat" ? "active" : ""}`}
              onClick={() => setActiveSidebarTab("combat")}
            >
              🎲 Combat
            </button>
            <button
              className={`drawer-tab-btn ${activeSidebarTab === "log" ? "active" : ""}`}
              onClick={() => setActiveSidebarTab("log")}
            >
              📜 Log
            </button>
            <button
              className={`drawer-tab-btn ${activeSidebarTab === "ai" ? "active" : ""}`}
              onClick={() => {
                setActiveSidebarTab("ai");
                fetchTelemetry();
              }}
            >
              🧠 AI Brain
            </button>
            <button
              className={`drawer-tab-btn ${activeSidebarTab === "rag" ? "active" : ""}`}
              onClick={() => setActiveSidebarTab("rag")}
            >
              📚 Advisor
            </button>
          </div>
          <button
            className="drawer-close-btn"
            onClick={() => setSidebarOpen(false)}
            title="Close Drawer [Esc]"
          >
            ✕
          </button>
        </div>

        <div className="drawer-body">
          {activeSidebarTab === "combat" && (
            <div>
              {stickyCombatEvent ? (
                <CombatPanel event={stickyCombatEvent} units={gameData?.units || []} />
              ) : (
                <div style={{ textAlign: "center", padding: "40px 10px", color: "var(--text-muted)", fontStyle: "italic", fontSize: 13 }}>
                  No recent combat engagements.<br />
                  Deploy an attack order to observe combat resolution and dice rolls.
                </div>
              )}
            </div>
          )}

          {activeSidebarTab === "log" && (
            <div className="log-container">
              {logEvents.length > 0 ? (
                logEvents.map((log, index) => (
                  <div key={index} className={`log-entry log-${log.type}`}>
                    <span className="log-time">[{log.time}]</span>
                    <span className="log-text">{log.text}</span>
                  </div>
                ))
              ) : (
                <div style={{ fontSize: "12px", color: "var(--text-muted)", fontStyle: "italic", textAlign: "center", padding: "20px" }}>
                  Awaiting battlefield events...
                </div>
              )}
            </div>
          )}

          {activeSidebarTab === "ai" && (
            <EfficientZeroV2TelemetryPanel
              telemetry={telemetry || gameData?.telemetry}
              onRefreshTelemetry={fetchTelemetry}
            />
          )}

          {activeSidebarTab === "rag" && (
            <RagAssistantPanel gameData={gameData} />
          )}
        </div>
      </aside>

      {/* Drawer click-away backdrop on smaller screens */}
      {sidebarOpen && <div className="drawer-backdrop" onClick={() => setSidebarOpen(false)} />}

      {/* Unit card tooltip preview on hover */}
      {cardPreview && (
        <UnitCardTooltip
          key={cardPreview.unit.id}
          unitKey={cardPreview.unit.unit_key}
          hp={cardPreview.unit.hp}
          anchorX={cardPreview.x}
          anchorY={cardPreview.y}
        />
      )}

      {/* ========================================================
          REACTION FIRE MODAL
      ======================================================== */}
      {pendingReaction && !reactionDecisionBusy && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.55)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 100,
          }}
        >
          <div
            style={{
              width: 480,
              maxWidth: "92vw",
              background: "rgba(8, 10, 18, 0.96)",
              border: "1px solid rgba(0, 240, 255, 0.4)",
              boxShadow: "0 0 32px rgba(0, 240, 255, 0.3)",
              borderRadius: 8,
              padding: 20,
            }}
          >
            <div
              style={{
                fontFamily: "var(--font-tech)",
                fontSize: 16,
                letterSpacing: 1.5,
                marginBottom: 12,
                color: "var(--neon-cyan)",
              }}
            >
              ⚡ REACTION FIRE OPPORTUNITY
            </div>
            <div style={{ fontSize: 13, lineHeight: 1.6, color: "var(--text-primary)", marginBottom: 18 }}>
              Enemy movement triggered a reaction fire opportunity.<br />
              Reactor: <b>{pendingReactionReactorLabel}</b><br />
              Target: <b>{pendingReactionTargetLabel}</b>
            </div>
            <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
              <button
                className="btn-tactical"
                onClick={() => void handleResolveReaction(false)}
                disabled={reactionDecisionBusy}
              >
                ⏭ Skip
              </button>
              <button
                className="btn-tactical btn-tactical-start"
                onClick={() => void handleResolveReaction(true)}
                disabled={reactionDecisionBusy}
              >
                ⚡ Use Reaction Fire
              </button>
            </div>
          </div>
        </div>
      )}
            {/* ========================================================
          BOTTOM UNITS DOCK (ORDER OF BATTLE) - DOCKED LIKE ACTIONS
      ======================================================== */}
      {hudVisible && (
        <aside
          className={`bottom-units-dock ${bottomUnitsOpen ? "dock-open" : "dock-collapsed"} ${
            squadDrawerOpen ? "with-left-drawer" : "full-width"
          }`}
        >
          <div
            className="bottom-units-header"
            onClick={() => setBottomUnitsOpen((prev) => !prev)}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
              <span style={{ fontSize: "15px" }}>🎖️</span>
              <span className="bottom-units-header-title">ORDER OF BATTLE / UNITS</span>
              <span className="roster-header-badge badge-ready">🟢 {readyCount} READY</span>
              {doneCount > 0 && (
                <span
                  className="roster-header-badge badge-done"
                  style={{
                    background: "rgba(168, 85, 247, 0.2)",
                    borderColor: "rgba(168, 85, 247, 0.4)",
                    color: "#c084fc",
                  }}
                >
                  ✓ {doneCount} DONE
                </span>
              )}
              <span className="left-squad-toggle-count">{panelUnits.length} UNITS</span>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <button
                className="drawer-close-btn"
                onClick={(e) => {
                  e.stopPropagation();
                  setBottomUnitsOpen((prev) => !prev);
                }}
                title={bottomUnitsOpen ? "Collapse Units Dock [U]" : "Expand Units Dock [U]"}
                style={{ fontSize: "13px", width: "26px", height: "26px" }}
              >
                {bottomUnitsOpen ? "▼" : "▲"}
              </button>
            </div>
          </div>

          {bottomUnitsOpen && (
            <div className="bottom-units-body">
              <UnitStatePanel
                units={panelUnits}
                activeSide={gameData?.active_side}
                activatedUnits={gameData?.activated_units || []}
                selectedUnitId={selectedUnitId}
                targetUnitId={hoveredTargetId}
                onSelectUnit={(unit: Unit) => {
                  setSelectedUnitId(unit.id);
                  if (typeof (window as any).onUnitClick === "function") {
                    (window as any).onUnitClick(unit);
                  }
                }}
              />
            </div>
          )}
        </aside>
      )}

    </div>
  );
}

export default App;