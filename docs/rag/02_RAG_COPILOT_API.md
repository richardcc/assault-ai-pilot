# RAG Copilot API

## `POST /api/rag/query`

### Request
```json
{
  "query": "What modifiers apply to hindered LOS?",
  "mode": "hybrid"
}
```

### Response
```json
{
  "mode": "hybrid",
  "answer": "Consulta: ...",
  "citations": [
    { "source_type": "rule", "source_id": "10.9.2", "snippet": "..." }
  ],
  "evidence": { "rules_count": 3, "data_count": 1 },
  "limitations": []
}
```

## `POST /api/rag/explain_action`

### Request
```json
{
  "action": { "unit_id": "US_2", "action": "RangedCombat" },
  "state_snapshot": { "nearest_vp_distance": 2 },
  "trace_context": [{ "action": "move" }, { "action": "attack" }]
}
```

### Response
```json
{
  "short_explanation": "US_2 ejecuta ...",
  "citations": [
    { "source_type": "rule", "source_id": "10.7", "snippet": "..." }
  ],
  "limitations": []
}
```

## `POST /api/rag/recommend_actions`

### Request
```json
{
  "side": "US",
  "state_snapshot": {
    "legal_actions": [
      { "action": "Move", "tags": ["objective_progress"] },
      { "action": "RangedAttack", "tags": ["pressure"] }
    ]
  }
}
```

### Response
```json
{
  "recommendations": [
    {
      "action": { "action": "Move", "tags": ["objective_progress"] },
      "rationale_short": "prioriza progreso objetivo...",
      "risk_note": "riesgo medio ...",
      "citations": []
    }
  ],
  "limitations": []
}
```

## `POST /api/rag/training_analysis`

### Request
```json
{
  "runs": [
    {
      "run_id": "smoke_42",
      "events": [
        { "action": "WAIT", "damage": 0, "capture_event": false },
        { "action": "MOVE", "damage": 0, "capture_event": false }
      ]
    }
  ]
}
```

### Response
```json
{
  "patterns": ["high_wait_ratio", "low_capture_pressure"],
  "metrics": { "total_steps": 2, "wait_ratio": 0.5, "capture_ratio": 0.0, "damage_ratio": 0.0 },
  "examples": [{ "action": "MOVE", "damage": 0, "capture_event": false }],
  "recommendations": ["Revisar penalización de WAIT..."],
  "citations": [],
  "limitations": []
}
```
