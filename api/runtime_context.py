from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from api.config import api_config
from pixelle_video.utils.configured_path import resolve_configured_path
from pixelle_video.utils.os_util import get_pixelle_video_root_path
from pixelle_video.utils.project_identity import (
    build_path_id,
    build_project_root_id,
    resolve_project_root,
)

API_CHECKOUT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class ApiRuntimeContext:
    """Immutable filesystem and identity contract for one API process."""

    checkout_root: Path
    project_root: Path
    output_root: Path
    checkout_root_id: str
    project_root_id: str
    output_root_id: str


def build_api_runtime_context(
    project_root: str | Path | None = None,
    *,
    checkout_root: str | Path | None = None,
    output_root: str | Path | None = None,
) -> ApiRuntimeContext:
    resolved_checkout_root = resolve_project_root(checkout_root or API_CHECKOUT_ROOT)
    resolved_root = resolve_project_root(project_root or get_pixelle_video_root_path())
    resolved_output_root = resolve_configured_path(
        output_root if output_root is not None else api_config.artifact_base_path,
        project_root=resolved_root,
        setting_name="PIXELLE_ARTIFACT_BASE_PATH",
    )
    return ApiRuntimeContext(
        checkout_root=resolved_checkout_root,
        project_root=resolved_root,
        output_root=resolved_output_root,
        checkout_root_id=build_project_root_id(resolved_checkout_root),
        project_root_id=build_project_root_id(resolved_root),
        output_root_id=build_path_id(resolved_output_root),
    )


_API_RUNTIME_CONTEXT = build_api_runtime_context()


def get_api_runtime_context() -> ApiRuntimeContext:
    """Return the process-scoped API runtime context."""
    return _API_RUNTIME_CONTEXT


def resolve_api_configured_path(
    configured_path: str | Path,
    *,
    setting_name: str,
) -> Path:
    """Resolve an API path setting against the process-scoped project root."""
    return resolve_configured_path(
        configured_path,
        project_root=get_api_runtime_context().project_root,
        setting_name=setting_name,
    )


__all__ = [
    "ApiRuntimeContext",
    "build_api_runtime_context",
    "get_api_runtime_context",
    "resolve_api_configured_path",
]
