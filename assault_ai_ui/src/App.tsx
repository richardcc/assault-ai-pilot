import "./App.css";
import GameCanvas from "./game/GameCanvas";
import { gameController } from "./game/gameControllerInstance";

function App() {
  return (
    <div className="app">

      {/* HEADER */}
      <header className="header">
        <div className="header-left">

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

        <div className="header-center">
          Turn: (pending)
        </div>

        <div className="header-right">
          🤖 Assistant
        </div>
      </header>

      {/* MAIN */}
      <main className="main">

        <aside className="left">
          <h3>AI / Actions</h3>
          <p>Select a unit</p>
        </aside>

        <section className="center">
          <GameCanvas />
        </section>

        <aside className="right">
          <h3>Event Log</h3>
          <p>Events will appear here</p>
        </aside>

      </main>

      {/* FOOTER */}
      <footer className="footer">
        <div>Units | Actions | Info</div>
      </footer>

    </div>
  );
}

export default App;
