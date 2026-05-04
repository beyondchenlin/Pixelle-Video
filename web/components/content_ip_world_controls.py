from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import streamlit as st

from web.components.ip_prompt_chain_controls import (
    load_ip_prompt_chain_asset_bibles,
    render_ip_prompt_chain_controls,
)
from web.i18n import tr
from web.utils.content_api import generate_world_hint_draft
from web.utils.streamlit_helpers import safe_rerun

logger = logging.getLogger(__name__)

CONTENT_IP_STATE_PREFIX = "content_ip"
CONTENT_WORLD_HINT_KEY = "content_generation_world_hint"
CONTENT_WORLD_HINT_SOURCE_KEY = "content_generation_world_hint_source"
CONTENT_IP_PROFILE_WORLD_HINT_KEY = "content_ip_profile_world_hint"

Translate = Callable[..., str]


def build_content_ip_world_payload(
    *,
    ip_payload: Mapping[str, Any] | None = None,
    generation_world_hint: str | None = None,
) -> dict[str, Any]:
    """Build the formal content IP/world payload for request submission."""
    source = dict(ip_payload or {})
    payload: dict[str, Any] = {"ip_enabled": bool(source.get("ip_enabled", False))}
    if payload["ip_enabled"]:
        ip_asset_bible_id = _first_text(source.get("ip_asset_bible_id"))
        ip_profile_id = _first_text(source.get("ip_profile_id"))
        if ip_asset_bible_id:
            payload["ip_asset_bible_id"] = ip_asset_bible_id
        if ip_profile_id:
            payload["ip_profile_id"] = ip_profile_id

    world_hint = _first_text(generation_world_hint)
    if world_hint:
        payload["generation_world_hint"] = world_hint
    return payload


def render_content_ip_world_controls(
    *,
    ui=st,
    translate: Translate = tr,
    pixelle_video=None,
    content_context: Mapping[str, Any] | None = None,
    storyboard_prompt_language: str = "zh_CN",
    world_preset_id: str | None = None,
    asset_bible_loader: Callable[[], Sequence[Mapping[str, Any]]] | None = None,
    world_hint_draft_generator: Callable[..., Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Render left-column content IP and request-scoped world hint controls."""
    session_state = ui.session_state
    with ui.expander(translate("content.ip_world.section_title"), expanded=True):
        asset_bibles: Sequence[Mapping[str, Any]] = ()
        if asset_bible_loader is None:
            asset_bibles = _load_content_ip_asset_bibles(
                pixelle_video=pixelle_video,
                session_state=session_state,
                ui=ui,
                translate=translate,
            )

        ip_payload = render_ip_prompt_chain_controls(
            ui=ui,
            asset_bibles=asset_bibles,
            asset_bible_loader=asset_bible_loader,
            translate=translate,
            state_key_prefix=CONTENT_IP_STATE_PREFIX,
            label_key_prefix="content.ip_world",
        )
        ip_profile_world_hint = _first_text(ip_payload.pop("ip_profile_world_hint", None))
        if ip_profile_world_hint:
            session_state[CONTENT_IP_PROFILE_WORLD_HINT_KEY] = ip_profile_world_hint

        generation_world_hint = ui.text_area(
            translate("content.ip_world.generation_world_hint"),
            key=CONTENT_WORLD_HINT_KEY,
            height=96,
            help=translate("content.ip_world.generation_world_hint_help"),
        )

        use_default_col, generate_col = ui.columns((1, 1))
        with use_default_col:
            if ui.button(
                translate("content.ip_world.use_ip_default"),
                key="content_world_hint_use_ip_default",
                width="stretch",
            ):
                _use_ip_default_world_hint(
                    ui=ui,
                    translate=translate,
                    ip_profile_world_hint=ip_profile_world_hint
                    or session_state.get(CONTENT_IP_PROFILE_WORLD_HINT_KEY),
                )
        with generate_col:
            if ui.button(
                translate("content.ip_world.generate_from_content"),
                key="content_world_hint_generate_from_content",
                width="stretch",
            ):
                _generate_content_world_hint(
                    ui=ui,
                    translate=translate,
                    content_context=content_context,
                    storyboard_prompt_language=storyboard_prompt_language,
                    world_preset_id=world_preset_id,
                    ip_profile_world_hint=ip_profile_world_hint
                    or session_state.get(CONTENT_IP_PROFILE_WORLD_HINT_KEY),
                    world_hint_draft_generator=world_hint_draft_generator,
                )

    return build_content_ip_world_payload(
        ip_payload=ip_payload,
        generation_world_hint=session_state.get(CONTENT_WORLD_HINT_KEY, generation_world_hint),
    )


def _load_content_ip_asset_bibles(
    *,
    pixelle_video,
    session_state,
    ui,
    translate: Translate,
) -> list[dict[str, Any]]:
    if pixelle_video is None:
        return []
    try:
        return load_ip_prompt_chain_asset_bibles(
            pixelle_video=pixelle_video,
            session_state=session_state,
        )
    except Exception:
        logger.exception("failed to load content IP asset bibles")
        ui.warning(translate("content.ip_world.load_failed"))
        return []


def _use_ip_default_world_hint(
    *,
    ui,
    translate: Translate,
    ip_profile_world_hint: Any,
) -> None:
    ip_world_hint = _first_text(ip_profile_world_hint)
    if not ip_world_hint:
        ui.warning(translate("content.ip_world.missing_ip_default"))
        return
    ui.session_state[CONTENT_WORLD_HINT_KEY] = ip_world_hint
    ui.session_state[CONTENT_WORLD_HINT_SOURCE_KEY] = "ip_default"
    safe_rerun()


def _generate_content_world_hint(
    *,
    ui,
    translate: Translate,
    content_context: Mapping[str, Any] | None,
    storyboard_prompt_language: str,
    world_preset_id: str | None,
    ip_profile_world_hint: Any,
    world_hint_draft_generator: Callable[..., Mapping[str, Any]] | None,
) -> None:
    source_text = _first_text((content_context or {}).get("text"))
    if not source_text:
        ui.warning(translate("content.ip_world.missing_content"))
        return
    draft_generator = world_hint_draft_generator or generate_world_hint_draft
    response = draft_generator(
        source_text=source_text,
        title=_first_text((content_context or {}).get("title")) or None,
        world_preset_id=world_preset_id,
        storyboard_prompt_language=storyboard_prompt_language,
        ip_default_world_hint=_first_text(ip_profile_world_hint) or None,
    )
    ui.session_state[CONTENT_WORLD_HINT_KEY] = _first_text(
        response.get("world_hint_draft")
    )
    ui.session_state[CONTENT_WORLD_HINT_SOURCE_KEY] = "generated_from_script"
    safe_rerun()


def _first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


__all__ = [
    "CONTENT_IP_PROFILE_WORLD_HINT_KEY",
    "CONTENT_IP_STATE_PREFIX",
    "CONTENT_WORLD_HINT_KEY",
    "CONTENT_WORLD_HINT_SOURCE_KEY",
    "build_content_ip_world_payload",
    "render_content_ip_world_controls",
]
