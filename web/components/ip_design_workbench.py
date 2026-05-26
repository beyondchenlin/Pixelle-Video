from __future__ import annotations

from collections.abc import Callable
from typing import Any

import streamlit as st

from pixelle_video.platform_context import (
    DEFAULT_PROJECT_ID,
    DEFAULT_WORKSPACE_ID,
    first_explicit_text,
)
from pixelle_video.services.ip_color_palette import build_color_palette_prompt_entries
from pixelle_video.services.ip_profile_readiness import ip_generation_identity_terms
from web.i18n import tr
from web.ip_design.models import (
    AssetBibleDraft,
    CharacterProfileDraft,
    FieldId,
    IPProfileDraft,
    ListSceneCastsResponse,
    PropAssetDraft,
    SaveResponse,
    SceneAssetDraft,
    SceneCastDraft,
    StyleProfileDraft,
)
from web.ip_design.session_keys import IPSessionKeys
from web.ip_design.asset_bible_payloads import _to_ip_profile_draft
from web.utils.asset_bible_payloads import (
    build_asset_bible_draft_payload_from_response,
    upsert_ip_profile_draft,
)
from web.utils.streamlit_helpers import (
    build_model_from_form,
    find_item,
    first_text,
    keyed_text_area,
    keyed_text_input,
    list_of_dicts,
    populate_form_from_model,
    split_csv,
    text_list,
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
        response = ip_design_client.list_asset_bibles(
            workspace_id=workspace_id,
            project_id=project_id,
        )
    except Exception:
        ui.error(translate("ip_design.asset_bible.load_failed"))
        return

    if not response.success:
        ui.error(translate("ip_design.asset_bible.load_failed"))
        return

    asset_bibles = [ab.model_dump() for ab in response.asset_bibles]
    selected_asset_bible, asset_bible_id = _render_asset_bible_selector(
        asset_bibles=asset_bibles,
        ip_design_client=ip_design_client,
        workspace_id=workspace_id,
        project_id=project_id,
        ui=ui,
        translate=translate,
    )
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

    scene_casts = list_of_dicts(scene_response.scene_casts)

    tabs = ui.tabs([
        translate("ip_design.tab.ip_profile"),
        translate("ip_design.tab.scene_cast"),
        translate("ip_design.tab.presets"),
        translate("ip_design.tab.history"),
        translate("ip_design.tab.readiness"),
    ])

    with tabs[0]:
        _render_ip_profile_tab(
            ip_design_client=ip_design_client,
            workspace_id=workspace_id,
            project_id=project_id,
            asset_bible_id=asset_bible_id,
            selected_asset_bible=selected_asset_bible,
            asset_bibles=asset_bibles,
            ui=ui,
            translate=translate,
        )

    with tabs[1]:
        _render_scene_cast_tab(
            ip_design_client=ip_design_client,
            workspace_id=workspace_id,
            project_id=project_id,
            asset_bible_id=asset_bible_id,
            scene_casts=scene_casts,
            ui=ui,
            translate=translate,
        )

    with tabs[2]:
        _render_presets_tab(
            ip_design_client=ip_design_client,
            workspace_id=workspace_id,
            project_id=project_id,
            ui=ui,
            translate=translate,
        )

    with tabs[3]:
        _render_history_tab(
            ip_design_client=ip_design_client,
            asset_bible_id=asset_bible_id,
            ui=ui,
            translate=translate,
        )

    with tabs[4]:
        _render_readiness_tab(
            selected_asset_bible=selected_asset_bible,
            ui=ui,
            translate=translate,
        )


# ── Asset Bible selector (shared by the IP profile tab) ──

def _render_asset_bible_selector(
    *,
    asset_bibles: list[dict[str, Any]],
    ip_design_client,
    workspace_id: str,
    project_id: str,
    ui,
    translate: Translate,
) -> tuple[dict[str, Any], str]:
    with ui.container(border=True):
        ui.markdown(f"#### {translate('ip_design.asset_bible.title')}")
        if asset_bibles:
            selected_id = _select_asset_bible(asset_bibles, ui=ui, translate=translate)
            selected_asset_bible = find_item(asset_bibles, "asset_bible_id", selected_id) or {}
            _render_asset_bible_summary(selected_asset_bible, ui=ui, translate=translate)
        else:
            selected_id = ""
            selected_asset_bible = {}
            ui.caption(translate("ip_design.asset_bible.empty"))

        asset_bible_id = keyed_text_input(
            ui,
            translate("ip_design.asset_bible.id"),
            key=IPSessionKeys.ASSET_BIBLE.asset_bible_id,
            value=selected_id,
        )

    return selected_asset_bible, asset_bible_id


# ── Tab: IP Profile ──

def _render_ip_profile_tab(
    *,
    ip_design_client,
    workspace_id: str,
    project_id: str,
    asset_bible_id: str,
    selected_asset_bible: dict[str, Any],
    asset_bibles: list[dict[str, Any]],
    ui,
    translate: Translate,
) -> None:
    ip_profiles = list_of_dicts(selected_asset_bible.get("ip_profiles"))
    ip_profile_options = [
        first_text(p.get("ip_profile_id")) for p in ip_profiles if first_text(p.get("ip_profile_id"))
    ]
    ip_profile_options.append("__new_ip__")

    def _on_ip_profile_change():
        _clear_ip_form_session_state(ui)
        st.session_state["_form_populated"] = False

    selected_ip_id = ui.selectbox(
        translate("ip_design.asset_bible.ip_profile"),
        ip_profile_options,
        key=IPSessionKeys.FORM.ip_profile_select,
        format_func=lambda x: translate("ip_design.asset_bible.new_ip_profile") if x == "__new_ip__" else x,
        on_change=_on_ip_profile_change,
    )

    if selected_ip_id == "__new_ip__":
        ip_profile_dict = {}
    else:
        ip_profile_dict = _find_ip_profile(selected_asset_bible, selected_ip_id)

    if ip_profile_dict and not st.session_state.get("_form_populated"):
        ip_profile_draft = _to_ip_profile_draft(ip_profile_dict)
        populate_form_from_model(ip_profile_draft, IPSessionKeys.FORM)
        st.session_state[IPSessionKeys.FORM.color_palette] = _read_color_palette_prompt(
            ip_profile_dict.get("color_palette")
        )
        st.session_state[IPSessionKeys.FORM.role_presets] = "\n".join(
            text_list(ip_profile_dict.get("role_presets"))
        )
        st.session_state["_form_populated"] = True

    # Block 1: Basic Settings
    with ui.container(border=True):
        ui.caption(translate("ip_design.asset_bible.section_basic"))
        ip_type = _render_select_or_custom(
            ui,
            translate("ip_design.asset_bible.ip_type"),
            key=IPSessionKeys.FORM.ip_type,
            value=first_text(ip_profile_dict.get("ip_type")),
            options=["cartoon_animal", "anime_human", "hybrid_real_anime", "line_drawing", "3d_cartoon"],
        )
        keyed_text_input(
            ui,
            translate("ip_design.asset_bible.ip_profile_id"),
            key=IPSessionKeys.FORM.ip_profile_id,
            value=first_text(ip_profile_dict.get("ip_profile_id")),
        )
        keyed_text_input(
            ui,
            translate("ip_design.asset_bible.ip_name"),
            key=IPSessionKeys.FORM.name,
            value=first_text(ip_profile_dict.get("name")),
        )
        keyed_text_area(
            ui,
            translate("ip_design.asset_bible.logline"),
            key=IPSessionKeys.FORM.logline,
            value=first_text(ip_profile_dict.get("logline")),
            height=68,
        )
        keyed_text_area(
            ui,
            translate("ip_design.asset_bible.visual_summary"),
            key=IPSessionKeys.FORM.visual_summary,
            value=first_text(ip_profile_dict.get("visual_summary")),
            height=88,
        )

    # Block 2: Visual Anchors
    with ui.container(border=True):
        ui.caption(translate("ip_design.asset_bible.section_visual"))
        keyed_text_input(
            ui,
            translate("ip_design.asset_bible.identity_lock"),
            key=IPSessionKeys.FORM.identity_lock,
            value=", ".join(text_list(ip_profile_dict.get("identity_lock"))),
        )
        keyed_text_input(
            ui,
            translate("ip_design.asset_bible.color_palette"),
            key=IPSessionKeys.FORM.color_palette,
            value=_read_color_palette_prompt(ip_profile_dict.get("color_palette")),
        )
        keyed_text_input(
            ui,
            translate("ip_design.asset_bible.minimal_traits"),
            key=IPSessionKeys.FORM.minimal_traits,
            value=", ".join(text_list(ip_profile_dict.get("minimal_traits"))),
        )

    # Block 3: Adaptable Items
    with ui.container(border=True):
        ui.caption(translate("ip_design.asset_bible.section_adaptable"))
        keyed_text_input(
            ui,
            translate("ip_design.asset_bible.adaptable_slots"),
            key=IPSessionKeys.FORM.adaptable_slots,
            value=", ".join(text_list(ip_profile_dict.get("adaptable_slots"))),
        )

    # Block 4: Replacement Strategy
    with ui.container(border=True):
        ui.caption(translate("ip_design.asset_bible.section_replacement"))
        _render_select_or_custom(
            ui,
            translate("ip_design.asset_bible.default_slot_preference"),
            key=IPSessionKeys.FORM.default_slot_preference,
            value=first_text(ip_profile_dict.get("default_slot_preference"), "prefer_supporting"),
            options=["prefer_supporting", "prefer_main", "auto", "minimal"],
        )
        keyed_text_input(
            ui,
            translate("ip_design.asset_bible.presence_spectrum"),
            key=IPSessionKeys.FORM.presence_spectrum,
            value=", ".join(text_list(ip_profile_dict.get("presence_spectrum"))),
        )

    # Block 5: Role Capabilities
    with ui.container(border=True):
        ui.caption(translate("ip_design.asset_bible.section_roles"))
        keyed_text_area(
            ui,
            translate("ip_design.asset_bible.role_presets"),
            key=IPSessionKeys.FORM.role_presets,
            value="\n".join(text_list(ip_profile_dict.get("role_presets"))),
            height=136,
        )

    # Block 6: Constraints
    with ui.container(border=True):
        ui.caption(translate("ip_design.asset_bible.section_constraints"))
        keyed_text_input(
            ui,
            translate("ip_design.asset_bible.negative_constraints"),
            key=IPSessionKeys.FORM.negative_constraints,
            value=", ".join(text_list(ip_profile_dict.get("negative_constraints"))),
        )
        keyed_text_input(
            ui,
            translate("ip_design.asset_bible.semantic_boundary"),
            key=IPSessionKeys.FORM.semantic_boundary,
            value=", ".join(text_list(ip_profile_dict.get("semantic_boundary"))),
        )
        keyed_text_input(
            ui,
            translate("ip_design.asset_bible.identity_suppression_rules"),
            key=IPSessionKeys.FORM.identity_suppression_rules,
            value=", ".join(text_list(ip_profile_dict.get("identity_suppression_rules"))),
        )
        keyed_text_input(
            ui,
            translate("ip_design.asset_bible.forbidden_elements"),
            key=IPSessionKeys.FORM.forbidden_elements,
            value=", ".join(text_list(ip_profile_dict.get("forbidden_elements"))),
        )

    # Block 7: Visible Text
    with ui.container(border=True):
        ui.caption(translate("ip_design.asset_bible.section_text"))
        keyed_text_input(
            ui,
            translate("ip_design.asset_bible.visible_text_whitelist"),
            key=IPSessionKeys.FORM.visible_text_whitelist,
            value=", ".join(text_list(ip_profile_dict.get("visible_text_whitelist"))),
        )

    if _ip_profile_ready_for_generation(ip_profile_dict):
        ui.caption(translate("ip_design.asset_bible.generation_available"))
    else:
        ui.caption(translate("ip_design.asset_bible.generation_unavailable"))

    if ui.button(
        translate("ip_design.asset_bible.save"),
        key="ip_design_save_asset_bible",
    ):
        asset_bible_id_form = st.session_state.get(IPSessionKeys.ASSET_BIBLE.asset_bible_id, "")
        ip_profile_id_form = st.session_state.get(IPSessionKeys.FORM.ip_profile_id, "")
        ip_name_form = st.session_state.get(IPSessionKeys.FORM.name, "")
        if not all(v.strip() for v in (asset_bible_id_form, ip_profile_id_form, ip_name_form)):
            ui.error(translate("ip_design.asset_bible.missing_required"))
            return

        # Build model from form for simple fields
        draft = build_model_from_form(IPProfileDraft, IPSessionKeys.FORM)
        ip_profile_save = draft.model_dump()

        # Carry over carrier fields from original data (no widget → not in model_dump)
        _CARRIER_FIELDS: list[tuple[str, type]] = [
            ("identity_anchors", list),
            ("variable_slots", list),
            ("world_hint", str),
            ("style_hint", str),
            ("image_text_palette", dict),
            ("metadata", dict),
        ]
        for field_name, field_type in _CARRIER_FIELDS:
            raw = ip_profile_dict.get(field_name)
            if field_type is list:
                ip_profile_save[field_name] = text_list(raw) if raw else []
            elif field_type is dict:
                ip_profile_save[field_name] = raw if isinstance(raw, dict) else {}
            else:
                ip_profile_save[field_name] = first_text(raw) if raw else ""

        # Patch role_presets (newline-split from text area)
        raw_role_presets = st.session_state.get(IPSessionKeys.FORM.role_presets, "")
        ip_profile_save["role_presets"] = [
            s.strip() for s in raw_role_presets.splitlines() if s.strip()
        ]

        # Patch color_palette
        raw_color_rules = st.session_state.get(IPSessionKeys.FORM.color_palette, "")
        existing_color_palette = ip_profile_dict.get("color_palette", {})
        ip_profile_save["color_palette"] = build_color_palette_prompt_entries(
            existing_color_palette, raw_color_rules,
        )

        try:
            is_existing = bool(find_item(asset_bibles, "asset_bible_id", asset_bible_id_form))
            payload = _build_asset_bible_save_payload(
                source_asset_bible=selected_asset_bible if is_existing else {},
                ip_profile=ip_profile_save,
            )
            ip_design_client.save_asset_bible(
                workspace_id=workspace_id,
                project_id=project_id,
                asset_bible_id=asset_bible_id_form,
                payload=payload,
            )
        except Exception:
            ui.error(translate("ip_design.asset_bible.save_failed"))
        else:
            ui.success(translate("ip_design.asset_bible.saved"))


# ── Tab: Scene Cast ──

def _render_scene_cast_tab(
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
                find_item(scene_casts, "scene_cast_id", selected_scene_cast_id) or {}
            )
            _render_scene_cast_summary(selected_scene_cast, ui=ui, translate=translate)
        else:
            selected_scene_cast_id = ""
            selected_scene_cast = {}
            ui.caption(translate("ip_design.scene_cast.empty"))

        keyed_text_input(
            ui,
            translate("ip_design.scene_cast.id"),
            key=IPSessionKeys.SCENE_CAST.scene_cast_id,
            value=selected_scene_cast_id,
        )
        keyed_text_input(
            ui,
            translate("ip_design.scene_cast.storyboard_plan_id"),
            key=IPSessionKeys.SCENE_CAST.storyboard_plan_id,
            value=first_text(selected_scene_cast.get("storyboard_plan_id")),
        )
        keyed_text_input(
            ui,
            translate("ip_design.scene_cast.frame_id"),
            key=IPSessionKeys.SCENE_CAST.frame_id,
            value=first_text(selected_scene_cast.get("frame_id")),
        )
        keyed_text_input(
            ui,
            translate("ip_design.scene_cast.character_ids"),
            key=IPSessionKeys.SCENE_CAST.character_ids,
            value=", ".join(text_list(selected_scene_cast.get("character_ids"))),
        )
        keyed_text_input(
            ui,
            translate("ip_design.scene_cast.scene_id"),
            key=IPSessionKeys.SCENE_CAST.scene_id,
            value=first_text(selected_scene_cast.get("scene_id")),
        )
        keyed_text_input(
            ui,
            translate("ip_design.scene_cast.prop_ids"),
            key=IPSessionKeys.SCENE_CAST.prop_ids,
            value=", ".join(text_list(selected_scene_cast.get("prop_ids"))),
        )
        keyed_text_input(
            ui,
            translate("ip_design.scene_cast.style_id"),
            key=IPSessionKeys.SCENE_CAST.style_id,
            value=first_text(selected_scene_cast.get("style_id")),
        )
        keyed_text_area(
            ui,
            translate("ip_design.scene_cast.continuity_notes"),
            key=IPSessionKeys.SCENE_CAST.continuity_notes,
            value="\n".join(text_list(selected_scene_cast.get("continuity_notes"))),
            height=88,
        )

        col1, col2 = ui.columns([1, 1])
        with col1:
            if ui.button(
                translate("ip_design.scene_cast.save"),
                key="ip_design_save_scene_cast",
            ):
                scene_cast_id = st.session_state.get(IPSessionKeys.SCENE_CAST.scene_cast_id, "")
                storyboard_plan_id = st.session_state.get(IPSessionKeys.SCENE_CAST.storyboard_plan_id, "")
                frame_id = st.session_state.get(IPSessionKeys.SCENE_CAST.frame_id, "")
                if not all(v.strip() for v in (scene_cast_id, storyboard_plan_id, frame_id)):
                    ui.error(translate("ip_design.scene_cast.missing_required"))
                else:
                    payload = {
                        "storyboard_plan_id": storyboard_plan_id,
                        "frame_id": frame_id,
                        "character_ids": split_csv(st.session_state.get(IPSessionKeys.SCENE_CAST.character_ids, "")),
                        "scene_id": st.session_state.get(IPSessionKeys.SCENE_CAST.scene_id, ""),
                        "prop_ids": split_csv(st.session_state.get(IPSessionKeys.SCENE_CAST.prop_ids, "")),
                        "style_id": st.session_state.get(IPSessionKeys.SCENE_CAST.style_id, ""),
                        "continuity_notes": [
                            s.strip()
                            for s in st.session_state.get(IPSessionKeys.SCENE_CAST.continuity_notes, "").splitlines()
                            if s.strip()
                        ],
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

        with col2:
            if hasattr(ip_design_client, "delete_scene_cast") and selected_scene_cast_id:
                if ui.button(
                    translate("ip_design.scene_cast.delete"),
                    key="ip_design_delete_scene_cast",
                ):
                    try:
                        ip_design_client.delete_scene_cast(
                            workspace_id=workspace_id,
                            project_id=project_id,
                            asset_bible_id=asset_bible_id,
                            scene_cast_id=selected_scene_cast_id,
                        )
                    except Exception:
                        ui.error(translate("ip_design.scene_cast.delete_failed"))
                    else:
                        ui.success(translate("ip_design.scene_cast.deleted"))


# ── Tab: Presets ──

def _render_presets_tab(
    *,
    ip_design_client,
    workspace_id: str,
    project_id: str,
    ui,
    translate: Translate,
) -> None:
    _render_asset_bible_preset_import(
        ip_design_client=ip_design_client,
        workspace_id=workspace_id,
        project_id=project_id,
        ui=ui,
        translate=translate,
    )


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
        presets = list_of_dicts(ip_design_client.list_asset_bible_presets())
    except Exception:
        ui.caption(translate("ip_design.asset_bible.presets_load_failed"))
        return {"saved": False}
    if not presets:
        return {"saved": False}

    preset_ids = [
        first_text(item.get("preset_id"))
        for item in presets
        if first_text(item.get("preset_id"))
    ]
    if not preset_ids:
        return {"saved": False}
    selected_preset_id = first_text(
        ui.selectbox(
            translate("ip_design.asset_bible.builtin_presets"),
            preset_ids,
            key=IPSessionKeys.PRESET.select,
            format_func=lambda preset_id: _format_asset_bible_preset_option(
                find_item(presets, "preset_id", preset_id) or {}
            ),
        )
    )
    import_asset_bible_id = keyed_text_input(
        ui,
        translate("ip_design.asset_bible.import_id"),
        key=IPSessionKeys.PRESET.import_id,
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
            conflict_policy="overwrite",
        )
    except Exception:
        ui.error(translate("ip_design.asset_bible.import_failed"))
        return {"asset_bible_id": import_asset_bible_id, "saved": False}
    ui.success(translate("ip_design.asset_bible.imported"))
    return {"asset_bible_id": "", "saved": True}


# ── Tab: History ──

def _render_history_tab(
    *,
    ip_design_client,
    asset_bible_id: str,
    ui,
    translate: Translate,
) -> None:
    ui.markdown(f"#### {translate('ip_design.tab.history')}")
    if hasattr(ip_design_client, "get_asset_bible_history"):
        try:
            history = ip_design_client.get_asset_bible_history(
                asset_bible_id=asset_bible_id,
            )
            entries = list_of_dicts(history.get("entries", [])) if isinstance(history, dict) else []
            if entries:
                for entry in entries:
                    timestamp = first_text(entry.get("timestamp"))
                    action = first_text(entry.get("action"))
                    summary = first_text(entry.get("summary"))
                    if timestamp or action:
                        ui.caption(f"{timestamp} - {action}: {summary}" if summary else f"{timestamp} - {action}")
            else:
                ui.caption(translate("ip_design.history.empty"))
        except Exception:
            ui.caption(translate("ip_design.history.unavailable"))
    else:
        ui.caption(translate("ip_design.history.unavailable"))


# ── Tab: Readiness ──

def _render_readiness_tab(
    *,
    selected_asset_bible: dict[str, Any],
    ui,
    translate: Translate,
) -> None:
    ui.markdown(f"#### {translate('ip_design.tab.readiness')}")
    ip_profiles = list_of_dicts(selected_asset_bible.get("ip_profiles"))
    if not ip_profiles:
        ui.caption(translate("ip_design.readiness.no_profiles"))
        return

    for profile in ip_profiles:
        profile_id = first_text(profile.get("ip_profile_id"), profile.get("name"))
        ui.markdown(f"**{profile_id}**")
        identity_terms = list(ip_generation_identity_terms(profile))
        if identity_terms:
            ui.caption(f"{translate('ip_design.readiness.ready')}: {', '.join(identity_terms)}")
        else:
            ui.caption(translate("ip_design.readiness.not_ready"))
            missing = []
            for field in FieldId:
                if not profile.get(field.value):
                    missing.append(field.value)
            if missing:
                ui.caption(f"{translate('ip_design.readiness.missing_fields')}: {', '.join(missing)}")


# ── Selection helpers ──

def _select_asset_bible(asset_bibles: list[dict[str, Any]], *, ui, translate: Translate) -> str:
    def _on_asset_bible_change():
        _clear_ip_form_session_state(ui)
        ui.session_state.pop(IPSessionKeys.ASSET_BIBLE.asset_bible_id, None)
        ui.session_state.pop(IPSessionKeys.FORM.ip_profile_select, None)

    options = [first_text(item.get("asset_bible_id")) for item in asset_bibles]
    options = [option for option in options if option]
    selected = ui.selectbox(
        translate("ip_design.asset_bible.select"),
        options,
        key=IPSessionKeys.ASSET_BIBLE.select,
        format_func=lambda item_id: _format_asset_bible_option(
            find_item(asset_bibles, "asset_bible_id", item_id) or {}
        ),
        on_change=_on_asset_bible_change,
    )
    return first_text(selected)


def _select_scene_cast(scene_casts: list[dict[str, Any]], *, ui, translate: Translate) -> str:
    options = [first_text(item.get("scene_cast_id")) for item in scene_casts]
    options = [option for option in options if option]
    selected = ui.selectbox(
        translate("ip_design.scene_cast.select"),
        options,
        key=IPSessionKeys.SCENE_CAST.select,
        format_func=lambda item_id: _format_scene_cast_option(
            find_item(scene_casts, "scene_cast_id", item_id) or {}
        ),
    )
    return first_text(selected)


# ── Summary renderers ──

def _render_asset_bible_summary(
    asset_bible: dict[str, Any],
    *,
    ui,
    translate: Translate,
) -> None:
    ip_count = len(list_of_dicts(asset_bible.get("ip_profiles")))
    summary = (
        f"{first_text(asset_bible.get('asset_bible_id'))} · "
        f"{translate('ip_design.asset_bible.counts', characters=len(list_of_dicts(asset_bible.get('character_profiles'))), scenes=len(list_of_dicts(asset_bible.get('scene_assets'))), props=len(list_of_dicts(asset_bible.get('prop_assets'))), styles=len(list_of_dicts(asset_bible.get('style_profiles'))))}"
    )
    if ip_count:
        summary += f" · IP×{ip_count}"
    ui.caption(summary)


def _render_scene_cast_summary(
    scene_cast: dict[str, Any],
    *,
    ui,
    translate: Translate,
) -> None:
    summary = translate(
        "ip_design.scene_cast.summary",
        scene_cast_id=first_text(scene_cast.get("scene_cast_id")),
        storyboard_plan_id=first_text(scene_cast.get("storyboard_plan_id")),
        frame_id=first_text(scene_cast.get("frame_id")),
        characters=", ".join(text_list(scene_cast.get("character_ids"))),
        scene_id=first_text(scene_cast.get("scene_id")),
        props=", ".join(text_list(scene_cast.get("prop_ids"))),
        style_id=first_text(scene_cast.get("style_id")),
    )
    ui.caption(summary)


# ── Formatting helpers ──

def _format_asset_bible_option(asset_bible: dict[str, Any]) -> str:
    asset_bible_id = first_text(asset_bible.get("asset_bible_id"))
    ip_count = len(list_of_dicts(asset_bible.get("ip_profiles")))
    ip_part = _first_ip_name(asset_bible)
    if ip_count > 1:
        ip_part += f" +{ip_count - 1}"
    return " · ".join(item for item in (asset_bible_id, ip_part) if item)


def _format_asset_bible_preset_option(preset: dict[str, Any]) -> str:
    return first_text(preset.get("display_name"), preset.get("preset_id"))


def _format_scene_cast_option(scene_cast: dict[str, Any]) -> str:
    scene_cast_id = first_text(scene_cast.get("scene_cast_id"))
    frame = "/".join(
        item
        for item in (
            first_text(scene_cast.get("storyboard_plan_id")),
            first_text(scene_cast.get("frame_id")),
        )
        if item
    )
    return " · ".join(item for item in (scene_cast_id, frame) if item)


def _derive_asset_bible_id_from_preset(preset_id: str) -> str:
    base = preset_id.removeprefix("builtin_asset_bible_")
    return f"{base}_bible" if base else ""


def _first_ip_name(asset_bible: dict[str, Any]) -> str:
    profiles = list_of_dicts(asset_bible.get("ip_profiles"))
    return first_text(profiles[0].get("name")) if profiles else ""


def _first_ip_profile_id(asset_bible: dict[str, Any]) -> str:
    profiles = list_of_dicts(asset_bible.get("ip_profiles"))
    return first_text(profiles[0].get("ip_profile_id")) if profiles else ""


def _find_ip_profile(asset_bible: dict[str, Any], ip_profile_id: str) -> dict[str, Any]:
    profiles = list_of_dicts(asset_bible.get("ip_profiles"))
    for profile in profiles:
        if first_text(profile.get("ip_profile_id")) == first_text(ip_profile_id):
            return profile
    return {}


def _clear_ip_form_session_state(ui) -> None:
    preserve = {
        IPSessionKeys.ASSET_BIBLE.select,
        IPSessionKeys.ASSET_BIBLE.asset_bible_id,
        IPSessionKeys.FORM.ip_profile_select,
        IPSessionKeys.PRESET.select,
        IPSessionKeys.PRESET.import_id,
        "ip_design_save_asset_bible",
        "ip_design_import_builtin_asset_bible",
        "ip_design_save_scene_cast",
        "ip_design_delete_scene_cast",
    }
    for key in list(getattr(ui, "session_state", {}).keys()):
        if key.startswith("ip_design_") and key not in preserve:
            del ui.session_state[key]


def _build_asset_bible_save_payload(
    *,
    source_asset_bible: dict[str, Any],
    ip_profile: dict[str, Any],
) -> dict[str, Any]:
    if source_asset_bible:
        payload = build_asset_bible_draft_payload_from_response(source_asset_bible)
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


def _ip_profile_ready_for_generation(ip_profile: dict[str, Any]) -> bool:
    return bool(ip_generation_identity_terms(ip_profile))


def _render_select_or_custom(
    ui,
    label: str,
    *,
    key: str,
    value: str = "",
    options: list[str],
) -> str:
    custom_value = "__custom__"
    all_options = [*options, custom_value]
    current_value = first_text(value)
    select_index = all_options.index(current_value) if current_value in all_options else len(all_options) - 1

    selected = ui.selectbox(label, all_options, key=f"{key}_select", index=select_index)

    if selected == custom_value:
        return keyed_text_input(ui, label, key=key, value=current_value if current_value not in options else "")
    st.session_state[key] = selected
    return selected


def _read_color_palette_prompt(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    prompts: list[str] = []
    for key, item in value.items():
        if not str(key).startswith("rule_"):
            continue
        if isinstance(item, dict):
            prompt = first_text(item.get("prompt"))
            if prompt:
                prompts.append(prompt)
    return ", ".join(prompts)


__all__ = ["render_ip_design_workbench"]
