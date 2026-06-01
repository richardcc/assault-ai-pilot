type ControllerType = "human" | "ai";
type GameMode = "human" | "ai" | "ai_vs_ai" | "replay";
type Listener = (state: any) => void;

export class GameController {

  private mode: GameMode = "human";
  private state: any = null;

  private listeners: Listener[] = [];
  private lastState: any = null;

  private socket: WebSocket | null = null;

  // ✅ NUEVO: referencia al highlight layer
  private highlightLayer: any = null;

  // ----------------------------------
  async start(mode: GameMode) {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      console.log("⚠️ already started");
      return;
    }

    this.mode = mode;

    console.log("Starting mode:", mode);

    // ✅ iniciar partida en backend
    await fetch("http://127.0.0.1:8000/api/game/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        scenario_id: "mettete_i_piedi_terra_1_min",
        sides: {
          GE: "human",
          US: "ai"
        }
      })
    });

    await this.loadScenario();

    setTimeout(() => {
      this.startWebSocket();
    }, 300);

    if (mode === "ai" || mode === "ai_vs_ai") {
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
  private startLoop() {
    console.log("🤖 AI loop started (backend-driven)");

    const loop = async () => {

      if (!this.state) {
        setTimeout(loop, 1000);
        return;
      }

      const data = this.state;
      const activeSide = data.active_side;

      if (!activeSide) {
        setTimeout(loop, 1000);
        return;
      }

      // ✅ solo ejecuta si el lado es IA
      if (data?.sides?.[activeSide] !== "ai") {
        setTimeout(loop, 500);
        return;
      }

      console.log("🤖 CALLING BACKEND AI TURN");

      try {

        const res = await fetch("http://127.0.0.1:8000/api/game/ai-turn", {
          method: "POST"
        });

        const result = await res.json();
        (window as any).onAIOrders?.(result.steps);

        // ✅ NUEVO: render visual de acciones IA
        if (result.steps && this.highlightLayer) {

          for (let i = 0; i < result.steps.length; i++) {

            const step = result.steps[i];

            setTimeout(() => {
              this.highlightLayer.highlightAction(step, this.state);
            }, i * 400); // delay animado
          }
        }

      } catch (e) {
        console.error("❌ AI turn error", e);
      }

      // ✅ dejar tiempo a websocket
      setTimeout(loop, 800);
    };

    loop();
  }

  // ----------------------------------
  private async loadReplay() {
    console.warn("Replay not implemented yet");
  }
}