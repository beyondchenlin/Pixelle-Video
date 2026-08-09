from __future__ import annotations

import httpx

from pixelle_video.platform_context import CONFIGURED_API_BASE_URL

DEFAULT_TIMEOUT = 60.0
DEFAULT_ENDPOINT = f"{CONFIGURED_API_BASE_URL}/content/world-hint-draft"


def generate_world_hint_draft(
    *,
    source_text: str,
    title: str | None = None,
    world_preset_id: str | None = None,
    storyboard_prompt_language: str = "zh_CN",
    ip_default_world_hint: str | None = None,
    endpoint: str = DEFAULT_ENDPOINT,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict:
    response = httpx.post(
        endpoint,
        json={
            "source_text": source_text,
            "title": title,
            "world_preset_id": world_preset_id,
            "storyboard_prompt_language": storyboard_prompt_language,
            "ip_default_world_hint": ip_default_world_hint,
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()
