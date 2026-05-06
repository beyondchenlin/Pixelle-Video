from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, field_validator

from api.asset_bible_responses import asset_bible_response_payload, build_asset_bible_response
from api.schemas.asset_bible import AssetBiblePayloadResponse, AssetBibleResponse
from api.schemas.storyboard_workbench import validate_public_reference_id

router = APIRouter(tags=["Asset Bible Presets"])


class AssetBiblePresetImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    preset_id: str
    asset_bible_id: str | None = None
    conflict_policy: Literal["fail"] = "fail"

    @field_validator("workspace_id", "preset_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_public_reference_id(info.field_name, value)

    @field_validator("asset_bible_id")
    @classmethod
    def validate_optional_asset_bible_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_public_reference_id("asset_bible_id", value)


class AssetBiblePresetSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preset_id: str
    revision: str
    source: str
    display_name: str
    description: str
    tags: list[str]
    preview_asset_path: str | None = None


class AssetBiblePresetListResponse(BaseModel):
    items: list[AssetBiblePresetSummaryResponse]


class AssetBiblePresetDetailResponse(AssetBiblePresetSummaryResponse):
    asset_bible: AssetBiblePayloadResponse


class AssetBiblePresetEnvelopeResponse(BaseModel):
    preset: AssetBiblePresetDetailResponse


@router.get("/presets/asset-bibles", response_model=AssetBiblePresetListResponse)
async def list_asset_bible_presets(request: Request) -> AssetBiblePresetListResponse:
    registry = _get_asset_bible_preset_registry(request)
    return AssetBiblePresetListResponse(items=registry.list_summaries())


@router.get(
    "/presets/asset-bibles/{preset_id}",
    response_model=AssetBiblePresetEnvelopeResponse,
)
async def load_asset_bible_preset(
    preset_id: str,
    request: Request,
) -> AssetBiblePresetEnvelopeResponse:
    preset_id = _validate_public_id("preset_id", preset_id)
    registry = _get_asset_bible_preset_registry(request)
    try:
        preset = registry.get_preset(preset_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    summary = preset.to_summary_dict()
    return AssetBiblePresetEnvelopeResponse(
        preset=AssetBiblePresetDetailResponse(
            **summary,
            asset_bible=asset_bible_response_payload(
                preset.asset_bible.to_dict(),
                project_id=preset.asset_bible.project_id,
                asset_bible_id=preset.asset_bible.asset_bible_id,
            ),
        )
    )


@router.post(
    "/projects/{project_id}/asset-bible/import-from-preset",
    response_model=AssetBibleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_asset_bible_preset(
    project_id: str,
    payload: AssetBiblePresetImportRequest,
    request: Request,
) -> AssetBibleResponse:
    project_id = _validate_public_id("project_id", project_id)
    repository = _get_asset_bible_repository(request)
    registry = _get_asset_bible_preset_registry(request)
    try:
        asset_bible = registry.build_project_asset_bible(
            preset_id=payload.preset_id,
            workspace_id=payload.workspace_id,
            project_id=project_id,
            asset_bible_id=payload.asset_bible_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    saved = await repository.save_asset_bible(payload.workspace_id, asset_bible.to_dict())
    return build_asset_bible_response(
        asset_bible=asset_bible_response_payload(
            saved,
            project_id=project_id,
            asset_bible_id=asset_bible.asset_bible_id,
        )
    )


def _get_asset_bible_repository(request: Request):
    repository = getattr(request.app.state, "asset_bible_repository", None)
    if repository is None:
        raise HTTPException(status_code=503, detail="asset bible repository is not configured")
    return repository


def _get_asset_bible_preset_registry(request: Request):
    registry = getattr(request.app.state, "asset_bible_preset_registry", None)
    if registry is None:
        raise HTTPException(status_code=503, detail="asset bible preset registry is not configured")
    return registry


def _validate_public_id(field_name: str, value: str) -> str:
    try:
        return validate_public_reference_id(field_name, value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


__all__ = ["router"]
