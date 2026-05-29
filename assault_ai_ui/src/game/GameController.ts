import { suggestMove } from "../ai/suggestMove";

type ControllerType = "human" | "ai";
type GameMode = "human" | "ai" | "ai_vs_ai" | "replay";
type Listener = (state: any) => void;

export class GameController {

  private mode: GameMode = "human";
  private state: any = null;

  private listeners: Listener[] = [];
  private lastState: any = null;

  private socket: WebSocket | null = null;

  // ----------------------------------
  async start(mode: GameMode) {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      console.log("⚠️ already started");
      return;
    }

    this.mode = mode;

    console.log("Starting mode:", mode);

    // ✅ ✅ 🔥 FIX CLAVE: iniciar partida en backend con sides
    await fetch("http://127.0.0.1:8000/api/game/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        scenario_id: "mettete_i_piedi_terra_1_min",

        // ✅ aquí defines quién controla cada bando
        sides: {
          GE: "human",
          US: "ai"
        }
      })
    });

    // ✅ luego cargas estado inicial
    await this.loadScenario();

    setTimeout(() => {
      this.startWebSocket();
    }, 300);

    if (mode === "ai") {
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

      // ✅ ONLY accept MAP_STATE
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
  private async sendMove(unitId: string, move: any) {

    if (!move.action_id) return;

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
  private startLoop() {
    console.log("🤖 AI loop started");

    const loop = () => {

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

      if (data?.sides?.[activeSide] !== "ai") {
        setTimeout(loop, 500);
        return;
      }

      const units = data.units || [];
      const activated = data.activated_units || [];

      const availableUnits = units.filter((u: any) =>
        u.side === activeSide &&
        !activated.includes(u.id)
      );

      if (availableUnits.length === 0) {
        setTimeout(loop, 500);
        return;
      }

      for (const unit of availableUnits) {
        const move = suggestMove(unit, data);

        if (move) {
          console.log("🤖 AI move:", unit.unit_id, move);
          this.sendMove(unit.id, move);
        }
      }

      setTimeout(loop, 1000);
    };

    loop();
  }

  // ----------------------------------
  private async loadReplay() {
    console.warn("Replay not implemented yet");
  }
}