import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from services.scenario_service_ui import load_ui_scenario
# =====================================================
# LOADERS
# =====================================================

# ✅ IMPORTANTE:
# load_scenario_raw AHORA YA CONSTRUYE HEXES + TERRAIN
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
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =====================================================
# LOAD TACTICAL RULEBOOK
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
# ENDPOINTS
# =====================================================

@app.get("/api/engine/status")
def engine_status():
    """
    Engine health + capability info.
    """
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
    """
    Explain one activation using HRL + Tactical layers.
    """
    return engine.explain_activation(request.activation)

# =====================================================
# SCENARIO (CON HEXES + TERRAIN)
# =====================================================

@app.get("/api/scenarios/{scenario_id}")
def get_scenario(scenario_id: str):
    """
    Return scenario with:
    ✅ pieces
    ✅ grid
    ✅ hexes (built from map pieces)
    ✅ terrain per hex
    """
    try:
        scenario = load_scenario_raw(scenario_id)
        return scenario

    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Scenario not found"
        )

    except Exception as e:
        print(f"[ERROR] Scenario build failed: {e}")
        raise HTTPException(
            status_code=500,
            detail="Scenario build error"
        )

# =====================================================
# MAP PIECES (RAW)
# =====================================================

@app.get("/api/map_pieces")
def list_map_pieces_raw():
    """
    Return list of map piece IDs.
    """
    try:
        catalog = load_map_piece_catalog_raw()
        pieces = catalog.get("pieces", {})
        return sorted(pieces.keys())

    except FileNotFoundError:
        raise HTTPException(
            status_code=500,
            detail="Map piece catalog not found"
        )


@app.get("/api/map_pieces/{piece_id}")
def get_map_piece_raw(piece_id: str):
    """
    Return raw map piece definition.
    """
    try:
        return load_map_piece_raw(piece_id)

    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Map piece not found"
        )

# =====================================================
# UNITS (RAW)
# =====================================================

@app.get("/api/units")
def list_units_raw():
    """
    Return available unit keys.
    """
    try:
        catalog = load_unit_catalog_raw()
        units = catalog.get("units", {})
        return sorted(units.keys())

    except FileNotFoundError:
        raise HTTPException(
            status_code=500,
            detail="Unit catalog not found"
        )


@app.get("/api/units/{unit_key}")
def get_unit_raw(unit_key: str):
    """
    Return raw unit definition.
    """
    try:
        return load_unit_raw(unit_key)

    except KeyError:
        raise HTTPException(
            status_code=404,
            detail="Unit not found"
        )

# =====================================================
# SCENARIO (UI ADAPTER)
# =====================================================

@app.get("/api/ui/scenarios/{scenario_id}")
def get_ui_scenario(scenario_id: str):
    """
    Return UI-friendly scenario:
    ✅ flat hex list
    ✅ normalized unit positions
    ✅ simplified structure
    """
    try:
        return load_ui_scenario(scenario_id)

    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Scenario not found"
        )

    except Exception as e:
        print(f"[ERROR] UI scenario build failed: {e}")
        raise HTTPException(
            status_code=500,
            detail="Scenario UI error"
        )