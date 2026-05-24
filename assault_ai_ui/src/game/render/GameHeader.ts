type GameStatePayload = {
  scenario_name?: string;
  turn?: number;          // ✅ puede no venir al inicio
  active_side?: string;
};

type Props = {
  state: GameStatePayload | null;
};

export function GameHeader({ state }: Props) {
  if (!state) {
    return <div className="game-header">Loading...</div>;
  }

  return (
    <div className="game-header">
      <div className="header-row">
        <span className="scenario">
          {state.scenario_name ?? "Scenario"}
        </span>

        <span className="turn">
          Turn: {state.turn != null ? state.turn : "-"}
        </span>

        <span className="active-side">
          Active: {state.active_side ?? "-"}
        </span>
      </div>
    </div>
  );
}