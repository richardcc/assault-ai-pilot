# assault_model/map/map_piece_loader.py

import json
from pathlib import Path
from typing import Dict, List, Tuple

from assault_model.map.map_piece import MapPieceDefinition
from assault_model.map.hex import Hex
from assault_model.map.terrain import Terrain
from assault_model.map.hex_state import HexState
from assault_model.map.hex_edge_feature import HexEdgeFeature


class MapPieceCatalogError(Exception):
    """Raised when the map piece catalog is invalid or cannot be loaded."""


def load_map_piece_catalog(path: Path) -> Dict[str, MapPieceDefinition]:
    """
    Load a map piece catalog from a JSON file and convert it into
    MapPieceDefinition objects.

    This loader is responsible only for reading static map data.
    No game rules or logic are applied here.
    """
    if not path.exists():
        raise MapPieceCatalogError(f"Map piece catalog not found: {path}")

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise MapPieceCatalogError(
            f"Failed to read map piece catalog: {exc}"
        ) from exc

    if "pieces" not in raw:
        raise MapPieceCatalogError("Invalid catalog format: missing 'pieces' key")

    catalog: Dict[str, MapPieceDefinition] = {}

    for piece_id, data in raw["pieces"].items():
        try:
            # -------------------------------------------------
            # Base hex loading (FIXED: supports hexes by rows)
            # -------------------------------------------------
            hexes: List[Hex] = []

            for row in data.get("hexes", []):
                for h in row:
                    try:
                        terrain = Terrain(h["terrain"])
                    except ValueError as exc:
                        raise MapPieceCatalogError(
                            f"Invalid terrain '{h['terrain']}' in piece '{piece_id}'"
                        ) from exc

                    hexes.append(
                        Hex(
                            q=int(h["q"]),
                            r=int(h["r"]),
                            terrain=terrain,
                        )
                    )

            # -------------------------------------------------
            # Optional hex state loading
            # -------------------------------------------------
            hex_states: Dict[Tuple[int, int], HexState] = {}

            for key, state_data in data.get("hex_states", {}).items():
                q, r = map(int, key.split(","))

                state = HexState(hex_=None)
                state.building = state_data.get("building", False)
                state.woods = state_data.get("woods", False)

                hex_states[(q, r)] = state

            # -------------------------------------------------
            # Optional hex edge feature loading
            # -------------------------------------------------
            hex_edges: Dict[
                Tuple[Tuple[int, int], Tuple[int, int]], HexEdgeFeature
            ] = {}

            for edge in data.get("hex_edges", []):
                a = tuple(map(int, edge["from"].split(",")))
                b = tuple(map(int, edge["to"].split(",")))

                try:
                    feature = HexEdgeFeature(edge["feature"])
                except ValueError as exc:
                    raise MapPieceCatalogError(
                        f"Invalid edge feature '{edge['feature']}' in piece '{piece_id}'"
                    ) from exc

                hex_edges[(a, b)] = feature

            # -------------------------------------------------
            # MapPieceDefinition construction
            # -------------------------------------------------
            piece = MapPieceDefinition(
                piece_id=piece_id,
                description=data.get("description", ""),
                hexes=hexes,
                hex_states=hex_states,
                hex_edges=hex_edges,
            )

        except Exception as exc:
            raise MapPieceCatalogError(
                f"Invalid map piece entry '{piece_id}': {exc}"
            ) from exc

        catalog[piece_id] = piece

    return catalog