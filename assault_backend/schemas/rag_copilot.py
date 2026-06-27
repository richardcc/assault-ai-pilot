from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class RagQueryRequest(BaseModel):
    query: str
    mode: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


class RagExplainActionRequest(BaseModel):
    action: Dict[str, Any]
    state_snapshot: Dict[str, Any]
    trace_context: Optional[List[Dict[str, Any]]] = None


class RagRecommendActionsRequest(BaseModel):
    state_snapshot: Dict[str, Any]
    side: str
    constraints: Optional[Dict[str, Any]] = None


class RagTrainingAnalysisRequest(BaseModel):
    runs: List[Dict[str, Any]]


class RagExplainSituationRequest(BaseModel):
    state_snapshot: Dict[str, Any]
