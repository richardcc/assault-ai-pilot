import json
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple


RULE_CHUNKS_PATH = Path("assault_rag/data/rulebook/chunks/rulebook_chunks.json")
GAME_DATA_CHUNKS_PATH = Path("assault_rag/data/game_data/chunks/game_data_chunks.json")


def _tokenize(text: str) -> Set[str]:
    return {t for t in re.findall(r"[a-zA-Z0-9_]+", text.lower()) if len(t) > 1}


def _score(text: str, query_tokens: Set[str]) -> int:
    text_tokens = _tokenize(text)
    return len(text_tokens & query_tokens)


def _load_json(path: Path) -> List[Dict]:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def retrieve_hybrid_knowledge(
    query: str,
    max_rule_chunks: int = 5,
    max_data_chunks: int = 5,
) -> Dict[str, List[Dict]]:
    """
    Hybrid retrieval across:
    - rulebook chunks (procedural rules)
    - game data chunks (unit catalog + scenarios)
    """
    query_tokens = _tokenize(query)
    rules = _load_json(RULE_CHUNKS_PATH)
    data = _load_json(GAME_DATA_CHUNKS_PATH)

    ranked_rules: List[Tuple[int, Dict]] = []
    for chunk in rules:
        s = _score(chunk.get("text", ""), query_tokens)
        if s > 0:
            ranked_rules.append((s, chunk))
    ranked_rules.sort(key=lambda x: x[0], reverse=True)

    ranked_data: List[Tuple[int, Dict]] = []
    for chunk in data:
        s = _score(chunk.get("text", ""), query_tokens)
        if s > 0:
            ranked_data.append((s, chunk))
    ranked_data.sort(key=lambda x: x[0], reverse=True)

    return {
        "rules": [c for _, c in ranked_rules[:max_rule_chunks]],
        "game_data": [c for _, c in ranked_data[:max_data_chunks]],
    }
