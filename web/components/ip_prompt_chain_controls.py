from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

import streamlit as st

from pixelle_video.platform_context import resolve_business_context
from web.i18n import tr
from web.state.ip_design_client import resolve_ip_design_client

Translate = Callable[..., str]


def render_ip_prompt_chain_controls(
    *,
    ui=st,
    asset_bibles: Sequence[Mapping[str, Any]] = (),
    asset_bible_loader: Callable[[], Sequence[Mapping[str, Any]]] | None = None,
    translate: Translate = tr,
) -> dict[str, Any]:
    """Render standard-generation controls for applying a designed IP profile."""
    enabled = bool(
        ui.toggle(
            translate("style.ip_prompt_chain.enabled"),
            value=bool(ui.session_state.get("style_ip_enabled", False)),
            key="style_ip_enabled",
            help=translate("style.ip_prompt_chain.enabled_help"),
        )
    )
    if not enabled:
        return {"ip_enabled": False}

    if asset_bible_loader is not None:
        asset_bibles = asset_bible_loader()

    normalized_asset_bibles = [
        dict(item)
        for item in asset_bibles
        if _first_text(item.get("asset_bible_id"))
    ]
    if not normalized_asset_bibles:
        ui.warning(translate("style.ip_prompt_chain.empty_asset_bibles"))
        return {"ip_enabled": False}

    asset_bible_options = [
        _first_text(item.get("asset_bible_id")) for item in normalized_asset_bibles
    ]
    asset_bible_id = _select_valid_option(
        ui=ui,
        label=translate("style.ip_prompt_chain.asset_bible"),
        key="style_ip_asset_bible_id",
        options=asset_bible_options,
        format_func=lambda item_id: _format_ip_asset_bible_option(
            _find_mapping_item(normalized_asset_bibles, "asset_bible_id", item_id)
            or {}
        ),
    )
    selected_asset_bible = (
        _find_mapping_item(normalized_asset_bibles, "asset_bible_id", asset_bible_id)
        or {}
    )
    ip_profiles = [
        dict(item)
        for item in _list_of_dicts(selected_asset_bible.get("ip_profiles"))
        if _first_text(item.get("ip_profile_id"))
    ]
    if not ip_profiles:
        ui.warning(translate("style.ip_prompt_chain.empty_profiles"))
        return {"ip_enabled": False}

    ip_profile_options = [_first_text(item.get("ip_profile_id")) for item in ip_profiles]
    ip_profile_id = _select_valid_option(
        ui=ui,
        label=translate("style.ip_prompt_chain.ip_profile"),
        key="style_ip_profile_id",
        options=ip_profile_options,
        format_func=lambda item_id: _format_ip_profile_option(
            _find_mapping_item(ip_profiles, "ip_profile_id", item_id) or {}
        ),
    )
    selected_profile = (
        _find_mapping_item(ip_profiles, "ip_profile_id", ip_profile_id) or {}
    )
    profile_name = _first_text(selected_profile.get("name"))
    if profile_name:
        ui.caption(
            translate(
                "style.ip_prompt_chain.selected_profile",
                ip_profile_name=profile_name,
            )
        )

    payload = {
        "ip_enabled": True,
        "ip_asset_bible_id": asset_bible_id,
        "ip_profile_id": ip_profile_id,
    }
    ip_profile_world_hint = _first_text(selected_profile.get("world_hint"))
    if ip_profile_world_hint:
        payload["ip_profile_world_hint"] = ip_profile_world_hint
    return payload


def load_ip_prompt_chain_asset_bibles(
    *,
    pixelle_video,
    session_state,
) -> list[dict[str, Any]]:
    """Load IP AssetBibles through the existing IP design client boundary."""
    client = resolve_ip_design_client(session_state, pixelle_video=pixelle_video)
    if client is None:
        return []
    business_context = resolve_business_context(session_state)
    response = client.list_asset_bibles(**business_context)
    return _list_of_dicts(response.get("asset_bibles"))


def _select_valid_option(
    *,
    ui,
    label: str,
    key: str,
    options: Sequence[str],
    format_func,
) -> str:
    option_list = [_first_text(option) for option in options]
    option_list = [option for option in option_list if option]
    selected = _first_text(ui.session_state.get(key))
    index = option_list.index(selected) if selected in option_list else 0
    if option_list and selected not in option_list:
        ui.session_state[key] = option_list[index]
    value = ui.selectbox(
        label,
        option_list,
        index=index,
        key=key,
        format_func=format_func,
    )
    return _first_text(value)


def _format_ip_asset_bible_option(asset_bible: Mapping[str, Any]) -> str:
    asset_bible_id = _first_text(asset_bible.get("asset_bible_id"))
    ip_names = [
        _first_text(profile.get("name"))
        for profile in _list_of_dicts(asset_bible.get("ip_profiles"))
    ]
    suffix = " / ".join(item for item in ip_names if item)
    if asset_bible_id and suffix:
        return f"{asset_bible_id} - {suffix}"
    return asset_bible_id or suffix


def _format_ip_profile_option(ip_profile: Mapping[str, Any]) -> str:
    ip_profile_id = _first_text(ip_profile.get("ip_profile_id"))
    profile_name = _first_text(ip_profile.get("name"))
    if ip_profile_id and profile_name:
        return f"{profile_name} ({ip_profile_id})"
    return ip_profile_id or profile_name


def _find_mapping_item(
    items: Sequence[Mapping[str, Any]],
    field_name: str,
    value: str,
) -> Mapping[str, Any] | None:
    expected = _first_text(value)
    for item in items:
        if _first_text(item.get(field_name)) == expected:
            return item
    return None


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


__all__ = [
    "load_ip_prompt_chain_asset_bibles",
    "render_ip_prompt_chain_controls",
]
