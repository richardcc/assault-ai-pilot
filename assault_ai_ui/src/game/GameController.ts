export class GameController {
  private mode: GameMode = "human";
  private state: GameState | null = null;

  private listeners: Listener[] = [];
  private lastState: GameState | null = null;

  private socket: WebSocket | null = null;

  // ----------------------------------
  async start(mode: GameMode) {
    // ✅ evitar doble start
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      console.log("⚠️ already started");
      return;
    }

    this.mode = mode;

    console.log("Starting mode:", mode);

    if (mode === "replay") {
      await this.loadReplay();
    } else {
      await this.loadScenario();
    }

    setTimeout(() => {
      this.startWebSocket();
    }, 300);
  }

  // ----------------------------------
  private async loadScenario() {
    try {
      const res = await fetch(
        "http://127.0.0.1:8000/api/ui/scenarios/mettete_i_piedi_terra_1_min"
      );

      const data = await res.json();

      if (!data || !data.hexes) {
        console.error("❌ Invalid scenario data", data);
        return;
      }

      this.state = {
        turn: 1,
        raw: data,
      };

      console.log("✅ Scenario loaded:", data);

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
      const data = JSON.parse(event.data);

      if (!this.state) return;

      this.state = {
        turn: this.state.turn,
        raw: {
          ...this.state.raw,
          units: data.units,
        },
      };

      this.emit();
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
  // ✅ NUEVO: obtener unidad por ID
  getUnitById(id: string) {
    const units = this.state?.raw?.units;
    if (!units) return null;

    return units.find((u: any) => u.id === id) || null;
  }

  // ----------------------------------
  // ✅ NUEVO: obtener posición
  getUnitPosition(id: string) {
    const unit = this.getUnitById(id);
    if (!unit) return null;

    return {
      q: unit.q,
      r: unit.r,
    };
  }

  // ----------------------------------
  private async loadReplay() {
    console.warn("Replay not implemented yet");
  }

  private startLoop() {
    console.warn("AI loop not implemented yet");
  }
}