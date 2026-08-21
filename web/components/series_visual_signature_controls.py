from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

import streamlit as st

from pixelle_video.models.series_visual_signature_identity import (
    SeriesVisualSignatureParticipationMode,
    SeriesVisualSignatureStructureMode,
)
from pixelle_video.models.series_visual_signature_strategy import (
    SeriesVisualSignatureConsistencyMode,
    SeriesVisualSignatureMode,
)
from pixelle_video.models.visual_expression import VisualExpressionMode
from pixelle_video.platform_context import resolve_business_context
from pixelle_video.utils.bool_parsing import coerce_bool
from web.i18n import tr
from web.utils.streamlit_helpers import first_text, list_of_dicts, text_list

Translate = Callable[..., str]


def resolve_ip_design_client(*args, **kwargs):
    """Load the client boundary only when visual signatures are enabled."""
    from web.state.ip_design_client import resolve_ip_design_client as resolver

    return resolver(*args, **kwargs)


def render_series_visual_signature_controls(
    *,
    ui=st,
    asset_bibles: Sequence[Mapping[str, Any]] = (),
    asset_bible_loader: Callable[[], Sequence[Mapping[str, Any]]] | None = None,
    translate: Translate = tr,
    state_key_prefix: str = "style_ip",
    label_key_prefix: str = "style.ip_prompt_chain",
) -> dict[str, Any]:
    """Render standard-generation controls for applying a designed visual signature profile."""
    enabled_key = _state_key(state_key_prefix, "enabled")
    asset_bible_key = _state_key(state_key_prefix, "asset_bible_id")
    profile_key = _state_key(state_key_prefix, "profile_id")
    normalized_label_prefix = first_text(label_key_prefix) or "style.ip_prompt_chain"
    enabled = coerce_bool(
        ui.toggle(
            translate(f"{normalized_label_prefix}.enabled"),
            value=coerce_bool(ui.session_state.get(enabled_key, False), default=False),
            key=enabled_key,
            help=translate(f"{normalized_label_prefix}.enabled_help"),
        ),
        default=False,
    )
    if not enabled:
        return {"series_visual_signature_enabled": False}

    if asset_bible_loader is not None:
        asset_bibles = asset_bible_loader()

    normalized_asset_bibles = [
        dict(item)
        for item in asset_bibles
        if first_text(item.get("asset_bible_id"))
    ]
    if not normalized_asset_bibles:
        ui.warning(translate(f"{normalized_label_prefix}.empty_asset_bibles"))
        return {"series_visual_signature_enabled": False}

    asset_bible_options = [
        first_text(item.get("asset_bible_id")) for item in normalized_asset_bibles
    ]
    asset_bible_id = _select_valid_option(
        ui=ui,
        label=translate(f"{normalized_label_prefix}.asset_bible"),
        key=asset_bible_key,
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
        for item in list_of_dicts(selected_asset_bible.get("ip_profiles"))
        if first_text(item.get("series_visual_signature_profile_id"))
    ]
    if not ip_profiles:
        ui.warning(translate(f"{normalized_label_prefix}.empty_profiles"))
        return {"series_visual_signature_enabled": False}

    ip_profile_options = [first_text(item.get("series_visual_signature_profile_id")) for item in ip_profiles]
    series_visual_signature_profile_id = _select_valid_option(
        ui=ui,
        label=translate(f"{normalized_label_prefix}.ip_profile"),
        key=profile_key,
        options=ip_profile_options,
        format_func=lambda item_id: _format_ip_profile_option(
            _find_mapping_item(ip_profiles, "series_visual_signature_profile_id", item_id) or {}
        ),
    )
    selected_profile = (
        _find_mapping_item(ip_profiles, "series_visual_signature_profile_id", series_visual_signature_profile_id) or {}
    )
    profile_name = first_text(selected_profile.get("name"))
    if profile_name:
        ui.caption(
            translate(
                f"{normalized_label_prefix}.selected_profile",
                ip_profile_name=profile_name,
            )
        )

    _render_ip_capability_preview(selected_profile, ui=ui, translate=translate)

    llm_prompt_assembly_enabled = False
    ui.caption(
        translate("series_visual_signature.prompt_assembly.deterministic_v46")
    )

    series_visual_signature_expression_mode = _select_valid_option(
        ui=ui,
        label=translate(f"{normalized_label_prefix}.series_visual_signature_expression_mode"),
        key=_state_key(state_key_prefix, "series_visual_signature_expression_mode"),
        options=[item.value for item in VisualExpressionMode],
        format_func=lambda value: translate(f"{normalized_label_prefix}.series_visual_signature_expression_mode.option.{value}"),
    )
    series_visual_signature_structure_mode = _select_valid_option(
        ui=ui,
        label=translate(f"{normalized_label_prefix}.series_visual_signature_structure_mode"),
        key=_state_key(state_key_prefix, "series_visual_signature_structure_mode"),
        options=[item.value for item in SeriesVisualSignatureStructureMode],
        format_func=lambda value: translate(f"{normalized_label_prefix}.series_visual_signature_structure_mode.option.{value}"),
    )
    series_visual_signature_participation_mode = _select_valid_option(
        ui=ui,
        label=translate(f"{normalized_label_prefix}.series_visual_signature_participation_mode"),
        key=_state_key(state_key_prefix, "series_visual_signature_participation_mode"),
        options=[item.value for item in SeriesVisualSignatureParticipationMode],
        format_func=lambda value: translate(f"{normalized_label_prefix}.series_visual_signature_participation_mode.option.{value}"),
    )
    series_visual_signature_mode = _select_valid_option(
        ui=ui,
        label=translate(f"{normalized_label_prefix}.series_visual_signature_mode"),
        key=_state_key(state_key_prefix, "series_visual_signature_mode"),
        options=[item.value for item in SeriesVisualSignatureMode],
        format_func=lambda value: translate(f"{normalized_label_prefix}.series_visual_signature_mode.option.{value}"),
    )
    series_visual_signature_consistency_mode = _select_valid_option(
        ui=ui,
        label=translate(f"{normalized_label_prefix}.series_visual_signature_consistency_mode"),
        key=_state_key(state_key_prefix, "series_visual_signature_consistency_mode"),
        options=[item.value for item in SeriesVisualSignatureConsistencyMode],
        format_func=lambda value: translate(f"{normalized_label_prefix}.series_visual_signature_consistency_mode.option.{value}"),
    )
    ui.caption(translate(f"{normalized_label_prefix}.series_visual_signature_expression_mode_help"))
    ui.caption(translate(f"{normalized_label_prefix}.series_visual_signature_structure_mode_help"))
    ui.caption(translate(f"{normalized_label_prefix}.series_visual_signature_participation_mode_help"))
    ui.caption(translate(f"{normalized_label_prefix}.series_visual_signature_mode_help"))
    ui.caption(translate(f"{normalized_label_prefix}.series_visual_signature_consistency_mode_help"))
    presentation_payload = _render_presentation_policy_controls(
        ui=ui,
        translate=translate,
        state_key_prefix=state_key_prefix,
        label_key_prefix=normalized_label_prefix,
    )

    payload = {
        "series_visual_signature_enabled": True,
        "series_visual_signature_asset_bible_id": asset_bible_id,
        "series_visual_signature_profile_id": series_visual_signature_profile_id,
        "series_visual_signature_expression_mode": series_visual_signature_expression_mode,
        "series_visual_signature_structure_mode": series_visual_signature_structure_mode,
        "series_visual_signature_participation_mode": series_visual_signature_participation_mode,
        "series_visual_signature_mode": series_visual_signature_mode,
        "series_visual_signature_consistency_mode": series_visual_signature_consistency_mode,
        "series_visual_signature_llm_prompt_assembly_enabled": llm_prompt_assembly_enabled,
        "mandatory_content_bound_anchor": True,
        "series_visual_signature_contract_version": "final_visual_prompt_contract.v4_6",
        "series_visual_signature_output_validation_mode": "required",
        "series_visual_signature_output_max_attempts": 3,
        **presentation_payload,
    }
    ip_profile_world_hint = first_text(selected_profile.get("world_hint"))
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

    # Typed clients return ListAssetBiblesResponse; legacy/mock clients may still
    # return a plain dict. Keep this boundary tolerant so content IP controls do
    # not crash while the migration is in progress.
    if isinstance(response, Mapping):
        if not response.get("success", True):
            return []
        return list_of_dicts(response.get("asset_bibles"))
    if not getattr(response, "success", True):
        return []
    return list_of_dicts(getattr(response, "asset_bibles", []))


def resolve_selected_ip_prompt_chain_profile_summary(
    *,
    session_state,
    asset_bibles,
    state_key_prefix: str = "style_ip",
) -> dict[str, Any]:
    """Resolve the currently selected IP profile without rendering Streamlit widgets."""
    enabled_key = _state_key(state_key_prefix, "enabled")
    asset_bible_key = _state_key(state_key_prefix, "asset_bible_id")
    profile_key = _state_key(state_key_prefix, "profile_id")
    if not coerce_bool(session_state.get(enabled_key, False), default=False):
        return {}
    asset_bible = _find_mapping_item(
        [dict(item) for item in asset_bibles if isinstance(item, Mapping)],
        "asset_bible_id",
        session_state.get(asset_bible_key),
    ) or {}
    profile = _find_mapping_item(
        list_of_dicts(asset_bible.get("ip_profiles")),
        "series_visual_signature_profile_id",
        session_state.get(profile_key),
    ) or {}
    summary = {
        "series_visual_signature_asset_bible_id": first_text(asset_bible.get("asset_bible_id")),
        "series_visual_signature_profile_id": first_text(profile.get("series_visual_signature_profile_id")),
        "ip_profile_name": first_text(profile.get("name")),
    }
    world_hint = first_text(profile.get("world_hint"))
    if world_hint:
        summary["ip_profile_world_hint"] = world_hint
    return {key: value for key, value in summary.items() if value}


def _render_ip_capability_preview(
    selected_profile: Mapping[str, Any],
    *,
    ui,
    translate: Translate,
) -> None:
    """Render a read-only preview of the selected visual signature profile capabilities."""
    if not selected_profile:
        return
    with ui.container(border=True):
        ui.caption(translate("content.ip_world.ip_capability_preview"))
        anchors = text_list(selected_profile.get("identity_lock"))
        if anchors:
            ui.caption(translate("content.ip_world.capability_visual_anchors", anchors=", ".join(anchors[:6])))
        visual = first_text(selected_profile.get("visual_summary"))
        if visual:
            ui.caption(translate("content.ip_world.capability_visual_summary", summary=visual))
        roles = text_list(selected_profile.get("role_presets"))
        if roles:
            role_names = [r.split("：")[0] for r in roles[:4] if "：" in r]
            if role_names:
                ui.caption(translate("content.ip_world.capability_available_roles", roles=" / ".join(role_names)))
        presence = text_list(selected_profile.get("presence_spectrum"))
        if presence:
            first = presence[0].split("：")[0] if "：" in presence[0] else presence[0]
            last = presence[-1].split("：")[0] if "：" in presence[-1] else presence[-1]
            ui.caption(translate("content.ip_world.capability_presence_range", first=first, last=last))
        ready = bool(anchors)
        ui.caption(translate("content.ip_world.capability_status_ready") if ready else translate("content.ip_world.capability_status_missing"))


def _text_list(value: Any) -> list[str]:
    return text_list(value)


def _select_valid_option(
    *,
    ui,
    label: str,
    key: str,
    options: Sequence[str],
    format_func,
) -> str:
    option_list = [first_text(option) for option in options]
    option_list = [option for option in option_list if option]
    selected = first_text(ui.session_state.get(key))
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
    return first_text(value)


def _render_presentation_policy_controls(
    *,
    ui,
    translate: Translate,
    state_key_prefix: str,
    label_key_prefix: str,
) -> dict[str, Any]:
    ui.caption(translate("series_visual_signature.presentation.mandatory_v46_note"))
    return {
        "series_visual_signature_presentation_mode": "content_bound_mandatory_ip",
        "series_visual_signature_enforcement": "strict",
        "series_visual_signature_fallback_enabled": False,
        "series_visual_signature_fallback_mode": "disabled",
        "series_visual_signature_min_visibility": "clear",
    }


def _state_key(prefix: str, suffix: str) -> str:
    normalized_prefix = first_text(prefix) or "style_ip"
    if suffix in {"enabled", "asset_bible_id", "profile_id"}:
        if normalized_prefix == "style_ip":
            return f"style_series_visual_signature_{suffix}"
        if normalized_prefix == "content_ip":
            return f"content_series_visual_signature_{suffix}"
    return f"{normalized_prefix}_{suffix}"


def _format_ip_asset_bible_option(asset_bible: Mapping[str, Any]) -> str:
    asset_bible_id = first_text(asset_bible.get("asset_bible_id"))
    ip_names = [
        first_text(profile.get("name"))
        for profile in list_of_dicts(asset_bible.get("ip_profiles"))
    ]
    suffix = " / ".join(item for item in ip_names if item)
    if asset_bible_id and suffix:
        return f"{asset_bible_id} - {suffix}"
    return asset_bible_id or suffix


def _format_ip_profile_option(ip_profile: Mapping[str, Any]) -> str:
    series_visual_signature_profile_id = first_text(ip_profile.get("series_visual_signature_profile_id"))
    profile_name = first_text(ip_profile.get("name"))
    if series_visual_signature_profile_id and profile_name:
        return f"{profile_name} ({series_visual_signature_profile_id})"
    return series_visual_signature_profile_id or profile_name


def _find_mapping_item(
    items: Sequence[Mapping[str, Any]],
    field_name: str,
    value: str,
) -> Mapping[str, Any] | None:
    expected = first_text(value)
    for item in items:
        if first_text(item.get(field_name)) == expected:
            return item
    return None


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    return list_of_dicts(value)


def _first_text(*values: Any) -> str:
    return first_text(*values)


__all__ = [
    "load_ip_prompt_chain_asset_bibles",
    "render_series_visual_signature_controls",
    "resolve_selected_ip_prompt_chain_profile_summary",
]
