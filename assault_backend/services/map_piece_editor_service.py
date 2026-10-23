"""
assault_backend/services/map_piece_editor_service.py

Lifecycle Service for Map Piece Editor:
- Manages published map pieces in assets/catalogs/map_piece_catalog.json
- Manages draft map pieces in assets/catalogs/map_piece_drafts/
- Validates shapes, sparse hex coordinates, and terrain types
- Supports draft creation, clone, update, schema validation, publish, and unpublish
"""

import copy
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from assault_model.paths import ASSETS_DIR, CATALOGS_DIR, MAP_PIECE_CATALOG_PATH
from assault_model.map.terrain import Terrain
from assault_model.map.hex_edge_feature import HexEdgeFeature

MAP_PIECE_DRAFTS_DIR = CATALOGS_DIR / "map_piece_drafts"

VALID_TERRAINS = {t.value for t in Terrain}
VALID_EDGE_FEATURES = {f.value for f in HexEdgeFeature}


class MapPieceEditorService:
    def __init__(self, catalog_path: Path = MAP_PIECE_CATALOG_PATH, drafts_dir: Path = MAP_PIECE_DRAFTS_DIR):
        self.catalog_path = catalog_path
        self.drafts_dir = drafts_dir
        self.drafts_dir.mkdir(parents=True, exist_ok=True)

    def _load_catalog_dict(self) -> Dict[str, Any]:
        if not self.catalog_path.exists():
            return {"pieces": {}}
        try:
            with open(self.catalog_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"pieces": {}}

    def _save_catalog_dict(self, data: Dict[str, Any]) -> None:
        self.catalog_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.catalog_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def list_pieces(self) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []

        # 1. Published Pieces from Catalog
        cat = self._load_catalog_dict()
        for pid, pdata in cat.get("pieces", {}).items():
            shape = pdata.get("shape", [9, 8])
            hexes = pdata.get("hexes", [])
            edges = pdata.get("hex_edges", [])
            result.append({
                "id": pid,
                "description": pdata.get("description", ""),
                "status": "published",
                "is_draft": False,
                "shape": shape,
                "hex_count": len(hexes),
                "edge_count": len(edges),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })

        # 2. Draft Pieces from Drafts Directory
        if self.drafts_dir.exists():
            for f in sorted(self.drafts_dir.glob("*.json")):
                try:
                    with open(f, "r", encoding="utf-8") as df:
                        ddata = json.load(df)
                    pid = ddata.get("id", f.stem)
                    shape = ddata.get("shape", [9, 8])
                    hexes = ddata.get("hexes", [])
                    edges = ddata.get("hex_edges", [])
                    mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).isoformat()
                    result.append({
                        "id": pid,
                        "description": ddata.get("description", ""),
                        "status": "draft",
                        "is_draft": True,
                        "shape": shape,
                        "hex_count": len(hexes),
                        "edge_count": len(edges),
                        "file_name": f.name,
                        "updated_at": mtime,
                    })
                except Exception:
                    continue

        return result

    def get_piece(self, piece_id: str, is_draft: Optional[bool] = None) -> Optional[Dict[str, Any]]:
        # If is_draft is specified True, check drafts first
        if is_draft is True or is_draft is None:
            draft_path = self.drafts_dir / f"{piece_id}.json"
            if draft_path.exists():
                with open(draft_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    data["is_draft"] = True
                    data["status"] = "draft"
                    if "id" not in data:
                        data["id"] = piece_id
                    return data

        # Check published catalog
        cat = self._load_catalog_dict()
        if piece_id in cat.get("pieces", {}):
            data = copy.deepcopy(cat["pieces"][piece_id])
            data["id"] = piece_id
            data["is_draft"] = False
            data["status"] = "published"
            return data

        return None

    def validate_piece(self, data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        errors: List[str] = []

        pid = data.get("id")
        if not pid or not isinstance(pid, str) or not re.match(r"^[a-zA-Z0-9_\-]+$", pid):
            errors.append("Map piece 'id' is required and must contain only alphanumeric characters, underscores, or hyphens.")

        shape = data.get("shape")
        if not isinstance(shape, (list, tuple)) or len(shape) != 2:
            errors.append("Field 'shape' must be an array of [width, height], e.g. [9, 8].")
        else:
            w, h = shape
            if not isinstance(w, int) or not isinstance(h, int) or w <= 0 or h <= 0:
                errors.append("Map piece dimensions [width, height] must be positive integers.")

        hexes = data.get("hexes", [])
        if not isinstance(hexes, list):
            errors.append("Field 'hexes' must be a list of hex objects.")
        else:
            w = shape[0] if isinstance(shape, (list, tuple)) and len(shape) == 2 and isinstance(shape[0], int) else 999
            h = shape[1] if isinstance(shape, (list, tuple)) and len(shape) == 2 and isinstance(shape[1], int) else 999
            for idx, hx in enumerate(hexes):
                if not isinstance(hx, dict):
                    errors.append(f"Hex at index {idx} must be an object.")
                    continue
                q = hx.get("q")
                r = hx.get("r")
                if q is None or not isinstance(q, int) or r is None or not isinstance(r, int):
                    errors.append(f"Hex at index {idx} missing valid integer coordinates 'q' and 'r'.")
                elif q < 0 or q >= w or r < 0 or r >= h:
                    errors.append(f"Hex ({q}, {r}) at index {idx} is outside piece boundaries [0..{w-1}, 0..{h-1}].")

                terrain = hx.get("terrain")
                if terrain and terrain not in VALID_TERRAINS:
                    errors.append(f"Hex ({q}, {r}) has unknown terrain '{terrain}'. Valid: {sorted(list(VALID_TERRAINS))}")

        edges = data.get("hex_edges", [])
        if not isinstance(edges, list):
            errors.append("Field 'hex_edges' must be a list.")
        else:
            for idx, ed in enumerate(edges):
                if not isinstance(ed, dict):
                    errors.append(f"Edge feature at index {idx} must be an object.")
                    continue
                feat = ed.get("feature")
                if feat and feat not in VALID_EDGE_FEATURES:
                    errors.append(f"Edge feature '{feat}' at index {idx} is invalid. Valid: {sorted(list(VALID_EDGE_FEATURES))}")

        return (len(errors) == 0, errors)

    def create_draft(self, piece_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        data = copy.deepcopy(data)
        data["id"] = piece_id
        if "shape" not in data:
            data["shape"] = [9, 8]
        if "hexes" not in data:
            data["hexes"] = []
        if "hex_edges" not in data:
            data["hex_edges"] = []
        if "description" not in data:
            data["description"] = f"Map section {data['shape'][0]}x{data['shape'][1]}"

        draft_path = self.drafts_dir / f"{piece_id}.json"
        with open(draft_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        data["is_draft"] = True
        data["status"] = "draft"
        return data

    def update_draft(self, piece_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        data = copy.deepcopy(data)
        data["id"] = piece_id
        draft_path = self.drafts_dir / f"{piece_id}.json"
        with open(draft_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        data["is_draft"] = True
        data["status"] = "draft"
        return data

    def delete_draft(self, piece_id: str) -> bool:
        draft_path = self.drafts_dir / f"{piece_id}.json"
        if draft_path.exists():
            draft_path.unlink()
            return True
        return False

    def clone_piece(self, source_id: str, new_id: str, from_draft: bool = False) -> Dict[str, Any]:
        source = self.get_piece(source_id, is_draft=from_draft)
        if not source:
            raise ValueError(f"Source map piece '{source_id}' not found.")

        cloned = copy.deepcopy(source)
        cloned["id"] = new_id
        cloned["description"] = f"{source.get('description', '')} (Cloned)"
        return self.create_draft(new_id, cloned)

    def publish_piece(self, draft_id: str) -> Dict[str, Any]:
        draft_data = self.get_piece(draft_id, is_draft=True)
        if not draft_data:
            raise FileNotFoundError(f"Draft piece '{draft_id}' not found.")

        valid, errors = self.validate_piece(draft_data)
        if not valid:
            raise ValueError(f"Cannot publish invalid map piece: {'; '.join(errors)}")

        cat = self._load_catalog_dict()
        if "pieces" not in cat:
            cat["pieces"] = {}

        piece_entry = {
            "description": draft_data.get("description", ""),
            "shape": draft_data.get("shape", [9, 8]),
            "hexes": draft_data.get("hexes", []),
        }
        if draft_data.get("hex_edges"):
            piece_entry["hex_edges"] = draft_data.get("hex_edges")

        cat["pieces"][draft_id] = piece_entry
        self._save_catalog_dict(cat)

        # Remove draft once published
        self.delete_draft(draft_id)

        piece_entry["id"] = draft_id
        piece_entry["is_draft"] = False
        piece_entry["status"] = "published"
        return piece_entry

    def unpublish_piece(self, piece_id: str) -> Dict[str, Any]:
        cat = self._load_catalog_dict()
        if piece_id not in cat.get("pieces", {}):
            raise FileNotFoundError(f"Published map piece '{piece_id}' not found in catalog.")

        piece_data = copy.deepcopy(cat["pieces"][piece_id])
        piece_data["id"] = piece_id

        # Save to drafts
        draft = self.create_draft(piece_id, piece_data)

        # Remove from published catalog
        del cat["pieces"][piece_id]
        self._save_catalog_dict(cat)

        return draft


map_piece_editor_service = MapPieceEditorService()
