import asyncio
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from assault_backend.engine import ExplainableEngine
from assault_backend.game_session import GameSession
from assault_backend.hrl_service import HRLService
from assault_backend.schemas.explain import (
    ExplainActivationRequest,
    ExplainActivationResponse,
)
from assault_backend.services.action_service import get_unit_actions
from assault_backend.services.map_piece_service import (
    load_map_piece_catalog_raw,
    load_map_piece_raw,
)
from assault_backend.services.targeting_service import compute_targeting_info
from assault_backend.services.unit_service import load_unit_catalog_raw, load_unit_raw
from assault_backend.services.scenario_service_ui import load_ui_scenario
from assault_backend.tactical_service import TacticalService
from assault_backend.routers.rag import router as rag_router
from assault_rag.copilot.index_builder import (
    ensure_game_data_chunks,
    ensure_rule_chunks,
    get_rule_index_status,
    load_rule_chunks,
)
from assault_sim.decision.decision_engine import DecisionEngine
from assault_model.actions.action_catalog import ActionCatalog
from assault_model.map.hex_utils import safe_hex_distance
from assault_model.map.terrain_config import terrain_config
from assault_model.actions.status import WaitAction


game_session = GameSession()
RAG_STARTUP_STATUS = {
    "ok": False,
    "data_chunks": 0,
    "rule_chunks": 0,
    "rule_index_status": {},
    "error": None,
}

@asynccontextmanager
async def app_lifespan(_app: FastAPI):
    """
    Build/load RAG indexes when backend starts, instead of first query.
    Keeps first-request latency low and surfaces ingestion issues early.
    """
    try:
        # Auto-build canonical rulebook chunks from docs when missing.
        ensure_rule_chunks()
        rule_index_status = get_rule_index_status()
        data_chunks = ensure_game_data_chunks()
        rule_chunks = load_rule_chunks()
        if not rule_chunks:
            raise RuntimeError("Rulebook index file exists but loaded zero chunks.")
        RAG_STARTUP_STATUS.update(
            {
                "ok": True,
                "data_chunks": len(data_chunks),
                "rule_chunks": len(rule_chunks),
                "rule_index_status": rule_index_status,
                "error": None,
            }
        )
        print(
            "[RAG STARTUP]"
            f" data_chunks={len(data_chunks)}"
            f" rule_chunks={len(rule_chunks)}"
            f" rule_index={rule_index_status.get('active_path')}"
        )
    except Exception as e:
        RAG_STARTUP_STATUS.update(
            {
                "ok": False,
                "error": str(e),
                "rule_index_status": get_rule_index_status(),
            }
        )
        # Keep backend up for game frontend even if RAG preload fails.
        # RAG endpoints will return actionable errors if invoked.
        print(f"[RAG STARTUP] preload_failed={e}")

    yield


app = FastAPI(title="Assault Backend", version="1.0", lifespan=app_lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    # Allow common LAN dev hosts (e.g. http://192.168.1.28:5173)
    allow_origin_regex=(
        r"^https?://("
        r"localhost|127\.0\.0\.1|"
        r"192\.168\.\d{1,3}\.\d{1,3}|"
        r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
        r"172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}"
        r")(:\d+)?$"
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SCENARIOS_PATH = (
    Path(__file__).resolve().parent.parent
    / "assault_sim"
    / "assets"
    / "scenarios"
)

engine = ExplainableEngine(
    hrl_service=HRLService(),
    tactical_service=TacticalService(),
)

app.include_router(rag_router)


@app.get("/api/engine/status")
def engine_status():
    return {
        "status": "ready",
        "engine": "assault-backend",
        "explanations_enabled": True,
        "layers": {"strategic": "local_heuristic", "tactical": "event_summary"},
    }


@app.get("/api/rag/health")
def rag_health():
    return RAG_STARTUP_STATUS


@app.post("/api/explain/activation", response_model=ExplainActivationResponse)
def explain_activation(request: ExplainActivationRequest):
    return engine.explain_activation(request.activation)


@app.get("/api/ui/scenarios/{scenario_id}")
async def get_scenario(scenario_id: str):
    try:
        return load_ui_scenario(scenario_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ui/scenarios")
def list_ui_scenarios():
    try:
        if not SCENARIOS_PATH.exists():
            raise FileNotFoundError("scenarios path not found")
        scenario_ids = sorted(
            p.stem
            for p in SCENARIOS_PATH.iterdir()
            if p.is_file() and p.suffix.lower() == ".json"
        )
        return {"scenarios": scenario_ids}
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


def _is_human_turn_for_side(side: str | None) -> bool:
    if game_session.env is None or not side:
        return False
    runtime = getattr(game_session.env, "runtime", None)
    active_side = str(getattr(runtime, "active_side", "") or "").upper()
    side_norm = str(side or "").upper()
    if active_side != side_norm:
        return False
    side_mode = str((game_session.sides_config or {}).get(side_norm, "")).lower()
    return side_mode == "human"


def _side_has_pending_activations(env, side: str | None) -> bool:
    if env is None or not side:
        return False
    state = getattr(env, "game_state", None)
    runtime = getattr(env, "runtime", None)
    if state is None or runtime is None:
        return False
    side_norm = str(side).upper()
    activated = set(getattr(runtime, "activated_units", set()) or set())
    for u in getattr(state, "units", []) or []:
        if not getattr(u, "alive", False):
            continue
        if str(getattr(u, "side", "")).upper() != side_norm:
            continue
        if getattr(u, "unit_id", None) not in activated:
            return True
    return False


@app.post("/api/game/start")
def game_start(req: GameStartRequest):
    try:
        game_session.env = None
        if hasattr(game_session, "sb3_ai"):
            game_session.sb3_ai = None
        game_session.start(req.scenario_id, req.sides)
        if game_session.env is None:
            raise RuntimeError("env not initialized")
        return {"status": "started", "scenario": req.scenario_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/game/state")
def game_state():
    return game_session.get_state()


@app.get("/api/game/trace")
def game_trace(limit: int = 5000):
    if game_session.env is None:
        raise HTTPException(status_code=400, detail="no game")
    n = max(1, min(int(limit or 5000), 50000))
    events = game_session.trace_events[-n:]
    return {
        "trace_path": str(game_session.trace_path) if game_session.trace_path is not None else None,
        "events_count": len(game_session.trace_events),
        "events": events,
    }


@app.post("/api/game/step")
async def game_step(payload: Dict):
    action_id = payload.get("action_id")
    if not action_id:
        return {"error": "missing action_id"}
    if game_session.env is None:
        raise HTTPException(status_code=400, detail="no game")
    action_id_str = str(action_id)
    if action_id_str.startswith("WAIT:"):
        unit_id = action_id_str.split(":", 1)[1]
    elif ":" in action_id_str:
        unit_id = action_id_str.split(":", 2)[1]
    else:
        unit_id = ""
    state = game_session.env.game_state
    unit = next((u for u in state.units if getattr(u, "unit_id", None) == unit_id), None)
    unit_side = getattr(unit, "side", None) if unit is not None else None
    last_ai = getattr(game_session, "last_backend_ai_decision", None) or {}
    if last_ai:
        same_unit = str(last_ai.get("unit_id") or "") == str(unit_id or "")
        same_action = str(last_ai.get("action_id") or "") == str(action_id_str or "")
        if same_unit and not same_action:
            print(
                "[FRONTEND_OVERRIDE_DEBUG]"
                f" kind=action_mismatch"
                f" unit={unit_id}"
                f" backend_action_id={last_ai.get('action_id')}"
                f" frontend_action_id={action_id_str}"
            )
    if not _is_human_turn_for_side(unit_side):
        if last_ai:
            print(
                "[FRONTEND_OVERRIDE_DEBUG]"
                f" kind=forbidden_step_on_non_human_turn"
                f" unit={unit_id}"
                f" side={unit_side}"
                f" active_side={getattr(getattr(game_session.env, 'runtime', None), 'active_side', None)}"
                f" backend_last_action_id={last_ai.get('action_id')}"
                f" frontend_action_id={action_id_str}"
            )
        raise HTTPException(
            status_code=403,
            detail=f"manual step denied: side={unit_side} is not active human side",
        )
    try:
        _, reward, done, info = game_session.env.step(action_id)
        runtime = getattr(game_session.env, "runtime", None)
        active_after = str(getattr(runtime, "active_side", "") or "").upper()
        side_mode_after = str((game_session.sides_config or {}).get(active_after, "")).lower()
        if (
            side_mode_after == "human"
            and active_after
            and not _side_has_pending_activations(game_session.env, active_after)
        ):
            # Auto-pass when a human-controlled side has no activations left.
            _, reward2, done2, info2 = game_session.env.step(None)
            reward = float(reward or 0.0) + float(reward2 or 0.0)
            done = bool(done or done2)
            if isinstance(info, dict) and isinstance(info2, dict):
                info = {**info, **info2}
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
    if not _is_human_turn_for_side(getattr(unit, "side", None)):
        raise HTTPException(
            status_code=403,
            detail=f"manual actions denied: side={getattr(unit, 'side', None)} is not active human side",
        )
    try:
        return get_unit_actions(game_session.env, unit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/game/ai-turn")
def game_ai_turn():
    if game_session.env is None:
        return {"error": "no game"}

    env = game_session.env
    if bool(getattr(getattr(env, "game_state", None), "done", False)):
        # Match already ended; do not execute extra AI steps.
        return {"state": game_session.get_state(), "steps": []}
    if not hasattr(game_session, "decision_engine"):
        game_session.decision_engine = DecisionEngine()
    if not hasattr(game_session, "sb3_ai") or game_session.sb3_ai is None:
        try:
            from assault_backend.services.sb3_ai_service import SB3AIService

            game_session.sb3_ai = SB3AIService()
            print(f"[AI TURN] SB3 model loaded: {game_session.sb3_ai.model_path}")
        except Exception as e:
            game_session.sb3_ai = None
            print(f"[AI TURN] SB3 unavailable, falling back to heuristic: {e}")

    decision_engine = game_session.decision_engine
    sb3_ai = game_session.sb3_ai
    mission_planner = getattr(game_session, "mission_planner", None)
    runtime = env.runtime
    active_side = getattr(runtime, "active_side", None)
    result = decision_engine.compute_intent(env)
    if result is None:
        # No intent available: pass activation/turn to avoid side lock.
        try:
            env.step(None)
        except Exception:
            pass
        return {"state": game_session.get_state(), "steps": []}

    unit, heuristic_action = result
    action = heuristic_action
    source = "heuristic"
    planner_context = None
    if mission_planner is not None and unit is not None:
        try:
            planner_context = mission_planner.build_context(env.game_state, unit, active_side)
        except Exception:
            planner_context = None
    sb3_status = "not_attempted"
    sb3_reason = "default_heuristic"
    runtime_scenario_id = getattr(getattr(env, "scenario", None), "id", None) or getattr(
        getattr(env, "scenario", None), "name", None
    )
    if sb3_ai is not None and sb3_ai.can_control_side(active_side, scenario_id=runtime_scenario_id):
        sb3_status = "attempted"
        try:
            sb3_unit, sb3_action, _opt = sb3_ai.choose_unit_and_action(
                env,
                active_side,
                planner_context=planner_context,
            )
            if sb3_action is not None:
                unit = sb3_unit or unit
                if mission_planner is not None and unit is not None:
                    try:
                        planner_context = mission_planner.build_context(env.game_state, unit, active_side)
                    except Exception:
                        planner_context = None
                action = sb3_action
                source = "sb3"
                sb3_status = "used"
                sb3_reason = "ok"
            else:
                sb3_status = "skipped"
                sb3_reason = "no_action_returned"
        except Exception as e:
            print(f"[AI TURN] SB3 inference failed, fallback heuristic: {e}")
            action = heuristic_action
            source = "heuristic_fallback"
            sb3_status = "failed"
            sb3_reason = f"inference_failed:{type(e).__name__}"
    elif sb3_ai is None:
        sb3_status = "skipped"
        sb3_reason = "sb3_unavailable"
    else:
        sb3_status = "skipped"
        sb3_reason = f"side_not_controlled:{active_side}"

    proposed_action_id = getattr(action, "action_id", None)
    proposed_source = source
    corrected_reason: str | None = None

    def _fmt_ax(q, r) -> str:
        if q is None or r is None:
            return "[]"
        try:
            return f"[{chr(65 + int(q))}{int(r) + 1}]"
        except Exception:
            return "[]"

    def _is_non_displacement_move(action_obj, unit_obj) -> bool:
        if action_obj is None or unit_obj is None:
            return False
        unit_pos = getattr(unit_obj, "position", None)
        if unit_pos is None:
            return False
        path = getattr(action_obj, "move_path", None) or getattr(action_obj, "path", None)
        if not path:
            return False
        end = path[-1]
        if end is None:
            return False
        return (
            getattr(end, "q", None) == getattr(unit_pos, "q", None)
            and getattr(end, "r", None) == getattr(unit_pos, "r", None)
        )

    def _action_is_currently_legal(unit_obj, action_obj) -> bool:
        if unit_obj is None or action_obj is None:
            return False
        try:
            legal_actions = ActionCatalog(env.game_state, unit_obj, terrain_config).actions()
        except Exception:
            return False
        legal_ids = {
            str(getattr(a, "action_id", "") or "")
            for a in legal_actions
        }
        aid = str(getattr(action_obj, "action_id", "") or "")
        if not aid:
            return False
        return aid in legal_ids

    def _nearest_uncaptured_vp_dist_from_pos(state_obj, side: str | None, pos) -> float | None:
        if state_obj is None or not side or pos is None:
            return None
        points = getattr(getattr(state_obj, "victory", None), "points", []) or []
        if not points:
            return None
        side_to_ownership = getattr(state_obj, "side_to_ownership", {}) or {}
        own_ownership = side_to_ownership.get(str(side).upper())
        best = None
        for vp in points:
            coords = getattr(vp, "hex_coords", None)
            if coords is None:
                continue
            hs = getattr(state_obj, "hex_states", {}).get(coords)
            if hs is not None and getattr(hs, "ownership", None) == own_ownership:
                continue
            try:
                d = safe_hex_distance(pos, coords)
            except Exception:
                continue
            if best is None or d < best:
                best = d
        return float(best) if best is not None else None

    def _nearest_uncaptured_vp_coords_from_pos(state_obj, side: str | None, pos) -> tuple[int, int] | None:
        if state_obj is None or not side or pos is None:
            return None
        points = getattr(getattr(state_obj, "victory", None), "points", []) or []
        if not points:
            return None
        side_to_ownership = getattr(state_obj, "side_to_ownership", {}) or {}
        own_ownership = side_to_ownership.get(str(side).upper())
        best_coords = None
        best_d = None
        for vp in points:
            coords = getattr(vp, "hex_coords", None)
            if coords is None:
                continue
            hs = getattr(state_obj, "hex_states", {}).get(coords)
            if hs is not None and getattr(hs, "ownership", None) == own_ownership:
                continue
            try:
                d = safe_hex_distance(pos, coords)
            except Exception:
                continue
            if best_d is None or d < best_d:
                best_d = d
                best_coords = (int(coords[0]), int(coords[1]))
        return best_coords

    def _enemy_min_dist(state_obj, side: str | None, pos) -> float | None:
        if state_obj is None or not side or pos is None:
            return None
        best = None
        for e in getattr(state_obj, "units", []) or []:
            if not getattr(e, "alive", False):
                continue
            if str(getattr(e, "side", "")).upper() == str(side).upper():
                continue
            epos = getattr(e, "position", None)
            if epos is None:
                continue
            try:
                d = safe_hex_distance(pos, epos)
            except Exception:
                continue
            if best is None or d < best:
                best = d
        return float(best) if best is not None else None

    def _is_backstep_under_low_threat(unit_obj, action_obj) -> bool:
        if unit_obj is None or action_obj is None:
            return False
        unit_pos = getattr(unit_obj, "position", None)
        if unit_pos is None:
            return False
        path = getattr(action_obj, "move_path", None) or getattr(action_obj, "path", None)
        if not path:
            return False
        end = path[-1]
        if end is None:
            return False
        side = getattr(unit_obj, "side", None)
        d_before = _nearest_uncaptured_vp_dist_from_pos(env.game_state, side, unit_pos)
        d_after = _nearest_uncaptured_vp_dist_from_pos(env.game_state, side, end)
        if d_before is None or d_after is None:
            return False
        enemy_d = _enemy_min_dist(env.game_state, side, unit_pos)
        low_threat = enemy_d is None or enemy_d > 2.0
        return low_threat and d_after > d_before

    def _best_catalog_fallback(unit_obj):
        if unit_obj is None:
            return WaitAction("SYSTEM")
        try:
            legal_actions = ActionCatalog(env.game_state, unit_obj, terrain_config).actions()
        except Exception:
            return WaitAction(getattr(unit_obj, "unit_id", "SYSTEM"))
        if not legal_actions:
            return WaitAction(getattr(unit_obj, "unit_id", "SYSTEM"))

        def _is_uncaptured_vp_hex_for_side(end_pos) -> bool:
            if end_pos is None:
                return False
            state_obj = env.game_state
            side = getattr(unit_obj, "side", None)
            if state_obj is None or not side:
                return False
            coords = (getattr(end_pos, "q", None), getattr(end_pos, "r", None))
            if coords[0] is None or coords[1] is None:
                return False
            points = getattr(getattr(state_obj, "victory", None), "points", []) or []
            vp_coords = {tuple(getattr(vp, "hex_coords", (None, None))) for vp in points}
            if coords not in vp_coords:
                return False
            side_to_ownership = getattr(state_obj, "side_to_ownership", {}) or {}
            own_ownership = side_to_ownership.get(str(side).upper())
            hs = getattr(state_obj, "hex_states", {}).get(coords)
            if hs is None:
                return False
            return getattr(hs, "ownership", None) != own_ownership

        def _score(a):
            name = str(getattr(a, "__class__", type("X", (), {})).__name__ or "").upper()
            aid = str(getattr(a, "action_id", "") or "").upper()
            is_attack = any(k in name for k in ("ATTACK", "FIRE")) or "RANGED" in aid
            path = getattr(a, "move_path", None) or getattr(a, "path", None)
            has_movement = bool(path)
            unit_pos = getattr(unit_obj, "position", None)
            end = path[-1] if path else None
            same_hex = False
            if unit_pos is not None and end is not None:
                same_hex = (
                    getattr(end, "q", None) == getattr(unit_pos, "q", None)
                    and getattr(end, "r", None) == getattr(unit_pos, "r", None)
                )

            backstep_low_threat = has_movement and _is_backstep_under_low_threat(unit_obj, a)

            if is_attack:
                if not has_movement:
                    # Pure attacks are preferred when legal.
                    return (4, 0.0)
                if same_hex or backstep_low_threat:
                    # Don't pick tactical drift from composite actions.
                    return (1, -10.0)
                try:
                    d = decision_engine.option_executor._nearest_uncaptured_vp_dist_from_pos(  # type: ignore[attr-defined]
                        env.game_state, getattr(unit_obj, "side", None), end
                    )
                    dval = float(d) if d is not None else 999.0
                except Exception:
                    dval = 999.0
                # Composite attacks are good, but behind pure attacks.
                return (3, -dval)
            if has_movement:
                if same_hex:
                    return (0, 999.0)
                if _is_uncaptured_vp_hex_for_side(end):
                    # Hard-priority: if we can step on an uncaptured VP now, do it.
                    return (5, 0.0)
                if backstep_low_threat:
                    return (0, 998.0)
                try:
                    d = decision_engine.option_executor._nearest_uncaptured_vp_dist_from_pos(  # type: ignore[attr-defined]
                        env.game_state, getattr(unit_obj, "side", None), end
                    )
                    dval = float(d) if d is not None else 999.0
                except Exception:
                    dval = 999.0
                # Prefer real displacement that improves objective proximity.
                return (2, -dval)
            if aid.startswith("WAIT:") or "WAIT" in name:
                return (1, 0.0)
            return (1, -1.0)

        return max(legal_actions, key=_score)

    def _planner_stage_adjust(action_obj):
        if planner_context is None or unit is None:
            return action_obj, None
        stage = str(getattr(planner_context, "stage", "") or "").upper()
        focus_hex = getattr(planner_context, "focus_hex", None)
        if stage != "STEP_IN" or focus_hex is None:
            return action_obj, None
        path = getattr(action_obj, "move_path", None) or getattr(action_obj, "path", None)
        if path:
            end = path[-1]
            if end is not None and (getattr(end, "q", None), getattr(end, "r", None)) == tuple(focus_hex):
                return action_obj, None
        try:
            legal_actions = ActionCatalog(env.game_state, unit, terrain_config).actions()
        except Exception:
            return action_obj, None
        for a in legal_actions:
            p = getattr(a, "move_path", None) or getattr(a, "path", None)
            if not p:
                continue
            end = p[-1]
            if end is None:
                continue
            if (getattr(end, "q", None), getattr(end, "r", None)) == tuple(focus_hex):
                return a, "planner_step_in_priority"
        return action_obj, None

    def _log_vp_fallback_debug(unit_obj, chosen_action, fallback_source: str):
        if unit_obj is None:
            return
        try:
            pos = getattr(unit_obj, "position", None)
            side = getattr(unit_obj, "side", None)
            vp_coords = _nearest_uncaptured_vp_coords_from_pos(env.game_state, side, pos)
            legal_actions = ActionCatalog(env.game_state, unit_obj, terrain_config).actions()
            vp_move_ids = []
            for a in legal_actions:
                path = getattr(a, "move_path", None) or getattr(a, "path", None)
                if not path:
                    continue
                end = path[-1]
                if end is None or vp_coords is None:
                    continue
                if (getattr(end, "q", None), getattr(end, "r", None)) == vp_coords:
                    vp_move_ids.append(str(getattr(a, "action_id", "") or ""))
            vp_dist = None
            if vp_coords is not None and pos is not None:
                try:
                    vp_dist = int(safe_hex_distance(pos, vp_coords))
                except Exception:
                    vp_dist = None
            hs = getattr(env.game_state, "hex_states", {}).get(vp_coords) if vp_coords is not None else None
            vp_owner = getattr(hs, "ownership", None) if hs is not None else None
            vp_contested = getattr(hs, "contested", None) if hs is not None else None
            chosen_id = str(getattr(chosen_action, "action_id", None) or "")
            print(
                "[AI VP DEBUG]"
                f" source={fallback_source}"
                f" unit={getattr(unit_obj, 'unit_id', None)}"
                f" from=({getattr(pos, 'q', None)},{getattr(pos, 'r', None)})"
                f" nearest_vp={vp_coords}"
                f" vp_dist={vp_dist}"
                f" vp_owner={vp_owner}"
                f" vp_contested={vp_contested}"
                f" vp_reachable_now={len(vp_move_ids) > 0}"
                f" vp_moves={vp_move_ids[:4]}"
                f" chosen={chosen_id}"
            )
        except Exception as e:
            print(f"[AI VP DEBUG] logging_failed={e}")

    # Safety gate: reject stale/invalid actions and pseudo-moves from policy.
    # Rule: backend must not "out-decide" SB3 by selecting an alternative action.
    # For SB3 proposals, execute as-is if valid; otherwise degrade to WAIT.
    action, planner_adjust_reason = _planner_stage_adjust(action)
    if planner_adjust_reason:
        corrected_reason = corrected_reason or planner_adjust_reason
        source = "planner_stage_recovery"

    if not _action_is_currently_legal(unit, action) or _is_non_displacement_move(action, unit):
        rej_path = getattr(action, "move_path", None) or getattr(action, "path", None)
        rej_to = rej_path[-1] if rej_path else None
        rej_q = getattr(rej_to, "q", None) if rej_to is not None else None
        rej_r = getattr(rej_to, "r", None) if rej_to is not None else None
        print(
            "[AI TURN DEBUG] rejected_action"
            f" source={source}"
            f" unit={getattr(unit, 'unit_id', None)}"
            f" action_id={getattr(action, 'action_id', None)}"
            f" to_ax={_fmt_ax(rej_q, rej_r)}"
            f" non_displacement={_is_non_displacement_move(action, unit)}"
        )
        if source.startswith("sb3"):
            action = WaitAction(getattr(unit, "unit_id", "SYSTEM"))
            source = "wait_recovery_sb3_rejected"
            corrected_reason = corrected_reason or "rejected_policy_action"
        else:
            # Non-SB3 path keeps legal recovery behavior.
            if not _action_is_currently_legal(unit, action) or _is_non_displacement_move(action, unit):
                action = _best_catalog_fallback(unit)
                source = "catalog_recovery"
                corrected_reason = corrected_reason or "illegal_or_non_displacement"
                _log_vp_fallback_debug(unit, action, source)
                if not _action_is_currently_legal(unit, action):
                    action = WaitAction(getattr(unit, "unit_id", "SYSTEM"))
                    source = "wait_recovery"
                    corrected_reason = corrected_reason or "no_legal_catalog_action"

    # Safety gate: block tactical backstep drift in low-threat context.
    if _is_backstep_under_low_threat(unit, action):
        rej_path = getattr(action, "move_path", None) or getattr(action, "path", None)
        rej_to = rej_path[-1] if rej_path else None
        rej_q = getattr(rej_to, "q", None) if rej_to is not None else None
        rej_r = getattr(rej_to, "r", None) if rej_to is not None else None
        print(
            "[AI TURN DEBUG] rejected_backstep"
            f" source={source}"
            f" unit={getattr(unit, 'unit_id', None)}"
            f" action_id={getattr(action, 'action_id', None)}"
            f" to_ax={_fmt_ax(rej_q, rej_r)}"
        )
        if str(source).startswith("sb3"):
            action = WaitAction(getattr(unit, "unit_id", "SYSTEM"))
            source = "wait_recovery_sb3_backstep"
            corrected_reason = corrected_reason or "backstep_low_threat"
        else:
            action = _best_catalog_fallback(unit)
            source = "catalog_recovery_no_backstep"
            corrected_reason = corrected_reason or "backstep_low_threat"
            _log_vp_fallback_debug(unit, action, source)
            if not _action_is_currently_legal(unit, action) or _is_backstep_under_low_threat(unit, action):
                action = WaitAction(getattr(unit, "unit_id", "SYSTEM"))
                source = "wait_recovery_no_backstep"
                corrected_reason = corrected_reason or "backstep_no_safe_fallback"
        if not _action_is_currently_legal(unit, action):
            corrected_reason = corrected_reason or "backstep_no_safe_fallback"

    # Debug: show selected unit current position + returned action.
    try:
        u_pos = getattr(unit, "position", None)
        u_q = getattr(u_pos, "q", None) if u_pos is not None else None
        u_r = getattr(u_pos, "r", None) if u_pos is not None else None
        a_name = str(getattr(action, "__class__", type("X", (), {})).__name__ or "")
        a_id = getattr(action, "action_id", None)
        a_target = getattr(action, "target_id", None)
        a_path = getattr(action, "move_path", None) or getattr(action, "path", None)
        a_to = None
        if a_path:
            end = a_path[-1]
            a_to = (getattr(end, "q", None), getattr(end, "r", None))
        src_txt = str(source or "")
        if src_txt.startswith("heuristic"):
            src_colored = f"\x1b[33m{src_txt}\x1b[0m"
        elif src_txt.startswith("sb3"):
            src_colored = f"\x1b[36m{src_txt}\x1b[0m"
        else:
            src_colored = src_txt

        print(
            "[AI TURN DEBUG]"
            f" side={active_side}"
            f" source={src_colored}"
            f" sb3_status={sb3_status}"
            f" sb3_reason={sb3_reason}"
            f" planner_stage={str(getattr(planner_context, 'stage', '') or '')}"
            f" planner_focus={str(getattr(planner_context, 'focus_vp_id', '') or '')}"
            f" unit={getattr(unit, 'unit_id', None)}"
            f" from=({u_q},{u_r})"
            f" from_ax={_fmt_ax(u_q, u_r)}"
            f" action={a_name}"
            f" action_id={a_id}"
            f" target={a_target}"
            f" to={a_to}"
            f" to_ax={_fmt_ax(a_to[0], a_to[1]) if a_to else '[]'}"
        )
    except Exception as _e:
        print(f"[AI TURN DEBUG] logging_failed: {_e}")

    env.step(action)
    if mission_planner is not None and planner_context is not None:
        try:
            mission_planner.register_outcome(env.game_state, planner_context, action)
        except Exception:
            pass

    final_action_id = getattr(action, "action_id", None)
    corrected = (
        str(source).lower() != str(proposed_source).lower()
        or str(final_action_id or "") != str(proposed_action_id or "")
    )

    def _step_payload(unit_obj, action_obj, src: str):
        action_name = str(getattr(action_obj, "__class__", type("X", (), {})).__name__ or "").upper()
        unit_id = unit_obj.unit_id if unit_obj is not None else None
        raw_action_id = getattr(action_obj, "action_id", None)
        is_wait = "WAIT" in action_name
        action_id = raw_action_id
        if not action_id and is_wait and unit_id:
            # WaitAction currently has no explicit action_id in model classes.
            action_id = f"WAIT:{unit_id}"
        is_attack = any(k in action_name for k in ("ATTACK", "FIRE"))
        payload = {
            "unit": unit_id,
            "unit_id": unit_id,
            "action": action_obj.__class__.__name__,
            "action_id": action_id,
            "source": src,
            # Frontend highlight/log compatibility.
            "kind": "wait" if is_wait else ("attack" if is_attack else "move"),
            "type": "WAIT" if is_wait else ("ATTACK" if is_attack else "MOVE"),
        }
        payload["sb3_status"] = sb3_status
        payload["sb3_reason"] = sb3_reason
        payload["proposed_action_id"] = proposed_action_id
        payload["proposed_source"] = proposed_source
        payload["corrected"] = corrected
        if planner_context is not None:
            payload["planner_stage"] = str(getattr(planner_context, "stage", "") or "")
            payload["planner_intent"] = str(getattr(planner_context, "intent", "") or "")
            payload["planner_focus_vp_id"] = getattr(planner_context, "focus_vp_id", None)
            payload["planner_replan_reason"] = str(getattr(planner_context, "replan_reason", "") or "")
        if corrected:
            payload["corrected_reason"] = corrected_reason or "backend_recovery"
        target_id = getattr(action_obj, "target_id", None)
        if target_id is not None:
            payload["target_id"] = target_id
        target_hex = getattr(action_obj, "target_hex", None)
        if target_hex is not None and isinstance(target_hex, (tuple, list)) and len(target_hex) >= 2:
            payload["target_q"] = target_hex[0]
            payload["target_r"] = target_hex[1]
        move_path = getattr(action_obj, "move_path", None) or getattr(action_obj, "path", None)
        if move_path:
            end = move_path[-1]
            payload["move_q"] = getattr(end, "q", None)
            payload["move_r"] = getattr(end, "r", None)
            payload["move_to"] = {"q": payload["move_q"], "r": payload["move_r"]}
            # Legacy UI fields consumed by some handlers.
            payload["q"] = payload["move_q"]
            payload["r"] = payload["move_r"]
        elif target_hex is not None and isinstance(target_hex, (tuple, list)) and len(target_hex) >= 2:
            payload["q"] = target_hex[0]
            payload["r"] = target_hex[1]
        return payload

    steps = [_step_payload(unit, action, source)]
    game_session.last_backend_ai_decision = {
        "unit_id": getattr(unit, "unit_id", None),
        "action_id": getattr(action, "action_id", None),
        "source": source,
        "side": active_side,
        "turn": int(getattr(getattr(env, "game_state", None), "turn", 0) or 0),
    }
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
