# assault_backend and UI Class Contracts

## assault_backend

`ExplainableEngine`, `GameSession`, `HRLCache`, `HRLService`, `TacticalCache`, `TacticalService`, `SB3AIService`, `GameStartRequest`, `UnitActionsRequest`, `StrategicState`, `ActivationPayload`, `ExplainActivationRequest`, `ExplainActivationResponse`, `ScenarioSide`, `ScenarioResponse`

- **Input contract**: API payloads, tactical/strategic request context, model-ready state.
- **Output contract**: validated schemas, service responses, cached artifacts.
- **Responsibility**: bridge runtime/simulation logic to API and inference services.

## assault_ai_ui/src/game

`GameController`, `HighlightLayer`, `UnitLayer`, `SoundService`

- **Input contract**: frontend game events, user interactions, render/audio state.
- **Output contract**: UI state transitions, rendered overlays/layers, sound effects.
- **Responsibility**: game orchestration and rendering/audio integration on UI.
