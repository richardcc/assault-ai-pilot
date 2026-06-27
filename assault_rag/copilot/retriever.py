import re
from typing import Dict, List, Set, Tuple

from assault_rag.copilot.index_builder import ensure_game_data_chunks, load_rule_chunks


def _tokenize(text: str) -> Set[str]:
    return {t for t in re.findall(r"[a-zA-Z0-9_]+", (text or "").lower()) if len(t) > 1}


def _score(text: str, query_tokens: Set[str]) -> int:
    return len(_tokenize(text) & query_tokens)


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
    query_tokens = _tokenize(query)

    rules_ranked: List[Tuple[int, Dict]] = []
    data_ranked: List[Tuple[int, Dict]] = []

    if mode in {"rules", "hybrid"}:
        for chunk in load_rule_chunks():
            score = _score(chunk.get("text", ""), query_tokens)
            if score > 0:
                rules_ranked.append((score, chunk))
        rules_ranked.sort(key=lambda x: x[0], reverse=True)

    if mode in {"data", "hybrid"}:
        for chunk in ensure_game_data_chunks():
            score = _score(chunk.get("text", ""), query_tokens)
            if score > 0:
                data_ranked.append((score, chunk))
        data_ranked.sort(key=lambda x: x[0], reverse=True)

    return {
        "rules": [c for _, c in rules_ranked[:max_rules]],
        "game_data": [c for _, c in data_ranked[:max_data]],
    }
