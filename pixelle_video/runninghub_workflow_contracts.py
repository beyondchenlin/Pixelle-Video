from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pixelle_video.utils.os_util import get_root_path

RUNNINGHUB_SOURCE = "runninghub"
MEDIA_WORKFLOW_DOMAINS = frozenset({"image", "video"})
ANALYSIS_WORKFLOW_DOMAINS = frozenset(
    {"analysis", "image_analysis", "video_analysis"}
)
RUNNINGHUB_NON_MEDIA_DOMAINS = frozenset({"tts", "image_analysis", "video_analysis"})
RUNNINGHUB_ALLOWED_DOMAINS = MEDIA_WORKFLOW_DOMAINS | RUNNINGHUB_NON_MEDIA_DOMAINS

_ANALYSIS_IDENTIFIER_MARKERS = (
    "analyse_",
    "analyze_",
    "analysis_",
    "image_analysis",
    "video_analysis",
    "image_understanding",
    "video_understanding",
)


def runninghub_registry_root() -> Path:
    return Path(get_root_path("workflows", RUNNINGHUB_SOURCE)).resolve()


def runninghub_descriptor_path(name: str) -> Path:
    descriptor_name = Path(str(name)).name
    if not descriptor_name:
        raise ValueError("RunningHub workflow descriptor name is required")
    return runninghub_registry_root() / descriptor_name


def validate_runninghub_descriptor_registry_boundary(workflow_path: str | Path) -> Path:
    resolved_path = Path(workflow_path).resolve()
    registry_root = runninghub_registry_root()
    try:
        resolved_path.relative_to(registry_root)
    except ValueError as exc:
        raise ValueError(
            "RunningHub workflow descriptors must be loaded from the packaged "
            f"{registry_root} registry; user override paths are not trusted "
            "workflow contracts"
        ) from exc
    return resolved_path


def load_runninghub_descriptor(workflow_path: str | Path) -> dict[str, Any]:
    path = validate_runninghub_descriptor_registry_boundary(workflow_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"RunningHub workflow descriptor must be a JSON object: {path}")
    return validate_runninghub_descriptor_contract(path, payload)


def validate_runninghub_descriptor_contract(
    workflow_path: str | Path,
    descriptor: Mapping[str, Any],
) -> dict[str, Any]:
    path = validate_runninghub_descriptor_registry_boundary(workflow_path)
    source = str(descriptor.get("source") or "").strip().lower()
    if source != RUNNINGHUB_SOURCE:
        raise ValueError(f"RunningHub workflow descriptor must declare source: {path}")

    workflow_id = str(descriptor.get("workflow_id") or "").strip()
    if not workflow_id:
        raise ValueError(f"RunningHub workflow missing workflow_id: {path}")

    media_type = _normalized_domain(descriptor.get("media_type"))
    workflow_domain = _normalized_domain(descriptor.get("workflow_domain"))
    service_domain = _normalized_domain(descriptor.get("service_domain"))
    declared_domains = {
        domain for domain in (workflow_domain, service_domain) if domain is not None
    }

    if media_type is not None:
        if _descriptor_identifier_looks_like_analysis(path):
            raise ValueError(
                f"RunningHub analysis-looking workflow cannot declare media_type: {path}"
            )
        if media_type not in MEDIA_WORKFLOW_DOMAINS:
            raise ValueError(
                f"RunningHub workflow media_type must be image or video: {path}"
            )
        if any(domain != media_type for domain in declared_domains):
            raise ValueError(
                f"RunningHub workflow has conflicting media contract metadata: {path}"
            )
        return {
            "source": RUNNINGHUB_SOURCE,
            "workflow_id": workflow_id,
            "media_type": media_type,
            **({"workflow_domain": workflow_domain} if workflow_domain else {}),
            **({"service_domain": service_domain} if service_domain else {}),
        }

    media_domains = declared_domains & MEDIA_WORKFLOW_DOMAINS
    if media_domains:
        raise ValueError(
            f"RunningHub media workflow requires explicit media_type: {path}"
        )
    if not declared_domains:
        raise ValueError(
            f"RunningHub workflow descriptor requires an explicit domain contract: {path}"
        )
    unknown_domains = declared_domains - RUNNINGHUB_ALLOWED_DOMAINS
    if unknown_domains:
        raise ValueError(
            f"RunningHub workflow descriptor has unsupported domain metadata: {path}"
        )
    if declared_domains & ANALYSIS_WORKFLOW_DOMAINS:
        if workflow_domain not in {"image_analysis", "video_analysis"}:
            raise ValueError(
                f"RunningHub analysis workflow requires explicit workflow_domain: {path}"
            )
        if service_domain not in {"image_analysis", "video_analysis"}:
            raise ValueError(
                f"RunningHub analysis workflow requires explicit service_domain: {path}"
            )
        if workflow_domain != service_domain:
            raise ValueError(
                f"RunningHub analysis workflow domain metadata does not match: {path}"
            )

    return {
        "source": RUNNINGHUB_SOURCE,
        "workflow_id": workflow_id,
        **({"workflow_domain": workflow_domain} if workflow_domain else {}),
        **({"service_domain": service_domain} if service_domain else {}),
    }


def runninghub_descriptor_domains(
    descriptor: Mapping[str, Any],
) -> tuple[str | None, str | None]:
    return (
        _normalized_domain(descriptor.get("workflow_domain")),
        _normalized_domain(descriptor.get("service_domain")),
    )


def _normalized_domain(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    return normalized or None


def _descriptor_identifier_looks_like_analysis(workflow_path: Path) -> bool:
    normalized = str(workflow_path).replace("\\", "/").strip().lower()
    filename = workflow_path.name.lower()
    return any(
        filename.startswith(marker) or f"/{marker}" in normalized
        for marker in _ANALYSIS_IDENTIFIER_MARKERS
    )
