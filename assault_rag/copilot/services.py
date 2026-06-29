import json
import os
import re
import urllib.error
import urllib.request
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
    return bool(terms & UNIT_QUERY_HINTS)


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


def _ollama_chat(model: str, prompt: str, timeout_s: float = 25.0) -> str:
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
    mode = classify_query_mode(query, requested_mode)
    evidence = _prefer_data_for_unit_queries(
        query=query,
        evidence=retrieve_evidence(query, mode=mode),
    )
    citations: List[Dict] = []
    citations.extend(_build_citation(r, "rule", query=query) for r in evidence.get("rules", []))
    citations.extend(_build_citation(d, "data", query=query) for d in evidence.get("game_data", []))
    limitations: List[str] = []
    if not citations:
        limitations.append("NO_EVIDENCE")
    if _looks_like_unit_catalog_query(query) and len(evidence.get("game_data", [])) == 0:
        limitations.append("NO_GAME_DATA_EVIDENCE_FOR_UNIT_QUERY")
    answer = _build_query_answer(query, evidence)
    if _llm_enabled():
        try:
            llm_answer = _answer_with_llm(query, evidence, context=context)
            if llm_answer:
                answer = llm_answer
            else:
                limitations.append("LLM_EMPTY_RESPONSE_FALLBACK")
        except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
            limitations.append("LLM_UNAVAILABLE_FALLBACK")
        except Exception:
            limitations.append("LLM_ERROR_FALLBACK")
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
    units = list(state_snapshot.get("units", []) or [])
    alive_by_side: Dict[str, int] = {}
    for unit in units:
        side = str(unit.get("side", "UNKNOWN")).upper()
        hp = unit.get("hp", None)
        alive = (hp is None) or (float(hp) > 0)
        if alive:
            alive_by_side[side] = alive_by_side.get(side, 0) + 1

    turn = state_snapshot.get("turn", "N/A")
    active_side = state_snapshot.get("active_side", "UNKNOWN")
    vp_live = state_snapshot.get("vp_score_live", {}) or {}
    vp_txt = ", ".join(f"{k}:{v}" for k, v in vp_live.items()) if vp_live else "no_vp_data"
    units_txt = ", ".join(f"{k}:{v}" for k, v in sorted(alive_by_side.items())) if alive_by_side else "no_units"

    query = (
        f"Explain current game situation turn={turn} active_side={active_side} "
        f"alive_units={units_txt} vp={vp_txt} and provide tactical priorities and risks"
    )
    ev = rag_query(query, requested_mode="hybrid")

    priorities: List[str] = []
    risks: List[str] = []
    opportunities: List[str] = []
    key_unit_alerts: List[str] = []

    active_side_norm = str(active_side).upper()
    own_units = [u for u in units if str(u.get("side", "")).upper() == active_side_norm]
    enemy_units = [u for u in units if str(u.get("side", "")).upper() != active_side_norm]
    vp_hexes_raw = list(state_snapshot.get("vps", []) or [])

    vp_hexes: List[tuple[int, int]] = []
    for vp in vp_hexes_raw:
        if isinstance(vp, dict):
            q = _to_int(vp.get("q"))
            r = _to_int(vp.get("r"))
            if q is not None and r is not None:
                vp_hexes.append((q, r))
        elif isinstance(vp, (list, tuple)) and len(vp) >= 2:
            q = _to_int(vp[0])
            r = _to_int(vp[1])
            if q is not None and r is not None:
                vp_hexes.append((q, r))

    own_with_coords = [(u, _unit_coords(u)) for u in own_units]
    enemy_with_coords = [(u, _unit_coords(u)) for u in enemy_units]
    own_with_coords = [(u, c) for (u, c) in own_with_coords if c is not None]
    enemy_with_coords = [(u, c) for (u, c) in enemy_with_coords if c is not None]

    # Overextension / critical HP heuristic.
    low_hp_own = []
    for unit in own_units:
        hp = unit.get("hp", None)
        if hp is None:
            continue
        try:
            if float(hp) <= 1:
                low_hp_own.append(unit)
        except Exception:
            continue
    if low_hp_own:
        risks.append("Riesgo de sobreextensión: hay unidades propias con HP crítico.")
        for unit in low_hp_own[:2]:
            key_unit_alerts.append(
                f"Unidad clave en riesgo: {unit.get('id', unit.get('unit_id', 'UNKNOWN'))} (HP={unit.get('hp')})."
            )

    # Map-driven tactical geometry (frontline pressure + VP races).
    if own_with_coords and enemy_with_coords:
        close_contacts = 0
        isolated_own = 0
        own_units_near_vp = 0
        enemy_units_near_vp = 0

        for own_u, (oq, or_) in own_with_coords:
            nearest_enemy = min(
                _hex_distance(oq, or_, eq, er)
                for _, (eq, er) in enemy_with_coords
            )
            if nearest_enemy <= 2:
                close_contacts += 1
            if nearest_enemy >= 5:
                isolated_own += 1

            if vp_hexes:
                nearest_vp = min(_hex_distance(oq, or_, vq, vr) for (vq, vr) in vp_hexes)
                if nearest_vp <= 2:
                    own_units_near_vp += 1

        for _, (eq, er) in enemy_with_coords:
            if vp_hexes:
                nearest_vp = min(_hex_distance(eq, er, vq, vr) for (vq, vr) in vp_hexes)
                if nearest_vp <= 2:
                    enemy_units_near_vp += 1

        if close_contacts >= max(1, len(own_with_coords) // 2):
            priorities.append("Línea de contacto corta: priorizar foco de fuego sobre el mismo eje de choque.")
        if isolated_own > 0:
            risks.append("Hay unidades propias aisladas por geometría del mapa (enemigo lejano/apoyo débil).")
        if own_units_near_vp > enemy_units_near_vp:
            opportunities.append("Ventaja posicional cerca de VP: ventana para consolidar control en objetivos.")
        elif enemy_units_near_vp > own_units_near_vp:
            risks.append("El enemigo tiene mejor despliegue alrededor de VP; riesgo de pérdida por posición.")

        for own_u, (oq, or_) in own_with_coords[:6]:
            nearest_enemy = min(
                _hex_distance(oq, or_, eq, er)
                for _, (eq, er) in enemy_with_coords
            )
            if nearest_enemy <= 1:
                key_unit_alerts.append(
                    f"{own_u.get('id', own_u.get('unit_id', 'UNKNOWN'))} en contacto inmediato (dist={nearest_enemy})."
                )

    elif units:
        # Map snapshot without usable coordinates.
        if "MAP_COORDS_MISSING" not in key_unit_alerts:
            key_unit_alerts.append("Faltan coordenadas q/r en snapshot; análisis geométrico parcial.")

    # VP pressure / capture-window heuristic.
    vp_gap_value = 0.0
    side_behind_on_vp = False
    if vp_live and active_side_norm in vp_live:
        own_vp = float(vp_live.get(active_side_norm, 0) or 0)
        enemy_best = max(
            (float(v or 0) for s, v in vp_live.items() if str(s).upper() != active_side_norm),
            default=0.0,
        )
        vp_gap_value = enemy_best - own_vp
        side_behind_on_vp = own_vp <= enemy_best
        if side_behind_on_vp:
            if vp_gap_value >= 3.0:
                risks.append(
                    "Desventaja crítica de VP: el rival controla claramente los objetivos; riesgo alto de derrota por puntos."
                )
                priorities.append(
                    "Recuperar al menos un VP de inmediato y evitar intercambios de bajo impacto."
                )
                opportunities.append(
                    "Única ventana útil: recapturar VP este turno para frenar la bola de nieve de puntos."
                )
            else:
                opportunities.append(
                    "Ventana de captura activa: conviene priorizar entrada/retención de VP este turno."
                )
                priorities.append("Forzar progresión a objetivo antes de intercambios de bajo impacto.")
        else:
            priorities.append("Conservar ventaja de VP evitando pérdidas de control en hexes expuestos.")

    # Relative pressure by alive units.
    own_alive = len(own_units)
    enemy_alive = len(enemy_units)
    if own_alive > 0 and enemy_alive > 0:
        ratio = enemy_alive / max(1, own_alive)
        if ratio >= 1.25:
            risks.append("Presión enemiga alta: evitar avances sin cobertura y mantener apoyo mutuo.")
        elif ratio <= 0.8:
            opportunities.append("Superioridad local detectada: oportunidad para maniobra agresiva de captura.")

    # Endgame urgency.
    max_turns = state_snapshot.get("max_turns", None)
    try:
        turn_num = int(turn)
        max_turns_num = int(max_turns) if max_turns is not None else None
    except Exception:
        turn_num = None
        max_turns_num = None
    if turn_num is not None and max_turns_num is not None and max_turns_num > 0:
        remaining = max_turns_num - turn_num
        if remaining <= 2:
            priorities.append("Fase final: priorizar acciones decisivas sobre reposicionamientos neutrales.")

    if active_side_norm in alive_by_side:
        priorities.append("Mantener iniciativa del lado activo y preservar acciones con mayor impacto en VP.")
    if vp_live:
        priorities.append("Priorizar control/recaptura de hexes de objetivo con mayor valor de VP.")
    if len(units) > 0:
        risks.append("Exposición de unidades aisladas sin cobertura o apoyo de fuego.")
    if state_snapshot.get("done"):
        risks.append("Partida finalizada: recomendaciones solo informativas.")

    situation_summary = (
        f"Turno {turn}, lado activo {active_side}. "
        f"Unidades vivas por bando: {units_txt}. "
        f"Marcador VP: {vp_txt}."
    )

    # LLM structured refinement: smarter wording with tactical consistency.
    llm_refined = _llm_refine_situation(
        state_snapshot=state_snapshot,
        evidence=ev,
        priorities=priorities,
        risks=risks,
        opportunities=opportunities,
        key_unit_alerts=key_unit_alerts,
    )
    if llm_refined:
        situation_summary = str(llm_refined.get("situation_summary") or situation_summary)
        priorities = list(llm_refined.get("priorities") or priorities)
        risks = list(llm_refined.get("risks") or risks)
        opportunities = list(llm_refined.get("opportunities") or opportunities)
        key_unit_alerts = list(llm_refined.get("key_unit_alerts") or key_unit_alerts)

    # Guardrail: avoid optimistic output under strong VP deficit.
    if side_behind_on_vp and vp_gap_value >= 3.0:
        if not any("desventaja" in r.lower() or "riesgo alto" in r.lower() for r in risks):
            risks.insert(
                0,
                "Desventaja crítica de VP: riesgo alto de derrota por puntos si no se recaptura un objetivo ya.",
            )
        if not any("recuperar" in p.lower() or "recaptur" in p.lower() for p in priorities):
            priorities.insert(0, "Recuperar al menos un VP este turno es prioridad absoluta.")
        opportunities = [
            o
            for o in opportunities
            if "ventana de captura activa" not in o.lower()
        ]
        opportunities.insert(0, "Única oportunidad realista: recapturar VP inmediato para cortar la ventaja rival.")

    return {
        "situation_summary": situation_summary,
        "priorities": priorities[:3],
        "risks": risks[:3],
        "opportunities": opportunities[:3],
        "key_unit_alerts": key_unit_alerts[:3],
        "citations": ev["citations"][:6],
        "limitations": ev["limitations"],
    }
