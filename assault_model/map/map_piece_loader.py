import json
from pathlib import Path
from typing import Dict, List, Tuple

from assault_model.map.map_piece import MapPieceDefinition
from assault_model.map.hex import Hex
from assault_model.map.terrain import Terrain
from assault_model.map.hex_edge_feature import HexEdgeFeature


class MapPieceCatalogError(Exception):
    pass


def load_map_piece_catalog(path: Path) -> Dict[str, MapPieceDefinition]:

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

            # ✅ SHAPE
            if "shape" not in data:
                raise MapPieceCatalogError(
                    f"Piece '{piece_id}' missing 'shape'"
                )

            width, height = data["shape"]

            # -------------------------------------------------
            # ✅ GENERATE FULL GRID (default CLEAR)
            # -------------------------------------------------
            hex_map: Dict[Tuple[int, int], Hex] = {}

            for q in range(width):
                for r in range(height):
                    hex_map[(q, r)] = Hex(q=q, r=r, terrain=Terrain.CLEAR)

            # -------------------------------------------------
            # ✅ APPLY EXCEPTIONS (flat list)
            # -------------------------------------------------
            for h in data.get("hexes", []):
                q = int(h["q"])
                r = int(h["r"])

                if (q, r) not in hex_map:
                    raise MapPieceCatalogError(
                        f"Hex ({q},{r}) outside shape in piece '{piece_id}'"
                    )

                terrain_name = h.get("terrain", "clear")

                try:
                    terrain = Terrain(terrain_name)
                except ValueError as exc:
                    raise MapPieceCatalogError(
                        f"Invalid terrain '{terrain_name}' in piece '{piece_id}'"
                    ) from exc

                hex_map[(q, r)] = Hex(q=q, r=r, terrain=terrain)

            hexes: List[Hex] = list(hex_map.values())

            # -------------------------------------------------
            # EDGE FEATURES
            # -------------------------------------------------
            hex_edges: Dict[
                Tuple[Tuple[int, int], Tuple[int, int]],
                HexEdgeFeature,
            ] = {}

            for edge in data.get("hex_edges", []):
                a = tuple(map(int, edge["from"].split(",")))
                b = tuple(map(int, edge["to"].split(",")))

                feature = HexEdgeFeature(edge["feature"])
                hex_edges[(a, b)] = feature

            # -------------------------------------------------
            # BUILD PIECE
            # -------------------------------------------------
            piece = MapPieceDefinition(
                piece_id=piece_id,
                description=data.get("description", ""),
                shape=(width, height),
                hexes=hexes,
                hex_edges=hex_edges,
            )

        except Exception as exc:
            raise MapPieceCatalogError(
                f"Invalid map piece entry '{piece_id}': {exc}"
            ) from exc

        catalog[piece_id] = piece

    return catalog