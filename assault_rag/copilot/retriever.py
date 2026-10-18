import json
import math
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


class BM25Index:
    """
    High-performance Okapi BM25 Index with Inverted Postings and Field Boosting.
    Based on modern IR/RAG literature (Robertson et al., Trotman et al. 2014).
    """
    def __init__(self, chunks: List[Dict], k1: float = 1.2, b: float = 0.75):
        self.chunks = chunks
        self.N = len(chunks)
        self.k1 = k1
        self.b = b
        self.doc_lengths: List[int] = []
        # Inverted index: token -> list of (doc_idx, tf, is_meta)
        self.inverted_index: Dict[str, List[Tuple[int, int, bool]]] = {}

        for idx, chunk in enumerate(chunks):
            text_tokens = list(_tokenize(str(chunk.get("text", "") or "")))
            meta_str = " ".join([
                str(chunk.get("chunk_id", "") or ""),
                str(chunk.get("source_id", "") or ""),
                str(chunk.get("rule_id", "") or ""),
                str(chunk.get("title", "") or ""),
                json.dumps(chunk.get("metadata", {}) or {}),
            ])
            meta_tokens = set(_tokenize(meta_str))
            doc_len = len(text_tokens) + len(meta_tokens)
            self.doc_lengths.append(max(1, doc_len))

            tf_map: Dict[str, int] = {}
            for t in text_tokens:
                tf_map[t] = tf_map.get(t, 0) + 1
            for t in meta_tokens:
                tf_map[t] = tf_map.get(t, 0) + 2

            for t, tf in tf_map.items():
                is_meta = t in meta_tokens
                if t not in self.inverted_index:
                    self.inverted_index[t] = []
                self.inverted_index[t].append((idx, tf, is_meta))

        self.avgdl = sum(self.doc_lengths) / max(1, self.N)
        self.idf: Dict[str, float] = {}
        for t, postings in self.inverted_index.items():
            df = len(postings)
            self.idf[t] = math.log(1.0 + (self.N - df + 0.5) / (df + 0.5))

    def search(self, query_tokens: Set[str], top_k: int = 5) -> List[Tuple[float, Dict]]:
        scores: Dict[int, float] = {}
        for t in query_tokens:
            if t not in self.inverted_index:
                continue
            idf_t = self.idf[t]
            for doc_idx, tf, is_meta in self.inverted_index[t]:
                boost = 2.5 if is_meta else 1.0
                dl = self.doc_lengths[doc_idx]
                denom = tf * boost + self.k1 * (1.0 - self.b + self.b * (dl / self.avgdl))
                num = (tf * boost) * (self.k1 + 1.0)
                term_score = idf_t * (num / denom)
                scores[doc_idx] = scores.get(doc_idx, 0.0) + term_score

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [(score, self.chunks[idx]) for idx, score in ranked[:top_k]]


@lru_cache(maxsize=1)
def _get_rule_bm25() -> BM25Index:
    chunks = load_rule_chunks()
    return BM25Index(chunks)


@lru_cache(maxsize=1)
def _get_data_bm25() -> BM25Index:
    all_data_chunks = ensure_game_data_chunks()
    seen_chunk_ids: Set[str] = set()
    deduped: List[Dict] = []
    for chunk in all_data_chunks:
        chunk_id = str(chunk.get("chunk_id", ""))
        if chunk_id and chunk_id in seen_chunk_ids:
            continue
        if chunk_id:
            seen_chunk_ids.add(chunk_id)
        deduped.append(chunk)
    return BM25Index(deduped)


def invalidate_retriever_caches() -> None:
    _tokenize_cached.cache_clear()
    _expanded_query_tokens_for_query.cache_clear()
    _get_rule_bm25.cache_clear()
    _get_data_bm25.cache_clear()


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

    rules_results: List[Dict] = []
    data_results: List[Dict] = []

    if mode in {"rules", "hybrid"}:
        rule_bm25 = _get_rule_bm25()
        rules_ranked = rule_bm25.search(query_tokens, top_k=max_rules)
        rules_results = [chunk for _, chunk in rules_ranked]

    if mode in {"data", "hybrid"}:
        data_bm25 = _get_data_bm25()
        data_ranked = data_bm25.search(query_tokens, top_k=max_data)
        data_results = [chunk for _, chunk in data_ranked]

    return {
        "rules": rules_results,
        "game_data": data_results,
    }
