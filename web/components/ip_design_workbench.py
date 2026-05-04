from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import streamlit as st

from pixelle_video.platform_context import (
    DEFAULT_PROJECT_ID,
    DEFAULT_WORKSPACE_ID,
    first_explicit_text,
)
from web.i18n import tr
from web.utils.asset_bible_api import (
    build_asset_bible_draft_payload_from_response,
    upsert_ip_profile_draft,
)

Translate = Callable[..., str]


def render_ip_design_workbench(
    *,
    ip_design_client,
    ui=st,
    translate: Translate = tr,
) -> None:
    state = getattr(ui, "session_state", {})
    workspace_id = first_explicit_text(state.get("workspace_id"), DEFAULT_WORKSPACE_ID)
    project_id = first_explicit_text(state.get("project_id"), DEFAULT_PROJECT_ID)

    if ip_design_client is None:
        ui.info(translate("ip_design.unavailable"))
        return

    ui.markdown(f"### {translate('ip_design.surface.title')}")
    ui.caption(translate("ip_design.surface.caption"))

    try:
        asset_response = ip_design_client.list_asset_bibles(
            workspace_id=workspace_id,
            project_id=project_id,
        )
    except Exception:
        ui.error(translate("ip_design.asset_bible.load_failed"))
        return

    asset_bibles = _list_of_dicts(asset_response.get("asset_bibles"))
    asset_bible_result = _render_asset_bible_section(
        ip_design_client=ip_design_client,
        workspace_id=workspace_id,
        project_id=project_id,
        asset_bibles=asset_bibles,
        ui=ui,
        translate=translate,
    )
    asset_bible_id = asset_bible_result["asset_bible_id"]
    if not asset_bible_id:
        return

    try:
        scene_response = ip_design_client.list_scene_casts(
            workspace_id=workspace_id,
            project_id=project_id,
            asset_bible_id=asset_bible_id,
        )
    except Exception:
        ui.error(translate("ip_design.scene_cast.load_failed"))
        return

    _render_scene_cast_section(
        ip_design_client=ip_design_client,
        workspace_id=workspace_id,
        project_id=project_id,
        asset_bible_id=asset_bible_id,
        scene_casts=_list_of_dicts(scene_response.get("scene_casts")),
        ui=ui,
        translate=translate,
    )


def _render_asset_bible_section(
    *,
    ip_design_client,
    workspace_id: str,
    project_id: str,
    asset_bibles: list[dict[str, Any]],
    ui,
    translate: Translate,
) -> dict[str, Any]:
    with ui.container(border=True):
        ui.markdown(f"#### {translate('ip_design.asset_bible.title')}")
        if asset_bibles:
            selected_id = _select_asset_bible(asset_bibles, ui=ui, translate=translate)
            selected_asset_bible = _find_item(asset_bibles, "asset_bible_id", selected_id) or {}
            _render_asset_bible_summary(selected_asset_bible, ui=ui, translate=translate)
        else:
            selected_id = ""
            selected_asset_bible = {}
            ui.caption(translate("ip_design.asset_bible.empty"))

        preset_result = _render_asset_bible_preset_import(
            ip_design_client=ip_design_client,
            workspace_id=workspace_id,
            project_id=project_id,
            ui=ui,
            translate=translate,
        )
        if preset_result.get("saved"):
            return {"asset_bible_id": "", "saved": True}

        asset_bible_id = _text_input(
            ui,
            translate("ip_design.asset_bible.id"),
            key="ip_design_asset_bible_id",
            value=selected_id,
        )
        ip_profile_id = _text_input(
            ui,
            translate("ip_design.asset_bible.ip_profile_id"),
            key="ip_design_ip_profile_id",
            value=_first_ip_profile_id(selected_asset_bible) or "ip_main",
        )
        ip_profile = _find_ip_profile(selected_asset_bible, ip_profile_id)
        ip_name = _text_input(
            ui,
            translate("ip_design.asset_bible.ip_name"),
            key="ip_design_ip_name",
            value=_first_text(ip_profile.get("name")),
        )
        logline = _text_area(
            ui,
            translate("ip_design.asset_bible.logline"),
            key="ip_design_logline",
            value=_first_text(ip_profile.get("logline")),
            height=68,
        )
        world_hint = _text_area(
            ui,
            translate("ip_design.asset_bible.world_hint"),
            key="ip_design_world_hint",
            value=_first_text(ip_profile.get("world_hint")),
            height=68,
        )
        style_hint = _text_area(
            ui,
            translate("ip_design.asset_bible.style_hint"),
            key="ip_design_style_hint",
            value=_first_text(ip_profile.get("style_hint")),
            height=68,
        )
        identity_lock = _text_input(
            ui,
            translate("ip_design.asset_bible.identity_lock"),
            key="ip_design_identity_lock",
            value=", ".join(_text_list(ip_profile.get("identity_lock"))),
        )
        identity_anchors = _text_input(
            ui,
            translate("ip_design.asset_bible.identity_anchors"),
            key="ip_design_identity_anchors",
            value=", ".join(_text_list(ip_profile.get("identity_anchors"))),
        )
        identity_suppression_rules = _text_input(
            ui,
            translate("ip_design.asset_bible.identity_suppression_rules"),
            key="ip_design_identity_suppression_rules",
            value=", ".join(_text_list(ip_profile.get("identity_suppression_rules"))),
        )
        variable_slots = _text_input(
            ui,
            translate("ip_design.asset_bible.variable_slots"),
            key="ip_design_variable_slots",
            value=", ".join(_text_list(ip_profile.get("variable_slots"))),
        )
        semantic_boundary = _text_input(
            ui,
            translate("ip_design.asset_bible.semantic_boundary"),
            key="ip_design_semantic_boundary",
            value=", ".join(_text_list(ip_profile.get("semantic_boundary"))),
        )
        negative_constraints = _text_input(
            ui,
            translate("ip_design.asset_bible.negative_constraints"),
            key="ip_design_negative_constraints",
            value=", ".join(_text_list(ip_profile.get("negative_constraints"))),
        )
        visible_text_whitelist = _text_input(
            ui,
            translate("ip_design.asset_bible.visible_text_whitelist"),
            key="ip_design_visible_text_whitelist",
            value=", ".join(_text_list(ip_profile.get("visible_text_whitelist"))),
        )
        if _ip_profile_ready_for_generation(ip_profile):
            ui.caption(translate("ip_design.asset_bible.generation_available"))
        else:
            ui.caption(translate("ip_design.asset_bible.generation_unavailable"))

        if ui.button(
            translate("ip_design.asset_bible.save"),
            key="ip_design_save_asset_bible",
        ):
            is_existing_asset = asset_bible_id == selected_id
            if not _has_text(asset_bible_id, ip_profile_id, ip_name):
                ui.error(translate("ip_design.asset_bible.missing_required"))
            else:
                try:
                    payload = _build_asset_bible_save_payload(
                        source_asset_bible=selected_asset_bible if is_existing_asset else {},
                        ip_profile={
                            "ip_profile_id": ip_profile_id,
                            "name": ip_name,
                            "logline": logline,
                            "world_hint": world_hint,
                            "style_hint": style_hint,
                            "identity_lock": _split_csv(identity_lock),
                            "identity_anchors": _split_csv(identity_anchors),
                            "identity_suppression_rules": _split_csv(identity_suppression_rules),
                            "variable_slots": _split_csv(variable_slots),
                            "semantic_boundary": _split_csv(semantic_boundary),
                            "negative_constraints": _split_csv(negative_constraints),
                            "visible_text_whitelist": _split_csv(visible_text_whitelist),
                        },
                    )
                    ip_design_client.save_asset_bible(
                        workspace_id=workspace_id,
                        project_id=project_id,
                        asset_bible_id=asset_bible_id,
                        payload=payload,
                    )
                except Exception:
                    ui.error(translate("ip_design.asset_bible.save_failed"))
                else:
                    ui.success(translate("ip_design.asset_bible.saved"))
                    return {"asset_bible_id": "", "saved": True}

        return {"asset_bible_id": _first_text(asset_bible_id, selected_id), "saved": False}


def _render_asset_bible_preset_import(
    *,
    ip_design_client,
    workspace_id: str,
    project_id: str,
    ui,
    translate: Translate,
) -> dict[str, Any]:
    if not hasattr(ip_design_client, "list_asset_bible_presets"):
        return {"saved": False}
    try:
        presets = _list_of_dicts(ip_design_client.list_asset_bible_presets())
    except Exception:
        ui.caption(translate("ip_design.asset_bible.presets_load_failed"))
        return {"saved": False}
    if not presets:
        return {"saved": False}

    preset_ids = [
        _first_text(item.get("preset_id"))
        for item in presets
        if _first_text(item.get("preset_id"))
    ]
    if not preset_ids:
        return {"saved": False}
    selected_preset_id = _first_text(
        ui.selectbox(
            translate("ip_design.asset_bible.builtin_presets"),
            preset_ids,
            key="ip_design_builtin_asset_bible_preset_select",
            format_func=lambda preset_id: _format_asset_bible_preset_option(
                _find_item(presets, "preset_id", preset_id) or {}
            ),
        )
    )
    import_asset_bible_id = _text_input(
        ui,
        translate("ip_design.asset_bible.import_id"),
        key="ip_design_import_asset_bible_id",
        value=_derive_asset_bible_id_from_preset(selected_preset_id),
    )
    if not ui.button(
        translate("ip_design.asset_bible.import"),
        key="ip_design_import_builtin_asset_bible",
    ):
        return {"saved": False}
    try:
        ip_design_client.import_asset_bible_preset(
            workspace_id=workspace_id,
            project_id=project_id,
            preset_id=selected_preset_id,
            asset_bible_id=import_asset_bible_id,
        )
    except Exception:
        ui.error(translate("ip_design.asset_bible.import_failed"))
        return {"saved": False}
    ui.success(translate("ip_design.asset_bible.imported"))
    return {"asset_bible_id": "", "saved": True}


def _render_scene_cast_section(
    *,
    ip_design_client,
    workspace_id: str,
    project_id: str,
    asset_bible_id: str,
    scene_casts: list[dict[str, Any]],
    ui,
    translate: Translate,
) -> None:
    with ui.container(border=True):
        ui.markdown(f"#### {translate('ip_design.scene_cast.title')}")
        if scene_casts:
            selected_scene_cast_id = _select_scene_cast(scene_casts, ui=ui, translate=translate)
            selected_scene_cast = (
                _find_item(scene_casts, "scene_cast_id", selected_scene_cast_id) or {}
            )
            _render_scene_cast_summary(selected_scene_cast, ui=ui, translate=translate)
        else:
            selected_scene_cast_id = ""
            selected_scene_cast = {}
            ui.caption(translate("ip_design.scene_cast.empty"))

        scene_cast_id = _text_input(
            ui,
            translate("ip_design.scene_cast.id"),
            key="ip_design_scene_cast_id",
            value=selected_scene_cast_id,
        )
        storyboard_plan_id = _text_input(
            ui,
            translate("ip_design.scene_cast.storyboard_plan_id"),
            key="ip_design_storyboard_plan_id",
            value=_first_text(selected_scene_cast.get("storyboard_plan_id")),
        )
        frame_id = _text_input(
            ui,
            translate("ip_design.scene_cast.frame_id"),
            key="ip_design_frame_id",
            value=_first_text(selected_scene_cast.get("frame_id")),
        )
        character_ids = _text_input(
            ui,
            translate("ip_design.scene_cast.character_ids"),
            key="ip_design_character_ids",
            value=", ".join(_text_list(selected_scene_cast.get("character_ids"))),
        )
        scene_id = _text_input(
            ui,
            translate("ip_design.scene_cast.scene_id"),
            key="ip_design_scene_id",
            value=_first_text(selected_scene_cast.get("scene_id")),
        )
        prop_ids = _text_input(
            ui,
            translate("ip_design.scene_cast.prop_ids"),
            key="ip_design_prop_ids",
            value=", ".join(_text_list(selected_scene_cast.get("prop_ids"))),
        )
        style_id = _text_input(
            ui,
            translate("ip_design.scene_cast.style_id"),
            key="ip_design_style_id",
            value=_first_text(selected_scene_cast.get("style_id")),
        )
        continuity_notes = _text_area(
            ui,
            translate("ip_design.scene_cast.continuity_notes"),
            key="ip_design_continuity_notes",
            value="\n".join(_text_list(selected_scene_cast.get("continuity_notes"))),
            height=88,
        )

        if not ui.button(
            translate("ip_design.scene_cast.save"),
            key="ip_design_save_scene_cast",
        ):
            return
        if not _has_text(scene_cast_id, storyboard_plan_id, frame_id):
            ui.error(translate("ip_design.scene_cast.missing_required"))
            return

        payload = {
            "storyboard_plan_id": storyboard_plan_id,
            "frame_id": frame_id,
            "character_ids": _split_csv(character_ids),
            "scene_id": scene_id,
            "prop_ids": _split_csv(prop_ids),
            "style_id": style_id,
            "continuity_notes": _split_lines(continuity_notes),
        }
        try:
            ip_design_client.save_scene_cast(
                workspace_id=workspace_id,
                project_id=project_id,
                asset_bible_id=asset_bible_id,
                scene_cast_id=scene_cast_id,
                payload=payload,
            )
        except Exception:
            ui.error(translate("ip_design.scene_cast.save_failed"))
        else:
            ui.success(translate("ip_design.scene_cast.saved"))


def _select_asset_bible(asset_bibles: list[dict[str, Any]], *, ui, translate: Translate) -> str:
    options = [_first_text(item.get("asset_bible_id")) for item in asset_bibles]
    options = [option for option in options if option]
    selected = ui.selectbox(
        translate("ip_design.asset_bible.select"),
        options,
        key="ip_design_asset_bible_select",
        format_func=lambda item_id: _format_asset_bible_option(
            _find_item(asset_bibles, "asset_bible_id", item_id) or {}
        ),
    )
    return _first_text(selected)


def _select_scene_cast(scene_casts: list[dict[str, Any]], *, ui, translate: Translate) -> str:
    options = [_first_text(item.get("scene_cast_id")) for item in scene_casts]
    options = [option for option in options if option]
    selected = ui.selectbox(
        translate("ip_design.scene_cast.select"),
        options,
        key="ip_design_scene_cast_select",
        format_func=lambda item_id: _format_scene_cast_option(
            _find_item(scene_casts, "scene_cast_id", item_id) or {}
        ),
    )
    return _first_text(selected)


def _render_asset_bible_summary(
    asset_bible: Mapping[str, Any],
    *,
    ui,
    translate: Translate,
) -> None:
    summary = (
        f"{_first_text(asset_bible.get('asset_bible_id'))} · "
        f"{_first_ip_name(asset_bible)} · "
        f"{translate('ip_design.asset_bible.counts', characters=len(_list_of_dicts(asset_bible.get('character_profiles'))), scenes=len(_list_of_dicts(asset_bible.get('scene_assets'))), props=len(_list_of_dicts(asset_bible.get('prop_assets'))), styles=len(_list_of_dicts(asset_bible.get('style_profiles'))))}"
    )
    ui.caption(summary)


def _render_scene_cast_summary(
    scene_cast: Mapping[str, Any],
    *,
    ui,
    translate: Translate,
) -> None:
    summary = translate(
        "ip_design.scene_cast.summary",
        scene_cast_id=_first_text(scene_cast.get("scene_cast_id")),
        storyboard_plan_id=_first_text(scene_cast.get("storyboard_plan_id")),
        frame_id=_first_text(scene_cast.get("frame_id")),
        characters=", ".join(_text_list(scene_cast.get("character_ids"))),
        scene_id=_first_text(scene_cast.get("scene_id")),
        props=", ".join(_text_list(scene_cast.get("prop_ids"))),
        style_id=_first_text(scene_cast.get("style_id")),
    )
    ui.caption(summary)


def _format_asset_bible_option(asset_bible: Mapping[str, Any]) -> str:
    asset_bible_id = _first_text(asset_bible.get("asset_bible_id"))
    ip_name = _first_ip_name(asset_bible)
    return " · ".join(item for item in (asset_bible_id, ip_name) if item)


def _format_asset_bible_preset_option(preset: Mapping[str, Any]) -> str:
    return _first_text(preset.get("display_name"), preset.get("preset_id"))


def _format_scene_cast_option(scene_cast: Mapping[str, Any]) -> str:
    scene_cast_id = _first_text(scene_cast.get("scene_cast_id"))
    frame = "/".join(
        item
        for item in (
            _first_text(scene_cast.get("storyboard_plan_id")),
            _first_text(scene_cast.get("frame_id")),
        )
        if item
    )
    return " · ".join(item for item in (scene_cast_id, frame) if item)


def _derive_asset_bible_id_from_preset(preset_id: str) -> str:
    base = preset_id.removeprefix("builtin_asset_bible_")
    return f"{base}_bible" if base else ""


def _first_ip_name(asset_bible: Mapping[str, Any]) -> str:
    return _first_text(_first_dict(asset_bible.get("ip_profiles")).get("name"))


def _first_ip_profile_id(asset_bible: Mapping[str, Any]) -> str:
    return _first_text(_first_dict(asset_bible.get("ip_profiles")).get("ip_profile_id"))


def _find_ip_profile(asset_bible: Mapping[str, Any], ip_profile_id: str) -> dict[str, Any]:
    profiles = _list_of_dicts(asset_bible.get("ip_profiles"))
    for profile in profiles:
        if _first_text(profile.get("ip_profile_id")) == _first_text(ip_profile_id):
            return profile
    return profiles[0] if profiles else {}


def _build_asset_bible_save_payload(
    *,
    source_asset_bible: Mapping[str, Any],
    ip_profile: dict[str, Any],
) -> dict[str, Any]:
    if source_asset_bible:
        payload = build_asset_bible_draft_payload_from_response(dict(source_asset_bible))
        return upsert_ip_profile_draft(payload, ip_profile)
    normalized = build_asset_bible_draft_payload_from_response(
        {
            "ip_profiles": [ip_profile],
            "character_profiles": [],
            "scene_assets": [],
            "prop_assets": [],
            "style_profiles": [],
        }
    )
    normalized.setdefault("character_profiles", [])
    normalized.setdefault("scene_assets", [])
    normalized.setdefault("prop_assets", [])
    normalized.setdefault("style_profiles", [])
    return normalized


def _ip_profile_ready_for_generation(ip_profile: Mapping[str, Any]) -> bool:
    return bool(
        _text_list(ip_profile.get("identity_lock"))
        or _text_list(ip_profile.get("identity_anchors"))
    )


def _text_input(ui, label: str, *, key: str, value: str = "") -> str:
    if key in ui.session_state:
        return ui.text_input(label, key=key)
    return ui.text_input(label, value=value, key=key)


def _text_area(ui, label: str, *, key: str, value: str = "", height: int) -> str:
    if key in ui.session_state:
        return ui.text_area(label, key=key, height=height)
    return ui.text_area(label, value=value, key=key, height=height)


def _find_item(items: list[dict[str, Any]], field_name: str, value: str) -> dict[str, Any] | None:
    for item in items:
        if _first_text(item.get(field_name)) == value:
            return item
    return None


def _first_dict(value: Any) -> dict[str, Any]:
    items = _list_of_dicts(value)
    return items[0] if items else {}


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_first_text(item) for item in value if _first_text(item)]


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _split_lines(value: str) -> list[str]:
    return [item.strip() for item in value.splitlines() if item.strip()]


def _has_text(*values: str) -> bool:
    return all(value.strip() for value in values)


def _first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


__all__ = ["render_ip_design_workbench"]
