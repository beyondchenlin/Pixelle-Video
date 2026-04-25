from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from pixelle_video.models.text_overlay import build_text_rendering_settings
from pixelle_video.services.text_rendering_orchestrator import TextRenderingOrchestrator

TEXT_RENDERING_RESULT_SUMMARY_KEYS = (
    "caption_rendering_summary",
    "text_layer_summary",
    "image_text_policy_summary",
)
TEXT_RENDER_PACKAGE_ARTIFACT_PATH = "text_render_package.json"


def record_text_rendering_contract_summary(
    target: Any,
    *,
    text_rendering: Mapping[str, Any] | None,
    narrations: Sequence[str] = (),
    render_backend: str | None = None,
    frame_count: int | None = None,
    task_id: str | None = None,
    task_dir: str | Path | None = None,
    supported_overlay: bool,
    disabled_reason: str | None,
    image_text_status: str = "not_applicable",
) -> Any:
    result = TextRenderingOrchestrator().build(
        text_rendering=text_rendering,
        narrations=narrations,
        render_backend=render_backend,
        frame_count=frame_count if frame_count is not None else len(narrations),
        task_id=task_id,
    )
    setattr(target, "text_rendering_result", result)
    setattr(target, "text_render_package", result.text_render_package)
    _persist_text_render_package(task_dir, result.text_render_package)

    observability = getattr(target, "observability", None)
    if observability is None:
        observability = {}
        setattr(target, "observability", observability)

    observability["caption_rendering_summary"] = {
        "enabled": bool(result.caption_settings.enabled),
        "caption_cue_count": len(result.text_render_package.caption_cues),
        "style_profile_id": result.caption_settings.style_profile,
        "renderer_targets": sorted(result.caption_settings.renderer_targets),
        "artifacts": {},
        "fallbacks": [],
    }
    observability["text_layer_summary"] = _build_text_layer_summary(
        result,
        supported_overlay=supported_overlay,
        disabled_reason=disabled_reason,
    )
    observability["image_text_policy_summary"] = {
        "status": image_text_status,
        "suppress_embedded_text": bool(
            result.image_text_policy.suppress_embedded_text
        ),
    }
    return result


def build_text_rendering_result_metadata(
    observability: Mapping[str, Any] | None,
    *,
    text_render_package_path: str | None = TEXT_RENDER_PACKAGE_ARTIFACT_PATH,
) -> dict[str, Any]:
    """Build the public metadata.result text rendering fields from observability."""
    source = observability or {}
    result_metadata = {
        key: copy.deepcopy(source.get(key))
        for key in TEXT_RENDERING_RESULT_SUMMARY_KEYS
    }
    if text_render_package_path and any(
        isinstance(source.get(key), Mapping) for key in TEXT_RENDERING_RESULT_SUMMARY_KEYS
    ):
        result_metadata["text_render_package_path"] = text_render_package_path
    return result_metadata


def resolve_overlay_disabled_reason(
    text_rendering: Mapping[str, Any] | None,
    unsupported_reason: str,
) -> str:
    settings = build_text_rendering_settings(text_rendering)
    return unsupported_reason if settings.overlay.enabled else "overlay_disabled"


def _build_text_layer_summary(
    result,
    *,
    supported_overlay: bool,
    disabled_reason: str | None,
) -> dict:
    overlay_enabled = bool(result.settings.overlay.enabled)
    text_layer_enabled = bool(supported_overlay and result.overlay_plan.candidates)
    effective_disabled_reason = None
    if not text_layer_enabled:
        effective_disabled_reason = disabled_reason or (
            "overlay_unsupported" if overlay_enabled else "overlay_disabled"
        )

    summary = {
        "enabled": text_layer_enabled,
        "renderer": "disabled",
        "track_count": 0,
        "cue_count": 0,
        "native_prompt_hint_count": 0,
        "style_profile_ids": [result.overlay_style.id],
        "artifacts": {},
        "fallbacks": [],
        "targets": (
            sorted(result.overlay_policy.enabled_targets) if overlay_enabled else []
        ),
    }
    if effective_disabled_reason:
        summary["disabled_reason"] = effective_disabled_reason
    return summary


def _persist_text_render_package(task_dir: str | Path | None, package) -> None:
    if not task_dir:
        return
    package_path = Path(task_dir) / TEXT_RENDER_PACKAGE_ARTIFACT_PATH
    package_path.parent.mkdir(parents=True, exist_ok=True)
    package_path.write_text(
        json.dumps(package.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
