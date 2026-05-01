from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from api.schemas.storyboard_workbench import validate_public_reference_id


def build_storyboard_frame_images_endpoint(
    *,
    api_base_url: str,
    storyboard_id: str,
    frame_id: str,
) -> str:
    storyboard_id = _validate_public_id("storyboard_id", storyboard_id)
    frame_id = _validate_public_id("frame_id", frame_id)
    return (
        f"{api_base_url.rstrip('/')}/storyboards/{storyboard_id}/"
        f"frames/{frame_id}/images"
    )


def build_storyboard_frame_select_endpoint(
    *,
    api_base_url: str,
    storyboard_id: str,
    frame_id: str,
) -> str:
    storyboard_id = _validate_public_id("storyboard_id", storyboard_id)
    frame_id = _validate_public_id("frame_id", frame_id)
    return (
        f"{api_base_url.rstrip('/')}/storyboards/{storyboard_id}/"
        f"frames/{frame_id}/select-image"
    )


def build_storyboard_frame_regenerate_endpoint(
    *,
    api_base_url: str,
    storyboard_id: str,
    frame_id: str,
) -> str:
    storyboard_id = _validate_public_id("storyboard_id", storyboard_id)
    frame_id = _validate_public_id("frame_id", frame_id)
    return (
        f"{api_base_url.rstrip('/')}/storyboards/{storyboard_id}/"
        f"frames/{frame_id}/regenerate-image"
    )


def list_storyboard_image_candidates(
    *,
    api_base_url: str,
    workspace_id: str,
    storyboard_id: str,
    frame_id: str,
    artifact_id: str,
    timeout: float = 30.0,
) -> dict[str, Any]:
    endpoint = build_storyboard_frame_images_endpoint(
        api_base_url=api_base_url,
        storyboard_id=storyboard_id,
        frame_id=frame_id,
    )
    params = {
        "workspace_id": _validate_public_id("workspace_id", workspace_id),
        "artifact_id": _validate_public_id("artifact_id", artifact_id),
    }
    response = httpx.get(endpoint, params=params, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    _validate_candidate_list_response(
        data,
        workspace_id=params["workspace_id"],
        storyboard_id=_validate_public_id("storyboard_id", storyboard_id),
        frame_id=_validate_public_id("frame_id", frame_id),
        artifact_id=params["artifact_id"],
    )
    return data


def select_storyboard_image_candidate(
    *,
    api_base_url: str,
    workspace_id: str,
    storyboard_id: str,
    frame_id: str,
    artifact_id: str,
    version_id: str,
    actor_id: str | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    endpoint = build_storyboard_frame_select_endpoint(
        api_base_url=api_base_url,
        storyboard_id=storyboard_id,
        frame_id=frame_id,
    )
    payload = {
        "workspace_id": _validate_public_id("workspace_id", workspace_id),
        "artifact_id": _validate_public_id("artifact_id", artifact_id),
        "version_id": _validate_public_id("version_id", version_id),
    }
    normalized_actor_id = _optional_public_id("actor_id", actor_id)
    if normalized_actor_id:
        payload["actor_id"] = normalized_actor_id

    response = httpx.post(endpoint, json=payload, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    _validate_action_response(data, response_name="selection response")
    return data


def regenerate_storyboard_frame_image(
    *,
    api_base_url: str,
    workspace_id: str,
    storyboard_id: str,
    frame_id: str,
    artifact_id: str,
    timeout: float = 30.0,
) -> dict[str, Any]:
    endpoint = build_storyboard_frame_regenerate_endpoint(
        api_base_url=api_base_url,
        storyboard_id=storyboard_id,
        frame_id=frame_id,
    )
    payload = {
        "workspace_id": _validate_public_id("workspace_id", workspace_id),
        "artifact_id": _validate_public_id("artifact_id", artifact_id),
    }

    response = httpx.post(endpoint, json=payload, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    _validate_action_response(data, response_name="regeneration response")
    return data


def _validate_candidate_list_response(
    data: Any,
    *,
    workspace_id: str,
    storyboard_id: str,
    frame_id: str,
    artifact_id: str,
) -> None:
    if not isinstance(data, dict):
        raise ValueError("candidate list response must be a JSON object")
    for field_name, expected in (
        ("workspace_id", workspace_id),
        ("storyboard_id", storyboard_id),
        ("frame_id", frame_id),
        ("artifact_id", artifact_id),
    ):
        if data.get(field_name) != expected:
            raise ValueError(f"candidate list {field_name} does not match request")
    candidates = data.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("candidate list response must include candidates")
    for index, candidate in enumerate(candidates):
        _validate_candidate(candidate, index=index, frame_id=frame_id, artifact_id=artifact_id)


def _validate_candidate(
    candidate: Any,
    *,
    index: int,
    frame_id: str,
    artifact_id: str,
) -> None:
    if not isinstance(candidate, dict):
        raise ValueError(f"candidate {index} must be a JSON object")
    for field_name in (
        "artifact_id",
        "version_id",
        "frame_id",
        "prompt_plan_id",
        "status",
    ):
        _validate_public_id(f"candidate {index} {field_name}", candidate.get(field_name))
    if candidate.get("artifact_id") != artifact_id:
        raise ValueError(f"candidate {index} artifact_id does not match request")
    if candidate.get("frame_id") != frame_id:
        raise ValueError(f"candidate {index} frame_id does not match request")

    storage_key = str(candidate.get("storage_key") or "").strip()
    if not storage_key or _is_unsafe_storage_key(storage_key):
        raise ValueError(f"candidate {index} storage_key must be an object-store key")
    url = candidate.get("url")
    if url is not None and not _is_safe_access_url(url):
        raise ValueError(f"candidate {index} url must be a controlled access URL")
    _reject_forbidden_metadata(candidate.get("metadata") or {}, path=f"candidate {index} metadata")


def _validate_action_response(data: Any, *, response_name: str) -> None:
    if not isinstance(data, dict):
        raise ValueError(f"{response_name} must be a JSON object")
    if data.get("success") is not True:
        raise ValueError(f"{response_name} did not succeed")
    _reject_forbidden_metadata(data, path=response_name)


def _reject_forbidden_metadata(value: Any, *, path: str) -> None:
    forbidden_names = {
        "local_path",
        "workflow_path",
        "provider_url",
        "raw_provider_params",
        "raw_request",
        "raw_response",
    }
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = str(key).lower()
            if normalized_key in forbidden_names:
                raise ValueError(f"{path} must not expose {key}")
            _reject_forbidden_metadata(item, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_forbidden_metadata(item, path=f"{path}[{index}]")
    elif isinstance(value, str) and _looks_like_local_path(value):
        raise ValueError(f"{path} must not expose local paths")


def _validate_public_id(field_name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    return validate_public_reference_id(field_name, value)


def _optional_public_id(field_name: str, value: str | None) -> str:
    if value is None:
        return ""
    normalized = value.strip()
    if not normalized:
        return ""
    return _validate_public_id(field_name, normalized)


def _is_unsafe_storage_key(value: str) -> bool:
    parsed = urlparse(value)
    return (
        bool(parsed.scheme)
        or value.startswith("/")
        or value.startswith("\\")
        or value.startswith("~")
        or ".." in value.split("/")
        or _looks_like_local_path(value)
    )


def _is_safe_access_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.strip()
    if _looks_like_local_path(normalized):
        return False
    parsed = urlparse(normalized)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _looks_like_local_path(value: str) -> bool:
    normalized = value.strip()
    return (
        "\\" in normalized
        or normalized.lower().startswith("file:")
        or normalized.startswith("/")
        or normalized.startswith("../")
        or normalized.startswith("~")
        or (len(normalized) >= 3 and normalized[1] == ":" and normalized[2] in {"/", "\\"})
    )


__all__ = [
    "build_storyboard_frame_images_endpoint",
    "build_storyboard_frame_regenerate_endpoint",
    "build_storyboard_frame_select_endpoint",
    "list_storyboard_image_candidates",
    "regenerate_storyboard_frame_image",
    "select_storyboard_image_candidate",
]
