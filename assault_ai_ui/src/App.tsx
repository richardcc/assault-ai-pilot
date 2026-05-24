import "./App.css";
import GameCanvas from "./game/GameCanvas";
import { gameController } from "./game/gameControllerInstance";

function App() {
  return (
    <div className="app">

      {/* =========================
          HEADER
      ========================= */}
      <div className="header">
        <div>ASSAULT AI</div>

        <div>
          <button onClick={() => gameController.start("human")}>
            🎮 Human vs AI
          </button>

          <button onClick={() => gameController.start("ai_vs_ai")}>
            🤖 AI vs AI
          </button>

          <button onClick={() => gameController.start("replay")}>
            🔁 Replay
          </button>

          <button onClick={() => gameController.stop()}>
            ⛔ Stop
          </button>
        </div>
      </div>

      {/* =========================
          MAIN LAYOUT
      ========================= */}
      <div className="main">

        {/* LEFT PANEL */}
        <div className="left">
          <h3>AI / Actions</h3>
          <p>Select a unit</p>
        </div>

        {/* ✅ CENTER = MAP */}
        <div className="center">
          <GameCanvas />
        </div>

        {/* RIGHT PANEL */}
        <div className="right">
          <h3>Event Log</h3>
          <p>Events will appear here</p>
        </div>

      </div>

      {/* =========================
          FOOTER
      ========================= */}
      <div className="footer">
        Units | Actions | Info
      </div>

    </div>
  );
}

export default App;