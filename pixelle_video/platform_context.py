from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

DEFAULT_API_PORT = 8001
DEFAULT_API_BASE_URL = (
    os.getenv("PIXELLE_API_BASE_URL")
    or f"http://localhost:{os.getenv('PIXELLE_API_PORT', str(DEFAULT_API_PORT))}/api"
).rstrip("/")
DEFAULT_PROJECT_ID = "project_1"
DEFAULT_WORKSPACE_ID = "workspace_1"


def first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def first_explicit_text(explicit_value: Any, *fallback_values: Any) -> str:
    if explicit_value is not None:
        return str(explicit_value).strip()
    return first_text(*fallback_values)


def resolve_workspace_id(
    source: Mapping[str, Any] | None = None,
    *,
    default: str = DEFAULT_WORKSPACE_ID,
) -> str:
    return first_text((source or {}).get("workspace_id"), default)


def resolve_project_id(
    source: Mapping[str, Any] | None = None,
    *,
    default: str = DEFAULT_PROJECT_ID,
) -> str:
    return first_text((source or {}).get("project_id"), default)


def resolve_api_base_url(
    source: Mapping[str, Any] | None = None,
    *,
    default: str = DEFAULT_API_BASE_URL,
) -> str:
    return first_text((source or {}).get("api_base_url"), default).rstrip("/")


def resolve_business_context(
    *sources: Mapping[str, Any] | None,
) -> dict[str, str]:
    merged: dict[str, Any] = {}
    for source in sources:
        if source is not None:
            merged.update(source)
    return {
        "workspace_id": resolve_workspace_id(merged),
        "project_id": resolve_project_id(merged),
    }


__all__ = [
    "DEFAULT_API_BASE_URL",
    "DEFAULT_API_PORT",
    "DEFAULT_PROJECT_ID",
    "DEFAULT_WORKSPACE_ID",
    "first_explicit_text",
    "first_text",
    "resolve_api_base_url",
    "resolve_business_context",
    "resolve_project_id",
    "resolve_workspace_id",
]
