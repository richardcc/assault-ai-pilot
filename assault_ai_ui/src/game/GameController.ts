import { suggestMove } from "../ai/suggestMove";

type ControllerType = "human" | "ai";

export class GameController {

  private mode: GameMode = "human";
  private state: any = null;

  private listeners: Listener[] = [];
  private lastState: any = null;

  private socket: WebSocket | null = null;

  private controllersBySide: Record<string, ControllerType> = {
    US: "human",
    GE: "ai",
  };

  // ----------------------------------
  async start(mode: GameMode) {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      console.log("⚠️ already started");
      return;
    }

    this.mode = mode;

    console.log("Starting mode:", mode);

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
        "http://127.0.0.1:8000/api/ui/scenarios/mettete_i_piedi_terra_1_min"
      );

      const data = await res.json();

      // ✅ keep same structure as runtime
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
  private sendMove(unitId: string, move: any) {
    if (!this.socket) return;

    this.socket.send(
      JSON.stringify({
        action: "move",
        unit_id: unitId,
        q: move.q,
        r: move.r,
      })
    );
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

      if (this.controllersBySide[activeSide] !== "ai") {
        setTimeout(loop, 500);
        return;
      }

      const units = data.units || [];
      const activated = data.activated_units || [];

      const availableUnits = units.filter((u: any) =>
        u.side === activeSide &&
        !activated.includes(u.unit_id)
      );

      if (availableUnits.length === 0) {
        setTimeout(loop, 500);
        return;
      }

      for (const unit of availableUnits) {
        const move = suggestMove(unit, data);

        if (move) {
          console.log("🤖 AI move:", unit.unit_id, move);
          this.sendMove(unit.unit_id, move);
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