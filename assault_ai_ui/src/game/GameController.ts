export class GameController {
  private mode: GameMode = "human";
  private state: GameState | null = null;

  private listeners: Listener[] = [];
  private running = false;

  // 🔥 NUEVO
  private lastState: GameState | null = null;

  // ----------------------------------
  async start(mode: GameMode) {
    this.mode = mode;
    this.running = true;

    console.log("Starting mode:", mode);

    if (mode === "replay") {
      await this.loadReplay();
    } else {
      await this.loadScenario();
    }

    if (mode === "ai_vs_ai") {
      this.startLoop();
    }
  }

  // ----------------------------------
  private async loadScenario() {
    const res = await fetch(
      "http://127.0.0.1:8000/api/ui/scenarios/mettete_i_piedi_terra_1_min"
    );

    const data = await res.json();

    this.state = {
      turn: 1,
      raw: data,
    };

    console.log("✅ Scenario loaded:", data);

    this.emit();
  }

  // ----------------------------------
  subscribe(cb: Listener) {
    this.listeners.push(cb);

    // 🔥 CLAVE: replay inmediato
    if (this.lastState) {
      cb(this.lastState);
    }
  }

  private emit() {
    if (!this.state) return;

    // 🔥 guardado
    this.lastState = this.state;

    for (const cb of this.listeners) {
      cb(this.state);
    }
  }

  private sleep(ms: number) {
    return new Promise((r) => setTimeout(r, ms));
  }
}