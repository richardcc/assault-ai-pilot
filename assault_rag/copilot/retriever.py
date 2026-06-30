import re
from functools import lru_cache
from typing import Dict, List, Set, Tuple

from assault_rag.copilot.index_builder import ensure_game_data_chunks, load_rule_chunks


STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "what",
    "que",
    "con",
    "por",
    "para",
    "del",
    "las",
    "los",
    "una",
    "uno",
    "sobre",
    "actual",
    "juego",
}

TYPO_NORMALIZATION = {
    "riffles": "rifles",
    "riflees": "rifles",
    "rifels": "rifles",
    "uniddaes": "unidades",
    "unidadeses": "unidades",
    "catalogo": "catalogo",
    "puedaes": "puedes",
    "grafico": "gráfico",
    "graficos": "gráficos",
}

QUERY_EXPANSIONS = {
    "bunker": {"fortification", "fortifications", "casemate", "pillbox", "gun", "position", "crossing", "movement", "occupancy"},
    "pillbox": {"bunker", "casemate", "fortification", "crossing", "movement", "occupancy"},
    "fortification": {"bunker", "pillbox", "trench", "sandbag", "gun", "position", "crossing", "movement", "occupancy"},
    "fortifications": {"fortification", "bunker", "pillbox", "trench", "sandbag", "crossing", "movement", "occupancy"},
    "unidad": {"unit", "units", "category", "classification", "subtype", "catalog", "side"},
    "unidades": {"unit", "units", "category", "classification", "subtype", "catalog", "side"},
    "tipo": {"category", "classification", "subtype", "unit", "units"},
    "tipos": {"category", "classification", "subtype", "unit", "units"},
    "catalogo": {"catalog", "unit", "units", "stats", "classification"},
    "catálogo": {"catalog", "unit", "units", "stats", "classification"},
    "disponibles": {"unit", "units", "catalog", "side", "classification"},
    "rifles": {"rifle", "unit", "units", "infantry", "standard_infantry"},
    "rifle": {"rifles", "unit", "units", "infantry", "standard_infantry"},
    "infanteria": {"infantry", "unidad", "unidades", "attack", "defense", "dados"},
    "infantry": {"infanteria", "unit", "units", "attack", "defense", "dice"},
    "dado": {"dados", "die", "dice", "ataque", "defensa"},
    "dados": {"dado", "die", "dice", "ataque", "defensa"},
    "distancia": {"alcance", "range", "hex", "hexes"},
    "alcance": {"distancia", "range", "hex", "hexes"},
    "range": {"distancia", "alcance", "hex", "hexes"},
    "counter": {"counters", "ficha", "fichas", "icono", "símbolo", "unidad", "unit"},
    "counters": {"counter", "ficha", "fichas", "icono", "símbolo", "unidad", "unit"},
    "ficha": {"fichas", "counter", "icono", "símbolo", "unidad", "unit"},
    "fichas": {"ficha", "counter", "icono", "símbolo", "unidad", "unit"},
    "icono": {"iconos", "símbolo", "counter", "ficha", "unidad", "unit"},
    "iconos": {"icono", "símbolo", "counter", "ficha", "unidad", "unit"},
    "grafico": {"gráfico", "icono", "símbolo", "counter", "ficha"},
    "gráfico": {"grafico", "icono", "símbolo", "counter", "ficha"},
}

FUZZY_CANONICAL_TERMS = {
    "rifles",
    "rifle",
    "sniper",
    "mortar",
    "bazooka",
    "infantry",
    "artillery",
    "vehicle",
    "unit",
    "units",
    "catalog",
    "classification",
    "subtype",
    "fortification",
    "fortifications",
    "bunker",
    "pillbox",
    "trench",
    "sandbag",
    "movement",
    "crossing",
    "occupancy",
    "dado",
    "dados",
    "dice",
    "die",
    "distancia",
    "alcance",
    "range",
    "infanteria",
    "infantry",
    "counter",
    "counters",
    "ficha",
    "fichas",
    "icono",
    "iconos",
    "grafico",
    "gráfico",
}


def _levenshtein_distance_limited(a: str, b: str, limit: int = 2) -> int:
    """
    Levenshtein with early exit for small limits (query typo tolerance).
    """
    if a == b:
        return 0
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        row_min = cur[0]
        for j, cb in enumerate(b, start=1):
            ins = cur[j - 1] + 1
            dele = prev[j] + 1
            sub = prev[j - 1] + (0 if ca == cb else 1)
            val = min(ins, dele, sub)
            cur.append(val)
            if val < row_min:
                row_min = val
        if row_min > limit:
            return limit + 1
        prev = cur
    return prev[-1]


def _fuzzy_expand_query_tokens(query_tokens: Set[str]) -> Set[str]:
    expanded = set(query_tokens)
    for token in list(query_tokens):
        if len(token) < 4:
            continue
        # Small typo tolerance: distance <=2 for medium/long tokens.
        for canon in FUZZY_CANONICAL_TERMS:
            if canon in expanded:
                continue
            dist = _levenshtein_distance_limited(token, canon, limit=2)
            if dist <= 2:
                expanded.add(canon)
    return expanded


def _tokenize(text: str) -> Set[str]:
    tokens: Set[str] = set()
    for raw in re.findall(r"[a-zA-Z0-9_]+", (text or "").lower()):
        if len(raw) <= 1:
            continue
        raw_parts = [raw]
        if "_" in raw:
            raw_parts.extend(p for p in raw.split("_") if p)
        for part in raw_parts:
            if len(part) <= 1:
                continue
            normalized = TYPO_NORMALIZATION.get(part, part)
            if normalized in STOPWORDS:
                continue
            # Numeric-only tokens are too noisy for hybrid retrieval ("43", "1", etc.).
            # Keep alphanumeric unit ids (e.g. "us_43") via regex tokenization above.
            if normalized.isdigit():
                continue
            tokens.add(normalized)
    return tokens


@lru_cache(maxsize=8192)
def _tokenize_cached(text: str) -> frozenset[str]:
    return frozenset(_tokenize(text))


def _expand_query_tokens(query_tokens: Set[str]) -> Set[str]:
    expanded = set(query_tokens)
    for token in list(query_tokens):
        expanded.update(QUERY_EXPANSIONS.get(token, set()))
    return _fuzzy_expand_query_tokens(expanded)


@lru_cache(maxsize=4096)
def _expanded_query_tokens_for_query(query: str) -> frozenset[str]:
    return frozenset(_expand_query_tokens(_tokenize(query)))


@lru_cache(maxsize=1)
def _rule_index() -> tuple[tuple[Dict, frozenset[str]], ...]:
    chunks = load_rule_chunks()
    return tuple((chunk, _tokenize_cached(str(chunk.get("text", "") or ""))) for chunk in chunks)


@lru_cache(maxsize=1)
def _data_index() -> tuple[tuple[Dict, frozenset[str]], ...]:
    # ensure_game_data_chunks already backfills fortification chunks when needed.
    all_data_chunks = ensure_game_data_chunks()
    seen_chunk_ids: Set[str] = set()
    indexed: List[tuple[Dict, frozenset[str]]] = []
    for chunk in all_data_chunks:
        chunk_id = str(chunk.get("chunk_id", ""))
        if chunk_id and chunk_id in seen_chunk_ids:
            continue
        if chunk_id:
            seen_chunk_ids.add(chunk_id)
        indexed.append((chunk, _tokenize_cached(str(chunk.get("text", "") or ""))))
    return tuple(indexed)


def invalidate_retriever_caches() -> None:
    _tokenize_cached.cache_clear()
    _expanded_query_tokens_for_query.cache_clear()
    _rule_index.cache_clear()
    _data_index.cache_clear()


def classify_query_mode(query: str, requested_mode: str | None = None) -> str:
    if requested_mode in {"rules", "data", "hybrid"}:
        return requested_mode
    q = (query or "").lower()
    data_hints = [
        "unit",
        "units",
        "escenario",
        "scenario",
        "catalog",
        "stats",
        "movement",
        "max_strength",
        "trait",
    ]
    rules_hints = [
        "regla",
        "rule",
        "modificador",
        "modifier",
        "los",
        "spotting",
        "critical",
        "close combat",
    ]
    has_data = any(h in q for h in data_hints)
    has_rules = any(h in q for h in rules_hints)
    if has_data and not has_rules:
        return "data"
    if has_rules and not has_data:
        return "rules"
    return "hybrid"


def retrieve_evidence(
    query: str,
    mode: str = "hybrid",
    max_rules: int = 5,
    max_data: int = 5,
) -> Dict[str, List[Dict]]:
    query_tokens = set(_expanded_query_tokens_for_query(str(query or "")))

    rules_ranked: List[Tuple[int, Dict]] = []
    data_ranked: List[Tuple[int, Dict]] = []

    if mode in {"rules", "hybrid"}:
        for chunk, chunk_tokens in _rule_index():
            score = len(chunk_tokens & query_tokens)
            if score > 0:
                rules_ranked.append((score, chunk))
        rules_ranked.sort(key=lambda x: x[0], reverse=True)

    if mode in {"data", "hybrid"}:
        for chunk, chunk_tokens in _data_index():
            score = len(chunk_tokens & query_tokens)
            if score > 0:
                data_ranked.append((score, chunk))
        data_ranked.sort(key=lambda x: x[0], reverse=True)

    return {
        "rules": [c for _, c in rules_ranked[:max_rules]],
        "game_data": [c for _, c in data_ranked[:max_data]],
    }
