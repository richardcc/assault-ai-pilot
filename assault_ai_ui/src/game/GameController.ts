import { logCombatEvents } from "./systems/combatLog";
import { clearUnitActionMarkers, resolveActionMarker, setUnitActionMarker } from "./state/actionMarkers";

type ControllerType = "human" | "ai";
type GameMode = "human" | "ai" | "ai_vs_ai" | "replay";
type Listener = (state: any) => void;

export class GameController {

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
    this.state = newState;
    this.emit();
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
        if (result?.state) {
          // Keep controller state in sync immediately; relying only on WS can
          // cause stale active_side and trigger extra ai-turn calls.
          this.updateState(result.state);
        }

        const rawSteps = Array.isArray(result?.steps) ? result.steps : [];
        const steps = rawSteps.length > 0 ? [rawSteps[0]] : [];
        if (steps.length > 0) {
          const step0 = steps[0];
          const unitId = step0?.unit_id || step0?.unit;
          if (unitId) {
            setUnitActionMarker(unitId, resolveActionMarker(step0));
          }
        }
        (window as any).onAIOrders?.(steps);

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
        this.scheduleLoop(loop, hasAiStep ? 1100 : 1800);
        return;

      } catch (e) {
        console.error("❌ AI turn error", e);
        this.aiTurnInFlight = false;
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