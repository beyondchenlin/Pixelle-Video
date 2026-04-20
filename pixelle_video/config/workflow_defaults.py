from __future__ import annotations

from typing import Mapping, Optional, Sequence


BUILTIN_DEFAULT_WORKFLOWS = {
    "image": "selfhost/image_z_image_turbo.json",
    "video": "runninghub/video_wan2.1_fusionx.json",
    "tts": "selfhost/tts_edge.json",
}


def normalize_workflow_key(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def get_configured_default_workflow(
    comfyui_config: Mapping[str, object],
    domain: str,
) -> Optional[str]:
    domain_config = comfyui_config.get(domain, {})
    if domain == "tts" and isinstance(domain_config, Mapping):
        nested_comfyui = domain_config.get("comfyui", {})
        if isinstance(nested_comfyui, Mapping):
            nested_value = normalize_workflow_key(nested_comfyui.get("default_workflow"))
            if nested_value:
                return nested_value
    if isinstance(domain_config, Mapping):
        return normalize_workflow_key(domain_config.get("default_workflow"))
    return None


def resolve_default_workflow(
    domain: str,
    available_keys: Sequence[str],
    configured_workflow: Optional[str],
) -> Optional[str]:
    normalized_configured = normalize_workflow_key(configured_workflow)
    if normalized_configured and normalized_configured in available_keys:
        return normalized_configured

    builtin_default = BUILTIN_DEFAULT_WORKFLOWS.get(domain)
    if builtin_default and builtin_default in available_keys:
        return builtin_default

    return available_keys[0] if available_keys else None
