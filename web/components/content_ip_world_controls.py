from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import streamlit as st

from pixelle_video.prompt_language import CHINESE_PROMPT_LANGUAGE
from web.components.ip_prompt_chain_controls import (
    load_ip_prompt_chain_asset_bibles,
    render_ip_prompt_chain_controls,
)
from web.i18n import tr

logger = logging.getLogger(__name__)

CONTENT_IP_STATE_PREFIX = "content_ip"
CONTENT_GENERATION_NOTES_KEY = "content_generation_notes"
CONTENT_SLOT_PREFERENCE_KEY = "content_slot_preference"
CONTENT_PRESENCE_STRENGTH_KEY = "content_presence_strength"

Translate = Callable[..., str]


def build_content_ip_world_payload(
    *,
    ip_payload: Mapping[str, Any] | None = None,
    generation_notes: str | None = None,
    slot_preference: str | None = None,
    presence_strength: str | None = None,
) -> dict[str, Any]:
    """Build the formal content IP integration payload for request submission."""
    source = dict(ip_payload or {})
    payload: dict[str, Any] = {"ip_enabled": bool(source.get("ip_enabled", False))}
    if payload["ip_enabled"]:
        ip_asset_bible_id = _first_text(source.get("ip_asset_bible_id"))
        ip_profile_id = _first_text(source.get("ip_profile_id"))
        if ip_asset_bible_id:
            payload["ip_asset_bible_id"] = ip_asset_bible_id
        if ip_profile_id:
            payload["ip_profile_id"] = ip_profile_id

    notes = _first_text(generation_notes)
    if notes:
        payload["generation_notes"] = notes
    slot = _first_text(slot_preference)
    if slot and slot != "default":
        payload["slot_preference_override"] = slot
    strength = _first_text(presence_strength)
    if strength and strength != "default":
        payload["presence_strength"] = strength
    return payload


def render_content_ip_world_controls(
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
    """Render left-column IP character integration controls."""
    session_state = ui.session_state
    with ui.expander(translate("content.ip_world.section_title"), expanded=True):
        resolved_asset_bible_loader = asset_bible_loader
        asset_bibles: Sequence[Mapping[str, Any]] = ()
        if resolved_asset_bible_loader is None:
            resolved_asset_bible_loader = lambda: _load_content_ip_asset_bibles(
                pixelle_video=pixelle_video,
                session_state=session_state,
                ui=ui,
                translate=translate,
            )

        ip_payload = render_ip_prompt_chain_controls(
            ui=ui,
            asset_bibles=asset_bibles,
            asset_bible_loader=resolved_asset_bible_loader,
            translate=translate,
            state_key_prefix=CONTENT_IP_STATE_PREFIX,
            label_key_prefix="content.ip_world",
        )

        if ip_payload.get("ip_enabled"):
            ip_asset_bible_id = _first_text(ip_payload.get("ip_asset_bible_id"))
            ip_profile_id = _first_text(ip_payload.get("ip_profile_id"))
            selected_profile = _resolve_selected_ip_profile(
                asset_bible_loader=resolved_asset_bible_loader,
                asset_bible_id=ip_asset_bible_id,
                ip_profile_id=ip_profile_id,
            )

            slot_col, presence_col = ui.columns((1, 1))
            with slot_col:
                slot_preference = _render_select_or_default(
                    ui,
                    translate("content.ip_world.slot_preference_override"),
                    key=CONTENT_SLOT_PREFERENCE_KEY,
                    options=["prefer_supporting", "prefer_main", "auto", "minimal"],
                )
            with presence_col:
                presence_strength = _render_select_or_default(
                    ui,
                    translate("content.ip_world.presence_strength"),
                    key=CONTENT_PRESENCE_STRENGTH_KEY,
                    options=["more", "default", "less", "minimal"],
                )

            generation_notes = ui.text_area(
                translate("content.ip_world.generation_notes"),
                key=CONTENT_GENERATION_NOTES_KEY,
                value=session_state.get(CONTENT_GENERATION_NOTES_KEY, ""),
                height=72,
                help=translate("content.ip_world.generation_notes_help"),
            )

            _render_ip_capability_preview(selected_profile, ui=ui, translate=translate)
        else:
            slot_preference = ""
            presence_strength = ""
            generation_notes = ""

    return build_content_ip_world_payload(
        ip_payload=ip_payload,
        generation_notes=session_state.get(CONTENT_GENERATION_NOTES_KEY, generation_notes),
        slot_preference=session_state.get(CONTENT_SLOT_PREFERENCE_KEY, slot_preference),
        presence_strength=session_state.get(CONTENT_PRESENCE_STRENGTH_KEY, presence_strength),
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


def _resolve_selected_ip_profile(
    *,
    asset_bible_loader: Callable[[], Sequence[Mapping[str, Any]]],
    asset_bible_id: str,
    ip_profile_id: str,
) -> dict[str, Any]:
    if not asset_bible_id or not ip_profile_id:
        return {}
    try:
        asset_bibles = asset_bible_loader()
    except Exception:
        return {}
    for ab in asset_bibles:
        if _first_text(ab.get("asset_bible_id")) == asset_bible_id:
            for profile in _list_of_dicts(ab.get("ip_profiles")):
                if _first_text(profile.get("ip_profile_id")) == ip_profile_id:
                    return dict(profile)
    return {}


def _render_select_or_default(
    ui,
    label: str,
    *,
    key: str,
    options: list[str],
) -> str:
    """Render a selectbox with a 'default' option (use IP profile default)."""
    all_options = ["default", *options]
    current = _first_text(ui.session_state.get(key))
    index = all_options.index(current) if current in all_options else 0
    selected = ui.selectbox(label, all_options, key=key, index=index)
    return _first_text(selected)


def _render_ip_capability_preview(
    selected_profile: Mapping[str, Any],
    *,
    ui,
    translate: Translate,
) -> None:
    if not selected_profile:
        return
    with ui.container(border=True):
        ui.caption(translate("content.ip_world.ip_capability_preview"))
        anchors = _text_list(selected_profile.get("identity_lock"))
        if anchors:
            ui.caption(f"视觉锚点：{', '.join(anchors[:6])}")
        visual = _first_text(selected_profile.get("visual_summary"))
        if visual:
            ui.caption(f"视觉摘要：{visual}")
        roles = _text_list(selected_profile.get("role_presets"))
        if roles:
            role_names = [r.split("：")[0] for r in roles[:4] if "：" in r]
            if role_names:
                ui.caption(f"可扮角色：{' / '.join(role_names)}")
        presence = _text_list(selected_profile.get("presence_spectrum"))
        if presence:
            first = presence[0].split("：")[0] if "：" in presence[0] else presence[0]
            last = presence[-1].split("：")[0] if "：" in presence[-1] else presence[-1]
            ui.caption(f"出场范围：{first} ~ {last}")
        ready = bool(anchors)
        ui.caption(f"生成状态：{'✅ 可用' if ready else '⚠️ 缺少锚点'}")


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, (list, tuple)) or isinstance(value, (str, bytes)):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [_first_text(item) for item in value if _first_text(item)]


def _first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


__all__ = [
    "CONTENT_IP_STATE_PREFIX",
    "build_content_ip_world_payload",
    "render_content_ip_world_controls",
]
