from __future__ import annotations

from typing import Any

import httpx

from api.schemas.storyboard_workbench import validate_public_reference_id


def build_stale_target_endpoint(
    *,
    api_base_url: str,
    project_id: str,
    target_type: str,
    target_id: str,
) -> str:
    project_id = _validate_id("project_id", project_id)
    target_type = _validate_id("target_type", target_type)
    target_id = _validate_id("target_id", target_id)
    return (
        f"{api_base_url.rstrip('/')}/projects/{project_id}/stale/"
        f"targets/{target_type}/{target_id}"
    )


def build_stale_downstream_endpoint(
    *,
    api_base_url: str,
    project_id: str,
    upstream_type: str,
    upstream_id: str,
) -> str:
    project_id = _validate_id("project_id", project_id)
    upstream_type = _validate_id("upstream_type", upstream_type)
    upstream_id = _validate_id("upstream_id", upstream_id)
    return (
        f"{api_base_url.rstrip('/')}/projects/{project_id}/stale/"
        f"upstream/{upstream_type}/{upstream_id}/downstream"
    )


def get_stale_target_summary(
    *,
    api_base_url: str,
    project_id: str,
    workspace_id: str,
    target_type: str,
    target_id: str,
    timeout: float = 30.0,
) -> dict[str, Any]:
    endpoint = build_stale_target_endpoint(
        api_base_url=api_base_url,
        project_id=project_id,
        target_type=target_type,
        target_id=target_id,
    )
    params = {"workspace_id": _validate_id("workspace_id", workspace_id)}

    response = httpx.get(endpoint, params=params, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    _validate_target_response(data)
    return data


def get_stale_downstream(
    *,
    api_base_url: str,
    project_id: str,
    workspace_id: str,
    upstream_type: str,
    upstream_id: str,
    timeout: float = 30.0,
) -> dict[str, Any]:
    endpoint = build_stale_downstream_endpoint(
        api_base_url=api_base_url,
        project_id=project_id,
        upstream_type=upstream_type,
        upstream_id=upstream_id,
    )
    params = {"workspace_id": _validate_id("workspace_id", workspace_id)}

    response = httpx.get(endpoint, params=params, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    _validate_downstream_response(data)
    return data


def _validate_target_response(data: Any) -> None:
    if not isinstance(data, dict):
        raise ValueError("stale target response must be a JSON object")
    _require_bool(data, "success")
    _require_optional_text(data, "message")
    summary = data.get("stale_summary")
    if not isinstance(summary, dict):
        raise ValueError("stale target response must include stale_summary")

    for field_name in ("workspace_id", "project_id", "target_type", "target_id"):
        _require_text(summary, f"stale_summary.{field_name}")
    _require_bool(summary, "stale_summary.is_stale", source_key="is_stale")
    for field_name in ("stale_marks", "upstream_refs", "primary_reasons"):
        if not isinstance(summary.get(field_name), list):
            raise ValueError(f"stale_summary.{field_name} must be a list")


def _validate_downstream_response(data: Any) -> None:
    if not isinstance(data, dict):
        raise ValueError("stale downstream response must be a JSON object")
    _require_bool(data, "success")
    _require_optional_text(data, "message")
    downstream = data.get("downstream")
    if not isinstance(downstream, dict):
        raise ValueError("stale downstream response must include downstream")

    for field_name in ("workspace_id", "project_id", "upstream_type", "upstream_id"):
        _require_text(downstream, f"downstream.{field_name}")
    for field_name in ("dependency_edges", "downstream_refs"):
        if not isinstance(downstream.get(field_name), list):
            raise ValueError(f"downstream.{field_name} must be a list")


def _require_bool(data: dict[str, Any], field_name: str, *, source_key: str | None = None) -> None:
    key = source_key or field_name
    if not isinstance(data.get(key), bool):
        raise ValueError(f"{field_name} must be a boolean")


def _require_text(data: dict[str, Any], field_name: str) -> None:
    key = field_name.rsplit(".", 1)[-1]
    if not isinstance(data.get(key), str) or not data[key].strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _require_optional_text(data: dict[str, Any], field_name: str) -> None:
    value = data.get(field_name)
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")


def _validate_id(field_name: str, value: str) -> str:
    return validate_public_reference_id(field_name, value)
