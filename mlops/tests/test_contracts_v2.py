from __future__ import annotations

import pytest

from mlops.contracts_v2 import (
    SCHEMA_VERSION_V2,
    ContractViolation,
    validate_eval_payload,
)


def test_validate_eval_payload_accepts_minimal_valid_shape() -> None:
    payload = {
        "schema_version": SCHEMA_VERSION_V2,
        "eval_decision_steps_top": [
            {
                "step": 0,
                "action_id": "WAIT:U1",
                "unit_id": "U1",
                "mcts_action_candidates": [],
                "decision_score_selected": None,
            }
        ],
    }
    validate_eval_payload(payload)


def test_validate_eval_payload_rejects_wrong_schema_version() -> None:
    payload = {"schema_version": "reporting_v2", "eval_decision_steps_top": []}
    with pytest.raises(ContractViolation):
        validate_eval_payload(payload)


def test_validate_eval_payload_rejects_missing_required_step_field() -> None:
    payload = {
        "schema_version": SCHEMA_VERSION_V2,
        "eval_decision_steps_top": [
            {
                "step": 0,
                "action_id": "WAIT:U1",
                "mcts_action_candidates": [],
            }
        ],
    }
    with pytest.raises(ContractViolation):
        validate_eval_payload(payload)
