from fastapi.testclient import TestClient

from assault_backend.main import app


client = TestClient(app)


def _assert_citation_shape(citation: dict):
    assert "source_type" in citation
    assert "source_id" in citation
    assert "snippet" in citation
    assert isinstance(citation["snippet"], str)


def test_rag_query_golden_hybrid_response_shape():
    payload = {
        "query": "What is US_RIFLES_43 movement and what rule applies to hindered LOS?",
        "mode": "hybrid",
    }
    res = client.post("/api/rag/query", json=payload)
    assert res.status_code == 200, res.text
    body = res.json()

    assert body["mode"] in {"rules", "data", "hybrid"}
    assert isinstance(body.get("answer"), str)
    assert "citations" in body
    assert "limitations" in body
    assert "evidence" in body
    if body["citations"]:
        _assert_citation_shape(body["citations"][0])


def test_rag_explain_action_golden_response_shape():
    payload = {
        "action": {"unit_id": "US_2", "action": "RangedCombat"},
        "state_snapshot": {"nearest_vp_distance": 2},
        "trace_context": [
            {"action": "Move", "result": "ok"},
            {"action": "RangedCombat", "result": "damage"},
        ],
    }
    res = client.post("/api/rag/explain_action", json=payload)
    assert res.status_code == 200, res.text
    body = res.json()

    assert isinstance(body.get("short_explanation"), str)
    assert "citations" in body
    assert "limitations" in body
    if body["citations"]:
        _assert_citation_shape(body["citations"][0])


def test_rag_recommend_actions_golden_response_shape():
    payload = {
        "side": "US",
        "state_snapshot": {
            "legal_actions": [
                {"action": "Move", "tags": ["objective_progress", "capture"]},
                {"action": "RangedAttack", "tags": ["pressure"]},
                {"action": "Wait", "tags": []},
            ]
        },
    }
    res = client.post("/api/rag/recommend_actions", json=payload)
    assert res.status_code == 200, res.text
    body = res.json()

    assert "recommendations" in body
    assert "limitations" in body
    assert isinstance(body["recommendations"], list)
    if body["recommendations"]:
        rec = body["recommendations"][0]
        assert "action" in rec
        assert "rationale_short" in rec
        assert "risk_note" in rec
        assert "citations" in rec
        if rec["citations"]:
            _assert_citation_shape(rec["citations"][0])


def test_rag_training_analysis_golden_response_shape():
    payload = {
        "runs": [
            {
                "run_id": "smoke_001",
                "events": [
                    {"action": "WAIT", "damage": 0, "capture_event": False},
                    {"action": "MOVE", "damage": 0, "capture_event": False},
                    {"action": "RANGED_ATTACK", "damage": 1, "capture_event": True},
                ],
            }
        ]
    }
    res = client.post("/api/rag/training_analysis", json=payload)
    assert res.status_code == 200, res.text
    body = res.json()

    assert "patterns" in body
    assert "metrics" in body
    assert "examples" in body
    assert "recommendations" in body
    assert "citations" in body
    assert "limitations" in body
    assert "wait_ratio" in body["metrics"]
    assert "capture_ratio" in body["metrics"]
    assert "damage_ratio" in body["metrics"]
    if body["citations"]:
        _assert_citation_shape(body["citations"][0])


def test_rag_explain_situation_golden_response_shape():
    payload = {
        "state_snapshot": {
            "turn": 3,
            "active_side": "US",
            "vp_score_live": {"US": 4, "IT": 3},
            "units": [
                {"id": "US_1", "side": "US", "hp": 3},
                {"id": "US_2", "side": "US", "hp": 2},
                {"id": "IT_1", "side": "IT", "hp": 1},
            ],
            "done": False,
        }
    }
    res = client.post("/api/rag/explain_situation", json=payload)
    assert res.status_code == 200, res.text
    body = res.json()
    assert "situation_summary" in body
    assert "priorities" in body
    assert "risks" in body
    assert "opportunities" in body
    assert "key_unit_alerts" in body
    assert "citations" in body
    assert "limitations" in body
    if body["citations"]:
        _assert_citation_shape(body["citations"][0])
