from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import streamlit as st

from pixelle_video.contracts.ip_generation_request import build_formal_content_ip_world_payload
from pixelle_video.prompt_language import CHINESE_PROMPT_LANGUAGE
from web.components.series_visual_signature_controls import (
    load_ip_prompt_chain_asset_bibles,
    render_series_visual_signature_controls,
)
from web.i18n import tr
from web.utils.streamlit_helpers import first_text, safe_rerun

logger = logging.getLogger(__name__)

CONTENT_IP_STATE_PREFIX = "content_ip"
CONTENT_GENERATION_WORLD_HINT_KEY = "content_generation_world_hint"
CONTENT_GENERATION_WORLD_HINT_SOURCE_KEY = "content_generation_world_hint_source"
CONTENT_GENERATION_WORLD_HINT_LAST_VALUE_KEY = "content_generation_world_hint_last_value"
CONTENT_IP_PROFILE_WORLD_HINT_KEY = "content_ip_profile_world_hint"

Translate = Callable[..., str]


def generate_world_hint_draft(*args, **kwargs):
    """Load the remote draft client only after the user requests generation."""
    from web.utils.content_api import generate_world_hint_draft as generator

    return generator(*args, **kwargs)


def build_content_ip_world_payload(
    *,
    ip_payload: Mapping[str, Any] | None = None,
    generation_world_hint: str | None = None,
) -> dict[str, Any]:
    """Build the formal visual-signature/world payload for request submission."""
    source = dict(ip_payload or {})
    source["generation_world_hint"] = generation_world_hint
    return build_formal_content_ip_world_payload(source)


def render_content_series_visual_signature_controls(
    *,
    ui=st,
    translate: Translate = tr,
    pixelle_video=None,
    content_context: Mapping[str, Any] | None = None,
    storyboard_prompt_language: str = CHINESE_PROMPT_LANGUAGE,
    world_preset_id: str | None = None,
    asset_bible_loader: Callable[[], Sequence[Mapping[str, Any]]] | None = None,
    world_hint_draft_generator: Callable[..., Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Render the single left-column visual-signature and world-hint controls."""
    session_state = ui.session_state
    with ui.expander(translate("content.ip_world.section_title"), expanded=True):
        resolved_asset_bible_loader = asset_bible_loader
        asset_bibles: Sequence[Mapping[str, Any]] = ()
        if resolved_asset_bible_loader is None:

            def resolved_asset_bible_loader() -> Sequence[Mapping[str, Any]]:
                return _load_content_ip_asset_bibles(
                    pixelle_video=pixelle_video,
                    session_state=session_state,
                    ui=ui,
                    translate=translate,
                )

        ip_payload = render_series_visual_signature_controls(
            ui=ui,
            asset_bibles=asset_bibles,
            asset_bible_loader=resolved_asset_bible_loader,
            translate=translate,
            state_key_prefix=CONTENT_IP_STATE_PREFIX,
            label_key_prefix="content.ip_world",
        )

        ip_default_world_hint = (
            first_text(ip_payload.get("ip_profile_world_hint"))
            if ip_payload.get("series_visual_signature_enabled")
            else ""
        )
        _sync_ip_profile_world_hint(session_state, ip_default_world_hint)

        action_col, default_col = ui.columns((1, 1))
        with action_col:
            if ui.button(
                translate("content.ip_world.generate_from_content"),
                key="content_world_hint_generate_from_content",
            ):
                _handle_generate_world_hint_from_content(
                    session_state=session_state,
                    ui=ui,
                    translate=translate,
                    content_context=content_context,
                    storyboard_prompt_language=storyboard_prompt_language,
                    world_preset_id=world_preset_id,
                    ip_default_world_hint=ip_default_world_hint,
                    world_hint_draft_generator=(
                        world_hint_draft_generator or generate_world_hint_draft
                    ),
                )
        with default_col:
            if ui.button(
                translate("content.ip_world.use_ip_default"),
                key="content_world_hint_use_ip_default",
            ):
                _handle_use_ip_default_world_hint(
                    session_state=session_state,
                    ui=ui,
                    translate=translate,
                    ip_default_world_hint=ip_default_world_hint,
                )

        generation_world_hint = ui.text_area(
            translate("content.ip_world.generation_world_hint"),
            key=CONTENT_GENERATION_WORLD_HINT_KEY,
            value=session_state.get(CONTENT_GENERATION_WORLD_HINT_KEY, ""),
            height=92,
            help=translate("content.ip_world.generation_world_hint_help"),
        )
        _mark_world_hint_manual_if_user_edited(session_state, generation_world_hint)

    return build_content_ip_world_payload(
        ip_payload=ip_payload,
        generation_world_hint=session_state.get(
            CONTENT_GENERATION_WORLD_HINT_KEY,
            generation_world_hint,
        ),
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


def _sync_ip_profile_world_hint(session_state, ip_profile_world_hint: str) -> None:
    hint = first_text(ip_profile_world_hint)
    if hint:
        session_state[CONTENT_IP_PROFILE_WORLD_HINT_KEY] = hint
        return
    session_state.pop(CONTENT_IP_PROFILE_WORLD_HINT_KEY, None)


def _mark_world_hint_manual_if_user_edited(session_state, current_hint: str) -> None:
    current = first_text(current_hint)
    source = first_text(session_state.get(CONTENT_GENERATION_WORLD_HINT_SOURCE_KEY))
    last = first_text(session_state.get(CONTENT_GENERATION_WORLD_HINT_LAST_VALUE_KEY))
    if source in {"generated_from_script", "ip_default"} and last and current != last:
        session_state[CONTENT_GENERATION_WORLD_HINT_SOURCE_KEY] = "manual"
    if current:
        session_state[CONTENT_GENERATION_WORLD_HINT_LAST_VALUE_KEY] = current


def _handle_use_ip_default_world_hint(
    *,
    session_state,
    ui,
    translate: Translate,
    ip_default_world_hint: str,
) -> None:
    hint = first_text(ip_default_world_hint)
    if not hint:
        ui.warning(translate("content.ip_world.missing_ip_default"))
        return
    session_state[CONTENT_GENERATION_WORLD_HINT_KEY] = hint
    session_state[CONTENT_GENERATION_WORLD_HINT_SOURCE_KEY] = "ip_default"
    session_state[CONTENT_GENERATION_WORLD_HINT_LAST_VALUE_KEY] = hint
    safe_rerun()


def _handle_generate_world_hint_from_content(
    *,
    session_state,
    ui,
    translate: Translate,
    content_context: Mapping[str, Any] | None,
    storyboard_prompt_language: str,
    world_preset_id: str | None,
    ip_default_world_hint: str,
    world_hint_draft_generator: Callable[..., Mapping[str, Any]],
) -> None:
    context = dict(content_context or {})
    source_text = first_text(context.get("text"))
    if not source_text:
        ui.warning(translate("content.ip_world.missing_content"))
        return
    try:
        response = world_hint_draft_generator(
            source_text=source_text,
            title=first_text(context.get("title")) or None,
            world_preset_id=world_preset_id,
            storyboard_prompt_language=storyboard_prompt_language,
            ip_default_world_hint=first_text(ip_default_world_hint) or None,
        )
    except Exception:
        logger.exception("failed to generate content world hint draft")
        ui.warning(translate("content.ip_world.generate_failed"))
        return
    hint = (
        first_text(response.get("world_hint_draft"))
        if isinstance(response, Mapping)
        else ""
    )
    if not hint:
        ui.warning(translate("content.ip_world.generate_failed"))
        return
    session_state[CONTENT_GENERATION_WORLD_HINT_KEY] = hint
    session_state[CONTENT_GENERATION_WORLD_HINT_SOURCE_KEY] = "generated_from_script"
    session_state[CONTENT_GENERATION_WORLD_HINT_LAST_VALUE_KEY] = hint
    safe_rerun()


__all__ = [
    "CONTENT_GENERATION_WORLD_HINT_KEY",
    "CONTENT_IP_PROFILE_WORLD_HINT_KEY",
    "CONTENT_IP_STATE_PREFIX",
    "build_content_ip_world_payload",
    "render_content_series_visual_signature_controls",
]
