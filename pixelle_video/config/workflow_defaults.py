from __future__ import annotations

from typing import Mapping, Optional, Sequence

DEFAULT_TTS_WORKFLOW = "selfhost/tts_omnivoice_longform_bf16.json"
LEGACY_DEFAULT_TTS_WORKFLOWS = frozenset(
    {
        "selfhost/tts_index2.json",
        "selfhost/tts_index2_8g.json",
        "tts_index2.json",
        "tts_index2_8g.json",
    }
)

BUILTIN_DEFAULT_WORKFLOWS = {
    "image": "selfhost/image_z_image_turbo_gguf.json",
    "video": "runninghub/video_wan2.1_fusionx.json",
    "tts": DEFAULT_TTS_WORKFLOW,
}

WORKFLOW_DOMAIN_PREFIXES = {
    "image": ("image_",),
    "video": ("video_",),
    "tts": ("tts_",),
}


def normalize_workflow_key(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def is_legacy_default_tts_workflow(value: object) -> bool:
    normalized = normalize_workflow_key(value if isinstance(value, str) else None)
    return normalized in LEGACY_DEFAULT_TTS_WORKFLOWS


def upgrade_legacy_default_tts_workflow(value: object) -> object:
    if is_legacy_default_tts_workflow(value):
        return DEFAULT_TTS_WORKFLOW
    return value


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


def infer_workflow_domain(workflow_key: Optional[str]) -> Optional[str]:
    normalized_key = normalize_workflow_key(workflow_key)
    if not normalized_key:
        return None

    workflow_name = normalized_key.rsplit("/", 1)[-1]
    for domain, prefixes in WORKFLOW_DOMAIN_PREFIXES.items():
        if workflow_name.startswith(prefixes):
            return domain

    return None


def is_workflow_compatible(workflow_key: Optional[str], domain: str) -> bool:
    normalized_key = normalize_workflow_key(workflow_key)
    if not normalized_key:
        return False

    if domain not in WORKFLOW_DOMAIN_PREFIXES:
        return True

    return infer_workflow_domain(normalized_key) == domain


def filter_workflow_keys_for_domain(domain: str, available_keys: Sequence[str]) -> list[str]:
    compatible_keys: list[str] = []
    seen_keys: set[str] = set()

    for workflow_key in available_keys:
        normalized_key = normalize_workflow_key(workflow_key)
        if not normalized_key or normalized_key in seen_keys:
            continue

        seen_keys.add(normalized_key)
        if is_workflow_compatible(normalized_key, domain):
            compatible_keys.append(normalized_key)

    return compatible_keys


def resolve_default_workflow(
    domain: str,
    available_keys: Sequence[str],
    configured_workflow: Optional[str],
) -> Optional[str]:
    compatible_keys = filter_workflow_keys_for_domain(domain, available_keys)
    normalized_configured = normalize_workflow_key(configured_workflow)
    if normalized_configured and normalized_configured in compatible_keys:
        return normalized_configured

    builtin_default = BUILTIN_DEFAULT_WORKFLOWS.get(domain)
    if builtin_default and builtin_default in compatible_keys:
        return builtin_default

    return compatible_keys[0] if compatible_keys else None
