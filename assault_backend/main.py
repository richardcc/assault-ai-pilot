import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# =====================================================
# LOADERS (RAW JSON, NO INFERENCE)
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
# RAG schemas (separated by responsibility)
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
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =====================================================
# LOAD TACTICAL RULEBOOK (ONCE AT STARTUP)
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
# ENGINE (WARM SINGLETON)
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
    Returns engine readiness and capability information.
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
    Explain one activation using the warm Explainable Engine.
    """
    return engine.explain_activation(request.activation)

# =====================================================
# SCENARIO (RAW JSON)
# =====================================================

@app.get("/api/scenarios/{scenario_id}")
def get_scenario_raw(scenario_id: str):
    """
    Return the scenario JSON exactly as stored on disk.
    No transformation, no inference.
    """
    try:
        return load_scenario_raw(scenario_id)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Scenario not found"
        )

# =====================================================
# MAP PIECES (RAW JSON)
# =====================================================

@app.get("/api/map_pieces")
def list_map_pieces_raw():
    """
    Return list of available map piece IDs.
    Raw catalog keys, no transformation.
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
    Return a map piece JSON exactly as stored in catalog.
    No transformation, no inference.
    """
    try:
        return load_map_piece_raw(piece_id)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Map piece not found"
        )
# =====================================================
# UNITS (RAW JSON)
# =====================================================

@app.get("/api/units")
def list_units_raw():
    """
    Return list of available unit keys.
    Raw catalog keys, no transformation.
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
    Return a unit definition exactly as stored in unit_catalog.json.
    No transformation, no inference.
    """
    try:
        return load_unit_raw(unit_key)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail="Unit not found"
        )