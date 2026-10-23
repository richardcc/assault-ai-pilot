"""
assault_backend/services/scenario_editor_service.py

Service layer for creating, managing, validating, and publishing scenario drafts.
Provides full lifecycle support:
1. Create new draft scenario from template or clone from existing scenario.
2. Edit and persist draft scenarios in assets/scenarios/drafts/.
3. Comprehensive validation against engine schema and canonical catalogs.
4. Publish drafts into assets/scenarios/ for immediate engine & AI runtime use.
5. Revert/unpublish and delete drafts.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from assault_model.paths import (
    SCENARIOS_DIR,
    UNIT_CATALOG_PATH,
    MAP_PIECE_CATALOG_PATH,
)

DRAFTS_DIR = SCENARIOS_DIR / "drafts"

VALID_FORTIFICATIONS = {
    "gun_emplacement",
    "casemate",
    "bunker",
    "trench",
    "barbed_wire",
    "minefield",
}

VALID_EXPERIENCES = {"RECRUIT", "REGULAR", "VETERAN", "HARDENED"}
VALID_SIDES = {"US", "IT", "GE", "UK"}


def _ensure_drafts_dir() -> Path:
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    return DRAFTS_DIR


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_unit_catalog_dict() -> Dict[str, Any]:
    if not UNIT_CATALOG_PATH.exists():
        return {}
    try:
        raw = json.loads(UNIT_CATALOG_PATH.read_text(encoding="utf-8"))
        return raw.get("units", {}) or {}
    except Exception:
        return {}


def load_map_piece_catalog_dict() -> Dict[str, Any]:
    if not MAP_PIECE_CATALOG_PATH.exists():
        return {}
    try:
        raw = json.loads(MAP_PIECE_CATALOG_PATH.read_text(encoding="utf-8"))
        return raw.get("pieces", {}) or {}
    except Exception:
        return {}


def get_empty_scenario_template(scenario_id: str = "draft_new_scenario") -> Dict[str, Any]:
    return {
        "id": scenario_id,
        "name": "New Custom Scenario",
        "description": "Custom tactical scenario created via Scenario Editor.",
        "status": "draft",
        "max_turns": 8,
        "shape": [18, 12],
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "map": {
            "pieces": [
                {"id": "S3", "origin": [0, 0]}
            ],
            "fortifications": []
        },
        "morale_track": {
            "US": {"start": 3, "retreat": 7, "rout": 9, "surrender": 11},
            "IT": {"start": 2, "retreat": 6, "rout": 7, "surrender": 9}
        },
        "units": [
            {
                "unit_id": "US_1",
                "side": "US",
                "unit_key": "US_RIFLES_43",
                "position": [0, 2],
                "experience": "REGULAR"
            },
            {
                "unit_id": "IT_1",
                "side": "IT",
                "unit_key": "IT_RIFLES_43",
                "position": [4, 2],
                "experience": "REGULAR"
            }
        ],
        "reinforcements": [],
        "vp": {
            "value_per_hex": 2,
            "hexes": [
                {"q": 2, "r": 2, "initial_owner": "IT", "value": 2}
            ]
        },
        "victory_outcomes": {
            "tracked_side": "US",
            "metric": "objectives_captured",
            "timing": "end_of_last_turn",
            "table": [
                {"captured": {"min": 1, "max": 1}, "result": "Victory", "outcome_class": "victory"},
                {"captured": {"min": 0, "max": 0}, "result": "Defeat", "outcome_class": "defeat"}
            ]
        }
    }


def validate_scenario_payload(data: Dict[str, Any]) -> Tuple[bool, List[str], List[str]]:
    """
    Validates a scenario dictionary against engine rules and catalogs.
    Returns (is_valid, errors, warnings).
    """
    errors: List[str] = []
    warnings: List[str] = []

    # 1. Essential root metadata
    scenario_id = str(data.get("id", "")).strip()
    if not scenario_id:
        errors.append("Scenario must have a non-empty 'id'.")
    elif not all(c.isalnum() or c in ("_", "-") for c in scenario_id):
        errors.append(f"Scenario id '{scenario_id}' contains invalid characters (use alphanumeric, _, -).")

    max_turns = data.get("max_turns")
    if not isinstance(max_turns, int) or max_turns < 1 or max_turns > 30:
        errors.append(f"Invalid max_turns: {max_turns}. Expected integer between 1 and 30.")

    shape = data.get("shape")
    if not isinstance(shape, (list, tuple)) or len(shape) != 2:
        warnings.append("Scenario shape should be a 2-element list [width, height].")

    # 2. Map Pieces
    map_def = data.get("map", {})
    if not isinstance(map_def, dict):
        errors.append("'map' section must be a JSON object.")
        map_def = {}

    pieces = map_def.get("pieces", [])
    if not isinstance(pieces, list) or len(pieces) == 0:
        errors.append("Scenario 'map.pieces' must contain at least 1 map piece.")
    else:
        piece_cat = load_map_piece_catalog_dict()
        for idx, p in enumerate(pieces):
            if not isinstance(p, dict):
                errors.append(f"Map piece #{idx} must be a dictionary.")
                continue
            pid = p.get("id")
            if not pid:
                errors.append(f"Map piece #{idx} missing 'id'.")
            elif piece_cat and pid not in piece_cat:
                errors.append(f"Map piece #{idx} '{pid}' does not exist in map piece catalog.")

            origin = p.get("origin")
            if not isinstance(origin, (list, tuple)) or len(origin) != 2:
                errors.append(f"Map piece '{pid}' has invalid origin: {origin}. Expected [q, r].")

    # 3. Fortifications
    forts = map_def.get("fortifications", [])
    if isinstance(forts, list):
        for idx, f in enumerate(forts):
            if not isinstance(f, dict):
                errors.append(f"Fortification #{idx} must be a dictionary.")
                continue
            ftype = f.get("type")
            if ftype not in VALID_FORTIFICATIONS:
                errors.append(f"Fortification #{idx} has invalid type '{ftype}'. Allowed: {sorted(VALID_FORTIFICATIONS)}")
            q, r = f.get("q"), f.get("r")
            if not isinstance(q, int) or not isinstance(r, int):
                errors.append(f"Fortification #{idx} ({ftype}) coordinates [q={q}, r={r}] must be integers.")

    # 4. Units
    units = data.get("units", [])
    if not isinstance(units, list):
        errors.append("'units' must be a list.")
        units = []
    elif len(units) == 0:
        warnings.append("Scenario defines 0 initial units.")

    unit_cat = load_unit_catalog_dict()
    unit_ids_seen = set()

    for idx, u in enumerate(units):
        if not isinstance(u, dict):
            errors.append(f"Unit #{idx} must be a dictionary.")
            continue
        uid = str(u.get("unit_id", "")).strip()
        if not uid:
            errors.append(f"Unit #{idx} missing 'unit_id'.")
        elif uid in unit_ids_seen:
            errors.append(f"Duplicate unit_id '{uid}' at index #{idx}.")
        unit_ids_seen.add(uid)

        ukey = u.get("unit_key")
        if not ukey:
            errors.append(f"Unit '{uid}' missing 'unit_key'.")
        elif unit_cat and ukey not in unit_cat:
            errors.append(f"Unit '{uid}' references unknown unit_key '{ukey}'.")

        pos = u.get("position")
        if not isinstance(pos, (list, tuple)) or len(pos) != 2 or not isinstance(pos[0], int) or not isinstance(pos[1], int):
            errors.append(f"Unit '{uid}' has invalid position {pos}. Expected [q, r] integers.")

        side = u.get("side")
        if not side:
            errors.append(f"Unit '{uid}' missing 'side'.")

        exp = u.get("experience", "REGULAR")
        if exp not in VALID_EXPERIENCES:
            warnings.append(f"Unit '{uid}' has unusual experience '{exp}'. Standard: {sorted(VALID_EXPERIENCES)}")

    # 5. Morale Track
    morale = data.get("morale_track")
    if not isinstance(morale, dict) or len(morale) == 0:
        warnings.append("Scenario defines no 'morale_track'. Default morale rules will apply.")
    else:
        for side_key, track in morale.items():
            if not isinstance(track, dict):
                errors.append(f"Morale track for side '{side_key}' must be a dictionary.")
                continue
            start = track.get("start", 1)
            retreat = track.get("retreat", 6)
            rout = track.get("rout", 8)
            surrender = track.get("surrender", 10)
            if not (start <= retreat <= rout <= surrender):
                errors.append(
                    f"Morale track for side '{side_key}' invalid ordering: start({start}) <= "
                    f"retreat({retreat}) <= rout({rout}) <= surrender({surrender}) violated."
                )

    # 6. Victory Points
    vp = data.get("vp")
    if not isinstance(vp, dict):
        warnings.append("Scenario defines no 'vp' objective block.")
    else:
        hexes = vp.get("hexes", [])
        if not isinstance(hexes, list) or len(hexes) == 0:
            warnings.append("Victory Point 'vp.hexes' contains no objective hexes.")
        else:
            for idx, vh in enumerate(hexes):
                if not isinstance(vh, dict):
                    errors.append(f"VP hex #{idx} must be a dictionary.")
                    continue
                q, r = vh.get("q"), vh.get("r")
                if not isinstance(q, int) or not isinstance(r, int):
                    errors.append(f"VP hex #{idx} coordinates [q={q}, r={r}] must be integers.")

    return (len(errors) == 0, errors, warnings)


class ScenarioEditorService:
    """
    Central service for draft scenario lifecycle operations.
    """

    def __init__(self, scenarios_dir: Path = SCENARIOS_DIR):
        self.scenarios_dir = Path(scenarios_dir)
        self.drafts_dir = self.scenarios_dir / "drafts"
        self.drafts_dir.mkdir(parents=True, exist_ok=True)

    def list_all_scenarios(self) -> List[Dict[str, Any]]:
        """
        Lists all scenarios, categorizing each as 'draft' or 'published'.
        Deduplicates by scenario ID.
        """
        results: List[Dict[str, Any]] = []
        seen_ids = set()

        # 1. Draft scenarios
        if self.drafts_dir.exists():
            for p in sorted(self.drafts_dir.glob("*.json")):
                try:
                    meta = self._extract_summary(p, is_draft=True)
                    if meta["id"] not in seen_ids:
                        seen_ids.add(meta["id"])
                        results.append(meta)
                except Exception as e:
                    if p.stem not in seen_ids:
                        seen_ids.add(p.stem)
                        results.append({
                            "id": p.stem,
                            "name": p.stem,
                            "status": "draft",
                            "error": str(e),
                            "file_name": p.name,
                        })

        # 2. Published scenarios
        for p in sorted(self.scenarios_dir.glob("*.json")):
            if p.is_file():
                try:
                    meta = self._extract_summary(p, is_draft=False)
                    if meta["id"] not in seen_ids:
                        seen_ids.add(meta["id"])
                        results.append(meta)
                except Exception as e:
                    if p.stem not in seen_ids:
                        seen_ids.add(p.stem)
                        results.append({
                            "id": p.stem,
                            "name": p.stem,
                            "status": "published",
                            "error": str(e),
                            "file_name": p.name,
                        })

        return results

    def _extract_summary(self, path: Path, is_draft: bool) -> Dict[str, Any]:
        data = json.loads(path.read_text(encoding="utf-8"))
        scen_id = data.get("id") or path.stem
        units = data.get("units", [])
        pieces = data.get("map", {}).get("pieces", [])
        vp_hexes = data.get("vp", {}).get("hexes", [])
        forts = data.get("map", {}).get("fortifications", [])

        sides = sorted(list(set(
            [u.get("side") for u in units if isinstance(u, dict) and u.get("side")] +
            list(data.get("morale_track", {}).keys())
        )))

        mtime = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()

        return {
            "id": scen_id,
            "name": data.get("name") or data.get("title") or scen_id.replace("_", " ").title(),
            "description": data.get("description", ""),
            "status": "draft" if is_draft else "published",
            "max_turns": data.get("max_turns", 8),
            "shape": data.get("shape", [18, 12]),
            "unit_count": len(units),
            "map_piece_count": len(pieces),
            "vp_count": len(vp_hexes),
            "fortification_count": len(forts),
            "sides": sides,
            "file_name": path.name,
            "updated_at": data.get("updated_at") or mtime,
            "is_draft": is_draft,
        }

    list_scenarios = list_all_scenarios

    def get_scenario(self, scenario_id: str, prefer_draft: bool = True) -> Dict[str, Any]:
        """
        Loads the complete scenario JSON, searching drafts first if prefer_draft=True.
        """
        scenario_id = scenario_id.replace(".json", "")
        draft_file = self.drafts_dir / f"{scenario_id}.json"
        pub_file = self.scenarios_dir / f"{scenario_id}.json"

        target_file: Optional[Path] = None
        is_draft = False

        if prefer_draft and draft_file.exists():
            target_file = draft_file
            is_draft = True
        elif pub_file.exists():
            target_file = pub_file
            is_draft = False
        elif draft_file.exists():
            target_file = draft_file
            is_draft = True
        else:
            # Fallback scan by scenario id inside JSON or stem
            if prefer_draft and self.drafts_dir.exists():
                for p in self.drafts_dir.glob("*.json"):
                    if p.stem == scenario_id or p.stem.startswith(scenario_id):
                        target_file = p
                        is_draft = True
                        break
            if not target_file and self.scenarios_dir.exists():
                for p in self.scenarios_dir.glob("*.json"):
                    if p.stem == scenario_id or p.stem.startswith(scenario_id):
                        target_file = p
                        is_draft = False
                        break

        if not target_file or not target_file.exists():
            raise FileNotFoundError(f"Scenario '{scenario_id}' not found in drafts or published scenarios.")

        data = json.loads(target_file.read_text(encoding="utf-8"))
        data["status"] = "draft" if is_draft else "published"
        data["is_draft"] = is_draft
        return data

    def create_draft(
        self,
        scenario_id: str,
        data: Optional[Dict[str, Any]] = None,
        clone_from_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Creates a new draft scenario in assets/scenarios/drafts/.
        """
        scenario_id = scenario_id.strip().replace(" ", "_")
        if not scenario_id:
            raise ValueError("Scenario ID cannot be empty.")

        draft_file = self.drafts_dir / f"{scenario_id}.json"

        if clone_from_id:
            base_data = self.get_scenario(clone_from_id)
            base_data["id"] = scenario_id
            base_data["name"] = f"Draft clone of {base_data.get('name', clone_from_id)}"
            base_data["status"] = "draft"
            base_data["created_at"] = _now_iso()
            base_data["updated_at"] = _now_iso()
            draft_payload = base_data
        elif data:
            draft_payload = dict(data)
            draft_payload["id"] = scenario_id
            draft_payload["status"] = "draft"
            draft_payload["updated_at"] = _now_iso()
            if "created_at" not in draft_payload:
                draft_payload["created_at"] = _now_iso()
        else:
            draft_payload = get_empty_scenario_template(scenario_id)

        # Write to disk
        draft_file.write_text(json.dumps(draft_payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return draft_payload

    def update_draft(self, scenario_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Updates an existing draft scenario with new data.
        """
        scenario_id = scenario_id.strip()
        draft_file = self.drafts_dir / f"{scenario_id}.json"

        payload = dict(data)
        payload["id"] = scenario_id
        payload["status"] = "draft"
        payload["updated_at"] = _now_iso()

        draft_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return payload

    def validate_scenario(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validates scenario data and returns result payload.
        """
        valid, errors, warnings = validate_scenario_payload(data)
        return {
            "valid": valid,
            "errors": errors,
            "warnings": warnings,
            "timestamp": _now_iso(),
        }

    def publish_draft(self, scenario_id: str, target_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Publishes a draft scenario to canonical assets/scenarios/.
        Validates strict schema before publishing.
        """
        scenario_id = scenario_id.strip()
        draft_file = self.drafts_dir / f"{scenario_id}.json"

        if not draft_file.exists():
            raise FileNotFoundError(f"Draft scenario '{scenario_id}' does not exist.")

        data = json.loads(draft_file.read_text(encoding="utf-8"))

        dest_id = (target_id or data.get("id") or scenario_id).strip()
        data["id"] = dest_id
        data["status"] = "published"
        data["published_at"] = _now_iso()
        data["updated_at"] = _now_iso()

        valid, errors, warnings = validate_scenario_payload(data)
        if not valid:
            raise ValueError(f"Cannot publish invalid scenario. Validation errors: {'; '.join(errors)}")

        pub_file = self.scenarios_dir / f"{dest_id}.json"
        pub_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

        # Remove draft file once published so it's not duplicated in drafts list
        if draft_file.exists():
            draft_file.unlink()
        if dest_id != scenario_id:
            dest_draft = self.drafts_dir / f"{dest_id}.json"
            if dest_draft.exists():
                dest_draft.unlink()

        return {
            "ok": True,
            "id": dest_id,
            "status": "published",
            "published_path": str(pub_file),
            "warnings": warnings,
            "timestamp": _now_iso(),
        }

    def delete_draft(self, scenario_id: str) -> bool:
        """
        Deletes a draft scenario file.
        """
        draft_file = self.drafts_dir / f"{scenario_id}.json"
        if draft_file.exists():
            draft_file.unlink()
            return True
        return False

    def unpublish_scenario(self, scenario_id: str) -> Dict[str, Any]:
        """
        Moves a published scenario back to draft mode.
        """
        pub_file = self.scenarios_dir / f"{scenario_id}.json"
        if not pub_file.exists():
            raise FileNotFoundError(f"Published scenario '{scenario_id}' not found.")

        data = json.loads(pub_file.read_text(encoding="utf-8"))
        data["status"] = "draft"
        data["updated_at"] = _now_iso()

        draft_file = self.drafts_dir / f"{scenario_id}.json"
        draft_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

        # Remove published file
        pub_file.unlink()

        return {
            "ok": True,
            "id": scenario_id,
            "status": "draft",
            "draft_path": str(draft_file),
            "timestamp": _now_iso(),
        }


scenario_editor_service = ScenarioEditorService()
