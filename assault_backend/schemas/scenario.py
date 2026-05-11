from pydantic import BaseModel
from typing import List


class ScenarioSide(BaseModel):
    id: str
    label: str


class ScenarioResponse(BaseModel):
    id: str
    alias: str
    phase: int
    sequence: int
    goal: str
    max_turns: int
    sides: List[ScenarioSide]