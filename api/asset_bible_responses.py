from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError

from api.schemas.asset_bible import AssetBibleResponse
from pixelle_video.models.asset_bible import AssetBible


def build_asset_bible_response(*, asset_bible: dict[str, Any]) -> AssetBibleResponse:
    try:
        return AssetBibleResponse(asset_bible=asset_bible)
    except ValidationError as exc:
        raise HTTPException(
            status_code=502,
            detail=safe_response_validation_detail(
                exc,
                response_name="asset bible response",
            ),
        ) from exc


def asset_bible_response_payload(
    payload: Mapping[str, Any],
    *,
    project_id: str,
    asset_bible_id: str | None = None,
) -> dict[str, Any]:
    asset_bible = AssetBible.from_dict(payload)
    if asset_bible.project_id != project_id:
        raise HTTPException(status_code=502, detail="asset bible project does not match request")
    if asset_bible_id is not None and asset_bible.asset_bible_id != asset_bible_id:
        raise HTTPException(status_code=502, detail="asset bible ID does not match request")
    return public_asset_bible_payload(asset_bible.to_dict())


def public_asset_bible_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    public_payload = dict(payload)
    public_payload["ip_profiles"] = [
        public_ip_profile_payload(profile)
        for profile in public_payload.get("ip_profiles") or []
        if isinstance(profile, Mapping)
    ]
    return public_payload


def public_ip_profile_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    public_payload = dict(payload)
    public_payload.pop("forbidden_elements", None)
    return public_payload


def safe_response_validation_detail(
    exc: ValidationError,
    *,
    response_name: str,
    default_field_path: str | None = None,
) -> str:
    first_error = exc.errors()[0] if exc.errors() else {}
    location = first_error.get("loc") or ()
    field_path = ".".join(str(item) for item in location) or default_field_path or "response"
    reason = _safe_response_error_reason(first_error.get("ctx"))
    if reason:
        return f"{response_name} is invalid: {field_path} ({reason})"
    return f"{response_name} is invalid: {field_path}"


def _safe_response_error_reason(context: object) -> str | None:
    if not isinstance(context, Mapping):
        return None
    error = context.get("error")
    if not isinstance(error, ValueError):
        return None
    message = str(error)
    if _looks_safe_response_validation_message(message):
        return message
    return None


def _looks_safe_response_validation_message(message: str) -> bool:
    return "\\" not in message and "/" not in message and ":" not in message


__all__ = [
    "asset_bible_response_payload",
    "build_asset_bible_response",
    "public_asset_bible_payload",
    "public_ip_profile_payload",
    "safe_response_validation_detail",
]
