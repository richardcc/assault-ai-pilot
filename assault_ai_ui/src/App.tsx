import "./App.css";
import GameCanvas from "./GameCanvas";

function App() {
  return (
    <div className="app">

      {/* HEADER */}
      <header className="header">
        <div className="header-left">MODE: Replay | Play</div>
        <div className="header-center">Turn 1</div>
        <div className="header-right">🤖 Assistant</div>
      </header>

      {/* MAIN */}
      <main className="main">

        {/* LEFT PANEL */}
        <aside className="left">
          <h3>AI / Actions</h3>
          <p>Select a unit</p>
        </aside>

        {/* MAP */}
        <section className="center">
          <GameCanvas />
        </section>

        {/* RIGHT PANEL */}
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