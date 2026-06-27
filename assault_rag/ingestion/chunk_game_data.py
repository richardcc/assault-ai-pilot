import json
from pathlib import Path
from typing import Dict, List


UNIT_CATALOG_PATH = Path("assault_sim/assets/catalogs/unit_catalog.json")
SCENARIOS_DIR = Path("assault_sim/assets/scenarios")
OUTPUT_PATH = Path("assault_rag/data/game_data/chunks/game_data_chunks.json")


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


def build_game_data_chunks() -> List[Dict]:
    if not UNIT_CATALOG_PATH.exists():
        raise FileNotFoundError(f"Missing unit catalog: {UNIT_CATALOG_PATH}")
    if not SCENARIOS_DIR.exists():
        raise FileNotFoundError(f"Missing scenarios dir: {SCENARIOS_DIR}")

    catalog = json.loads(UNIT_CATALOG_PATH.read_text(encoding="utf-8"))
    chunks = _build_unit_chunks(catalog)
    chunks.extend(_build_scenario_chunks(SCENARIOS_DIR))
    return chunks


def main():
    chunks = build_game_data_chunks()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(chunks, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Created {len(chunks)} game-data chunks")
    print(f"Saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
