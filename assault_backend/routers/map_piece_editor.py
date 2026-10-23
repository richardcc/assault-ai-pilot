"""
assault_backend/routers/map_piece_editor.py

FastAPI Router for Map Piece Editor:
- Lists published and draft map pieces
- Retrieves individual map piece definitions
- Creates, updates, deletes drafts
- Clones published pieces or drafts
- Validates map piece schemas
- Publishes draft pieces directly into assets/catalogs/map_piece_catalog.json
- Unpublishes pieces back to drafts
"""

from typing import Any, Dict
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from assault_backend.services.map_piece_editor_service import (
    map_piece_editor_service,
    VALID_TERRAINS,
    VALID_EDGE_FEATURES,
)

router = APIRouter(prefix="/api/editor/map_pieces", tags=["map-piece-editor"])


class CreateDraftRequest(BaseModel):
    id: str
    description: str = ""
    shape: list[int] = [9, 8]
    hexes: list[Dict[str, Any]] = []
    hex_edges: list[Dict[str, Any]] = []


class UpdateDraftRequest(BaseModel):
    data: Dict[str, Any]


class CloneRequest(BaseModel):
    new_id: str


@router.get("")
def list_map_pieces():
    pieces = map_piece_editor_service.list_pieces()
    return {"ok": True, "count": len(pieces), "pieces": pieces}


@router.get("/constants")
def get_constants():
    return {
        "ok": True,
        "valid_terrains": sorted(list(VALID_TERRAINS)),
        "valid_edge_features": sorted(list(VALID_EDGE_FEATURES)),
    }


@router.get("/{piece_id}")
def get_map_piece(piece_id: str, is_draft: bool | None = None):
    p = map_piece_editor_service.get_piece(piece_id, is_draft=is_draft)
    if not p:
        raise HTTPException(status_code=404, detail=f"Map piece '{piece_id}' not found.")
    return {"ok": True, "piece": p}


@router.post("/draft")
def create_draft(req: CreateDraftRequest):
    data = req.model_dump()
    pid = data.pop("id")
    created = map_piece_editor_service.create_draft(pid, data)
    return {"ok": True, "piece": created}


@router.put("/draft/{piece_id}")
def update_draft(piece_id: str, req: UpdateDraftRequest):
    updated = map_piece_editor_service.update_draft(piece_id, req.data)
    return {"ok": True, "piece": updated}


@router.delete("/draft/{piece_id}")
def delete_draft(piece_id: str):
    deleted = map_piece_editor_service.delete_draft(piece_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Draft piece '{piece_id}' not found.")
    return {"ok": True, "message": f"Draft piece '{piece_id}' deleted."}


@router.post("/draft/{piece_id}/clone")
def clone_piece(piece_id: str, req: CloneRequest):
    try:
        cloned = map_piece_editor_service.clone_piece(piece_id, req.new_id, from_draft=True)
        return {"ok": True, "piece": cloned}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{piece_id}/clone")
def clone_published_piece(piece_id: str, req: CloneRequest):
    try:
        cloned = map_piece_editor_service.clone_piece(piece_id, req.new_id, from_draft=False)
        return {"ok": True, "piece": cloned}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/validate")
def validate_piece(req: UpdateDraftRequest):
    valid, errors = map_piece_editor_service.validate_piece(req.data)
    return {"ok": True, "valid": valid, "errors": errors}


@router.post("/draft/{piece_id}/publish")
def publish_draft(piece_id: str):
    try:
        pub = map_piece_editor_service.publish_piece(piece_id)
        return {"ok": True, "piece": pub}
    except FileNotFoundError as fnf:
        raise HTTPException(status_code=404, detail=str(fnf))
    except ValueError as ve:
        raise HTTPException(status_code=422, detail=str(ve))


@router.post("/{piece_id}/unpublish")
def unpublish_piece(piece_id: str):
    try:
        draft = map_piece_editor_service.unpublish_piece(piece_id)
        return {"ok": True, "piece": draft}
    except FileNotFoundError as fnf:
        raise HTTPException(status_code=404, detail=str(fnf))
