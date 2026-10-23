from assault_model.map.topography_analyzer import analyze_battlefield_topography
import json
import os
import re
import urllib.error
import urllib.request
from collections import defaultdict, deque
from threading import Lock
from typing import Dict, List

from assault_rag.copilot.retriever import classify_query_mode, retrieve_evidence


UNIT_QUERY_HINTS = {
    "unit",
    "units",
    "unidad",
    "unidades",
    "rifle",
    "rifles",
    "sniper",
    "mortar",
    "bazooka",
    "catalog",
    "catalogo",
    "catálogo",
    "disponibles",
}

_RAG_MEMORY_MAX_TURNS = max(1, int(os.getenv("ASSAULT_RAG_MEMORY_TURNS", "6")))
_RAG_MEMORY: dict[str, deque[dict]] = defaultdict(lambda: deque(maxlen=_RAG_MEMORY_MAX_TURNS))
_RAG_MEMORY_LOCK = Lock()


def _to_int(value):
    try:
        return int(value)
    except Exception:
        return None


def _hex_distance(aq: int, ar: int, bq: int, br: int) -> int:
    # Axial distance for hex grids.
    return (abs(aq - bq) + abs((aq + ar) - (bq + br)) + abs(ar - br)) // 2


def _unit_coords(unit: Dict) -> tuple[int, int] | None:
    q = _to_int(unit.get("q"))
    r = _to_int(unit.get("r"))
    if q is not None and r is not None:
        return q, r
    pos = unit.get("position")
    if isinstance(pos, dict):
        q = _to_int(pos.get("q"))
        r = _to_int(pos.get("r"))
        if q is not None and r is not None:
            return q, r
    if isinstance(pos, (list, tuple)) and len(pos) >= 2:
        q = _to_int(pos[0])
        r = _to_int(pos[1])
        if q is not None and r is not None:
            return q, r
    return None


def _query_terms(query: str) -> List[str]:
    terms = [t.lower() for t in re.findall(r"[a-zA-Z0-9_]+", query or "") if len(t) > 2]
    # Keep order, remove duplicates.
    seen = set()
    uniq: List[str] = []
    for t in terms:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq


def _looks_like_unit_catalog_query(query: str) -> bool:
    terms = set(_query_terms(query))
    if terms & UNIT_QUERY_HINTS:
        return True
    for t in terms:
        parts = set(t.split("_"))
        if parts & UNIT_QUERY_HINTS:
            return True
        if re.match(r"^[a-z]{2}_[a-z0-9_]+$", t.lower()):
            return True
    return False


def _looks_like_counter_query(query: str) -> bool:
    terms = set(_query_terms(query))
    counter_hints = {
        "counter",
        "counters",
        "ficha",
        "fichas",
        "icono",
        "iconos",
        "grafico",
        "gráfico",
        "simbolo",
        "símbolo",
    }
    return bool(terms & counter_hints)


def _looks_like_combat_resolution_query(query: str) -> bool:
    terms = set(_query_terms(query))
    combat_hints = {
        "dado",
        "dados",
        "die",
        "dice",
        "distancia",
        "alcance",
        "range",
        "contra",
        "vs",
        "ataque",
        "attack",
        "defensa",
        "defense",
        "infanteria",
        "infantry",
        "vehiculo",
        "vehicle",
    }
    return bool(terms & combat_hints)


def _conversation_id_from_context(context: Dict | None) -> str | None:
    ctx = context or {}
    cid = str(ctx.get("conversation_id", "") or "").strip()
    if not cid:
        return None
    return cid[:128]


def _looks_followup_ambiguous(query: str) -> bool:
    q = str(query or "").strip().lower()
    if not q:
        return False
    terms = _query_terms(q)
    if len(terms) <= 3:
        return True
    followup_tokens = {
        "eso",
        "esa",
        "ese",
        "sus",
        "stats",
        "detalles",
        "mas",
        "más",
        "tambien",
        "también",
    }
    return bool(set(terms) & followup_tokens)


def _memory_rewrite_query(query: str, context: Dict | None) -> str:
    cid = _conversation_id_from_context(context)
    if not cid:
        return query
    if not _looks_followup_ambiguous(query):
        return query
    with _RAG_MEMORY_LOCK:
        turns = list(_RAG_MEMORY.get(cid, []))
    if not turns:
        return query
    last_user_query = str(turns[-1].get("query", "") or "").strip()
    if not last_user_query:
        return query
    # Keep retrieval deterministic while injecting immediate intent carry-over.
    return f"{last_user_query} | seguimiento: {query.strip()}"


def _memory_store_turn(*, context: Dict | None, query: str, mode: str, answer: str, citations: List[Dict]) -> None:
    cid = _conversation_id_from_context(context)
    if not cid:
        return
    turn = {
        "query": str(query or "")[:800],
        "mode": str(mode or ""),
        "answer": str(answer or "")[:1200],
        "citation_ids": [str(c.get("source_id", "") or "")[:120] for c in (citations or [])[:6]],
    }
    with _RAG_MEMORY_LOCK:
        _RAG_MEMORY[cid].append(turn)


def _compact_state_snapshot(context: Dict | None) -> Dict:
    ctx = context or {}
    snap = ctx.get("state_snapshot", {}) if isinstance(ctx.get("state_snapshot", {}), dict) else {}
    units = list(snap.get("units", []) or [])
    vp_live = snap.get("vp_score_live", {}) or {}
    active_side = str(snap.get("active_side", "UNKNOWN")).upper()
    side_counts: Dict[str, int] = {}
    for u in units:
        side = str((u or {}).get("side", "UNKNOWN")).upper()
        hp = (u or {}).get("hp", None)
        alive = hp is None or float(hp) > 0
        if alive:
            side_counts[side] = side_counts.get(side, 0) + 1
    return {
        "turn": snap.get("turn"),
        "active_side": active_side,
        "vp_score_live": vp_live,
        "alive_units_by_side": side_counts,
        "done": bool(snap.get("done", False)),
    }


def _augment_query_with_state_context(query: str, context: Dict | None) -> str:
    compact = _compact_state_snapshot(context)
    if compact.get("turn") is None and not compact.get("vp_score_live"):
        return query
    return (
        f"{query.strip()} | "
        f"turn={compact.get('turn')} "
        f"active_side={compact.get('active_side')} "
        f"vp={compact.get('vp_score_live')} "
        f"alive_units={compact.get('alive_units_by_side')}"
    )


def _fallback_answer_from_state(query: str, context: Dict | None) -> str | None:
    compact = _compact_state_snapshot(context)
    ctx = context or {}
    snap = ctx.get("state_snapshot", {}) if isinstance(ctx.get("state_snapshot", {}), dict) else {}
    ai_obs = ctx.get("ai_observability", {}) if isinstance(ctx.get("ai_observability", {}), dict) else {}
    recent_ai = list(ai_obs.get("recent_decisions", []) or [])
    q_lower = str(query or "").lower()
    asks_unmoved_units = any(
        k in q_lower
        for k in (
            "no he movido",
            "no movi",
            "no moví",
            "unidades sin mover",
            "pendientes de mover",
            "sin activar",
            "no activadas",
        )
    )
    asks_moved_units = any(
        k in q_lower
        for k in (
            "han sido movidas",
            "han sido movidos",
            "que unidades movi",
            "qué unidades moví",
            "que unidades he movido",
            "qué unidades he movido",
            "unidades movidas",
            "ya movi",
            "ya moví",
            "ya se movieron",
            "se movieron",
            "activadas",
        )
    )
    if asks_moved_units and isinstance(snap, dict) and snap:
        active_side = str(snap.get("active_side", "") or "").upper()
        units = list(snap.get("units", []) or [])
        activated = {
            str(u)
            for u in (snap.get("activated_units", []) or [])
            if str(u).strip()
        }
        moved = []
        for u in units:
            side = str((u or {}).get("side", "") or "").upper()
            unit_id = str((u or {}).get("id", "") or "")
            unit_key = str((u or {}).get("unit_key", "") or "")
            alive = bool((u or {}).get("alive", True))
            if not unit_id or side != active_side:
                continue
            if not alive:
                continue
            if unit_id in activated:
                moved.append((unit_id, unit_key))
        if not moved:
            return (
                f"No veo unidades ya activadas/movidas para el lado activo {active_side} en este turno."
            )
        short = ", ".join(
            f"{uid}{f' ({uk})' if uk else ''}" for uid, uk in moved[:8]
        )
        more = f" (+{len(moved) - 8} más)" if len(moved) > 8 else ""
        return (
            f"Active side {active_side} units already activated/moved this turn: {short}{more}."
        )
    if asks_unmoved_units and isinstance(snap, dict) and snap:
        active_side = str(snap.get("active_side", "") or "").upper()
        units = list(snap.get("units", []) or [])
        activated = {
            str(u)
            for u in (snap.get("activated_units", []) or [])
            if str(u).strip()
        }
        pending = []
        for u in units:
            side = str((u or {}).get("side", "") or "").upper()
            unit_id = str((u or {}).get("id", "") or "")
            unit_key = str((u or {}).get("unit_key", "") or "")
            alive = bool((u or {}).get("alive", True))
            hp = (u or {}).get("hp", None)
            if not unit_id or side != active_side:
                continue
            if not alive or (hp is not None and float(hp) <= 0):
                continue
            if unit_id in activated:
                continue
            pending.append((unit_id, unit_key))
        if not pending:
            return (
                f"No veo unidades pendientes por mover para el lado activo {active_side} en este turno."
            )
        short = ", ".join(
            f"{uid}{f' ({uk})' if uk else ''}" for uid, uk in pending[:8]
        )
        more = f" (+{len(pending) - 8} más)" if len(pending) > 8 else ""
        return (
            f"Active side {active_side} units awaiting activation this turn: {short}{more}."
        )
    asks_last_ai_move = any(
        k in q_lower
        for k in (
            "que unidad",
            "qué unidad",
            "movio la ia",
            "movió la ia",
            "ultimo movimiento",
            "último movimiento",
            "que hizo la ia",
            "qué hizo la ia",
        )
    )
    asks_recent_ai_history = any(
        k in q_lower
        for k in (
            "ultimas decisiones",
            "últimas decisiones",
            "ultimos turnos",
            "últimos turnos",
            "ultimas acciones",
            "últimas acciones",
            "que hizo la ia en los ultimos",
            "qué hizo la ia en los últimos",
        )
    )
    if asks_recent_ai_history and recent_ai:
        tail = recent_ai[-3:]
        items = []
        for d in tail:
            turn = int(d.get("turn", compact.get("turn", 0)) or 0)
            side = str(d.get("side", compact.get("active_side", "UNKNOWN")) or "UNKNOWN")
            unit_id = str(d.get("unit_id", "?") or "?")
            action_desc = str(d.get("action_id", "") or d.get("action", "") or "unknown_action")
            src = str(d.get("source", "") or "unknown")
            items.append(f"T{turn} {side} {unit_id} -> {action_desc} [{src}]")
        return "Recent AI Decisions: " + " | ".join(items)
    if asks_last_ai_move and recent_ai:
        last = recent_ai[-1]
        unit_id = str(last.get("unit_id", "?") or "?")
        action_id = str(last.get("action_id", "") or "")
        action_name = str(last.get("action", "") or "")
        side = str(last.get("side", compact.get("active_side", "UNKNOWN")) or "UNKNOWN")
        turn = int(last.get("turn", compact.get("turn", 0)) or 0)
        source = str(last.get("source", "") or "EfficientZeroV2_MCTS")
        ai_status = str(last.get("ai_status", last.get("ezv2_status", "")) or "")
        corrected = bool(last.get("corrected", False))
        correction_note = " (decision corrected by backend safety)" if corrected else ""
        action_desc = action_id or action_name or "acción desconocida"
        status_note = f", status={ai_status}" if ai_status else ""
        return (
            f"Last recorded AI decision: Turn {turn}, Side {side}, Unit {unit_id}, "
            f"Action {action_desc}, Brain={source}{status_note}{correction_note}."
        )
    if compact.get("turn") is None and not compact.get("vp_score_live"):
        return None
    active = str(compact.get("active_side", "UNKNOWN"))
    vp_live = compact.get("vp_score_live", {}) or {}
    own_vp = float(vp_live.get(active, 0) or 0)
    enemy_best = max(
        (float(v or 0) for s, v in vp_live.items() if str(s).upper() != active),
        default=0.0,
    )
    gap = enemy_best - own_vp
    if gap >= 3:
        tactical = (
            "The AI prioritizes VP recapture/denial under score deficit; "
            "it must secure at least 1 objective this turn and avoid low-impact attrition."
        )
    elif gap > 0:
        tactical = (
            "The AI should increase objective pressure on VPs and minimize moves without control value."
        )
    else:
        tactical = (
            "With VP advantage, the AI should consolidate control, screen exposed units, and avoid unnecessary casualties."
        )
    return (
        f"Game context detected (Turn {compact.get('turn')}, Active Side {active}, VP {vp_live}). "
        f"{tactical}"
    )


def _query_targets_ai_decision(query: str) -> bool:
    q_lower = str(query or "").lower()
    return any(
        k in q_lower
        for k in (
            "movio la ia",
            "movió la ia",
            "que hizo la ia",
            "qué hizo la ia",
            "decision ia",
            "decisión ia",
            "ultimo movimiento",
            "último movimiento",
            "ultimas decisiones",
            "últimas decisiones",
            "ultimos turnos",
            "últimos turnos",
        )
    )


def _query_targets_live_state_ops(query: str) -> bool:
    q_lower = str(query or "").lower()
    return any(
        k in q_lower
        for k in (
            "no he movido",
            "no movi",
            "no moví",
            "unidades sin mover",
            "pendientes de mover",
            "sin activar",
            "no activadas",
            "que hice este turno",
            "qué hice este turno",
            "que movi",
            "qué moví",
            "han sido movidas",
            "han sido movidos",
            "unidades movidas",
            "se movieron",
            "activadas",
        )
    ) or _query_targets_ai_decision(query)


def _is_manual_scope(context: Dict | None) -> bool:
    ctx = context or {}
    return str(ctx.get("assistant_scope", "") or "").strip().lower() == "manual"


def _clean_text(text: str) -> str:
    # Flatten markdown-ish content so snippets are readable in UI.
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _focused_snippet(text: str, query: str, max_len: int = 220) -> str:
    clean = _clean_text(text)
    if not clean:
        return ""
    terms = _query_terms(query)
    lower = clean.lower()

    pos = -1
    for term in terms:
        idx = lower.find(term)
        if idx >= 0:
            pos = idx
            break

    if pos < 0:
        return clean[:max_len]

    half = max_len // 2
    start = max(0, pos - half)
    end = min(len(clean), start + max_len)
    snippet = clean[start:end].strip()
    if start > 0:
        snippet = "..." + snippet
    if end < len(clean):
        snippet = snippet + "..."
    return snippet


def _build_citation(entry: Dict, source_type: str, query: str) -> Dict:
    if source_type == "rule":
        source_id = entry.get("rule_id") or entry.get("source_id") or "unknown_rule"
    else:
        source_id = entry.get("source_id") or entry.get("chunk_id") or "unknown_data"
    return {
        "source_type": source_type,
        "source_id": source_id,
        "snippet": _focused_snippet(entry.get("text", "") or "", query=query),
    }


def _build_query_answer(query: str, evidence: Dict[str, List[Dict]]) -> str:
    rules = evidence.get("rules", [])
    data = evidence.get("game_data", [])
    if not rules and not data:
        return (
            "No encuentro evidencia suficiente en índices de reglas/datos para responder con confianza. "
            "Reformula la pregunta con unidad, escenario o regla específica."
        )

    parts: List[str] = [f"Consulta: {query.strip()}"]
    if data:
        d = data[0]
        parts.append(f"Dato canónico principal: {(d.get('text', '') or '').splitlines()[0]}")
    if rules:
        r = rules[0]
        rid = r.get("rule_id") or "rulebook"
        parts.append(f"Regla principal: {rid}")
    return " | ".join(parts)


def _prefer_data_for_unit_queries(query: str, evidence: Dict[str, List[Dict]]) -> Dict[str, List[Dict]]:
    """
    Unit catalog queries should be grounded on canonical game_data first.
    In hybrid mode, noisy rule chunks can dominate citations and confuse answers.
    """
    rules = list(evidence.get("rules", []) or [])
    data = list(evidence.get("game_data", []) or [])
    if not _looks_like_unit_catalog_query(query):
        return {"rules": rules, "game_data": data}
    if not data:
        return {"rules": rules, "game_data": data}
    # Keep responses focused: when we already have data evidence for unit stats,
    # avoid mixing in unrelated roadmap/rulebook chunks.
    return {"rules": [], "game_data": data}


def _llm_enabled() -> bool:
    return str(os.getenv("ASSAULT_RAG_LLM_ENABLED", "1")).strip().lower() in {"1", "true", "yes", "on"}


def _situation_llm_enabled() -> bool:
    # Keep LLM enabled by default for richer tactical narration.
    return str(os.getenv("ASSAULT_RAG_SITUATION_LLM_ENABLED", "1")).strip().lower() in {"1", "true", "yes", "on"}


def _ollama_chat(model: str, prompt: str, timeout_s: float | None = None) -> str:
    if timeout_s is None:
        timeout_s = float(os.getenv("ASSAULT_OLLAMA_TIMEOUT_S", "4.0"))
    base = str(os.getenv("ASSAULT_OLLAMA_BASE_URL", "http://127.0.0.1:11434")).rstrip("/")
    url = f"{base}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": float(os.getenv("ASSAULT_RAG_LLM_TEMPERATURE", "0.2")),
        },
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read().decode("utf-8")
    data = json.loads(raw)
    return str(data.get("response", "")).strip()


def _resolve_model(context: Dict | None = None) -> str:
    ctx = context or {}
    model_from_ctx = str(ctx.get("llm_model", "")).strip()
    if model_from_ctx:
        return model_from_ctx
    return str(os.getenv("ASSAULT_OLLAMA_MODEL", "qwen2.5:14b")).strip() or "qwen2.5:14b"


def _answer_with_llm(query: str, evidence: Dict[str, List[Dict]], context: Dict | None = None) -> str:
    model = _resolve_model(context)
    rules = evidence.get("rules", [])[:4]
    game_data = evidence.get("game_data", [])[:4]

    ev_lines: List[str] = []
    for idx, item in enumerate(rules, start=1):
        rid = item.get("rule_id") or item.get("source_id") or f"rule_{idx}"
        txt = (item.get("text", "") or "").strip().replace("\n", " ")
        ev_lines.append(f"[RULE {rid}] {txt[:600]}")
    for idx, item in enumerate(game_data, start=1):
        sid = item.get("source_id") or item.get("chunk_id") or f"data_{idx}"
        txt = (item.get("text", "") or "").strip().replace("\n", " ")
        ev_lines.append(f"[DATA {sid}] {txt[:600]}")

    prompt = (
        "Eres un copiloto de reglas de un wargame táctico.\n"
        "Responde en español, corto y preciso.\n"
        "Usa SOLO la evidencia dada. Si no alcanza, di que falta evidencia.\n"
        "Incluye al final una línea 'Base:' con ids de evidencia usados.\n\n"
        f"Pregunta: {query.strip()}\n\n"
        "Evidencia:\n"
        + ("\n".join(ev_lines) if ev_lines else "SIN EVIDENCIA")
    )
    return _ollama_chat(model=model, prompt=prompt)


def _extract_json_object(raw_text: str) -> Dict | None:
    text = str(raw_text or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _llm_refine_situation(
    *,
    state_snapshot: Dict,
    evidence: Dict,
    priorities: List[str],
    risks: List[str],
    opportunities: List[str],
    key_unit_alerts: List[str],
) -> Dict | None:
    if not _llm_enabled():
        return None
    model = _resolve_model({})
    turn = state_snapshot.get("turn", "N/A")
    active_side = str(state_snapshot.get("active_side", "UNKNOWN")).upper()
    vp_live = state_snapshot.get("vp_score_live", {}) or {}
    own_vp = float(vp_live.get(active_side, 0) or 0)
    enemy_best = max(
        (float(v or 0) for s, v in vp_live.items() if str(s).upper() != active_side),
        default=0.0,
    )
    vp_gap = enemy_best - own_vp
    evidence_lines = []
    for c in (evidence.get("citations", []) or [])[:6]:
        source_id = str(c.get("source_id", "") or "unknown")
        snippet = str(c.get("snippet", "") or "").strip().replace("\n", " ")
        evidence_lines.append(f"- [{source_id}] {snippet[:220]}")
    prompt = (
        "Eres analista táctico. Devuelve SOLO JSON válido.\n"
        "No inventes datos fuera del contexto.\n"
        "Si hay desventaja fuerte de VP, NO uses tono optimista genérico.\n\n"
        "Schema exacto:\n"
        '{"situation_summary":"...",'
        '"priorities":["..."],'
        '"risks":["..."],'
        '"opportunities":["..."],'
        '"key_unit_alerts":["..."]}\n\n'
        f"Contexto:\nturn={turn}\nactive_side={active_side}\n"
        f"vp_live={vp_live}\nown_vp={own_vp}\nenemy_best_vp={enemy_best}\nvp_gap={vp_gap}\n"
        f"heuristic_priorities={priorities[:3]}\n"
        f"heuristic_risks={risks[:3]}\n"
        f"heuristic_opportunities={opportunities[:3]}\n"
        f"heuristic_key_unit_alerts={key_unit_alerts[:3]}\n\n"
        "Evidencia:\n"
        + ("\n".join(evidence_lines) if evidence_lines else "- (sin evidencia)")
    )
    try:
        raw = _ollama_chat(model=model, prompt=prompt, timeout_s=12.0)
    except Exception:
        return None
    payload = _extract_json_object(raw)
    if not payload:
        return None
    out: Dict[str, List[str] | str] = {}
    out["situation_summary"] = str(payload.get("situation_summary", "") or "").strip()
    for k in ("priorities", "risks", "opportunities", "key_unit_alerts"):
        val = payload.get(k, [])
        if isinstance(val, list):
            out[k] = [str(x).strip() for x in val if str(x).strip()][:3]
        else:
            out[k] = []
    return out


def rag_query(query: str, requested_mode: str | None = None, context: Dict | None = None) -> Dict:
    manual_scope = _is_manual_scope(context)
    effective_query = _memory_rewrite_query(query, context)
    if not manual_scope:
        effective_query = _augment_query_with_state_context(effective_query, context)
    mode = classify_query_mode(effective_query, requested_mode)
    if mode == "rules" and _looks_like_counter_query(effective_query):
        # Counter/icon questions usually need both manual semantics and
        # unit/catalog anchors (labels, categories, symbols).
        mode = "hybrid"
    # UX guardrail: unit-definition questions in "rules" mode are often backed
    # by game-data catalog, but combat-resolution questions need rules + data.
    if (
        mode == "rules"
        and _looks_like_unit_catalog_query(effective_query)
        and not _looks_like_combat_resolution_query(effective_query)
    ):
        mode = "data"
    elif mode == "rules" and _looks_like_combat_resolution_query(effective_query):
        mode = "hybrid"
    evidence = _prefer_data_for_unit_queries(
        query=effective_query,
        evidence=retrieve_evidence(effective_query, mode=mode),
    )
    # UX fallback: users can leave "Datos" selected while asking rule/combat questions.
    # If data retrieval is empty, retry with hybrid before declaring NO_EVIDENCE.
    if (
        mode == "data"
        and len(evidence.get("game_data", [])) == 0
        and len(evidence.get("rules", [])) == 0
    ):
        fallback_evidence = _prefer_data_for_unit_queries(
            query=effective_query,
            evidence=retrieve_evidence(effective_query, mode="hybrid"),
        )
        if len(fallback_evidence.get("game_data", [])) > 0 or len(fallback_evidence.get("rules", [])) > 0:
            evidence = fallback_evidence
            mode = "hybrid"
    citations: List[Dict] = []
    citations.extend(_build_citation(r, "rule", query=effective_query) for r in evidence.get("rules", []))
    citations.extend(_build_citation(d, "data", query=effective_query) for d in evidence.get("game_data", []))
    limitations: List[str] = []
    if not citations:
        limitations.append("NO_EVIDENCE")
    if _looks_like_unit_catalog_query(effective_query) and len(evidence.get("game_data", [])) == 0:
        limitations.append("NO_GAME_DATA_EVIDENCE_FOR_UNIT_QUERY")
    if requested_mode == "data" and mode == "hybrid":
        limitations.append("AUTO_FALLBACK_DATA_TO_HYBRID")
    answer = _build_query_answer(effective_query, evidence)
    if _llm_enabled():
        try:
            llm_answer = _answer_with_llm(effective_query, evidence, context=context)
            if llm_answer:
                answer = llm_answer
            else:
                limitations.append("LLM_EMPTY_RESPONSE_FALLBACK")
        except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
            limitations.append("LLM_UNAVAILABLE_FALLBACK")
        except Exception:
            limitations.append("LLM_ERROR_FALLBACK")
    # For operational match questions, prefer live state/observability over
    # generic catalog/scenario citations that can mislead the answer.
    if (not manual_scope) and _query_targets_live_state_ops(query):
        obs_answer = _fallback_answer_from_state(query, context)
        if obs_answer:
            answer = obs_answer
            if "STATE_CONTEXT_FALLBACK" not in limitations:
                limitations.append("STATE_CONTEXT_FALLBACK")
    if (not manual_scope) and not citations:
        fallback = _fallback_answer_from_state(query, context)
        if fallback:
            answer = fallback
            limitations.append("STATE_CONTEXT_FALLBACK")
    _memory_store_turn(
        context=context,
        query=query,
        mode=mode,
        answer=answer,
        citations=citations,
    )
    return {
        "mode": mode,
        "answer": answer,
        "citations": citations[:8],
        "evidence": {
            "rules_count": len(evidence.get("rules", [])),
            "data_count": len(evidence.get("game_data", [])),
        },
        "limitations": limitations,
        "llm_model": _resolve_model(context),
    }


def explain_action_short(action: Dict, state_snapshot: Dict, trace_context: List[Dict] | None = None) -> Dict:
    action_name = str(action.get("action", "UNKNOWN_ACTION"))
    unit_id = str(action.get("unit_id", "UNKNOWN_UNIT"))
    query = f"Explain action {action_name} by unit {unit_id} with rules and tactical context"
    base = rag_query(query, requested_mode="hybrid")
    short = (
        f"{unit_id} ejecuta {action_name} porque encaja con el contexto táctico actual "
        f"(objetivo, amenaza y legalidad de acción)."
    )
    if trace_context:
        short += f" Se revisaron {len(trace_context)} eventos recientes de traza."
    if state_snapshot.get("nearest_vp_distance") is not None:
        short += f" Distancia a VP relevante: {state_snapshot.get('nearest_vp_distance')}."
    return {
        "short_explanation": short,
        "citations": base["citations"],
        "limitations": base["limitations"],
    }


def recommend_actions_advisory(state_snapshot: Dict, side: str, constraints: Dict | None = None) -> Dict:
    legal_actions: List[Dict] = list(state_snapshot.get("legal_actions", []) or [])
    if not legal_actions:
        return {
            "recommendations": [],
            "limitations": ["NO_LEGAL_ACTIONS_IN_SNAPSHOT"],
        }

    def _score(a: Dict) -> int:
        action_name = str(a.get("action", "")).upper()
        tags = {str(t).lower() for t in (a.get("tags", []) or [])}
        score = 0
        if "objective_progress" in tags or "capture" in tags:
            score += 5
        if "attack" in action_name or "fire" in action_name:
            score += 3
        if "retreat" in action_name:
            score -= 2
        return score

    ranked = sorted(legal_actions, key=_score, reverse=True)[:3]
    recommendations: List[Dict] = []
    for action in ranked:
        action_name = str(action.get("action", "UNKNOWN"))
        reason = "prioriza progreso objetivo y presión táctica controlada"
        risk = "riesgo medio de exposición si no hay cobertura"
        ev = rag_query(f"Recommend {action_name} for side {side}", requested_mode="hybrid")
        recommendations.append(
            {
                "action": action,
                "rationale_short": reason,
                "risk_note": risk,
                "citations": ev["citations"][:4],
            }
        )
    return {"recommendations": recommendations, "limitations": []}


def analyze_training_level1(runs: List[Dict]) -> Dict:
    total_steps = 0
    wait_steps = 0
    capture_events = 0
    damage_events = 0
    examples: List[Dict] = []

    for run in runs:
        events = run.get("events", []) or []
        for ev in events:
            total_steps += 1
            action_name = str(ev.get("action", "")).lower()
            if "wait" in action_name:
                wait_steps += 1
            if ev.get("capture_event", False):
                capture_events += 1
            if float(ev.get("damage", 0) or 0) > 0:
                damage_events += 1
        if events:
            examples.append(events[min(2, len(events) - 1)])

    wait_ratio = (wait_steps / total_steps) if total_steps else 0.0
    capture_ratio = (capture_events / total_steps) if total_steps else 0.0
    damage_ratio = (damage_events / total_steps) if total_steps else 0.0

    patterns = []
    if wait_ratio > 0.25:
        patterns.append("high_wait_ratio")
    if capture_ratio < 0.05:
        patterns.append("low_capture_pressure")
    if damage_ratio < 0.10:
        patterns.append("low_damage_output")

    recommendations = []
    if "high_wait_ratio" in patterns:
        recommendations.append("Revisar penalización de WAIT y presupuesto de fallback táctico.")
    if "low_capture_pressure" in patterns:
        recommendations.append("Aumentar shaping de progreso/entrada en VP en ventanas CAPTURE.")
    if "low_damage_output" in patterns:
        recommendations.append("Incrementar preferencia por líneas de fuego con follow-up legal.")

    ev = rag_query(
        "training analysis wait ratio capture pressure damage output recommendations",
        requested_mode="hybrid",
    )
    return {
        "patterns": patterns,
        "metrics": {
            "total_steps": total_steps,
            "wait_ratio": wait_ratio,
            "capture_ratio": capture_ratio,
            "damage_ratio": damage_ratio,
        },
        "examples": examples[:5],
        "recommendations": recommendations,
        "citations": ev["citations"][:6],
        "limitations": ev["limitations"],
    }


def explain_game_situation(state_snapshot: Dict) -> Dict:
    """
    Computes a comprehensive tactical situation report (SitRep) leveraging the full
    Assault XAI intelligence stack:
    1. Topography & Battlefield IPB (terrain breakdown, chokepoints, defilade corridors).
    2. Order of Battle (OOB) & 5D Tactical Roles (assault squads, HMG suppression, indirect mortars, snipers).
    3. Unit Traits Parity (smoke, camouflaged, low silhouette, heavy weight, anti-tank).
    4. Neural Brain Telemetry (EfficientZero V2 MCTS root value, win probability, time urgency).
    """
    from collections import Counter

    units = list(state_snapshot.get("units", []) or [])
    hexes = list(state_snapshot.get("hexes", []) or [])
    turn = state_snapshot.get("turn", 1)
    active_side = str(state_snapshot.get("active_side", "UNKNOWN")).upper()
    scenario_raw = str(state_snapshot.get("scenario_name", "Scenario"))
    scenario_name = scenario_raw.replace("_", " ").title()
    telemetry = state_snapshot.get("telemetry", {}) or {}
    ai_obs = state_snapshot.get("ai_observability", {}) or {}
    vp_live = state_snapshot.get("vp_score_live", {}) or {}

    # -------------------------------------------------------------
    # 1. TOPOGRAPHY & BATTLEFIELD IPB
    # -------------------------------------------------------------
    total_hexes = len(hexes) or 1
    terrain_counts = Counter(str(h.get("terrain", "clear")).lower() for h in hexes)
    building_count = sum(v for k, v in terrain_counts.items() if "building" in k or "urban" in k)
    woods_count = sum(v for k, v in terrain_counts.items() if any(w in k for w in ("woods", "forest", "grove", "brush")))
    clear_count = terrain_counts.get("clear", 0)

    urban_pct = round(building_count / total_hexes * 100, 1)
    forest_pct = round(woods_count / total_hexes * 100, 1)
    open_pct = round(clear_count / total_hexes * 100, 1)

    try:
        topo_profile = analyze_battlefield_topography(hex_data=hexes, scenario_id=scenario_raw)
        topo_counts = topo_profile.to_dict().get("counts", {})
        defilade_count = topo_counts.get("defilade_corridors", 0)
    except Exception:
        defilade_count = 0

    if urban_pct >= 25.0:
        dominant_terrain = f"Dense urban environment ({urban_pct}% structures, {defilade_count} covered defilade corridors). Favors room-to-room clearing and defensive ambushes."
    elif forest_pct >= 25.0:
        dominant_terrain = f"Wooded terrain ({forest_pct}% forests/groves). High concealment hindering long-range direct fire."
    else:
        dominant_terrain = f"Open combat zone ({open_pct}% clear ground). Broad line-of-sight favoring long-range direct overwatch."

    terrain_intel = {
        "scenario_name": scenario_name,
        "urban_pct": urban_pct,
        "forest_pct": forest_pct,
        "open_pct": open_pct,
        "defilade_corridors_count": defilade_count,
        "dominant_terrain_desc": dominant_terrain,
    }

    # -------------------------------------------------------------
    # 2. FORCES ORDER OF BATTLE (OOB) & ROLES
    # -------------------------------------------------------------
    enemy_side = "US" if active_side == "IT" else "IT"
    for u in units:
        s = str(u.get("side", "")).upper()
        if s and s != active_side:
            enemy_side = s
            break

    own_units = [u for u in units if str(u.get("side", "")).upper() == active_side]
    enemy_units = [u for u in units if str(u.get("side", "")).upper() != active_side]

    role_labels = {
        "assault_squad": "Assault & Breach",
        "suppression_mg": "HMG Suppression",
        "indirect_mortar": "Indirect Mortars",
        "infantry": "Rifle Infantry",
        "sniper": "Snipers",
        "combat_engineers": "Combat Engineers",
        "at_gun": "Anti-Tank Guns",
    }

    own_roles = Counter(role_labels.get(u.get("tactical_role", "infantry"), u.get("tactical_role", "infantry").replace("_", " ").title()) for u in own_units if (u.get("hp") or 1) > 0)
    enemy_roles = Counter(role_labels.get(u.get("tactical_role", "infantry"), u.get("tactical_role", "infantry").replace("_", " ").title()) for u in enemy_units if (u.get("hp") or 1) > 0)

    own_suppressed = sum(1 for u in own_units if u.get("is_suppressed") or u.get("status") == "suppressed")
    enemy_suppressed = sum(1 for u in enemy_units if u.get("is_suppressed") or u.get("status") == "suppressed")
    own_crit = sum(1 for u in own_units if (u.get("hp") is not None and u.get("hp") <= 1) or (u.get("health_pct") is not None and u.get("health_pct") <= 0.35))
    enemy_crit = sum(1 for u in enemy_units if (u.get("hp") is not None and u.get("hp") <= 1) or (u.get("health_pct") is not None and u.get("health_pct") <= 0.35))

    forces_oob = {
        "own_side": active_side,
        "enemy_side": enemy_side,
        "own_total": len(own_units),
        "enemy_total": len(enemy_units),
        "own_roles": dict(own_roles),
        "enemy_roles": dict(enemy_roles),
        "own_suppressed": own_suppressed,
        "enemy_suppressed": enemy_suppressed,
        "own_critical_hp": own_crit,
        "enemy_critical_hp": enemy_crit,
    }

    # -------------------------------------------------------------
    # 3. NEURAL MCTS TELEMETRY & STRATEGIC OUTLOOK
    # -------------------------------------------------------------
    root_val = float(telemetry.get("root_value", 0.0) or 0.0)
    win_prob = float(telemetry.get("win_prob", 0.5) or 0.5)
    total_decisions = int(ai_obs.get("total_decisions", 0) or 0)
    corrected_count = int(ai_obs.get("corrected_count", 0) or 0)

    if root_val >= 0.20 or win_prob >= 0.60:
        outlook = "Tactical Initiative Held (Offensive Advantage)"
    elif root_val <= -0.20 or win_prob <= 0.40:
        outlook = "High Defensive Pressure (Tactical Deficit)"
    else:
        outlook = "Contested Positional Equilibrium"

    neural_assessment = {
        "active_brain": "EfficientZero V2 (MCTS PUCT 253x)",
        "win_probability": round(win_prob * 100, 1),
        "root_value": round(root_val, 3),
        "total_decisions": total_decisions,
        "corrections": corrected_count,
        "strategic_outlook": outlook,
    }

    # -------------------------------------------------------------
    # 4. TACTICAL VECTORS (PRIORITIES, RISKS, OPPORTUNITIES, ALERTS)
    # -------------------------------------------------------------
    priorities: List[str] = []
    risks: List[str] = []
    opportunities: List[str] = []
    key_alerts: List[str] = []

    # Priorities based on force composition & objectives
    if own_roles.get("HMG Suppression", 0) > 0:
        priorities.append(f"Anchor defensive sectors with {own_roles['HMG Suppression']}x HMG elements to interdict open approach corridors.")
    if own_roles.get("Indirect Mortars", 0) > 0:
        priorities.append(f"Deploy {own_roles['Indirect Mortars']}x Indirect Mortar battery from covered defilade against hostile infantry concentrations.")
    if own_roles.get("Assault & Breach", 0) > 0:
        priorities.append(f"Advance assault echelons through covered defilade corridors ({defilade_count} hexes) toward target objectives.")

    # Objective VP priorities
    own_vp = float(vp_live.get(active_side, 0) or 0)
    enemy_best_vp = max((float(v or 0) for s, v in vp_live.items() if str(s).upper() != active_side), default=0.0)
    vp_gap = enemy_best_vp - own_vp

    if vp_gap >= 2.0:
        priorities.insert(0, f"Critical VP Deficit ({own_vp:.0f} vs {enemy_best_vp:.0f}): Force immediate breakthrough to contest closest objective hex.")
    elif vp_gap > 0:
        priorities.insert(0, "Increase pressure on contested VP hexes before end of turn window closes.")
    else:
        priorities.append("Consolidate VP advantage; screen captured objectives against counter-assault.")

    # Risks
    if len(enemy_units) > len(own_units):
        ratio = round(len(enemy_units) / max(1, len(own_units)), 1)
        risks.append(f"Numerical disparity: {len(enemy_units)} hostile squads vs {len(own_units)} friendly defenders ({ratio}:1 force ratio).")
    if own_crit > 0:
        risks.append(f"{own_crit} friendly squad(s) operating at critical health (<=1 HP); fall back to fortified structures.")
    if own_suppressed > 0:
        risks.append(f"{own_suppressed} friendly squad(s) currently suppressed; rallying or cover support required.")
    if enemy_roles.get("Combat Engineers", 0) > 0 or enemy_roles.get("Assault & Breach", 0) >= 4:
        risks.append("Hostile vanguard comprises specialized breach squads with high close-combat lethality.")

    # Opportunities
    if urban_pct >= 20.0:
        opportunities.append(f"Dense urban cover ({urban_pct}% structures) neutralizes long-range enemy fires and forces close-quarters engagement.")
    if defilade_count > 20:
        opportunities.append(f"Network of {defilade_count} defilade corridors enables covered infiltration avoiding open killzones.")
    if enemy_crit > 0:
        opportunities.append(f"{enemy_crit} hostile squad(s) heavily attrited; focus concentrated fire to secure eliminations.")
    if enemy_suppressed > 0:
        opportunities.append(f"{enemy_suppressed} hostile squad(s) suppressed; advance into close combat with defensive fire disabled.")

    # Unit-level alerts
    for u in own_units:
        uid = u.get("id")
        uk = u.get("unit_key")
        traits = u.get("traits", [])
        q, r = u.get("q"), u.get("r")
        hp = u.get("hp", 4)
        if "INDIRECT_FIRE" in traits:
            key_alerts.append(f"{uid} ({uk}) at Q:{q}, R:{r} [Mortar]: High-value battery; screen with infantry.")
        elif "suppression_mg" == u.get("tactical_role"):
            key_alerts.append(f"{uid} ({uk}) at Q:{q}, R:{r} [HMG Support]: Overwatch element; maintain defensive cone.")
        elif hp <= 1:
            key_alerts.append(f"{uid} ({uk}) at Q:{q}, R:{r}: Critical condition (1 HP). Vulnerable to elimination.")
        elif "HEAVY_WEIGHT" in traits:
            key_alerts.append(f"{uid} ({uk}) at Q:{q}, R:{r} [Heavy Weight]: Cannot traverse hills without mechanized transport.")

    # Executive Summary
    situation_summary = (
        f"Turn {turn} // Commander: {active_side}. "
        f"Forces: {len(own_units)} friendly squads vs {len(enemy_units)} hostile forces. "
        f"Terrain: {dominant_terrain} "
        f"Tactical Outlook: {outlook} (MCTS Win Prob: {round(win_prob * 100, 1)}%, Root Value: {round(root_val, 2):+0.2f})."
    )

    # Fast non-blocking LLM refinement if enabled
    if _situation_llm_enabled():
        try:
            ev = rag_query(f"tactical rules {scenario_name}", requested_mode="rules")
            llm_refined = _llm_refine_situation(
                state_snapshot=state_snapshot,
                evidence=ev,
                priorities=priorities,
                risks=risks,
                opportunities=opportunities,
                key_unit_alerts=key_alerts,
            )
            if llm_refined and isinstance(llm_refined, dict):
                situation_summary = str(llm_refined.get("situation_summary") or situation_summary)
                if llm_refined.get("priorities"):
                    priorities = list(llm_refined["priorities"])
                if llm_refined.get("risks"):
                    risks = list(llm_refined["risks"])
                if llm_refined.get("opportunities"):
                    opportunities = list(llm_refined["opportunities"])
                if llm_refined.get("key_unit_alerts"):
                    key_alerts = list(llm_refined["key_unit_alerts"])
        except Exception:
            pass  # Fall back directly to deterministic XAI SitRep

    citations = []
    try:
        ev = retrieve_evidence(f"tactical rules {scenario_name}", mode="rules")
        for item in (ev.get("rules", []) + ev.get("game_data", []))[:4]:
            citations.append({
                "source_type": item.get("source_type") or ("rule" if "rule_id" in item else "data"),
                "source_id": str(item.get("source_id") or item.get("rule_id", "rules")),
                "snippet": str(item.get("snippet") or item.get("text", ""))[:250],
            })
    except Exception:
        pass

    return {
        "situation_summary": situation_summary,
        "terrain_intel": terrain_intel,
        "forces_oob": forces_oob,
        "neural_assessment": neural_assessment,
        "priorities": priorities[:4],
        "risks": risks[:4],
        "opportunities": opportunities[:4],
        "key_unit_alerts": key_alerts[:4],
        "citations": citations,
        "limitations": [],
    }

def retrieve_doctrinal_citations_for_sitrep(
    turning_points: list[dict],
    max_citations: int = 4,
) -> list[dict]:
    """
    Retrieve grounded rulebook and doctrinal citations from assault_rag
    corresponding to decisive tactical match events (turning points).
    """
    if not turning_points:
        return []

    event_query_map = {
        "VP_CAPTURE": ("victory point control capture holding objective", "Governs objective control updates and VP hex mechanics"),
        "VP_LOSS": ("victory point control territory capture", "Pertains to loss of objective control and territory defense"),
        "MORALE_FAILURE": ("morale suppression recovery rally status marker", "Defines suppression effects, combat penalties, and broken status"),
        "KEY_RALLY": ("rally recovery morale order status check", "Specifies recovery check requirements and rally actions"),
        "SURPRISE_DAMAGE": ("line of sight cover defense modifier ambush", "Covers defensive terrain modifiers and concealment"),
        "HEAVY_ATTRITION": ("fire combat attack dice defense casualty", "Governs ranged combat resolution and casualty infliction"),
        "DECISIVE_ASSAULT": ("close combat assault defender advantage dice modifier", "Pertains to close assault resolution and defender bonuses"),
        "BREAKTHROUGH_MANEUVER": ("movement terrain move cost obstacle", "Governs movement costs, terrain transit, and offensive pushes"),
    }

    seen_ids = set()
    citations = []

    for tp in turning_points:
        if len(citations) >= max_citations:
            break
        etype = str(tp.get("event_type", "HEAVY_ATTRITION")).upper()
        query_text, default_reason = event_query_map.get(
            etype,
            ("fire combat combat resolution rules", "Standard tactical combat resolution rules"),
        )
        try:
            ev = retrieve_evidence(query=query_text, mode="hybrid", max_rules=2, max_data=1)
            for rule in ev.get("rules", []):
                rid = str(rule.get("rule_id", ""))
                if not rid or rid in seen_ids:
                    continue
                seen_ids.add(rid)
                
                raw_text = str(rule.get("text", "")).strip()
                # Clean up YAML frontmatter if present
                clean_lines = []
                for line in raw_text.splitlines():
                    if line.strip().startswith("topic:"):
                        topic_val = line.split(":", 1)[1].strip().strip('"').strip("'")
                    elif not line.strip().startswith("```") and not line.strip().startswith("---"):
                        clean_lines.append(line)
                excerpt = "\n".join(clean_lines[:6]).strip()
                if len(excerpt) > 280:
                    excerpt = excerpt[:277] + "..."

                citations.append({
                    "rule_id": rid,
                    "event_type": etype,
                    "topic": str(rule.get("topic", rule.get("rule_id", "Tactical Rule"))),
                    "text_snippet": excerpt or raw_text[:280],
                    "source": str(rule.get("source_id", rule.get("source", "Assault Rulebook"))),
                    "relevance_reason": default_reason,
                })
                if len(citations) >= max_citations:
                    break
        except Exception:
            continue

    return citations

