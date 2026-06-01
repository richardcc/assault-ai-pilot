import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from services.scenario_service_ui import load_ui_scenario
from game_session import GameSession

# ✅ sesión persistente
game_session = GameSession()

# =====================================================
# LOADERS
# =====================================================

from services.scenario_service import load_scenario_raw

from services.map_piece_service import (
    load_map_piece_catalog_raw,
    load_map_piece_raw,
)

from services.unit_service import (
    load_unit_catalog_raw,
    load_unit_raw,
)

# =====================================================
# RAG schemas
# =====================================================

from schemas.rag import (
    ExplainActivationRequest,
    ExplainActivationResponse,
)

from engine import ExplainableEngine
from hrl_service import HRLService
from tactical_service import TacticalService

# =====================================================
# FastAPI Application
# =====================================================

app = FastAPI(
    title="Assault RAG Backend",
    version="1.0",
)

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

# =====================================================
# LOAD RULEBOOK
# =====================================================

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

# =====================================================
# ENGINE
# =====================================================

engine = ExplainableEngine(
    hrl_service=HRLService(),
    tactical_service=TacticalService(
        typed_rules=TYPED_RULEBOOK
    ),
)

# =====================================================
# ENGINE ENDPOINTS
# =====================================================

@app.get("/api/engine/status")
def engine_status():
    return {
        "status": "ready",
        "engine": "assault-rag-backend",
        "rag_enabled": True,
        "layers": {
            "strategic": "assault_rag",
            "tactical": "rules_and_dice",
        },
    }


@app.post(
    "/api/explain/activation",
    response_model=ExplainActivationResponse,
)
def explain_activation(request: ExplainActivationRequest):
    return engine.explain_activation(request.activation)


# =====================================================
# ✅ SCENARIO + GAME STATE (UNIFICADO)
# =====================================================

@app.get("/api/ui/scenarios/{scenario_id}")
async def get_scenario(scenario_id: str):
    try:
        # ✅ iniciar sesión
        if game_session.env is None:
            game_session.start(scenario_id, {})

        # ✅ devolver estado real completo
        return game_session.get_state()

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================
# MAP PIECES (RAW)
# =====================================================

@app.get("/api/map_pieces")
def list_map_pieces_raw():
    try:
        catalog = load_map_piece_catalog_raw()
        pieces = catalog.get("pieces", {})
        return sorted(pieces.keys())
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="Map piece catalog not found")


@app.get("/api/map_pieces/{piece_id}")
def get_map_piece_raw(piece_id: str):
    try:
        return load_map_piece_raw(piece_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Map piece not found")


# =====================================================
# UNITS (RAW)
# =====================================================

@app.get("/api/units")
def list_units_raw():
    try:
        catalog = load_unit_catalog_raw()
        units = catalog.get("units", {})
        return sorted(units.keys())
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="Unit catalog not found")


@app.get("/api/units/{unit_key}")
def get_unit_raw(unit_key: str):
    try:
        return load_unit_raw(unit_key)
    except KeyError:
        raise HTTPException(status_code=404, detail="Unit not found")


# =====================================================
# GAME CONTROL
# =====================================================

from pydantic import BaseModel
from typing import Dict


class GameStartRequest(BaseModel):
    scenario_id: str
    sides: Dict[str, str]


class UnitActionsRequest(BaseModel):
    unit_id: str

@app.post("/api/game/start")
def game_start(req: GameStartRequest):

    print("[DEBUG][start] request:", req)

    try:
        # ✅ RESET EXPLÍCITO (muy importante)
        game_session.env = None

        # ✅ START REAL
        game_session.start(req.scenario_id, req.sides)

        # ✅ CHECK DURO
        if game_session.env is None:
            print("[ERROR][start] env is still None after start")
            raise Exception("env not initialized")

        print("[DEBUG][start] env created OK")

        return {
            "status": "started",
            "scenario": req.scenario_id,
        }

    except Exception as e:
        print("[ERROR][start] exception:", str(e))
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
        state, reward, done, info = game_session.env.step(action_id)

        return {
            "state": game_session.get_state(),
            "reward": reward,
            "done": done,
            "info": info
        }

    except Exception as e:
        print("[ERROR][step]", str(e))
        raise HTTPException(status_code=500, detail=str(e))

from fastapi import WebSocket, WebSocketDisconnect
import asyncio


from fastapi import WebSocket, WebSocketDisconnect
import asyncio


# =====================================================
# ✅ WEBSOCKET (GAME STATE REALTIME)
# =====================================================

@app.websocket("/ws/game")
async def websocket_game(ws: WebSocket):
    await ws.accept()
    print("✅ WebSocket connected")

    try:
        while game_session.env is None:
            await asyncio.sleep(0.1)

        env = game_session.env

        # 💣 ✅ FIX CLAVE
        loop = asyncio.get_running_loop()

        def handler(event):
            if event["type"] == "MAP_STATE":

                async def safe_send():
                    try:
                        await ws.send_json({
                            "type": "MAP_STATE",
                            "payload": event["payload"]
                        })
                    except Exception as e:
                        print("⚠️ WS dropped:", str(e))     


        if env.event_bus:
            env.event_bus.subscribe(handler)

        while True:
            await asyncio.sleep(1)

    except WebSocketDisconnect:
        print("❌ WebSocket disconnected")

    except Exception as e:
        print("❌ WebSocket error:", e)

# =====================================================
# GAME ACTIONS (QUERY ONLY - NO EXECUTION)
# =====================================================
from services.action_service import get_unit_actions


from fastapi import HTTPException
import time

@app.post("/api/game/actions")
def game_actions(req: UnitActionsRequest):

    # -------------------------------------------------
    # ✅ WAIT FOR ENV (fix race condition)
    # -------------------------------------------------
    for _ in range(10):  # max 1 second
        if game_session.env is not None:
            break
        time.sleep(0.1)

    if game_session.env is None:
        print("[ERROR][actions] env is None")
        raise HTTPException(status_code=400, detail="no game")

    # -------------------------------------------------
    # ✅ GET STATE
    # -------------------------------------------------
    state = game_session.env.game_state

    # -------------------------------------------------
    # ✅ FIND UNIT
    # -------------------------------------------------
    unit = next(
        (u for u in state.units if u.unit_id == req.unit_id),
        None
    )

    if not unit:
        print(f"[ERROR][actions] unit not found: {req.unit_id}")
        raise HTTPException(status_code=404, detail="unit not found")

    # -------------------------------------------------
    # ✅ DEBUG INFO (muy importante ahora)
    # -------------------------------------------------
    runtime = getattr(game_session.env, "runtime", None)

    if runtime:
        print(
            f"[DEBUG][actions] unit={unit.unit_id} "
            f"side={unit.side} "
            f"active_side={runtime.active_side} "
            f"activated={unit.unit_id in runtime.activated_units}"
        )
    else:
        print("[DEBUG][actions] runtime not available")

    # -------------------------------------------------
    # ✅ DELEGATE
    # -------------------------------------------------
    try:
        result = get_unit_actions(game_session.env, unit)

        print("[DEBUG][actions] result:", result)

        return result

    except Exception as e:
        print("[ERROR][actions] exception:", str(e))
        raise HTTPException(status_code=500, detail=str(e))
    

@app.post("/api/game/ai-turn")
def game_ai_turn():
    if game_session.env is None:
        return {"error": "no game"}

    env = game_session.env

    # ✅ reutilizar engine si quieres (mejor rendimiento)
    if not hasattr(game_session, "decision_engine"):
        game_session.decision_engine = DecisionEngine()

    decision_engine = game_session.decision_engine

    steps = []

    while True:
        runtime = env.runtime

        active_side = getattr(runtime, "active_side", None)
        activated = getattr(runtime, "activated_units", set())

        print(f"[AI TURN] side={active_side} activated={len(activated)}")

        # ✅ condición de parada:
        # si ya no hay unidades disponibles → fin turno
        result = decision_engine.compute_intent(env)

        if result is None:
            print("[AI TURN] no more actions → end turn")
            break

        unit, action = result

        print(f"[AI] unit={unit.unit_id} action={action.__class__.__name__}")

        env.step(action)

        steps.append({
            "unit": unit.unit_id,
            "action": action.__class__.__name__
        })

    return {
        "state": game_session.get_state(),
        "steps": steps
    }