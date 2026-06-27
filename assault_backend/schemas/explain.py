from typing import Any, Dict, List

from pydantic import BaseModel


class StrategicState(BaseModel):
    friendly_strength: str
    enemy_pressure: str
    objective_distance: str


class ActivationPayload(BaseModel):
    unit_id: str
    action: str
    events: List[Dict[str, Any]]
    strategic_state: StrategicState


class ExplainActivationRequest(BaseModel):
    activation: ActivationPayload


class ExplainActivationResponse(BaseModel):
    strategic_intent: Dict[str, Any]
    tactical_execution: Dict[str, Any]
