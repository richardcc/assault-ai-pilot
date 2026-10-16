from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA_VERSION_V2 = "reporting_v2_strict"


class ContractViolation(ValueError):
    """Raised when a payload violates the v2 strict contract."""


@dataclass(frozen=True)
class ContractField:
    key: str
    required: bool = False
    nullable: bool = True


REPLAY_STEP_FIELDS: tuple[ContractField, ...] = (
    ContractField("step", required=True, nullable=False),
    ContractField("action_id", required=True, nullable=False),
    ContractField("unit_id", required=True, nullable=False),
    ContractField("mcts_action_candidates", required=True, nullable=False),
    ContractField("decision_score_selected", required=False, nullable=True),
    ContractField("decision_score_selected_source", required=False, nullable=True),
    ContractField("decision_score_selected_available", required=False, nullable=True),
)


def _has_key(payload: Mapping[str, Any], key: str) -> bool:
    return key in payload


def validate_schema_version(payload: Mapping[str, Any]) -> None:
    ver = str(payload.get("schema_version", "") or "")
    if ver != SCHEMA_VERSION_V2:
        raise ContractViolation(
            f"schema_version mismatch: expected {SCHEMA_VERSION_V2}, got {ver or '<missing>'}"
        )


def validate_replay_step(payload: Mapping[str, Any]) -> None:
    for spec in REPLAY_STEP_FIELDS:
        if spec.required and not _has_key(payload, spec.key):
            raise ContractViolation(f"missing required field: {spec.key}")
        if _has_key(payload, spec.key) and payload.get(spec.key) is None and not spec.nullable:
            raise ContractViolation(f"non-nullable field is null: {spec.key}")


def validate_eval_payload(payload: Mapping[str, Any]) -> None:
    validate_schema_version(payload)
    rows = payload.get("eval_decision_steps_top", [])
    if rows is None:
        raise ContractViolation("eval_decision_steps_top must be an array")
    if not isinstance(rows, list):
        raise ContractViolation("eval_decision_steps_top must be a list")
    for idx, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ContractViolation(f"eval_decision_steps_top[{idx}] is not an object")
        validate_replay_step(row)
