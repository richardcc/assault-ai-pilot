from __future__ import annotations

from fastapi import APIRouter
from assault_backend.engine import ExplainableEngine
from assault_backend.hrl_service import HRLService
from assault_backend.tactical_service import TacticalService
from assault_backend.schemas.explain import (
    ExplainActivationRequest,
    ExplainActivationResponse,
)

router = APIRouter(tags=["explainability"])

engine = ExplainableEngine(
    hrl_service=HRLService(),
    tactical_service=TacticalService(),
)


@router.get("/api/engine/status")
def engine_status():
    return {
        "status": "ready",
        "engine": "assault-backend",
        "explanations_enabled": True,
        "layers": {"strategic": "local_heuristic", "tactical": "event_summary"},
    }


@router.post("/api/explain/activation", response_model=ExplainActivationResponse)
def explain_activation(request: ExplainActivationRequest):
    return engine.explain_activation(request.activation)
