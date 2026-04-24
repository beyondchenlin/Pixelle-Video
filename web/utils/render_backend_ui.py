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
    result_params = metadata.get("result") or {}
    summary = result_params.get("text_layer_summary")
    if not isinstance(summary, Mapping):
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
