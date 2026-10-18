from __future__ import annotations

import asyncio
import time
from typing import Dict

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from assault_backend.services.action_service import get_unit_actions
from assault_backend.services.targeting_service import compute_targeting_info
from assault_backend.session_state import ezv2_service, game_session
from assault_model.actions.action_catalog import ActionCatalog
from assault_model.actions.status import WaitAction
from assault_model.map.hex_utils import safe_hex_distance
from assault_model.map.hex_coord import HexCoord
from assault_model.map.terrain_config import terrain_config
from assault_model.runtime.execution_context import ExecutionContext
from assault_sim.decision.decision_engine import DecisionEngine

router = APIRouter(tags=["game"])


class GameStartRequest(BaseModel):
    scenario_id: str
    sides: Dict[str, str]


class UnitActionsRequest(BaseModel):
    unit_id: str


class ResolveReactionRequest(BaseModel):
    use_reaction: bool


class AIConfigRequest(BaseModel):
    checkpoint_path: str | None = None
    simulations: int | None = None
    temperature: float | None = None


@router.get("/api/game/ai-config")
def get_ai_config():
    return {
        "engine": "EfficientZeroV2",
        "active_checkpoint": ezv2_service.active_checkpoint_path if ezv2_service else None,
        "active_run_id": ezv2_service.active_run_id if ezv2_service else None,
        "simulations": ezv2_service.mcts_simulations if ezv2_service else 80,
        "temperature": ezv2_service.mcts_temperature if ezv2_service else 0.6,
        "device": ezv2_service.device if ezv2_service else "cpu",
        "checkpoints": ezv2_service.list_available_checkpoints() if ezv2_service else [],
        "unit_prefilter_enabled": ezv2_service.unit_prefilter_enabled if ezv2_service else True,
        "unit_prefilter_top_k": ezv2_service.unit_prefilter_top_k if ezv2_service else 2,
    }


@router.post("/api/game/ai-config")
def update_ai_config(req: AIConfigRequest):
    if ezv2_service is None:
        raise HTTPException(status_code=503, detail="EZV2 Service not initialized")
    if req.checkpoint_path:
        ok = ezv2_service.load_checkpoint(req.checkpoint_path)
        if not ok:
            raise HTTPException(status_code=400, detail="Failed to load checkpoint")
    if req.simulations is not None:
        ezv2_service.mcts_simulations = max(10, min(req.simulations, 2000))
    if req.temperature is not None:
        ezv2_service.mcts_temperature = max(0.01, min(req.temperature, 2.0))
    return get_ai_config()


@router.get("/api/game/telemetry")
def get_game_telemetry():
    return getattr(game_session, "last_telemetry", {}) or {}


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


@router.post("/api/game/start")
def game_start(req: GameStartRequest):
    try:
        game_session.env = None
        game_session.start(req.scenario_id, req.sides)
        if game_session.env is None:
            raise RuntimeError("env not initialized")
        return {"status": "started", "scenario": req.scenario_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/game/state")
def game_state():
    return game_session.get_state()


@router.get("/api/game/trace")
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


@router.post("/api/game/step")
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
    runtime = getattr(game_session.env, "runtime", None)
    if getattr(runtime, "pending_reaction", None):
        raise HTTPException(
            status_code=409,
            detail="pending reaction decision must be resolved first",
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
            _, reward2, done2, info2 = game_session.env.step(None)
            reward = float(reward or 0.0) + float(reward2 or 0.0)
            done = bool(done or done2)
            if isinstance(info, dict) and isinstance(info2, dict):
                info = {**info, **info2}
        return {"state": game_session.get_state(), "reward": reward, "done": done, "info": info}
    except ValueError as e:
        safe_state = jsonable_encoder(game_session.get_state())
        return JSONResponse(
            status_code=409,
            content={
                "ok": False,
                "code": "INVALID_OR_STALE_ACTION",
                "message": str(e),
                "state": safe_state,
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/game/reaction/resolve")
def game_resolve_reaction(req: ResolveReactionRequest):
    if game_session.env is None:
        raise HTTPException(status_code=400, detail="no game")
    runtime = getattr(game_session.env, "runtime", None)
    if runtime is None:
        raise HTTPException(status_code=500, detail="runtime missing")
    pending = getattr(runtime, "pending_reaction", None)
    if not pending:
        # Gracefully accept duplicate resolve calls without crashing frontend with 409
        return {"state": game_session.get_state(), "reaction": {"resolved": True, "already_cleared": True}}
    context = ExecutionContext(
        event_bus=getattr(game_session.env, "event_bus", None),
        game_map=getattr(game_session.env, "game_state", None).game_map if getattr(game_session.env, "game_state", None) is not None else None,
    )
    result = runtime.resolve_pending_reaction(use_reaction=bool(req.use_reaction), context=context)
    if not bool(result.get("resolved", False)):
        return {"state": game_session.get_state(), "reaction": {"resolved": False, "reason": str(result.get("reason", "reaction_unresolved"))}}
    game_session.env.game_state = runtime.base_state
    game_session.env._emit_map_state()
    return {"state": game_session.get_state(), "reaction": result}


@router.websocket("/ws/game")
async def websocket_game(ws: WebSocket):
    await ws.accept()
    try:
        while game_session.env is None:
            await asyncio.sleep(0.1)
        env = game_session.env
        loop = asyncio.get_running_loop()

        def handler(event):
            if event["type"] in {"MAP_STATE", "REACTION_WINDOW", "REACTION_FIRE", "REACTION_FIRE_SKIPPED"}:
                async def safe_send():
                    try:
                        await ws.send_json({"type": event["type"], "payload": event.get("payload", {})})
                    except Exception:
                        pass
                try:
                    loop.call_soon_threadsafe(asyncio.create_task, safe_send())
                except Exception:
                    pass

        if env.event_bus:
            env.event_bus.subscribe(handler)
        while True:
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass


@router.post("/api/game/actions")
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


@router.post("/api/game/ai-turn")
def game_ai_turn():
    if game_session.env is None:
        return {"error": "no game"}

    env = game_session.env
    if getattr(getattr(env, "runtime", None), "pending_reaction", None):
        return {"state": game_session.get_state(), "steps": [], "blocked": "pending_reaction"}
    if bool(getattr(getattr(env, "game_state", None), "done", False)):
        return {"state": game_session.get_state(), "steps": []}
    if not hasattr(game_session, "decision_engine"):
        game_session.decision_engine = DecisionEngine()

    decision_engine = game_session.decision_engine
    mission_planner = getattr(game_session, "mission_planner", None)
    runtime = env.runtime
    active_side = getattr(runtime, "active_side", None)

    runtime_scenario_id = (
        getattr(game_session, "scenario_id", None)
        or getattr(getattr(env, "scenario", None), "scenario_id", None)
        or getattr(getattr(env, "scenario", None), "id", None)
        or getattr(getattr(env, "scenario", None), "name", None)
    )

    action = None
    unit = None
    source = "heuristic"
    ai_status = "not_attempted"
    ai_reason = "default_heuristic"

    # --- 1. Primary AI Standard: EfficientZeroV2 ---
    if ezv2_service is not None:
        ai_status = "attempted"
        try:
            ezv2_res = ezv2_service.choose_action(
                env,
                active_side=active_side,
                scenario_id=str(runtime_scenario_id or ""),
            )
            raw_action = ezv2_res.get("action")
            raw_unit_id = ezv2_res.get("unit_id")
            if raw_action is not None:
                source = str(ezv2_res.get("source", "efficientzero_v2"))
                ai_status = "used"
                ai_reason = "ezv2_mcts_success"
                game_session.last_telemetry = ezv2_res.get("telemetry", {})
                if raw_unit_id:
                    unit = next((u for u in env.game_state.units if getattr(u, "unit_id", None) == raw_unit_id), None)
                if isinstance(raw_action, str):
                    if hasattr(env, "_resolve_action_by_id"):
                        action = env._resolve_action_by_id(raw_action)
                    if action is None and unit:
                        catalog_acts = ActionCatalog(env.game_state, unit, terrain_config).actions()
                        for a in catalog_acts:
                            if getattr(a, "action_id", None) is None and isinstance(a, WaitAction):
                                a.action_id = f"WAIT:{raw_unit_id}"
                            if getattr(a, "action_id", None) == raw_action:
                                action = a
                                break
                    if action is None:
                        action = raw_action
                else:
                    action = raw_action
            else:
                ai_status = "skipped"
                ai_reason = "no_action_returned"
        except Exception as e:
            print(f"[AI TURN] EZv2 inference failed, falling back to heuristic: {e}")
            ai_status = "failed"
            ai_reason = f"inference_failed:{type(e).__name__}"

    # --- 2. Fallback: DecisionEngine (Heuristic) only if no action proposed ---
    if action is None:
        result = decision_engine.compute_intent(env)
        if result is None:
            try:
                env.step(None)
            except Exception:
                pass
            return {"state": game_session.get_state(), "steps": []}
        h_unit, h_action = result
        unit = unit or h_unit
        action = action or h_action
        source = "heuristic"

    planner_context = None
    if mission_planner is not None and unit is not None:
        try:
            planner_context = mission_planner.build_context(env.game_state, unit, active_side)
        except Exception:
            planner_context = None

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
        aid = str(getattr(action_obj, "action_id", None) or (action_obj if isinstance(action_obj, str) else "") or "")
        if not aid:
            return False
        try:
            legal_actions = ActionCatalog(env.game_state, unit_obj, terrain_config).actions()
        except Exception:
            return False
        legal_ids = {str(getattr(a, "action_id", "") or "") for a in legal_actions}
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
                return (4, 0.0) if not has_movement else (3, -5.0)
            if has_movement:
                if same_hex or backstep_low_threat:
                    return (0, 998.0)
                try:
                    d = _nearest_uncaptured_vp_dist_from_pos(env.game_state, getattr(unit_obj, "side", None), end)
                    dval = float(d) if d is not None else 999.0
                except Exception:
                    dval = 999.0
                return (2, -dval)
            if aid.startswith("WAIT:") or "WAIT" in name:
                return (1, 0.0)
            return (1, -1.0)

        return max(legal_actions, key=_score)

    # Safety checks only for heuristic fallback: do not second-guess EfficientZeroV2 MCTS!
    if not str(source).startswith("efficientzero"):
        if not _action_is_currently_legal(unit, action) or _is_non_displacement_move(action, unit):
            action = _best_catalog_fallback(unit)
            source = "catalog_recovery"
            corrected_reason = "illegal_or_non_displacement"
            if not _action_is_currently_legal(unit, action):
                action = WaitAction(getattr(unit, "unit_id", "SYSTEM"))
                source = "wait_recovery"
                corrected_reason = "no_legal_catalog_action"

        if _is_backstep_under_low_threat(unit, action):
            action = _best_catalog_fallback(unit)
            source = "catalog_recovery_no_backstep"
            corrected_reason = "backstep_low_threat"
            if not _action_is_currently_legal(unit, action) or _is_backstep_under_low_threat(unit, action):
                action = WaitAction(getattr(unit, "unit_id", "SYSTEM"))
                source = "wait_recovery_no_backstep"
                corrected_reason = "backstep_no_safe_fallback"

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

    action_name = str(getattr(action, "__class__", type("X", (), {})).__name__ or "").upper()
    unit_id = unit.unit_id if unit is not None else None
    raw_action_id = getattr(action, "action_id", None)
    is_wait = "WAIT" in action_name
    action_id_str = raw_action_id or (f"WAIT:{unit_id}" if is_wait and unit_id else "WAIT")
    is_attack = any(k in action_name for k in ("ATTACK", "FIRE"))

    step_info = {
        "unit": unit_id,
        "unit_id": unit_id,
        "action": action.__class__.__name__,
        "action_id": action_id_str,
        "source": source,
        "kind": "wait" if is_wait else ("attack" if is_attack else "move"),
        "type": "WAIT" if is_wait else ("ATTACK" if is_attack else "MOVE"),
        "ai_status": ai_status,
        "ai_reason": ai_reason,
        "sb3_status": ai_status,  # For legacy UI backwards compatibility
        "sb3_reason": ai_reason,
        "proposed_action_id": proposed_action_id,
        "proposed_source": proposed_source,
        "corrected": corrected,
        "telemetry": getattr(game_session, "last_telemetry", {}),
    }
    if corrected:
        step_info["corrected_reason"] = corrected_reason or "backend_recovery"

    move_path = getattr(action, "move_path", None) or getattr(action, "path", None)
    if move_path:
        end = move_path[-1]
        step_info["move_q"] = getattr(end, "q", None)
        step_info["move_r"] = getattr(end, "r", None)
        step_info["move_to"] = {"q": step_info["move_q"], "r": step_info["move_r"]}
        step_info["q"] = step_info["move_q"]
        step_info["r"] = step_info["move_r"]

    target_id = getattr(action, "target_id", None)
    if target_id is not None:
        step_info["target_id"] = target_id
        tu = next((u for u in getattr(getattr(env, "game_state", None), "units", []) if getattr(u, "unit_id", None) == target_id), None)
        if tu and getattr(tu, "position", None):
            step_info["target_q"] = tu.position.q
            step_info["target_r"] = tu.position.r

    target_hex = getattr(action, "target_hex", None) or getattr(getattr(action, "fire_action", None), "target_hex", None)
    if target_hex is not None:
        th = HexCoord.from_any(target_hex)
        step_info["target_hex"] = [th.q, th.r]
        step_info["target_q"] = th.q
        step_info["target_r"] = th.r

    steps = [step_info]
    game_session.last_backend_ai_decision = {
        "unit_id": unit_id,
        "action_id": action_id_str,
        "source": source,
        "side": active_side,
        "turn": int(getattr(getattr(env, "game_state", None), "turn", 0) or 0),
        "telemetry": getattr(game_session, "last_telemetry", {}),
    }

    try:
        game_session.record_ai_decision(
            {
                "timestamp": time.time(),
                "side": active_side,
                "turn": int(getattr(getattr(env, "game_state", None), "turn", 0) or 0),
                "unit_id": unit_id,
                "action_id": action_id_str,
                "action": action.__class__.__name__,
                "source": source,
                "ai_status": ai_status,
                "ai_reason": ai_reason,
                "sb3_status": ai_status,
                "sb3_reason": ai_reason,
                "corrected": corrected,
                "corrected_reason": step_info.get("corrected_reason"),
                "telemetry": getattr(game_session, "last_telemetry", {}),
            }
        )
    except Exception:
        pass

    return {
        "state": game_session.get_state(),
        "steps": steps,
        "telemetry": getattr(game_session, "last_telemetry", {}),
    }


@router.get("/targeting")
def get_targeting(attacker_id: str, q: int, r: int):
    if game_session.env is None:
        raise HTTPException(status_code=400, detail="no game")
    gs = game_session.env.game_state
    result = compute_targeting_info(gs, attacker_id, q, r)
    if result is None:
        raise HTTPException(status_code=404, detail="invalid attacker")
    return result
