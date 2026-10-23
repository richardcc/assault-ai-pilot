"""
assault_backend/routers/scenario_editor.py

REST API endpoints for the Assault Scenario Editor.
Provides scenario draft creation, modification, validation, and publishing.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from assault_backend.services.scenario_editor_service import (
    scenario_editor_service,
    load_unit_catalog_dict,
    load_map_piece_catalog_dict,
    VALID_FORTIFICATIONS,
    VALID_EXPERIENCES,
    VALID_SIDES,
)

router = APIRouter(prefix="/api/editor", tags=["scenario-editor"])


class CreateDraftRequest(BaseModel):
    id: str = Field(..., description="Unique scenario ID for the new draft")
    name: Optional[str] = Field(None, description="Descriptive scenario name")
    clone_from_id: Optional[str] = Field(None, description="Existing scenario ID to clone from")
    data: Optional[Dict[str, Any]] = Field(None, description="Initial scenario payload")


class UpdateDraftRequest(BaseModel):
    data: Dict[str, Any] = Field(..., description="Full updated scenario payload")


class PublishDraftRequest(BaseModel):
    target_id: Optional[str] = Field(None, description="Optional target ID to publish as")


class ValidateRequest(BaseModel):
    data: Dict[str, Any] = Field(..., description="Scenario payload to validate")


@router.get("/scenarios")
def list_scenarios(
    status: Optional[str] = Query(None, description="Filter by status: 'draft', 'published', or None for all")
):
    try:
        scenarios = scenario_editor_service.list_all_scenarios()
        if status:
            scenarios = [s for s in scenarios if s.get("status") == status.lower()]
        return {"ok": True, "count": len(scenarios), "scenarios": scenarios}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scenarios/{scenario_id}")
def get_scenario(scenario_id: str, prefer_draft: bool = True):
    try:
        scenario = scenario_editor_service.get_scenario(scenario_id, prefer_draft=prefer_draft)
        return {"ok": True, "scenario": scenario}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scenarios/draft")
def create_draft(req: CreateDraftRequest):
    try:
        draft = scenario_editor_service.create_draft(
            scenario_id=req.id,
            data=req.data,
            clone_from_id=req.clone_from_id,
        )
        if req.name and not req.clone_from_id:
            draft["name"] = req.name
            draft = scenario_editor_service.update_draft(req.id, draft)
        return {"ok": True, "message": f"Draft '{req.id}' created successfully.", "scenario": draft}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/scenarios/draft/{scenario_id}")
def update_draft(scenario_id: str, req: UpdateDraftRequest):
    try:
        updated = scenario_editor_service.update_draft(scenario_id, req.data)
        return {"ok": True, "message": f"Draft '{scenario_id}' updated successfully.", "scenario": updated}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scenarios/draft/{scenario_id}/publish")
def publish_draft(scenario_id: str, req: Optional[PublishDraftRequest] = None):
    try:
        target_id = req.target_id if req else None
        res = scenario_editor_service.publish_draft(scenario_id, target_id=target_id)
        return {"ok": True, "message": f"Scenario '{res['id']}' published successfully.", **res}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scenarios/unpublish/{scenario_id}")
def unpublish_scenario(scenario_id: str):
    try:
        res = scenario_editor_service.unpublish_scenario(scenario_id)
        return {"ok": True, "message": f"Scenario '{scenario_id}' moved back to draft mode.", **res}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/scenarios/draft/{scenario_id}")
def delete_draft(scenario_id: str):
    try:
        deleted = scenario_editor_service.delete_draft(scenario_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Draft scenario '{scenario_id}' not found.")
        return {"ok": True, "message": f"Draft '{scenario_id}' deleted successfully."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scenarios/validate")
def validate_scenario(req: ValidateRequest):
    try:
        res = scenario_editor_service.validate_scenario(req.data)
        return {"ok": True, **res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/catalogs")
def get_catalogs():
    """
    Returns lookup data for UI dropdowns: units, map pieces, fortification types, sides, etc.
    """
    try:
        unit_cat = load_unit_catalog_dict()
        piece_cat = load_map_piece_catalog_dict()

        units_summary = [
            {
                "key": k,
                "name": v.get("name", k),
                "side": v.get("side", ""),
                "classification": v.get("classification", ""),
                "movement": v.get("movement", 0),
                "max_strength": v.get("max_strength", 4),
                "default_role": v.get("doctrine_profile", {}).get("default_role", "SCREEN"),
                "traits": v.get("traits", []),
            }
            for k, v in sorted(unit_cat.items())
        ]

        pieces_summary = [
            {
                "id": k,
                "name": v.get("name", k),
                "shape": v.get("shape", [9, 8]),
                "hex_count": len(v.get("hexes", [])),
            }
            for k, v in sorted(piece_cat.items())
        ]

        return {
            "ok": True,
            "units": units_summary,
            "map_pieces": pieces_summary,
            "fortifications": sorted(list(VALID_FORTIFICATIONS)),
            "experiences": sorted(list(VALID_EXPERIENCES)),
            "sides": sorted(list(VALID_SIDES)),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
