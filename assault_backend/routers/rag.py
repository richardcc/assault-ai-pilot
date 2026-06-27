import json
import os
import urllib.error
import urllib.request

from fastapi import APIRouter, HTTPException

from assault_backend.schemas.rag_copilot import (
    RagExplainSituationRequest,
    RagExplainActionRequest,
    RagQueryRequest,
    RagRecommendActionsRequest,
    RagTrainingAnalysisRequest,
)
from assault_rag.copilot.services import (
    analyze_training_level1,
    explain_action_short,
    explain_game_situation,
    rag_query,
    recommend_actions_advisory,
)

router = APIRouter(prefix="/api/rag", tags=["rag-copilot"])


@router.get("/ollama/status")
def rag_ollama_status():
    base = str(os.getenv("ASSAULT_OLLAMA_BASE_URL", "http://127.0.0.1:11434")).rstrip("/")
    url = f"{base}/api/tags"
    default_model = str(os.getenv("ASSAULT_OLLAMA_MODEL", "qwen2.5:14b")).strip() or "qwen2.5:14b"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)
        models = [
            str((m or {}).get("name", "")).strip()
            for m in (data.get("models", []) or [])
            if str((m or {}).get("name", "")).strip()
        ]
        return {
            "reachable": True,
            "base_url": base,
            "models": models,
            "default_model": default_model,
        }
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return {
            "reachable": False,
            "base_url": base,
            "models": [],
            "default_model": default_model,
        }
    except Exception:
        return {
            "reachable": False,
            "base_url": base,
            "models": [],
            "default_model": default_model,
        }


@router.post("/query")
def rag_query_endpoint(payload: RagQueryRequest):
    try:
        query = str(payload.query or "").strip()
        if not query:
            raise HTTPException(status_code=400, detail="missing query")
        return rag_query(query=query, requested_mode=payload.mode, context=payload.context)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/explain_action")
def rag_explain_action_endpoint(payload: RagExplainActionRequest):
    try:
        return explain_action_short(
            action=payload.action,
            state_snapshot=payload.state_snapshot,
            trace_context=payload.trace_context,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/explain_situation")
def rag_explain_situation_endpoint(payload: RagExplainSituationRequest):
    try:
        return explain_game_situation(payload.state_snapshot)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/recommend_actions")
def rag_recommend_actions_endpoint(payload: RagRecommendActionsRequest):
    try:
        side = str(payload.side or "").strip()
        if not side:
            raise HTTPException(status_code=400, detail="missing side")
        return recommend_actions_advisory(
            state_snapshot=payload.state_snapshot,
            side=side,
            constraints=payload.constraints,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/training_analysis")
def rag_training_analysis_endpoint(payload: RagTrainingAnalysisRequest):
    try:
        if not isinstance(payload.runs, list):
            raise HTTPException(status_code=400, detail="runs must be a list")
        return analyze_training_level1(payload.runs)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
