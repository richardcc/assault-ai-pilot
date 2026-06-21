import { formatCoords } from "./render/hexGridRenderer";
import { logCombatEvents } from "./systems/combatLog";
import { clearUnitActionMarkers, resolveActionMarker, setUnitActionMarker } from "./state/actionMarkers";

type ControllerType = "human" | "ai";
type GameMode = "human" | "ai" | "ai_vs_ai" | "replay";
type Listener = (state: any) => void;

export class GameController {
  private actionIdToAx(actionId: string | null | undefined): string {
    const raw = String(actionId || "");
    const parts = raw.split(":");
    if (parts.length < 4) return "[]";
    const q = Number(parts[parts.length - 2]);
    const r = Number(parts[parts.length - 1]);
    if (!Number.isFinite(q) || !Number.isFinite(r)) return "[]";
    return formatCoords(q, r);
  }

  private mode: GameMode = "human";
  private state: any = null;
  private scenarioId = "mettete_i_piedi_terra_1_min";
  private sidesConfig: Record<string, string> = { GE: "human", US: "ai" };

  private listeners: Listener[] = [];
  private lastState: any = null;

  private socket: WebSocket | null = null;
  private suppressReconnect = false;
  private aiLoopToken = 0;
  private aiLoopTimer: ReturnType<typeof setTimeout> | null = null;
  private startRequestToken = 0;
  private aiTurnInFlight = false;
  private pendingWsState: any = null;

  // ✅ NUEVO: referencia al highlight layer
  private highlightLayer: any = null;

  // ----------------------------------
  async start(
    mode: GameMode,
    scenarioId?: string,
    sidesConfig?: Record<string, string>
  ) {
    const requestToken = ++this.startRequestToken;
    this.stopLoop();

    // If a session is already running, treat start() as a full restart
    // (needed when user switches scenario from the dropdown).
    if (this.socket) {
      this.suppressReconnect = true;
      try {
        this.socket.close();
      } catch {
        // ignore websocket close errors on restart
      }
      this.socket = null;
    }

    this.mode = mode;
    clearUnitActionMarkers();
    if (scenarioId) {
      this.scenarioId = scenarioId;
    }
    if (sidesConfig && Object.keys(sidesConfig).length > 0) {
      this.sidesConfig = sidesConfig;
    }

    console.log("Starting mode:", mode);

    // ✅ iniciar partida en backend
    const startRes = await fetch("http://127.0.0.1:8000/api/game/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        scenario_id: this.scenarioId,
        sides: this.sidesConfig
      })
    });
    if (!startRes.ok) {
      const detail = await startRes.text();
      throw new Error(`Backend start failed (${startRes.status}): ${detail}`);
    }
    if (requestToken !== this.startRequestToken) return;

    await this.loadScenario();
    if (requestToken !== this.startRequestToken) return;

    setTimeout(() => {
      if (requestToken !== this.startRequestToken) return;
      this.startWebSocket();
    }, 300);

    if (requestToken !== this.startRequestToken) return;
    if (mode === "human" || mode === "ai" || mode === "ai_vs_ai") {
      this.startLoop();
    }
  }

  // ----------------------------------
  private async loadScenario() {
    try {
      const res = await fetch(
        "http://127.0.0.1:8000/api/game/state"
      );

      const data = await res.json();

      this.state = data;

      this.emit();

    } catch (e) {
      console.error("❌ Scenario load error", e);
    }
  }

  // ----------------------------------
  private startWebSocket() {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      return;
    }

    this.socket = new WebSocket("ws://127.0.0.1:8000/ws/game");

    this.socket.onopen = () => {
      console.log("✅ WS connected");
    };

    this.socket.onerror = (err) => {
      console.error("❌ WS error", err);
    };

    this.socket.onmessage = (event) => {
      const msg = JSON.parse(event.data);

      if (msg.type === "MAP_STATE" && msg.payload) {
        // During backend-driven AI turn animation, defer websocket sync.
        // Applying state immediately can snap units to final hexes and make
        // animation callbacks look like no-op after first turns.
        if (this.aiTurnInFlight) {
          this.pendingWsState = msg.payload;
          return;
        }
        this.state = msg.payload;
        this.emit();
      }
    };

    this.socket.onclose = () => {
      console.log("❌ WS closed");
      this.socket = null;

      if (this.suppressReconnect) {
        this.suppressReconnect = false;
        return;
      }

      setTimeout(() => {
        if (this.mode) {
          console.log("🔄 retry WS...");
          this.startWebSocket();
        }
      }, 1000);
    };
  }

  // ----------------------------------
  subscribe(cb: Listener) {
    this.listeners.push(cb);

    if (this.lastState) {
      cb(this.lastState);
    }
  }

  private emit() {
    if (!this.state) return;

    this.lastState = this.state;

    for (const cb of this.listeners) {
      cb(this.state);
    }
  }

  // ----------------------------------
  updateState(newState: any) {
    if (!newState || typeof newState !== "object") {
      return;
    }
    this.state = newState;
    this.emit();
    // Keep GameCanvas turn-transition hooks in sync (marker reset, unit sync).
    // Some flows (backend ai-turn loop) update controller state directly and
    // otherwise skip __setGameState, leaving activation markers stale.
    try {
      (window as any).__setGameState?.(newState);
    } catch {
      // ignore UI bridge failures
    }
  }

  // ----------------------------------
  // ✅ NUEVO: setter para conectar Pixi layer
  setHighlightLayer(layer: any) {
    this.highlightLayer = layer;
  }

  // ----------------------------------
  private async sendMove(unitId: string, move: any) {

    if (!move?.action_id) return;

    await fetch("http://127.0.0.1:8000/api/game/step", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        action_id: move.action_id
      })
    });
  }

  // ----------------------------------
  // 🔥 IA BACKEND + VISUAL HIGHLIGHTS
  // ----------------------------------
  private stopLoop() {
    this.aiLoopToken += 1;
    this.aiTurnInFlight = false;
    this.pendingWsState = null;
    if (this.aiLoopTimer) {
      clearTimeout(this.aiLoopTimer);
      this.aiLoopTimer = null;
    }
  }

  private scheduleLoop(loop: () => void, delayMs: number) {
    if (this.aiLoopTimer) {
      clearTimeout(this.aiLoopTimer);
    }
    this.aiLoopTimer = setTimeout(loop, delayMs);
  }

  private startLoop() {
    this.stopLoop();
    const token = this.aiLoopToken;
    console.log("🤖 AI loop started (backend-driven)");

    const loop = async () => {
      if (token !== this.aiLoopToken) return;

      if (!this.state) {
        this.scheduleLoop(loop, 1000);
        return;
      }

      const data = this.state;
      const activeSide = data.active_side;

      if (!activeSide) {
        this.scheduleLoop(loop, 1000);
        return;
      }

      // ✅ solo ejecuta si el lado es IA
      if (data?.sides?.[activeSide] !== "ai") {
        this.scheduleLoop(loop, 1200);
        return;
      }

      if (this.aiTurnInFlight) {
        this.scheduleLoop(loop, 400);
        return;
      }

      console.log("🤖 CALLING BACKEND AI TURN");
      this.aiTurnInFlight = true;

      try {

        const res = await fetch("http://127.0.0.1:8000/api/game/ai-turn", {
          method: "POST"
        });

        const result = await res.json();
        console.log("🤖 /api/game/ai-turn response:", result);

        const steps = Array.isArray(result?.steps) ? result.steps : [];
        if (steps.length > 0) {
          const step0 = steps[0];
          const unitId = step0?.unit_id || step0?.unit;
          const aiSource = String(step0?.source || "").toLowerCase();
          if (aiSource.startsWith("heuristic")) {
            const actionId = step0?.action_id || "?";
            const ax = this.actionIdToAx(actionId);
            (window as any).logSystemEvent?.(
              "heuristic",
              `🧠 Heuristic AI (${unitId || "?"}): ${actionId} ${ax} [${aiSource}]`
            );
          }
          const corrected = !!step0?.corrected;
          if (corrected) {
            const proposed = step0?.proposed_action_id || "?";
            const executed = step0?.action_id || "?";
            const proposedAx = this.actionIdToAx(proposed);
            const executedAx = this.actionIdToAx(executed);
            const reason = step0?.corrected_reason || "backend_recovery";
            console.warn(
              "🤖 AI action corrected before execution",
              { unitId, proposed, executed, reason, source: step0?.source }
            );
            (window as any).logSystemEvent?.(
              "alert",
              `⚠️ AI corrected (${unitId || "?"}): ${proposed} ${proposedAx} -> ${executed} ${executedAx} [${reason}]`
            );
          }
          if (unitId) {
            setUnitActionMarker(unitId, resolveActionMarker(step0));
          }
          const stepType = String(step0?.type || step0?.kind || "").toUpperCase();
          const moveQ = step0?.move_q ?? step0?.move_to?.q ?? step0?.q;
          const moveR = step0?.move_r ?? step0?.move_to?.r ?? step0?.r;
          if (stepType === "MOVE" || step0?.kind === "move") {
            const coordStr = moveQ != null && moveR != null ? formatCoords(moveQ, moveR) : "?";
            (window as any).logSystemEvent?.("move", `🤖 AI Order: Move ${unitId || "?"} to hex ${coordStr}`);
          } else {
            (window as any).logSystemEvent?.("combat", `⚔️ AI Order: Combat attack by ${unitId || "?"} on target ${step0?.target_id || "?"}`);
          }
        }
        (window as any).onAIOrders?.(steps);
        const animateOrder = (window as any).onAIAnimateOrder;
        if (typeof animateOrder === "function") {
          for (const step of steps) {
            try {
              await animateOrder(step);
            } catch {
              // keep loop resilient even if animation callback fails
            }
          }
        }

        if (result?.state) {
          // Apply backend state after animating AI steps. If we sync first, unit
          // sprites snap to final coordinates and movement animations become no-op.
          this.updateState(result.state);
        }

        // Log AI combat results to the System Log (the websocket MAP_STATE
        // payload does not carry last_events, so do it from the ai-turn result).
        logCombatEvents(result.state?.last_events, result.state?.units || []);

        // ✅ NUEVO: render visual de acciones IA
        if (steps.length > 0 && this.highlightLayer) {

          for (let i = 0; i < steps.length; i++) {

            const step = steps[i];

            setTimeout(() => {
              this.highlightLayer.highlightAction(step, this.state);
            }, i * 400); // delay animado
          }
        }
        const hasAiStep = steps.length > 0;
        this.aiTurnInFlight = false;
        if (this.pendingWsState) {
          this.updateState(this.pendingWsState);
          this.pendingWsState = null;
        }
        this.scheduleLoop(loop, hasAiStep ? 1100 : 1800);
        return;

      } catch (e) {
        console.error("❌ AI turn error", e);
        this.aiTurnInFlight = false;
        if (this.pendingWsState) {
          this.updateState(this.pendingWsState);
          this.pendingWsState = null;
        }
        this.scheduleLoop(loop, 1800);
        return;
      }
    };

    loop();
  }

  // ----------------------------------
  private async loadReplay() {
    console.warn("Replay not implemented yet");
  }
}