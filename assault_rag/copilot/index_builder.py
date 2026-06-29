import json
from pathlib import Path
from typing import Dict, List


ROOT = Path(__file__).resolve().parents[2]
RULE_CHUNKS_PATH = ROOT / "assault_rag" / "data" / "rulebook" / "chunks" / "rulebook_chunks.json"
RULE_TYPED_PATH = ROOT / "assault_rag" / "data" / "rulebook" / "typed" / "rulebook_typed.json"
RULEBOOK_DOCS_DIR = ROOT / "docs" / "game_rules"
UNIT_CATALOG_PATH = ROOT / "assault_sim" / "assets" / "catalogs" / "unit_catalog.json"
SCENARIOS_DIR = ROOT / "assault_sim" / "assets" / "scenarios"
GAME_DATA_CHUNKS_PATH = ROOT / "assault_rag" / "data" / "game_data" / "chunks" / "game_data_chunks.json"
FORTIFICATION_TABLE_PATH = (
    ROOT
    / "assault_sim"
    / "assets"
    / "rules_tables"
    / "fortification"
    / "fortification_modifiers.v1.json"
)


def _flatten_attack(attack: Dict) -> List[str]:
    lines: List[str] = []
    for fire_mode, by_target in attack.items():
        for target, by_range in by_target.items():
            for range_band, payload in by_range.items():
                dice = payload.get("dice", [])
                dice_text = ", ".join(dice) if dice else "none"
                lines.append(f"{fire_mode} vs {target} @ {range_band}: {dice_text}")
    return lines


def _build_unit_chunks(catalog: Dict) -> List[Dict]:
    chunks: List[Dict] = []
    for unit_key, unit in catalog.get("units", {}).items():
        lines = [
            f"Unit: {unit_key}",
            f"Side: {unit.get('side', 'UNKNOWN')}",
            f"Category: {unit.get('category', 'UNKNOWN')}",
            f"Subtype: {unit.get('subtype', 'UNKNOWN')}",
            f"Classification: {unit.get('classification', 'UNKNOWN')}",
            f"Movement: {unit.get('movement', 0)}",
            f"Max strength: {unit.get('max_strength', 0)}",
            f"Traits: {', '.join(unit.get('traits', [])) if unit.get('traits') else 'none'}",
        ]
        attack_lines = _flatten_attack(unit.get("attack", {}))
        if attack_lines:
            lines.append("Attack profile:")
            lines.extend(f"- {line}" for line in attack_lines)

        chunks.append(
            {
                "chunk_id": f"unit::{unit_key}",
                "source": "unit_catalog",
                "source_id": unit_key,
                "text": "\n".join(lines),
                "metadata": {
                    "side": unit.get("side"),
                    "category": unit.get("category"),
                    "classification": unit.get("classification"),
                },
            }
        )
    return chunks


def _build_scenario_chunks(scenarios_dir: Path) -> List[Dict]:
    chunks: List[Dict] = []
    for scenario_path in sorted(scenarios_dir.glob("*.json")):
        raw = json.loads(scenario_path.read_text(encoding="utf-8"))
        scenario_id = raw.get("id", scenario_path.stem)
        units = raw.get("units", [])
        vp_hexes = raw.get("vp", {}).get("hexes", [])
        tracked_side = raw.get("victory_outcomes", {}).get("tracked_side", "UNKNOWN")

        side_counts: Dict[str, int] = {}
        for unit in units:
            side = unit.get("side", "UNKNOWN")
            side_counts[side] = side_counts.get(side, 0) + 1
        side_summary = ", ".join(f"{k}={v}" for k, v in sorted(side_counts.items()))

        lines = [
            f"Scenario: {scenario_id}",
            f"File: {scenario_path.name}",
            f"Max turns: {raw.get('max_turns', 'N/A')}",
            f"Unit count: {len(units)}",
            f"VP hex count: {len(vp_hexes)}",
            f"Tracked side: {tracked_side}",
            f"Sides: {side_summary if side_summary else 'none'}",
        ]
        chunks.append(
            {
                "chunk_id": f"scenario::{scenario_id}",
                "source": "scenario",
                "source_id": scenario_id,
                "text": "\n".join(lines),
                "metadata": {
                    "file_name": scenario_path.name,
                    "max_turns": raw.get("max_turns"),
                    "unit_count": len(units),
                    "vp_hex_count": len(vp_hexes),
                    "tracked_side": tracked_side,
                },
            }
        )
    return chunks


def _build_fortification_chunks(table_data: Dict) -> List[Dict]:
    chunks: List[Dict] = []
    fortifications = table_data.get("fortifications", {}) or {}
    alias_map = {
        "gun_emplacement": ["gun position"],
        "casemate": ["pillbox"],
    }
    for fort_name, fort_payload in sorted(fortifications.items()):
        movement_delta = fort_payload.get("movement_delta", {}) or {}
        defense_bonus = fort_payload.get("defense_bonus", {}) or {}
        aliases = alias_map.get(fort_name, [])
        lines = [
            f"Fortification: {fort_name}",
            f"Aliases: {', '.join(aliases) if aliases else 'none'}",
            "Movement delta by move type:",
        ]
        for move_type, delta in sorted(movement_delta.items()):
            crossing = "forbidden" if delta is None else f"base + {delta}"
            lines.append(f"- {move_type}: {crossing}")
        lines.append("Defense bonus by unit category and attack sector:")
        for category, sector_map in sorted(defense_bonus.items()):
            for sector, dice in sorted((sector_map or {}).items()):
                dice_txt = ", ".join(dice or []) if dice else "none"
                lines.append(f"- {category} / {sector}: {dice_txt}")

        chunks.append(
            {
                "chunk_id": f"fortification::{fort_name}",
                "source": "fortification_table",
                "source_id": f"fortification::{fort_name}",
                "text": "\n".join(lines),
                "metadata": {
                    "fortification_type": fort_name,
                    "aliases": aliases,
                },
            }
        )
    return chunks


def ensure_fortification_chunks() -> List[Dict]:
    if not FORTIFICATION_TABLE_PATH.exists():
        return []
    table_data = json.loads(FORTIFICATION_TABLE_PATH.read_text(encoding="utf-8"))
    return _build_fortification_chunks(table_data)


def ensure_game_data_chunks() -> List[Dict]:
    if GAME_DATA_CHUNKS_PATH.exists():
        existing = json.loads(GAME_DATA_CHUNKS_PATH.read_text(encoding="utf-8"))
        # Keep compatibility with previous persisted chunk files by adding
        # fortification chunks at runtime if not present.
        has_fortification = any(str(c.get("source", "")) == "fortification_table" for c in existing)
        if has_fortification:
            return existing
        return existing + ensure_fortification_chunks()

    if not UNIT_CATALOG_PATH.exists():
        raise FileNotFoundError(f"Missing unit catalog: {UNIT_CATALOG_PATH}")
    if not SCENARIOS_DIR.exists():
        raise FileNotFoundError(f"Missing scenarios dir: {SCENARIOS_DIR}")

    catalog = json.loads(UNIT_CATALOG_PATH.read_text(encoding="utf-8"))
    chunks = _build_unit_chunks(catalog)
    chunks.extend(_build_scenario_chunks(SCENARIOS_DIR))
    chunks.extend(ensure_fortification_chunks())

    GAME_DATA_CHUNKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    GAME_DATA_CHUNKS_PATH.write_text(
        json.dumps(chunks, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return chunks


def load_rule_chunks() -> List[Dict]:
    if RULE_CHUNKS_PATH.exists():
        return json.loads(RULE_CHUNKS_PATH.read_text(encoding="utf-8"))
    if RULE_TYPED_PATH.exists():
        typed = json.loads(RULE_TYPED_PATH.read_text(encoding="utf-8"))
        return [
            {
                "rule_id": r.get("rule_id"),
                "text": r.get("text", ""),
                "source": "rulebook_typed",
            }
            for r in typed
        ]
    return []


def ensure_rule_chunks() -> List[Dict]:
    existing = load_rule_chunks()
    if existing:
        return existing

    if not RULEBOOK_DOCS_DIR.exists():
        raise FileNotFoundError(f"Missing rulebook docs dir: {RULEBOOK_DOCS_DIR}")

    chunks: List[Dict] = []
    md_files = sorted(RULEBOOK_DOCS_DIR.glob("*.md"))
    for md_path in md_files:
        text = md_path.read_text(encoding="utf-8").strip()
        if not text:
            continue
        # Simple fixed-size chunking to keep retrieval deterministic.
        chunk_size = 1400
        for idx in range(0, len(text), chunk_size):
            piece = text[idx: idx + chunk_size].strip()
            if not piece:
                continue
            chunks.append(
                {
                    "rule_id": f"{md_path.stem}::{idx // chunk_size}",
                    "text": piece,
                    "source": "game_rules_markdown",
                    "source_id": md_path.name,
                }
            )

    if not chunks:
        raise RuntimeError("Rulebook docs found but no chunks could be generated.")

    RULE_CHUNKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RULE_CHUNKS_PATH.write_text(
        json.dumps(chunks, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return chunks


def get_rule_index_status() -> Dict:
    chunks_exists = RULE_CHUNKS_PATH.exists()
    typed_exists = RULE_TYPED_PATH.exists()
    active_path = None
    if chunks_exists:
        active_path = str(RULE_CHUNKS_PATH)
    elif typed_exists:
        active_path = str(RULE_TYPED_PATH)
    return {
        "chunks_exists": chunks_exists,
        "typed_exists": typed_exists,
        "active_path": active_path,
    }
