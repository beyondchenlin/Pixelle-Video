from typing import Any, Mapping, MutableMapping, Optional

from pixelle_video.render_backend import DEFAULT_RENDER_BACKEND, SUPPORTED_RENDER_BACKENDS


def get_render_backend_default(configured_backend: Any) -> str:
    """Return a safe UI default for render backend selection."""
    if configured_backend in SUPPORTED_RENDER_BACKENDS:
        return str(configured_backend)
    return DEFAULT_RENDER_BACKEND


def copy_render_backend(source: Mapping[str, Any], target: MutableMapping[str, Any]) -> None:
    """Copy a supported render backend from one param dict to another."""
    render_backend = source.get("render_backend")
    if render_backend in SUPPORTED_RENDER_BACKENDS:
        target["render_backend"] = str(render_backend)


def get_task_render_backend(metadata: Mapping[str, Any]) -> Optional[str]:
    """Read the task backend from metadata, preferring explicit input over derived config."""
    input_params = metadata.get("input") or {}
    config_params = metadata.get("config") or {}

    for candidate in (
        input_params.get("render_backend_effective"),
        config_params.get("render_backend_effective"),
        input_params.get("render_backend"),
        config_params.get("render_backend"),
    ):
        if candidate:
            return str(candidate)
    return None


def get_task_text_layer_summary(metadata: Mapping[str, Any]) -> Optional[dict[str, Any]]:
    """Read the text layer summary from completed task metadata."""
    summary = _get_result_summary(metadata, "text_layer_summary")
    if summary is None:
        return None

    try:
        cue_count = int(summary.get("cue_count") or 0)
    except (TypeError, ValueError):
        cue_count = 0
    try:
        native_hint_count = int(summary.get("native_prompt_hint_count") or 0)
    except (TypeError, ValueError):
        native_hint_count = 0

    return {
        "renderer": str(summary.get("renderer") or "N/A"),
        "cue_count": cue_count,
        "native_prompt_hint_count": native_hint_count,
    }


def get_task_caption_rendering_summary(
    metadata: Mapping[str, Any],
) -> Optional[dict[str, Any]]:
    """Read the normal caption rendering summary from completed task metadata."""
    summary = _get_result_summary(metadata, "caption_rendering_summary")
    if summary is None:
        return None

    try:
        cue_count = int(summary.get("caption_cue_count") or 0)
    except (TypeError, ValueError):
        cue_count = 0

    return {
        "enabled": bool(summary.get("enabled")),
        "caption_cue_count": cue_count,
        "style_profile_id": str(summary.get("style_profile_id") or "N/A"),
        "renderer_targets": _format_targets(summary.get("renderer_targets")),
    }


def get_task_image_text_policy_summary(
    metadata: Mapping[str, Any],
) -> Optional[dict[str, Any]]:
    """Read the image text policy summary from completed task metadata."""
    summary = _get_result_summary(metadata, "image_text_policy_summary")
    if summary is None:
        return None

    return {
        "status": str(summary.get("status") or "N/A"),
        "suppress_embedded_text": bool(summary.get("suppress_embedded_text")),
    }


def format_task_boolean(value: Any, *, true_label: str, false_label: str) -> str:
    """Format a task metadata boolean with caller-provided localized labels."""
    return true_label if bool(value) else false_label


def _get_result_summary(
    metadata: Mapping[str, Any],
    key: str,
) -> Optional[Mapping[str, Any]]:
    result_params = metadata.get("result") or {}
    summary = result_params.get(key)
    if not isinstance(summary, Mapping):
        return None
    return summary


def _format_targets(targets: Any) -> str:
    if isinstance(targets, str):
        return targets
    if isinstance(targets, list):
        return ", ".join(str(target) for target in targets)
    return "N/A"
