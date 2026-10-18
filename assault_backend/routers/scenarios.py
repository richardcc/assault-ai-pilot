from __future__ import annotations

from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from assault_backend.services.map_piece_service import (
    load_map_piece_catalog_raw,
    load_map_piece_raw,
)
from assault_backend.services.scenario_service_ui import load_ui_scenario
from assault_backend.services.unit_service import (
    load_unit_catalog_raw,
    load_unit_raw,
)
from assault_backend.session_state import game_session

router = APIRouter(tags=["scenarios"])

from assault_model.paths import SCENARIOS_DIR as SCENARIOS_PATH


@router.get("/api/ui/scenarios")
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


@router.get("/api/ui/scenarios/{scenario_id}")
async def get_scenario(scenario_id: str):
    try:
        return load_ui_scenario(scenario_id)
    except Exception as e:
        safe_state = jsonable_encoder(game_session.get_state())
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "code": "STEP_RUNTIME_ERROR",
                "message": str(e),
                "state": safe_state,
            },
        )


@router.get("/api/map_pieces")
def list_map_pieces_raw():
    try:
        catalog = load_map_piece_catalog_raw()
        return sorted(catalog.get("pieces", {}).keys())
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="Map piece catalog not found")


@router.get("/api/map_pieces/{piece_id}")
def get_map_piece_raw(piece_id: str):
    try:
        return load_map_piece_raw(piece_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Map piece not found")


@router.get("/api/units")
def list_units_raw():
    try:
        catalog = load_unit_catalog_raw()
        return sorted(catalog.get("units", {}).keys())
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="Unit catalog not found")


@router.get("/api/units/{unit_key}")
def get_unit_raw(unit_key: str):
    try:
        return load_unit_raw(unit_key)
    except KeyError:
        raise HTTPException(status_code=404, detail="Unit not found")
