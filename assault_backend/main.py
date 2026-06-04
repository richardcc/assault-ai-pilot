import asyncio
import json
import time
from pathlib import Path
from typing import Dict

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from assault_backend.engine import ExplainableEngine
from assault_backend.game_session import GameSession
from assault_backend.hrl_service import HRLService
from assault_backend.schemas.rag import ExplainActivationRequest, ExplainActivationResponse
from assault_backend.services.action_service import get_unit_actions
from assault_backend.services.map_piece_service import (
    load_map_piece_catalog_raw,
    load_map_piece_raw,
)
from assault_backend.services.targeting_service import compute_targeting_info
from assault_backend.services.unit_service import load_unit_catalog_raw, load_unit_raw
from assault_backend.tactical_service import TacticalService
from assault_sim.decision.decision_engine import DecisionEngine


game_session = GameSession()

app = FastAPI(title="Assault RAG Backend", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

RULEBOOK_PATH = (
    Path(__file__).resolve().parent.parent
    / "assault_rag"
    / "data"
    / "rulebook"
    / "typed"
    / "rulebook_typed.json"
)
with open(RULEBOOK_PATH, "r", encoding="utf-8") as f:
    TYPED_RULEBOOK = json.load(f)

engine = ExplainableEngine(
    hrl_service=HRLService(),
    tactical_service=TacticalService(typed_rules=TYPED_RULEBOOK),
)


@app.get("/api/engine/status")
def engine_status():
    return {
        "status": "ready",
        "engine": "assault-rag-backend",
        "rag_enabled": True,
        "layers": {"strategic": "assault_rag", "tactical": "rules_and_dice"},
    }


@app.post("/api/explain/activation", response_model=ExplainActivationResponse)
def explain_activation(request: ExplainActivationRequest):
    return engine.explain_activation(request.activation)


@app.get("/api/ui/scenarios/{scenario_id}")
async def get_scenario(scenario_id: str):
    try:
        if game_session.env is None:
            game_session.start(scenario_id, {})
        return game_session.get_state()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/map_pieces")
def list_map_pieces_raw():
    try:
        catalog = load_map_piece_catalog_raw()
        return sorted(catalog.get("pieces", {}).keys())
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="Map piece catalog not found")


@app.get("/api/map_pieces/{piece_id}")
def get_map_piece_raw(piece_id: str):
    try:
        return load_map_piece_raw(piece_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Map piece not found")


@app.get("/api/units")
def list_units_raw():
    try:
        catalog = load_unit_catalog_raw()
        return sorted(catalog.get("units", {}).keys())
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="Unit catalog not found")


@app.get("/api/units/{unit_key}")
def get_unit_raw(unit_key: str):
    try:
        return load_unit_raw(unit_key)
    except KeyError:
        raise HTTPException(status_code=404, detail="Unit not found")


class GameStartRequest(BaseModel):
    scenario_id: str
    sides: Dict[str, str]


class UnitActionsRequest(BaseModel):
    unit_id: str


@app.post("/api/game/start")
def game_start(req: GameStartRequest):
    try:
        game_session.env = None
        game_session.start(req.scenario_id, req.sides)
        if game_session.env is None:
            raise RuntimeError("env not initialized")
        return {"status": "started", "scenario": req.scenario_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/game/state")
def game_state():
    return game_session.get_state()


@app.post("/api/game/step")
async def game_step(payload: Dict):
    action_id = payload.get("action_id")
    if not action_id:
        return {"error": "missing action_id"}
    try:
        _, reward, done, info = game_session.env.step(action_id)
        return {"state": game_session.get_state(), "reward": reward, "done": done, "info": info}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.websocket("/ws/game")
async def websocket_game(ws: WebSocket):
    await ws.accept()
    try:
        while game_session.env is None:
            await asyncio.sleep(0.1)
        env = game_session.env

        def handler(event):
            if event["type"] == "MAP_STATE":
                # Kept for parity with existing event-bus hook behavior.
                async def safe_send():
                    try:
                        await ws.send_json({"type": "MAP_STATE", "payload": event["payload"]})
                    except Exception:
                        pass

                _ = safe_send

        if env.event_bus:
            env.event_bus.subscribe(handler)
        while True:
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass


@app.post("/api/game/actions")
def game_actions(req: UnitActionsRequest):
    for _ in range(10):
        if game_session.env is not None:
            break
        time.sleep(0.1)
    if game_session.env is None:
        raise HTTPException(status_code=400, detail="no game")

    state = game_session.env.game_state
    unit = next((u for u in state.units if u.unit_id == req.unit_id), None)
    if not unit:
        raise HTTPException(status_code=404, detail="unit not found")
    try:
        return get_unit_actions(game_session.env, unit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/game/ai-turn")
def game_ai_turn():
    if game_session.env is None:
        return {"error": "no game"}

    env = game_session.env
    if not hasattr(game_session, "decision_engine"):
        game_session.decision_engine = DecisionEngine()
    if not hasattr(game_session, "sb3_ai"):
        try:
            from assault_backend.services.sb3_ai_service import SB3AIService

            game_session.sb3_ai = SB3AIService()
            print(f"[AI TURN] SB3 model loaded: {game_session.sb3_ai.model_path}")
        except Exception as e:
            game_session.sb3_ai = None
            print(f"[AI TURN] SB3 unavailable, falling back to heuristic: {e}")

    decision_engine = game_session.decision_engine
    sb3_ai = game_session.sb3_ai
    steps = []

    while True:
        runtime = env.runtime
        active_side = getattr(runtime, "active_side", None)
        result = decision_engine.compute_intent(env)
        if result is None:
            break

        unit, heuristic_action = result
        action = heuristic_action
        source = "heuristic"
        if sb3_ai is not None and sb3_ai.can_control_side(active_side):
            try:
                action, _opt = sb3_ai.choose_action(env, unit)
                source = "sb3"
            except Exception as e:
                print(f"[AI TURN] SB3 inference failed, fallback heuristic: {e}")
                action = heuristic_action
                source = "heuristic_fallback"

        env.step(action)
        steps.append({"unit": unit.unit_id, "action": action.__class__.__name__, "source": source})

    return {"state": game_session.get_state(), "steps": steps}


@app.get("/targeting")
def get_targeting(attacker_id: str, q: int, r: int):
    if game_session.env is None:
        raise HTTPException(status_code=400, detail="no game")
    gs = game_session.env.game_state
    result = compute_targeting_info(gs, attacker_id, q, r)
    if result is None:
        raise HTTPException(status_code=404, detail="invalid attacker")
    return result
