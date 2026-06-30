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
import { RagSituationPanel } from "./game/ui/RagSituationPanel";
import { RagRulesPanel } from "./game/ui/RagRulesPanel";
import { DraggableWindow } from "./game/ui/DraggableWindow";
import { logCombatEvents } from "./game/systems/combatLog";
import { getUnitActionMarker } from "./game/state/actionMarkers";
import { apiUrl } from "./config/backend";

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
  q: number;
  r: number;
};

function App() {
  const floatWindowIds = [
    "tactical-intel",
    "tactical-log",
    "tactical-situation",
    "tactical-rules",
    "tactical-status",
    "tactical-units",
    "tactical-dice",
  ] as const;
  const [gameData, setGameData] = useState<any>(null);
  const [deadUnits, setDeadUnits] = useState<Unit[]>([]);
  const [selectedUnitId, setSelectedUnitId] = useState<string | null>(null);
  const [hoveredTargetId, setHoveredTargetId] = useState<string | null>(null);
  const [availableMoves, setAvailableMoves] = useState<any[]>([]);
  const [attackHint, setAttackHint] = useState<string | null>(null);
  const [logEvents, setLogEvents] = useState<LogEntry[]>([]);
  const [activeMode, setActiveMode] = useState<string | null>(null);
  const [scenarioList, setScenarioList] = useState<string[]>([]);
  const [selectedScenario, setSelectedScenario] = useState<string>("");
  const [scenarioSides, setScenarioSides] = useState<string[]>([]);
  const [humanSide, setHumanSide] = useState<string>("");
  const [reactionDecisionBusy, setReactionDecisionBusy] = useState(false);
  const [stickyCombatEvent, setStickyCombatEvent] = useState<any>(null);
  const [autoAdvanceAfterHuman, setAutoAdvanceAfterHuman] = useState(true);
  const [waitingForManualAdvance, setWaitingForManualAdvance] = useState(false);

  const lastTurnRef = useRef<number>(-1);
  const lastActiveSideRef = useRef<string>("");
  const lastDoneRef = useRef<boolean>(false);
  const lastReactionWindowRef = useRef<string>("");
  const prevUnitsRef = useRef<Unit[] | null>(null);

  // Helper to add structured log events
  const addLog = (type: string, text: string) => {
    const time = new Date().toLocaleTimeString([], { 
      hour: "2-digit", 
      minute: "2-digit", 
      second: "2-digit" 
    });
    setLogEvents((prev) => [{ type, text, time }, ...prev].slice(0, 50));
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
    const sides = scenarioSides;
    if (!sides.length) return {};
    const chosenHumanSide = humanSide || sides[0];
    const cfg: Record<string, string> = {};
    for (const s of sides) {
      cfg[s] = mode === "ai_vs_ai" ? "ai" : (s === chosenHumanSide ? "human" : "ai");
    }
    return cfg;
  };

  // Subscribe to the game controller events
  useEffect(() => {
    (window as any).gameController = gameController;
    const unsubscribeState = gameController.subscribe((state: any) => {
      setGameData(state);
    });
    const unsubscribeTurnFlow = gameController.subscribeTurnFlow((flow) => {
      setAutoAdvanceAfterHuman(Boolean(flow?.autoAdvanceAfterHuman));
      setWaitingForManualAdvance(Boolean(flow?.waitingForManualAdvance));
    });

    (window as any).logSystemEvent = (type: string, text: string) => {
      addLog(type, text);
    };

    addLog("system", "🖥️ Tactical Control System initialized. Ready to launch.");

    return () => {
      unsubscribeState?.();
      unsubscribeTurnFlow?.();
      (window as any).logSystemEvent = undefined;
      (window as any).gameController = undefined;
    };
  }, []);

  useEffect(() => {
    const loadScenarioSides = async () => {
      if (!selectedScenario) return;
      try {
        const res = await fetch(apiUrl(`/api/ui/scenarios/${selectedScenario}`));
        if (!res.ok) {
          throw new Error(`Failed to load scenario data (${res.status})`);
        }
        const data = await res.json();
        const sidesFound = Array.from(
          new Set(
            (data?.units || [])
              .map((u: any) => String(u?.side || "").toUpperCase())
              .filter((s: string) => s.length > 0)
          )
        ) as string[];
        const normalizedSides = sidesFound.length ? sidesFound : ["GE", "US"];
        setScenarioSides(normalizedSides);
        setHumanSide((prev) => (prev && normalizedSides.includes(prev) ? prev : normalizedSides[0]));
      } catch (err) {
        console.error("❌ Could not load scenario sides", err);
        setScenarioSides(["GE", "US"]);
        setHumanSide((prev) => prev || "GE");
      }
    };
    loadScenarioSides();
  }, [selectedScenario]);

  useEffect(() => {
    const loadScenarios = async () => {
      try {
        const res = await fetch(apiUrl("/api/ui/scenarios"));
        if (!res.ok) {
          throw new Error(`Failed to load scenarios (${res.status})`);
        }
        const data = await res.json();
        const scenarios = Array.isArray(data?.scenarios) ? data.scenarios : [];
        setScenarioList(scenarios);
        if (scenarios.length > 0) {
          setSelectedScenario((prev) => prev || scenarios[0]);
        }
      } catch (err) {
        console.error("❌ Could not load scenarios", err);
        addLog("system", `❌ Could not load scenarios: ${String(err)}`);
      }
    };
    loadScenarios();
  }, []);

  // Monitor game state changes to output beautiful terminal logs
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

  // Emit a single explicit end-of-match log when done flips false -> true.
  useEffect(() => {
    if (!gameData) return;
    const doneNow = Boolean(gameData?.done);
    if (doneNow && !lastDoneRef.current) {
      const winner = gameData?.winner ? String(gameData.winner) : "Draw";
      const reason = String(gameData?.end_reason || "completed");
      addLog("system", `🏁 Match ended: ${winner} (${reason})`);
    }
    lastDoneRef.current = doneNow;
  }, [gameData?.done, gameData?.winner, gameData?.end_reason]);

  // If active side is not human, clear any stale human selection/orders.
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
  useEffect(() => {
    if (selectedUnitId) {
      const unit = gameData?.units?.find((u: any) => u.id === selectedUnitId);
      const label = unit ? (unitImages[unit.unit_key as keyof typeof unitImages]?.label || unit.unit_key) : "";
      addLog("select", `🟢 Target locked: ${selectedUnitId} [${label}]`);
    }
  }, [selectedUnitId, gameData]);

  // Log combat results (damage + dice used) to the System Log.
  // Logging is deduped by event id in combatLog, so it is safe even if the
  // same events arrive through multiple state updates.
  useEffect(() => {
    logCombatEvents(gameData?.last_events, gameData?.units || []);
  }, [gameData]);

  // Keep last combat dice/result visible until a new combat action arrives.
  useEffect(() => {
    const events = gameData?.last_events || [];
    const latest = events.slice().reverse().find((event: any) => event?.type === "ACTION_EFFECT");
    if (latest) {
      setStickyCombatEvent(latest);
    }
  }, [gameData?.last_events]);

  // Log VP ownership changes.
  useEffect(() => {
    const events = gameData?.last_events || [];
    for (const event of events) {
      if (event?.type !== "VP_CAPTURED") continue;
      const p = event.payload || {};
      const coords =
        p.q != null && p.r != null
          ? formatCoords(Number(p.q), Number(p.r))
          : "[?]";
      const newOwner = p.new_owner || "NONE";
      const prevOwner = p.previous_owner || "NONE";
      const value = Number(p.value || 0);
      addLog(
        "turn",
        `🏁 VP ${coords} ${prevOwner} -> ${newOwner} (+${value})`
      );
    }
  }, [gameData?.last_events]);

  // Log reaction decision windows and outcomes explicitly.
  useEffect(() => {
    const events = gameData?.last_events || [];
    for (const event of events) {
      const p = event?.payload || {};
      if (event?.type === "REACTION_WINDOW") {
        addLog("combat", `⏸️ Reaction window: ${String(p.reactor_id || "?")} can react to ${String(p.target_id || "?")}`);
      } else if (event?.type === "REACTION_FIRE_SKIPPED") {
        addLog("combat", `⏭️ Reaction skipped: ${String(p.reactor_id || "?")}`);
      }
    }
  }, [gameData?.last_events]);

  // Keep dead units visible in the roster even if they disappear from the map state
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

      // Backend used to drop dead units entirely; keep last snapshot if they vanish
      for (const prevUnit of previousUnits) {
        if (!currentIds.has(prevUnit.id)) {
          nextDeadMap.set(prevUnit.id, { ...prevUnit, hp: 0 });
        }
      }

      return Array.from(nextDeadMap.values());
    });

    prevUnitsRef.current = currentUnits;
  }, [gameData]);

  // Resolve which enemy unit an attack order is targeting, so we can
  // highlight it in the roster on hover.
  const resolveOrderTargetId = (order: any): string | null => {
    if (!order) return null;
    const actionType = String(order.type || order.kind || "").toUpperCase();
    const isAttack =
      order.kind === "attack" ||
      /RANGED|ASSAULT|ATTACK|REACTION|COMBAT|FIRE/.test(actionType);
    if (!isAttack) return null;

    if (order.target_id) return order.target_id;

    const q = order.target_q ?? order.q;
    const r = order.target_r ?? order.r;
    if (q == null || r == null) return null;

    const unit = (gameData?.units || []).find(
      (u: any) => u.q === q && u.r === r
    );
    return unit?.id ?? null;
  };

  // Action card trigger handler
  const handleActionCardClick = (action: any) => {
    if (typeof (window as any).onHexClick === "function") {
      const targetQ = action.q ?? action.target_q;
      const targetR = action.r ?? action.target_r;
      const actionType = action.kind === "attack" 
        ? (action.type ? action.type.toUpperCase() : "ATTACK")
        : "MOVE";
      const coordStr = targetQ != null && targetR != null ? formatCoords(targetQ, targetR) : "?";
      
      (window as any).logSystemEvent?.("move", `👤 Human Order: ${actionType} to hex ${coordStr}`);
      addLog("move", `👉 Order dispatched: ${actionType} to hex ${coordStr}`);
      
      if (targetQ != null && targetR != null) {
        (window as any).onHexClick(targetQ, targetR);
      } else {
        console.warn("⛔ Missing target coordinates for action", action);
      }
    }
  };

  // Start a game mode safely and log it
  const handleStartGame = (mode: string) => {
    if (!selectedScenario) {
      addLog("system", "❌ No scenario selected");
      return;
    }
    if (!scenarioSides.length) {
      addLog("system", "❌ Scenario sides are still loading. Please wait.");
      return;
    }
    if (!humanSide || !scenarioSides.includes(humanSide)) {
      addLog("system", "❌ Invalid human side for selected scenario.");
      return;
    }
    setActiveMode(mode);
    addLog(
      "system",
      `🚀 Launching match mode: [${mode.toUpperCase()}] // Scenario: ${selectedScenario} // Human: ${humanSide || "-"}`
    );
    // Force an initial camera fit for the next valid map state.
    (window as any).__forceInitialCameraFit = true;
    resetMatchUiState();
    gameController.start(
      mode as any,
      selectedScenario,
      buildSidesConfig(mode)
    );
  };

  const handleScenarioChange = (scenarioId: string) => {
    setSelectedScenario(scenarioId);
    // Avoid showing stale side options while new scenario metadata is loading.
    setScenarioSides([]);
    setHumanSide("");
    if (!scenarioId) return;
    addLog("system", `🗺️ Scenario changed: ${scenarioId}. Loading scenario metadata...`);
    resetMatchUiState();
  };

  // Safe handler to stop and refresh the session
  const handleStopGame = () => {
    addLog("system", "⛔ Terminating active session. Resetting control board...");
    setTimeout(() => {
      window.location.reload();
    }, 800);
  };

  const handleStartSelectedMode = () => {
    const modeToUse = activeMode || "human";
    handleStartGame(modeToUse);
  };

  const canStartGame = Boolean(
    selectedScenario &&
    scenarioSides.length > 0 &&
    humanSide &&
    scenarioSides.includes(humanSide)
  );

  const handleExportTrace = async () => {
    try {
      const res = await fetch(apiUrl("/api/game/trace?limit=50000"));
      if (!res.ok) {
        throw new Error(`Trace export failed (${res.status})`);
      }
      const payload = await res.json();
      const stamp = new Date().toISOString().replace(/[:.]/g, "-");
      const scenario = String(gameData?.scenario_name || selectedScenario || "scenario");
      const fileName = `trace_export_${scenario}_${stamp}.json`;
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json;charset=utf-8" });
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

  const handleSaveLayout = () => {
    try {
      window.dispatchEvent(new Event("assault:save-layout"));
      localStorage.setItem("assault.layout.savedAt", new Date().toISOString());
      addLog("system", "💾 Layout guardado (ventanas + panel de unidades).");
    } catch (err) {
      addLog("system", `❌ No se pudo guardar layout: ${String(err)}`);
    }
  };

  const handleResetLayout = () => {
    try {
      const keysToRemove: string[] = [];
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (!key) continue;
        if (key.startsWith("assault.window.") || key === "assault.units.layoutMode" || key === "assault.layout.savedAt") {
          keysToRemove.push(key);
        }
      }
      for (const key of keysToRemove) {
        localStorage.removeItem(key);
      }
      addLog("system", "♻️ Layout reseteado. Recargando interfaz...");
      setTimeout(() => window.location.reload(), 250);
    } catch (err) {
      addLog("system", `❌ No se pudo resetear layout: ${String(err)}`);
    }
  };

  const handleMapMode = () => {
    try {
      window.dispatchEvent(
        new CustomEvent("assault:set-window-state", {
          detail: { windowId: "*", minimized: true, visible: true },
        })
      );
      addLog("system", "🗺️ Modo Mapa: ventanas minimizadas.");
    } catch (err) {
      addLog("system", `❌ No se pudo activar Modo Mapa: ${String(err)}`);
    }
  };

  const handleToggleAutoAdvance = (enabled: boolean) => {
    gameController.setAutoAdvanceAfterHuman(enabled);
    addLog(
      "system",
      enabled
        ? "▶ Autoavance activado: la IA continua automaticamente tras tu accion."
        : "⏸ Autoavance desactivado: pulsa Avanzar para continuar tras tu accion."
    );
  };

  const handleManualAdvance = () => {
    gameController.continueAfterHumanAction();
    addLog("system", "▶ Avance manual solicitado: continuando turno de IA.");
  };

  // Find active specifications of the selected troop
  const selectedUnit = gameData?.units?.find((u: Unit) => u.id === selectedUnitId);
  const selectedUnitSpec = selectedUnit 
    ? unitImages[selectedUnit.unit_key as keyof typeof unitImages] 
    : null;
  const selectedUnitActionMarker = selectedUnit
    ? getUnitActionMarker(selectedUnit.id)
    : null;
  const selectedWaitOrder = selectedUnit
    ? (availableMoves || []).find((m: any) => m?.kind === "wait" && m?.action_id)
    : null;

  const executeActionById = async (actionId: string, order?: any) => {
    const activeSideNow = gameData?.active_side;
    const isHumanTurnNow = gameData?.sides?.[activeSideNow] === "human";
    if (!isHumanTurnNow) {
      return;
    }
    try {
      const executed = await (window as any).onExecuteOrder?.(order || { action_id: actionId });
      if (executed) return;
      // Avoid direct fallback POST here. onExecuteOrder is the single
      // execution path to prevent stale/double-dispatched action_ids.
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

  const pendingReaction = gameData?.pending_reaction || null;
  const pendingReactionReactor =
    pendingReaction?.reactor_id
      ? (gameData?.units || []).find((u: any) => String(u.id) === String(pendingReaction.reactor_id))
      : null;
  const pendingReactionTarget =
    pendingReaction?.target_id
      ? (gameData?.units || []).find((u: any) => String(u.id) === String(pendingReaction.target_id))
      : null;
  const pendingReactionReactorLabel = pendingReactionReactor
    ? (unitImages[pendingReactionReactor.unit_key as keyof typeof unitImages]?.label || pendingReactionReactor.unit_key || pendingReaction.reactor_id)
    : String(pendingReaction?.reactor_id || "Unknown");
  const pendingReactionTargetLabel = pendingReactionTarget
    ? (unitImages[pendingReactionTarget.unit_key as keyof typeof unitImages]?.label || pendingReactionTarget.unit_key || pendingReaction.target_id)
    : String(pendingReaction?.target_id || "Unknown");

  useEffect(() => {
    if (!pendingReaction) {
      lastReactionWindowRef.current = "";
      return;
    }
    const key = `${pendingReaction?.reactor_id || ""}->${pendingReaction?.target_id || ""}`;
    if (key && key !== lastReactionWindowRef.current) {
      addLog("combat", `⚡ Reacción disponible: ${pendingReactionReactorLabel} -> ${pendingReactionTargetLabel}`);
      lastReactionWindowRef.current = key;
    }
  }, [pendingReaction, pendingReactionReactorLabel, pendingReactionTargetLabel]);

  const handleResolveReaction = async (useReaction: boolean) => {
    if (!pendingReaction || reactionDecisionBusy) return;
    setReactionDecisionBusy(true);
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
      if (data?.state && typeof (window as any).__setGameState === "function") {
        (window as any).__setGameState(data.state);
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

  return (
    <div className="app">
      {/* =========================
          TACTICAL HEADER
      ========================= */}
      <div className="header">
        <div className="header-title">
          ⚡ ASSAULT AI <span>// COMMAND INTERFACE v1.2</span>
        </div>

        <div className="header-controls">
          <select
            className="btn-tactical"
            value={selectedScenario}
            onChange={(e) => handleScenarioChange(e.target.value)}
            title="Scenario"
            style={{ minWidth: 240 }}
          >
            {scenarioList.map((scenarioId) => (
              <option key={scenarioId} value={scenarioId}>
                {scenarioId}
              </option>
            ))}
          </select>

          <select
            className="btn-tactical"
            value={humanSide}
            onChange={(e) => setHumanSide(e.target.value)}
            title="Human side"
            style={{ minWidth: 140 }}
            disabled={!scenarioSides.length}
          >
            {!scenarioSides.length && (
              <option value="">Loading sides...</option>
            )}
            {scenarioSides.map((sideId) => (
              <option key={sideId} value={sideId}>
                Human: {sideId}
              </option>
            ))}
          </select>

          <button 
            className={`btn-tactical ${activeMode === "human" ? "active" : ""}`} 
            onClick={() => handleStartGame("human")}
          >
            🎮 Human vs AI
          </button>

          <button 
            className={`btn-tactical ${activeMode === "ai_vs_ai" ? "active" : ""}`} 
            onClick={() => handleStartGame("ai_vs_ai")}
          >
            🤖 AI vs AI
          </button>

          <button 
            className={`btn-tactical ${activeMode === "replay" ? "active" : ""}`} 
            onClick={() => handleStartGame("replay")}
          >
            🔁 Replay
          </button>

          <button
            className="btn-tactical"
            onClick={handleExportTrace}
            title="Download backend trace JSON"
          >
            💾 Export Trace
          </button>

          <button
            className="btn-tactical"
            onClick={handleSaveLayout}
            title="Guardar layout de ventanas y paneles"
          >
            🧩 Guardar Layout
          </button>

          <button
            className="btn-tactical"
            onClick={handleResetLayout}
            title="Resetear layout guardado"
          >
            ♻ Reset Layout
          </button>

          <button
            className="btn-tactical"
            onClick={handleMapMode}
            title="Minimizar todas las ventanas para vista limpia de mapa"
          >
            🗺 Modo Mapa
          </button>

          <button
            className="btn-tactical btn-tactical-start"
            onClick={handleStartSelectedMode}
            title="Start selected mode"
            disabled={!canStartGame}
          >
            ▶ Start
          </button>

          <button 
            className="btn-tactical btn-tactical-stop" 
            onClick={handleStopGame}
          >
            ⛔ Stop
          </button>
        </div>
      </div>

      {/* =========================
          MAIN GAME SCREEN GRID
      ========================= */}
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
      <DraggableWindow windowId="tactical-intel" title="Target Intel" initialX={16} initialY={92} width={360} bodyMaxHeight={640}>
        {selectedUnit ? (
          <div>
            <div className="spec-box">
              <div className="spec-header">
                {selectedUnitSpec?.full && (
                  <img
                    src={encodeURI(selectedUnitSpec.full)}
                    className="spec-avatar"
                    alt="Avatar"
                  />
                )}
                <div>
                  <div className="spec-title">{selectedUnitSpec?.label || selectedUnit.unit_key}</div>
                  <div className="spec-subtitle">ID: {selectedUnit.id}</div>
                  <div className="spec-inline-health-row">
                    <span className="spec-inline-health-hearts">
                      {selectedUnit.hp != null
                        ? Array.from({ length: selectedUnit.hp }).map((_, i) => (
                            <span key={i} style={{ color: "#ff3838" }}>❤️</span>
                          ))
                        : "-"}
                    </span>
                    {(selectedUnitActionMarker == null || selectedUnitActionMarker === "normal") && selectedWaitOrder && (
                      <button
                        className="spec-wait-btn"
                        onClick={() => void executeActionById(selectedWaitOrder.action_id, selectedWaitOrder)}
                        title="Wait / End activation"
                      >
                        WAIT
                      </button>
                    )}
                  </div>
                </div>
              </div>
              <div className="spec-stats">
                <div className={`spec-stat-item side-${selectedUnit.side}`}>
                  <div className="spec-stat-label">Side</div>
                  <div className="spec-stat-val" style={{ color: selectedUnit.side === "GE" ? "var(--neon-red)" : "var(--neon-cyan)" }}>
                    {sides[selectedUnit.side]?.label || selectedUnit.side}
                  </div>
                </div>
                <div className="spec-stat-item">
                  <div className="spec-stat-label">Coords</div>
                  <div className="spec-stat-val" style={{ fontFamily: "var(--font-mono)", fontSize: "11px" }}>
                    Q:{selectedUnit.q} R:{selectedUnit.r}
                  </div>
                </div>
              </div>
            </div>
            <DispatchedOrdersPanel
              availableMoves={availableMoves}
              selectedUnitId={selectedUnitId}
              isHumanTurn={gameData?.sides?.[gameData?.active_side] === "human"}
              onHoverOrder={(order) => setHoveredTargetId(resolveOrderTargetId(order))}
              onLeaveOrder={() => setHoveredTargetId(null)}
            />
            {attackHint && (
              <div
                style={{
                  marginTop: 8,
                  padding: "8px 10px",
                  fontSize: 11,
                  border: "1px solid rgba(255, 80, 80, 0.35)",
                  background: "rgba(255, 60, 60, 0.12)",
                  color: "#ffd6d6",
                  borderRadius: 6,
                  fontFamily: "var(--font-mono)",
                }}
              >
                {attackHint}
              </div>
            )}
          </div>
        ) : (
          <div className="awaiting-selection">
            <div className="radar-circle"></div>
            <div>
              <h4 style={{ margin: "0 0 4px 0", color: "var(--text-secondary)", fontSize: "13px" }}>Awaiting Target Lock</h4>
              <p style={{ fontSize: "11px", color: "var(--text-muted)", lineHeight: "1.4" }}>
                Select a tactical unit on the grid or troop roster to deploy commands.
              </p>
            </div>
          </div>
        )}
      </DraggableWindow>
      <DraggableWindow windowId="tactical-log" title="System Log" initialX={1540} initialY={92} width={360} bodyMaxHeight={640}>
        <div className="log-container">
          {logEvents.length > 0 ? (
            logEvents.map((log, index) => (
              <div key={index} className={`log-entry log-${log.type}`}>
                <span className="log-time">[{log.time}]</span>
                <span className="log-text">{log.text}</span>
              </div>
            ))
          ) : (
            <div style={{ fontSize: "12px", color: "var(--text-muted)", fontStyle: "italic", textAlign: "center", padding: "10px" }}>
              Awaiting telemetry transmissions...
            </div>
          )}
        </div>
      </DraggableWindow>
      <DraggableWindow windowId="tactical-situation" title="Asistente Tactico: Situacion" initialX={1080} initialY={95} width={390}>
        <RagSituationPanel gameData={gameData} />
      </DraggableWindow>
      <DraggableWindow windowId="tactical-rules" title="Asistente Tactico: Reglas" initialX={1080} initialY={420} width={390}>
        <RagRulesPanel gameData={gameData} />
      </DraggableWindow>
      <DraggableWindow windowId="tactical-status" title="Estado de Partida" initialX={360} initialY={82} width={700}>
        <div style={{ display: "grid", gap: 8, fontSize: 12 }}>
          <div>
            <strong>SCENARIO:</strong>{" "}
            <span style={{ color: "var(--neon-cyan)" }}>
              {(gameData?.scenario_name || "Initial Contact").toUpperCase()}
            </span>
          </div>
          <div>
            <strong>TURN:</strong>{" "}
            <span style={{ color: "var(--neon-cyan)" }}>{gameData?.turn ?? "-"}</span>
          </div>
          <div>
            <strong>VPs:</strong>{" "}
            <span style={{ color: "var(--neon-cyan)" }}>
              {Object.entries(gameData?.vp_score_live || {})
                .map(([sideId, score]) => `${sideId} ${score}`)
                .join(" | ") || "-"}
            </span>
          </div>
          <div>
            <strong>ACTIVE:</strong>{" "}
            <span
              style={{
                color:
                  gameData?.sides?.[gameData?.active_side] === "human"
                    ? "var(--neon-green)"
                    : "var(--neon-orange)",
              }}
            >
              {gameData?.active_side || "-"} ({gameData?.sides?.[gameData?.active_side]?.toUpperCase() || "-"})
            </span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <label style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              <input
                type="checkbox"
                checked={autoAdvanceAfterHuman}
                onChange={(e) => handleToggleAutoAdvance(e.target.checked)}
              />
              <strong>Autoavance</strong>
            </label>
            <button
              className="btn-tactical"
              onClick={handleManualAdvance}
              disabled={autoAdvanceAfterHuman || !waitingForManualAdvance}
              title="Continuar resolucion IA tras accion humana"
            >
              ▶ Avanzar
            </button>
            <span style={{ color: "var(--text-muted)", fontSize: 11 }}>
              {waitingForManualAdvance && !autoAdvanceAfterHuman
                ? "Esperando avance manual..."
                : "Flujo normal"}
            </span>
          </div>
          {gameData?.victory_outcome && (
            <div>
              <strong>OBJECTIVES:</strong>{" "}
              <span style={{ color: "var(--neon-cyan)" }}>
                {gameData.victory_outcome.tracked_side} {gameData.victory_outcome.captured}/
                {gameData.victory_outcome.objectives_total}
                {gameData.victory_outcome?.outcome?.result
                  ? ` (${gameData.victory_outcome.outcome.result})`
                  : ""}
              </span>
            </div>
          )}
          {gameData?.done && (
            <div>
              <strong>RESULT:</strong>{" "}
              <span style={{ color: "var(--neon-green)" }}>
                {gameData?.winner ? `${gameData.winner} wins` : "Draw"} ({gameData?.end_reason || "completed"})
              </span>
            </div>
          )}
        </div>
      </DraggableWindow>

      <DraggableWindow
        windowId="tactical-units"
        title="Unidades"
        initialX={80}
        initialY={520}
        width={1450}
        bodyMaxHeight={300}
      >
        <UnitStatePanel
          units={panelUnits}
          activeSide={gameData?.active_side}
          activatedUnits={gameData?.activated_units || []}
          selectedUnitId={selectedUnitId}
          targetUnitId={hoveredTargetId}
          onSelectUnit={(unit: Unit) => {
            // Direct callback helper triggered from troop dock cards
            setSelectedUnitId(unit.id);
            if (typeof (window as any).onUnitClick === "function") {
              (window as any).onUnitClick(unit);
            }
          }}
        />
      </DraggableWindow>

      <DraggableWindow windowId="tactical-dice" title="Combate / Tirada de Dados" initialX={1220} initialY={610} width={320}>
        {stickyCombatEvent && (
          <CombatPanel event={stickyCombatEvent} units={gameData?.units || []} />
        )}
        {!stickyCombatEvent && (
          <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
            Sin evento de combate reciente.
          </div>
        )}
      </DraggableWindow>
      {pendingReaction && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.45)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 40,
          }}
        >
          <div
            style={{
              width: 460,
              maxWidth: "92vw",
              background: "rgba(8, 10, 18, 0.95)",
              border: "1px solid rgba(0, 240, 255, 0.35)",
              boxShadow: "0 0 28px rgba(0, 240, 255, 0.25)",
              borderRadius: 8,
              padding: 16,
            }}
          >
            <div style={{ fontFamily: "var(--font-tech)", fontSize: 15, letterSpacing: 1, marginBottom: 10, color: "var(--neon-cyan)" }}>
              REACTION FIRE WINDOW
            </div>
            <div style={{ fontSize: 13, lineHeight: 1.5, color: "var(--text-primary)", marginBottom: 14 }}>
              Enemy movement triggered a reaction opportunity.<br />
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
    </div>
  );
}

export default App;