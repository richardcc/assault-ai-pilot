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
import { logCombatEvents } from "./game/systems/combatLog";

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
  const [gameData, setGameData] = useState<any>(null);
  const [deadUnits, setDeadUnits] = useState<Unit[]>([]);
  const [selectedUnitId, setSelectedUnitId] = useState<string | null>(null);
  const [hoveredTargetId, setHoveredTargetId] = useState<string | null>(null);
  const [availableMoves, setAvailableMoves] = useState<any[]>([]);
  const [logEvents, setLogEvents] = useState<LogEntry[]>([]);
  const [activeMode, setActiveMode] = useState<string | null>(null);

  const lastTurnRef = useRef<number>(-1);
  const lastActiveSideRef = useRef<string>("");
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

  // Subscribe to the game controller events
  useEffect(() => {
    gameController.subscribe((state: any) => {
      setGameData(state);
    });

    (window as any).logSystemEvent = (type: string, text: string) => {
      addLog(type, text);
    };

    addLog("system", "🖥️ Tactical Control System initialized. Ready to launch.");

    return () => {
      (window as any).logSystemEvent = undefined;
    };
  }, []);

  // Auto-start a default session so the map is visible on app load.
  useEffect(() => {
    if (activeMode || gameData) return;
    setActiveMode("human");
    gameController.start("human").catch((err) => {
      console.error("❌ Auto-start failed", err);
      addLog("system", `❌ Auto-start failed: ${String(err)}`);
    });
  }, [activeMode, gameData]);

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
    setActiveMode(mode);
    addLog("system", `🚀 Launching match mode: [${mode.toUpperCase()}]`);
    gameController.start(mode as any);
  };

  // Safe handler to stop and refresh the session
  const handleStopGame = () => {
    addLog("system", "⛔ Terminating active session. Resetting control board...");
    setTimeout(() => {
      window.location.reload();
    }, 800);
  };

  // Find active specifications of the selected troop
  const selectedUnit = gameData?.units?.find((u: Unit) => u.id === selectedUnitId);
  const selectedUnitSpec = selectedUnit 
    ? unitImages[selectedUnit.unit_key as keyof typeof unitImages] 
    : null;

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

  const latestCombatEvent = gameData?.last_events?.slice().reverse().find((event: any) => event.type === "ACTION_EFFECT");

  return (
    <div className="app">
      {/* =========================
          TACTICAL HEADER
      ========================= */}
      <div className="header">
        <div className="header-title">
          ⚡ ASSAULT AI <span>// COMMAND INTERFACE v1.2</span>
        </div>

        {/* Real-time turn indicator readout */}
        {gameData && (
          <div style={{ display: "flex", gap: "20px", fontFamily: "var(--font-tech)", fontSize: "14px", letterSpacing: "1px" }}>
            <div>SCENARIO: <span style={{ color: "var(--neon-cyan)" }}>{(gameData.scenario_name || "Initial Contact").toUpperCase()}</span></div>
            <div>TURN: <span style={{ color: "var(--neon-cyan)" }}>{gameData.turn}</span></div>
            <div style={{
              color: gameData.sides?.[gameData.active_side] === "human" ? "var(--neon-green)" : "var(--neon-orange)"
            }}>
              ACTIVE: {gameData.active_side} ({gameData.sides?.[gameData.active_side]?.toUpperCase() || "-"})
            </div>
          </div>
        )}

        <div className="header-controls">
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
        {/* LEFT PANEL - TARGET INTEL & ACTIONS */}
        <div className="panel-side">
          <div className="panel-title">Target Intel</div>
          
          {selectedUnit ? (
            <div>
              {/* Unit Specifications Card */}
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

                  <div className="spec-stat-item" style={{ gridColumn: "span 2" }}>
                    <div className="spec-stat-label">Health</div>
                    <div className="spec-stat-val" style={{ display: "flex", gap: "2px", fontSize: "12px", marginTop: "2px" }}>
                      {selectedUnit.hp != null
                        ? Array.from({ length: selectedUnit.hp }).map((_, i) => (
                            <span key={i} style={{ color: "#ff3838" }}>❤️</span>
                          ))
                        : "-"}
                    </div>
                  </div>
                </div>
              </div>

              {/* Dynamic Actions readout list */}
              <DispatchedOrdersPanel
                availableMoves={availableMoves}
                selectedUnitId={selectedUnitId}
                onHoverOrder={(order) => setHoveredTargetId(resolveOrderTargetId(order))}
                onLeaveOrder={() => setHoveredTargetId(null)}
              />
            </div>
          ) : (
            /* Radar scanning placeholder when no target is locked */
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
        </div>

        {/* CENTER PANEL - THE HEX GRID CANVAS */}
        <div className="center">
          <GameCanvas
            gameData={gameData}
            setGameData={setGameData}
            selectedUnitId={selectedUnitId}
            setSelectedUnitId={setSelectedUnitId}
            availableMoves={availableMoves}
            setAvailableMoves={setAvailableMoves}
          />
        </div>

        {/* RIGHT PANEL - REALTIME TELEMETRY TERMINAL */}
        <div className="panel-side right-log">
          <div className="panel-title">System Log</div>
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
        </div>
      </div>

      {/* =========================
          TACTICAL ROSTER FOOTER
      ========================= */}
      <div className="footer">
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

        {latestCombatEvent && (
          <CombatPanel event={latestCombatEvent} units={gameData?.units || []} />
        )}
      </div>
    </div>
  );
}

export default App;