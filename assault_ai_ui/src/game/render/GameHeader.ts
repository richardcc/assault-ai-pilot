type GameStatePayload = {
    scenario_name?: string;
    turn: number;
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
                    Scenario: {state.scenario_name ?? "Unknown"}
                </span>

                <span className="turn">
                    Turn: {state.turn}
                </span>

                <span className="active-side">
                    Active: {state.active_side ?? "None"}
                </span>
            </div>
        </div>
    );
}