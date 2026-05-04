from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from html import escape
from typing import Any

import streamlit as st
import streamlit.components.v1 as components

from pixelle_video.models.layered_template import LayeredTemplateSpec
from pixelle_video.models.media_placement import MediaPlacement, resolve_media_placement

PresetSelection = dict[str, Any]
PresetSelectionCallback = Callable[[PresetSelection], Any]
_PENDING_SELECTION_SESSION_KEY = "_layout_preview_workbench_selection"


@dataclass(frozen=True)
class TrustedPreviewHTML:
    html: str
    width: int | None = None
    height: int | None = None


@dataclass(frozen=True)
class DefaultLayoutSummary:
    canvas_width: int
    canvas_height: int
    media_width: int
    media_height: int
    media_placement: MediaPlacement
    render_summary: str | None = None
    template_summary: str | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | object) -> "DefaultLayoutSummary":
        return cls(
            canvas_width=_positive_int_field(value, "canvas_width"),
            canvas_height=_positive_int_field(value, "canvas_height"),
            media_width=_positive_int_field(value, "media_width"),
            media_height=_positive_int_field(value, "media_height"),
            media_placement=resolve_media_placement(
                _read_field(value, "media_placement")
            ),
            render_summary=_optional_text_field(value, "render_summary"),
            template_summary=_optional_text_field(value, "template_summary"),
        )

_RECENT_TITLE = "\u6700\u8fd1\u6a21\u677f\u5feb\u6377"
_NO_RECENT = "\u6682\u65e0\u6700\u8fd1\u6a21\u677f\u3002"
_APPLY_PREFIX = "\u5957\u7528"
_RECENT_TEMPLATE_LABELS = (
    "\u6a21\u677f\u4e00",
    "\u6a21\u677f\u4e8c",
    "\u6a21\u677f\u4e09",
    "\u6a21\u677f\u56db",
    "\u6a21\u677f\u4e94",
)
_APPLY_HELP = (
    "\u9009\u62e9\u6700\u8fd1\u6a21\u677f\uff0c\u4e3b\u5165\u53e3\u4f1a"
    "\u636e\u6b64\u56de\u586b\u5b8c\u6574\u89c4\u683c\u3002"
)
_CURRENT_SPEC = "\u5f53\u524d\u89c4\u683c"
_CURRENT_TEMPLATE_RULES = "\u5f53\u524d\u6a21\u677f\u89c4\u5219"
_NO_SPEC = "\u6682\u65e0\u53ef\u9884\u89c8\u7684\u6392\u7248\u89c4\u683c\u3002"
_CANVAS_SIZE = "\u753b\u5e03\u5c3a\u5bf8"
_MEDIA_SIZE = "\u5a92\u4f53\u5c3a\u5bf8"
_MEDIA_PLACEMENT = "\u4e3b\u5a92\u4f53\u4f4d\u7f6e"
_LAYER_COUNT = "\u56fe\u5c42\u6570\u91cf"
_RENDER_SUMMARY = "\u6e32\u67d3\u6458\u8981"
_TEMPLATE_SUMMARY = "\u6a21\u677f\u6458\u8981"
_UNKNOWN_RENDER = "\u672a\u63d0\u4f9b"
_NO_PREVIEW_HTML = (
    "\u6682\u65e0\u9884\u89c8 HTML\uff0c\u5b8c\u6210\u4e00\u6b21"
    "\u670d\u52a1\u7aef\u9884\u89c8\u540e\u4f1a\u663e\u793a\u5728\u8fd9\u91cc\u3002"
)
_REFRESH_PREVIEW_FRAME = "\u5237\u65b0\u771f\u5b9e\u9884\u89c8\u5e27"
_SAVE_MY_TEMPLATE = "\u4fdd\u5b58\u4e3a\u6211\u7684\u6a21\u677f"
_DELETE_RECENT_PRESET = "\u5220\u9664"
_DELETE_RECENT_HELP = "\u4ece\u6700\u8fd1\u6a21\u677f\u5feb\u6377\u4e2d\u79fb\u9664\u8fd9\u4e2a\u6a21\u677f\u3002"


def render_layout_preview_workbench(
    *,
    spec_payload: LayeredTemplateSpec | Mapping[str, Any] | None,
    recent_presets: Sequence[Mapping[str, Any] | object] | None = None,
    preview_html: TrustedPreviewHTML | str | None = None,
    real_preview_frame: Mapping[str, Any] | object | None = None,
    media_placement: MediaPlacement | Mapping[str, Any] | None = None,
    render_summary: str | None = None,
    template_summary: str | None = None,
    default_layout_summary: DefaultLayoutSummary | Mapping[str, Any] | object | None = None,
    on_preset_selected: PresetSelectionCallback | None = None,
    key_suffix: str = "",
    ui=st,
) -> PresetSelection | None:
    """Render the right-column layout preview workbench.

    The workbench is deliberately driven by explicit payloads. It may use
    session_state to surface a button click, but it does not treat Streamlit
    session_state, template_params, or ad-hoc HTML as layout facts.
    """

    spec = _coerce_spec(spec_payload)
    default_summary = _coerce_default_layout_summary(default_layout_summary)
    presets = _recent_presets(recent_presets)
    selected_action: PresetSelection | None = (
        _consume_action(ui=ui, key_suffix=key_suffix) if spec is not None else None
    )
    selected_preset = _consume_pending_selection(ui=ui, presets=presets)
    if selected_preset is not None and on_preset_selected is not None:
        on_preset_selected(selected_preset)

    with ui.container():
        ui.markdown(_build_workbench_css(), unsafe_allow_html=True)
        if spec is not None:
            rendered_action = _render_workbench_rows(
                ui=ui,
                spec=spec,
                media_placement=media_placement,
                render_summary=render_summary,
                template_summary=template_summary,
                key_suffix=key_suffix,
            )
            if selected_action is None:
                selected_action = rendered_action
        elif default_summary is not None:
            ui.markdown(
                _build_default_summary_html(default_summary),
                unsafe_allow_html=True,
            )
        else:
            ui.markdown(
                _build_summary_html(
                    spec=spec,
                    media_placement=media_placement,
                    render_summary=render_summary,
                    template_summary=template_summary,
                ),
                unsafe_allow_html=True,
            )
        recent_action = _render_recent_presets(
            ui=ui,
            presets=presets,
            key_suffix=key_suffix,
        )
        if selected_action is None:
            selected_action = recent_action
        if selected_preset is None:
            selected_preset = _consume_pending_selection(ui=ui, presets=presets)
            if selected_preset is not None and on_preset_selected is not None:
                on_preset_selected(selected_preset)

        _render_preview_container(
            ui=ui,
            spec=spec,
            preview_html=preview_html,
            real_preview_frame=real_preview_frame,
        )

    return selected_action or selected_preset


def _render_workbench_rows(
    *,
    ui,
    spec: LayeredTemplateSpec,
    media_placement: MediaPlacement | Mapping[str, Any] | None,
    render_summary: str | None,
    template_summary: str | None,
    key_suffix: str,
) -> PresetSelection | None:
    resolved_render_summary, resolved_template_summary = _resolved_summaries(
        spec=spec,
        render_summary=render_summary,
        template_summary=template_summary,
    )
    if not hasattr(ui, "columns"):
        selected_action = _render_workbench_actions(ui=ui, key_suffix=key_suffix)
        ui.markdown(
            _build_workbench_rows_html(
                spec=spec,
                media_placement=media_placement,
                render_summary=resolved_render_summary,
                template_summary=resolved_template_summary,
            ),
            unsafe_allow_html=True,
        )
        return selected_action

    selected_action: PresetSelection | None = None
    with ui.container(key=_workbench_row_key("actions_row", key_suffix=key_suffix)):
        selected_action = _render_workbench_actions(ui=ui, key_suffix=key_suffix)
    with ui.container(key=_workbench_row_key("metric_row", key_suffix=key_suffix)):
        ui.markdown(
            _build_summary_grid_html(spec=spec, media_placement=media_placement),
            unsafe_allow_html=True,
        )
    with ui.container(key=_workbench_row_key("meta_row", key_suffix=key_suffix)):
        ui.markdown(
            _build_meta_html(
                render_summary=resolved_render_summary,
                template_summary=resolved_template_summary,
            ),
            unsafe_allow_html=True,
        )
    return selected_action


def _render_workbench_actions(*, ui, key_suffix: str) -> PresetSelection | None:
    action_columns = _columns(ui, 2, gap="small")
    if action_columns is None:
        refresh_clicked = ui.button(
            _REFRESH_PREVIEW_FRAME,
            key=_action_button_key("refresh_preview_frame", key_suffix=key_suffix),
            width="stretch",
        )
        save_clicked = ui.button(
            _SAVE_MY_TEMPLATE,
            key=_action_button_key("save_template", key_suffix=key_suffix),
            width="stretch",
        )
    else:
        with action_columns[0]:
            refresh_clicked = ui.button(
                _REFRESH_PREVIEW_FRAME,
                key=_action_button_key("refresh_preview_frame", key_suffix=key_suffix),
                width="stretch",
            )
        with action_columns[1]:
            save_clicked = ui.button(
                _SAVE_MY_TEMPLATE,
                key=_action_button_key("save_template", key_suffix=key_suffix),
                width="stretch",
            )
    if refresh_clicked:
        return {"action": "refresh_preview_frame"}
    if save_clicked:
        return {"action": "save_template"}
    return None


def _consume_action(*, ui, key_suffix: str) -> PresetSelection | None:
    action_keys = {
        _action_button_key("refresh_preview_frame", key_suffix=key_suffix): "refresh_preview_frame",
        _action_button_key("save_template", key_suffix=key_suffix): "save_template",
        "layout_preview_refresh_preview_frame": "refresh_preview_frame",
        "layout_preview_save_template": "save_template",
    }
    for key, action in action_keys.items():
        if ui.session_state.get(key):
            return {"action": action}
    return None


def _render_recent_presets(
    *,
    ui,
    presets: list[dict[str, Any]],
    key_suffix: str,
) -> PresetSelection | None:
    if not presets:
        _caption(ui, _NO_RECENT)
        return None

    selected_action: PresetSelection | None = None
    with ui.container(key=_workbench_row_key("recent_presets", key_suffix=key_suffix)):
        ui.markdown(
            f"""
            <section class="layout-workbench-card layout-workbench-recent-card">
              <div class="layout-workbench-section-title">{_RECENT_TITLE}</div>
            </section>
            """,
            unsafe_allow_html=True,
        )
        for index, preset in enumerate(presets):
            preset_id = str(preset["preset_id"])
            label = _recent_preset_display_label(index)
            with ui.container(key=_recent_preset_item_key(preset_id, key_suffix=key_suffix)):
                ui.markdown(
                    f"""
                    <div class="layout-workbench-recent-item">
                      <span class="layout-workbench-recent-check" aria-hidden="true"></span>
                      <div class="layout-workbench-recent-copy">
                        <div class="layout-workbench-recent-name">{escape(label)}</div>
                        <div class="layout-workbench-recent-meta">{escape(_recent_preset_summary(preset))}</div>
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                action_columns = _columns(ui, [0.75, 0.25], gap="small")
                if action_columns is None:
                    if ui.button(
                        label,
                        key=_recent_preset_button_key(preset_id, key_suffix=key_suffix),
                        help=_recent_preset_help(preset),
                        width="stretch",
                    ):
                        ui.session_state[_PENDING_SELECTION_SESSION_KEY] = preset_id
                    if ui.button(
                        _DELETE_RECENT_PRESET,
                        key=_recent_preset_delete_button_key(preset_id, key_suffix=key_suffix),
                        help=_DELETE_RECENT_HELP,
                        width="stretch",
                    ):
                        selected_action = {
                            "action": "delete_recent_preset",
                            "preset_id": preset_id,
                        }
                    continue
                with action_columns[0]:
                    if ui.button(
                        label,
                        key=_recent_preset_button_key(preset_id, key_suffix=key_suffix),
                        help=_recent_preset_help(preset),
                        width="stretch",
                    ):
                        ui.session_state[_PENDING_SELECTION_SESSION_KEY] = preset_id
                with action_columns[1]:
                    if ui.button(
                        _DELETE_RECENT_PRESET,
                        key=_recent_preset_delete_button_key(preset_id, key_suffix=key_suffix),
                        help=_DELETE_RECENT_HELP,
                        width="stretch",
                    ):
                        selected_action = {
                            "action": "delete_recent_preset",
                            "preset_id": preset_id,
                        }
    return selected_action


def _render_recent_presets_legacy(
    *,
    ui,
    presets: list[dict[str, Any]],
    key_suffix: str,
) -> PresetSelection | None:
    if not presets:
        _caption(ui, _NO_RECENT)
        return None

    selected_action: PresetSelection | None = None
    with ui.container(key=_workbench_row_key("recent_presets", key_suffix=key_suffix)):
        ui.markdown(
            f"""
            <section class="layout-workbench-card layout-workbench-recent-card">
              <div class="layout-workbench-section-title">{_RECENT_TITLE}</div>
            </section>
            """,
            unsafe_allow_html=True,
        )
        columns = _columns(ui, len(presets), gap="small")
        for index, preset in enumerate(presets):
            preset_id = str(preset["preset_id"])
            label = _recent_preset_display_label(index)
            if columns is None:
                if ui.button(
                    label,
                    key=_recent_preset_button_key(preset_id, key_suffix=key_suffix),
                    help=_recent_preset_help(preset),
                    width="content",
                ):
                    ui.session_state[_PENDING_SELECTION_SESSION_KEY] = preset_id
                if ui.button(
                    _DELETE_RECENT_PRESET,
                    key=_recent_preset_delete_button_key(preset_id, key_suffix=key_suffix),
                    help=_DELETE_RECENT_HELP,
                    width="content",
                ):
                    selected_action = {
                        "action": "delete_recent_preset",
                        "preset_id": preset_id,
                    }
            else:
                with columns[index]:
                    if ui.button(
                        label,
                        key=_recent_preset_button_key(preset_id, key_suffix=key_suffix),
                        help=_recent_preset_help(preset),
                        width="content",
                    ):
                        ui.session_state[_PENDING_SELECTION_SESSION_KEY] = preset_id
                    if ui.button(
                        _DELETE_RECENT_PRESET,
                        key=_recent_preset_delete_button_key(preset_id, key_suffix=key_suffix),
                        help=_DELETE_RECENT_HELP,
                        width="content",
                    ):
                        selected_action = {
                            "action": "delete_recent_preset",
                            "preset_id": preset_id,
                        }
    return selected_action


def _build_workbench_css() -> str:
    return f"""
    <style>
      .layout-workbench-copy {{
        color: #675b4b;
        font-size: 13px;
        line-height: 1.45;
        margin: 0 0 8px;
      }}
      .layout-workbench-card {{
        border: 1px solid rgba(80, 67, 44, .16);
        border-radius: 8px;
        margin: 8px 0;
        padding: 10px 12px;
        background: rgba(255, 255, 255, .62);
      }}
      .layout-workbench-actions-row,
      .layout-workbench-metric-row,
      .layout-workbench-meta-row {{
        container-type: inline-size;
        border: 1px solid rgba(80, 67, 44, .16);
        border-radius: 8px;
        margin: 8px 0;
        padding: 10px 12px;
        background: rgba(255, 255, 255, .64);
      }}
      .layout-workbench-actions-row {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(min(220px, 100%), max-content));
        gap: 10px;
        justify-content: start;
        align-items: center;
      }}
      .layout-workbench-metric-row {{
        display: grid;
        grid-template-columns: minmax(0, 1fr);
        place-items: center stretch;
      }}
      .layout-workbench-meta-row {{
        display: grid;
        grid-template-columns: minmax(0, 1fr);
        place-items: center stretch;
      }}
      .layout-workbench-actions-row-placeholder {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(min(220px, 100%), max-content));
        gap: 10px;
        justify-content: start;
      }}
      .layout-workbench-action-placeholder {{
        min-height: 42px;
      }}
      div[class*="st-key-layout_preview_actions_row"] {{
        container-type: inline-size;
        border: 1px solid rgba(80, 67, 44, .16);
        border-radius: 8px;
        margin: 8px 0;
        padding: 10px 12px;
        background: rgba(255, 255, 255, .64);
      }}
      div[class*="st-key-layout_preview_actions_row"] > div[data-testid="stVerticalBlock"] {{
        gap: 0;
      }}
      div[class*="st-key-layout_preview_actions_row"] div[data-testid="stHorizontalBlock"] {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(min(220px, 100%), max-content));
        gap: 10px !important;
        justify-content: start;
      }}
      div[class*="st-key-layout_preview_actions_row"] div[data-testid="stColumn"] {{
        width: auto !important;
        min-width: 0 !important;
        flex: 0 0 auto !important;
      }}
      div[class*="st-key-layout_preview_actions_row"] button {{
        min-height: 42px;
        padding-inline: 16px;
        white-space: nowrap;
      }}
      div[class*="st-key-layout_preview_metric_row"],
      div[class*="st-key-layout_preview_meta_row"] {{
        display: grid;
        grid-template-columns: minmax(0, 1fr);
        place-items: center stretch;
        container-type: inline-size;
        border: 1px solid rgba(80, 67, 44, .16);
        border-radius: 8px;
        margin: 8px 0;
        padding: 10px 12px;
        background: rgba(255, 255, 255, .64);
      }}
      div[class*="st-key-layout_preview_metric_row"] > div[data-testid="stVerticalBlock"],
      div[class*="st-key-layout_preview_meta_row"] > div[data-testid="stVerticalBlock"] {{
        width: 100% !important;
        max-width: 100% !important;
        gap: 0;
      }}
      div[class*="st-key-layout_preview_metric_row"] div[data-testid="stElementContainer"],
      div[class*="st-key-layout_preview_meta_row"] div[data-testid="stElementContainer"],
      div[class*="st-key-layout_preview_metric_row"] div[data-testid="stMarkdown"],
      div[class*="st-key-layout_preview_meta_row"] div[data-testid="stMarkdown"],
      div[class*="st-key-layout_preview_metric_row"] div[data-testid="stMarkdownContainer"],
      div[class*="st-key-layout_preview_meta_row"] div[data-testid="stMarkdownContainer"] {{
        width: 100% !important;
        max-width: 100% !important;
      }}
      .layout-workbench-section-title {{
        color: #352a1f;
        font-weight: 800;
        font-size: 13px;
        margin-bottom: 6px;
      }}
      div[class*="st-key-layout_preview_recent_presets"] {{
        border: 1px solid rgba(80, 67, 44, .16);
        border-radius: 8px;
        margin: 8px 0;
        padding: 8px 10px;
        background: rgba(255, 255, 255, .62);
      }}
      div[class*="st-key-layout_preview_recent_presets"] > div[data-testid="stVerticalBlock"] {{
        gap: 8px;
      }}
      div[class*="st-key-layout_preview_recent_presets"] div[data-testid="stHorizontalBlock"] {{
        display: grid;
        grid-template-columns: minmax(0, 1fr) 74px;
        align-items: center;
        gap: 8px !important;
      }}
      div[class*="st-key-layout_preview_recent_presets"] div[data-testid="stColumn"] {{
        width: 100% !important;
        min-width: 0 !important;
        flex: 1 1 auto !important;
      }}
      div[class*="st-key-layout_preview_recent_presets"] .layout-workbench-card {{
        border: 0;
        border-radius: 0;
        margin: 0;
        padding: 0;
        background: transparent;
      }}
      div[class*="st-key-layout_preview_recent_presets"] .layout-workbench-section-title {{
        margin-bottom: 2px;
      }}
      div[class*="st-key-layout_preview_recent_item_"] {{
        border: 1px solid rgba(80, 67, 44, .12);
        border-radius: 8px;
        padding: 7px 8px;
        background: #fffdf8;
      }}
      div[class*="st-key-layout_preview_recent_item_"] > div[data-testid="stVerticalBlock"] {{
        gap: 6px;
      }}
      .layout-workbench-recent-item {{
        display: grid;
        grid-template-columns: 22px minmax(0, 1fr);
        align-items: center;
        gap: 8px;
        min-width: 0;
      }}
      .layout-workbench-recent-check {{
        display: block;
        width: 18px;
        height: 18px;
        border: 1px solid rgba(255, 75, 75, .78);
        border-radius: 5px;
        background: #ff4b4b;
        box-shadow: inset 0 0 0 3px #ff4b4b;
      }}
      .layout-workbench-recent-copy {{
        min-width: 0;
      }}
      .layout-workbench-recent-name {{
        color: #352a1f;
        font-size: 12px;
        font-weight: 900;
        line-height: 1.25;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }}
      .layout-workbench-recent-meta {{
        color: #756854;
        font-size: 11px;
        font-weight: 700;
        line-height: 1.25;
        margin-top: 1px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }}
      div[class*="st-key-layout_preview_recent_presets"] div[data-testid="stMarkdown"],
      div[class*="st-key-layout_preview_recent_presets"] div[data-testid="stMarkdownContainer"],
      div[class*="st-key-layout_preview_recent_presets"] div[data-testid="stElementContainer"] {{
        width: 100% !important;
        max-width: 100% !important;
      }}
      div[class*="st-key-layout_preview_recent_presets"] button {{
        min-height: 28px;
        width: 100% !important;
        padding: 4px 8px;
        border: 1px solid rgba(80, 67, 44, .12);
        border-radius: 6px;
        background: #fffdf8;
        color: #352a1f;
        font-size: 12px;
        font-weight: 800;
        line-height: 1.25;
        white-space: nowrap;
        box-shadow: none;
      }}
      div[class*="st-key-layout_preview_recent_presets"] div[data-testid="stHorizontalBlock"] div[data-testid="stColumn"]:last-child button {{
        border-color: rgba(255, 75, 75, .18);
        color: #b23b3b;
        background: #fff8f7;
      }}
      .layout-workbench-grid {{
        display: grid;
        gap: 8px;
        grid-template-columns: repeat(3, minmax(0, 1fr));
      }}
      .layout-workbench-summary-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(min(160px, 100%), 1fr));
        gap: 10px;
        height: 100%;
      }}
      .layout-workbench-metric {{
        border-left: 4px solid #b98242;
        border-radius: 8px;
        padding: 8px 12px;
        background: #fffdf8;
      }}
      .layout-workbench-label {{
        color: #756854;
        font-size: 13px;
        font-weight: 800;
      }}
      .layout-workbench-value {{
        color: #211a13;
        font-size: 18px;
        font-weight: 850;
      }}
      .layout-workbench-summary-grid .layout-workbench-metric {{
        min-width: 0;
      }}
      .layout-workbench-summary-grid .layout-workbench-label {{
        white-space: nowrap;
      }}
      .layout-workbench-summary-grid .layout-workbench-value {{
        line-height: 1.25;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }}
      .layout-workbench-default-strip {{
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 6px;
        margin-top: 4px;
      }}
      .layout-workbench-default-chip {{
        min-width: 0;
        border: 1px solid rgba(80, 67, 44, .12);
        border-radius: 6px;
        padding: 4px 7px;
        background: #fffdf8;
        color: #5f5547;
        font-size: 12px;
        line-height: 1.25;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }}
      .layout-workbench-default-chip strong {{
        color: #352a1f;
        font-weight: 800;
      }}
      .layout-workbench-meta {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(min(220px, 100%), 1fr));
        align-items: center;
        gap: 10px;
        min-width: 0;
        color: #675b4b;
        font-size: 14px;
        line-height: 1.35;
      }}
      .layout-workbench-meta-line {{
        min-width: 0;
        border-radius: 8px;
        padding: 8px 10px;
        background: #fffdf8;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }}
      .layout-workbench-meta-line strong {{
        color: #352a1f;
        font-weight: 800;
      }}
      .layout-workbench-preview-card {{
        border: 1px solid rgba(80, 67, 44, .16);
        border-radius: 8px;
        margin: 8px 0 0;
        padding: 10px 12px;
        background: rgba(255, 255, 255, .68);
      }}
      .layout-workbench-preview-frame {{
        width: 100%;
        height: 320px;
        max-height: 42vh;
        border-radius: 8px;
        overflow: hidden;
        background: linear-gradient(180deg, #f6f1e6 0%, #ece4d6 100%);
        display: flex;
        align-items: center;
        justify-content: center;
      }}
      .layout-workbench-real-preview {{
        display: block;
        width: 100%;
        height: 100%;
        object-fit: contain;
        background: #f8f4ea;
      }}
      .layout-workbench-empty-preview {{
        height: 180px;
        min-height: 0;
        text-align: center;
        color: #6d624f;
        font-size: 13px;
        line-height: 1.5;
        padding: 0 20px;
      }}
      .layout-workbench-preview-meta {{
        color: #857963;
        font-size: 11px;
        margin-top: 6px;
        word-break: break-all;
      }}
      @container (max-width: 560px) {{
        .layout-workbench-actions-row,
        .layout-workbench-actions-row-placeholder,
        .layout-workbench-summary-grid,
        .layout-workbench-meta {{
          grid-template-columns: 1fr;
        }}
      }}
      @media (max-width: 720px) {{
        .layout-workbench-grid {{ grid-template-columns: 1fr; }}
      }}
    </style>
    """


def _build_summary_html(
    *,
    spec: LayeredTemplateSpec | None,
    media_placement: MediaPlacement | Mapping[str, Any] | None,
    render_summary: str | None,
    template_summary: str | None,
) -> str:
    if spec is None:
        return f"""
        <section class="layout-workbench-card">
          <div class="layout-workbench-section-title">{_CURRENT_SPEC}</div>
          <p class="layout-workbench-copy">{_NO_SPEC}</p>
        </section>
        """

    resolved_render_summary, resolved_template_summary = _resolved_summaries(
        spec=spec,
        render_summary=render_summary,
        template_summary=template_summary,
    )
    return f"""
    <section class="layout-workbench-card">
      <div class="layout-workbench-section-title">{_CURRENT_SPEC}</div>
      {_build_summary_grid_html(spec=spec, media_placement=media_placement)}
      {_build_meta_html(render_summary=resolved_render_summary, template_summary=resolved_template_summary)}
    </section>
    """


def _build_default_summary_html(summary: DefaultLayoutSummary) -> str:
    render_summary = summary.render_summary or _UNKNOWN_RENDER
    template_summary = summary.template_summary or _UNKNOWN_RENDER
    return f"""
    <section class="layout-workbench-card">
      <div class="layout-workbench-section-title">{_CURRENT_TEMPLATE_RULES}</div>
      <div class="layout-workbench-default-strip">
        {_default_chip_html(_CANVAS_SIZE, f"{summary.canvas_width} x {summary.canvas_height}")}
        {_default_chip_html(_MEDIA_SIZE, f"{summary.media_width} x {summary.media_height}")}
        {_default_chip_html(_MEDIA_PLACEMENT, _media_placement_summary(summary.media_placement))}
        {_default_chip_html(_RENDER_SUMMARY, render_summary)}
        {_default_chip_html(_TEMPLATE_SUMMARY, template_summary)}
      </div>
    </section>
    """


def _build_workbench_rows_html(
    *,
    spec: LayeredTemplateSpec,
    media_placement: MediaPlacement | Mapping[str, Any] | None,
    render_summary: str,
    template_summary: str,
) -> str:
    return f"""
    <section class="layout-workbench-actions-row">
      <div class="layout-workbench-actions-row-placeholder">
        <div class="layout-workbench-action-placeholder"></div>
        <div class="layout-workbench-action-placeholder"></div>
      </div>
    </section>
    <section class="layout-workbench-metric-row">
      {_build_summary_grid_html(spec=spec, media_placement=media_placement)}
    </section>
    <section class="layout-workbench-meta-row">
      {_build_meta_html(render_summary=render_summary, template_summary=template_summary)}
    </section>
    """


def _build_default_summary_grid_html(summary: DefaultLayoutSummary) -> str:
    return f"""
    <div class="layout-workbench-summary-grid">
      {_metric_html(_CANVAS_SIZE, f"{summary.canvas_width} x {summary.canvas_height}")}
      {_metric_html(_MEDIA_SIZE, f"{summary.media_width} x {summary.media_height}")}
      {_metric_html(_MEDIA_PLACEMENT, _media_placement_summary(summary.media_placement))}
    </div>
    """


def _default_chip_html(label: str, value: str) -> str:
    escaped_value = escape(value)
    return f"""
    <span class="layout-workbench-default-chip" title="{escape(value, quote=True)}">
      <strong>{escape(label)}: </strong>{escaped_value}
    </span>
    """


def _recent_preset_help(preset: Mapping[str, Any]) -> str:
    label = str(preset["label"])
    preset_id = str(preset["preset_id"])
    return f"{_APPLY_PREFIX} {label} ({preset_id})。{_APPLY_HELP}"


def _recent_preset_summary(preset: Mapping[str, Any]) -> str:
    spec = _coerce_spec(preset.get("spec_payload"))
    if spec is None:
        return str(preset["preset_id"])
    return f"{len(spec.layers)} 层 · {spec.canvas_width}x{spec.canvas_height}"


def _recent_preset_display_label(index: int) -> str:
    if 0 <= index < len(_RECENT_TEMPLATE_LABELS):
        return _RECENT_TEMPLATE_LABELS[index]
    return f"\u6a21\u677f{index + 1}"


def _build_summary_grid_html(
    *,
    spec: LayeredTemplateSpec,
    media_placement: MediaPlacement | Mapping[str, Any] | None,
) -> str:
    return f"""
    <div class="layout-workbench-summary-grid">
      {_metric_html(_CANVAS_SIZE, f"{spec.canvas_width} x {spec.canvas_height}")}
      {_metric_html(_MEDIA_SIZE, f"{spec.media_width} x {spec.media_height}")}
      {_metric_html(_MEDIA_PLACEMENT, _media_placement_summary(media_placement))}
      {_metric_html(_LAYER_COUNT, str(len(spec.layers)))}
    </div>
    """


def _build_meta_html(*, render_summary: str, template_summary: str) -> str:
    return f"""
    <div class="layout-workbench-meta">
      <div class="layout-workbench-meta-line" title="{escape(render_summary, quote=True)}">
        <strong>{_RENDER_SUMMARY}: </strong>{escape(render_summary)}
      </div>
      <div class="layout-workbench-meta-line" title="{escape(template_summary, quote=True)}">
        <strong>{_TEMPLATE_SUMMARY}: </strong>{escape(template_summary)}
      </div>
    </div>
    """


def _resolved_summaries(
    *,
    spec: LayeredTemplateSpec,
    render_summary: str | None,
    template_summary: str | None,
) -> tuple[str, str]:
    resolved_render_summary = render_summary or str(
        spec.metadata.get("render_summary")
        or spec.metadata.get("render_backend")
        or _UNKNOWN_RENDER
    )
    resolved_template_summary = template_summary or (
        f"{spec.template_name} / {spec.template_type}"
    )
    return str(resolved_render_summary), str(resolved_template_summary)


def _media_placement_summary(
    media_placement: MediaPlacement | Mapping[str, Any] | None,
) -> str:
    placement = resolve_media_placement(media_placement)
    return (
        f"{placement.scale_percent}% · "
        f"X {placement.offset_x}px · Y {placement.offset_y}px"
    )


def _metric_html(label: str, value: str) -> str:
    return f"""
    <div class="layout-workbench-metric">
      <div class="layout-workbench-label">{escape(label)}</div>
      <div class="layout-workbench-value">{escape(value)}</div>
    </div>
    """


def _render_preview_container(
    *,
    ui,
    spec: LayeredTemplateSpec | None,
    preview_html: TrustedPreviewHTML | str | None,
    real_preview_frame: Mapping[str, Any] | object | None,
) -> None:
    preview_url = _real_preview_frame_url(real_preview_frame)
    preview_fingerprint = _real_preview_frame_fingerprint(real_preview_frame)
    trusted_preview_html = preview_html if isinstance(preview_html, TrustedPreviewHTML) else None
    if preview_url:
        ui.markdown(
            _build_real_preview_frame_html(
                preview_url=preview_url,
                preview_fingerprint=preview_fingerprint,
            ),
            unsafe_allow_html=True,
        )
        return
    if spec is not None and len(spec.layers) == 0:
        ui.markdown(_build_empty_preview_html(), unsafe_allow_html=True)
        return
    if trusted_preview_html:
        if trusted_preview_html.width and trusted_preview_html.height:
            components.html(
                _build_scaled_preview_html(trusted_preview_html),
                height=_scaled_preview_height(trusted_preview_html),
                scrolling=False,
            )
            return
        components.html(trusted_preview_html.html, height=320, scrolling=True)
        return
    _info(ui, _NO_PREVIEW_HTML)


def _scaled_preview_height(preview_html: TrustedPreviewHTML) -> int:
    return _preview_stage_max_height(preview_html)


def _build_scaled_preview_html(preview_html: TrustedPreviewHTML) -> str:
    width = max(1, int(preview_html.width or 1))
    height = max(1, int(preview_html.height or 1))
    max_height = _preview_stage_max_height(preview_html)
    srcdoc = escape(preview_html.html, quote=True)
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    html, body {{
      margin: 0;
      width: 100%;
      height: 100%;
      overflow: hidden;
      background: transparent;
    }}
    .layout-workbench-scaled-preview {{
      width: 100%;
      height: 100%;
      display: flex;
      align-items: center;
      justify-content: center;
      box-sizing: border-box;
      overflow: hidden;
      background: transparent;
    }}
    .layout-workbench-scaled-viewport {{
      flex: 0 0 auto;
      overflow: hidden;
      background: transparent;
    }}
    .layout-workbench-scaled-surface {{
      width: {width}px;
      height: {height}px;
      flex: 0 0 auto;
      overflow: hidden;
      background: transparent;
      transform-origin: top left;
    }}
    .layout-workbench-scaled-preview iframe {{
      display: block;
      width: {width}px;
      height: {height}px;
      border: 0;
      background: transparent;
    }}
  </style>
</head>
<body>
  <div
    class="layout-workbench-scaled-preview"
    data-preview-width="{width}"
    data-preview-height="{height}"
    data-preview-max-height="{max_height}"
  >
    <div class="layout-workbench-scaled-viewport">
      <div class="layout-workbench-scaled-surface">
        <iframe title="layout preview" srcdoc="{srcdoc}"></iframe>
      </div>
    </div>
  </div>
  <script>
    const shell = document.querySelector('.layout-workbench-scaled-preview');
    const viewport = shell.querySelector('.layout-workbench-scaled-viewport');
    const surface = viewport.querySelector('.layout-workbench-scaled-surface');
    const sourceWidth = Number(shell.dataset.previewWidth);
    const sourceHeight = Number(shell.dataset.previewHeight);
    const maxHeight = Number(shell.dataset.previewMaxHeight);
    function fitPreview() {{
      const scale = Math.min(
        shell.clientWidth / sourceWidth,
        maxHeight / sourceHeight
      );
      surface.style.transform = `scale(${{Math.max(0.01, scale)}})`;
      const renderedWidth = Math.ceil(sourceWidth * scale);
      const renderedHeight = Math.ceil(sourceHeight * scale);
      viewport.style.width = `${{renderedWidth}}px`;
      viewport.style.height = `${{renderedHeight}}px`;
      shell.style.height = `${{renderedHeight}}px`;
      if (window.frameElement && renderedHeight > 0) {{
        window.frameElement.style.height = `${{renderedHeight}}px`;
      }}
    }}
    window.addEventListener('resize', fitPreview);
    new ResizeObserver(fitPreview).observe(shell);
    fitPreview();
  </script>
</body>
</html>"""


def _preview_stage_max_height(preview_html: TrustedPreviewHTML) -> int:
    return 360


def _build_real_preview_frame_html(
    *,
    preview_url: str,
    preview_fingerprint: str | None,
) -> str:
    meta = ""
    if preview_fingerprint:
        meta = (
            '<div class="layout-workbench-preview-meta">'
            f"{escape(preview_fingerprint)}"
            "</div>"
        )
    return f"""
    <section class="layout-workbench-preview-card">
      <div class="layout-workbench-section-title">真实预览帧</div>
      <div class="layout-workbench-preview-frame">
        <img
          class="layout-workbench-real-preview"
          src="{escape(preview_url, quote=True)}"
          alt="真实预览帧"
          loading="lazy"
        />
      </div>
      {meta}
    </section>
    """


def _build_empty_preview_html() -> str:
    return """
    <section class="layout-workbench-preview-card">
      <div class="layout-workbench-section-title">即时预览</div>
      <div class="layout-workbench-preview-frame layout-workbench-empty-preview">
        <div>当前模板还没有图层</div>
      </div>
    </section>
    """


def _real_preview_frame_url(frame: Mapping[str, Any] | object | None) -> str | None:
    if frame is None:
        return None
    url = _read_field(frame, "url")
    if url is None:
        return None
    candidate = str(url).strip()
    return candidate or None


def _real_preview_frame_fingerprint(frame: Mapping[str, Any] | object | None) -> str | None:
    if frame is None:
        return None
    fingerprint = _read_field(frame, "fingerprint")
    if fingerprint is None:
        return None
    candidate = str(fingerprint).strip()
    return candidate or None


def _coerce_spec(
    spec_payload: LayeredTemplateSpec | Mapping[str, Any] | None,
) -> LayeredTemplateSpec | None:
    if spec_payload is None:
        return None
    if isinstance(spec_payload, LayeredTemplateSpec):
        return spec_payload
    try:
        return LayeredTemplateSpec.from_dict(spec_payload)
    except (KeyError, TypeError, ValueError):
        return None


def _coerce_default_layout_summary(
    summary: DefaultLayoutSummary | Mapping[str, Any] | object | None,
) -> DefaultLayoutSummary | None:
    if summary is None:
        return None
    if isinstance(summary, DefaultLayoutSummary):
        return summary
    try:
        return DefaultLayoutSummary.from_mapping(summary)
    except (KeyError, TypeError, ValueError):
        return None


def _recent_presets(
    recent_presets: Sequence[Mapping[str, Any] | object] | None,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in list(recent_presets or []):
        preset_id = _read_field(item, "preset_id") or _read_field(item, "id")
        if not preset_id:
            continue
        spec = _coerce_spec(_read_field(item, "spec") or _read_field(item, "spec_payload"))
        if spec is None:
            continue
        label = (
            _read_field(item, "template_name")
            or _read_field(item, "name")
            or _read_field(item, "label")
            or preset_id
        )
        normalized.append(
            {
                "preset_id": str(preset_id),
                "label": str(label),
                "last_used_at": _read_field(item, "last_used_at"),
                "spec_payload": spec.to_dict(),
            }
        )
    normalized.sort(key=_recent_sort_key, reverse=True)
    return normalized[:5]


def _consume_pending_selection(*, ui, presets: list[dict[str, Any]]) -> PresetSelection | None:
    selected_preset_id = ui.session_state.get(_PENDING_SELECTION_SESSION_KEY)
    if not selected_preset_id:
        return None
    ui.session_state.pop(_PENDING_SELECTION_SESSION_KEY, None)
    for preset in presets:
        if preset["preset_id"] == selected_preset_id:
            return {
                "preset_id": preset["preset_id"],
                "spec_payload": preset["spec_payload"],
            }
    return None


def _recent_sort_key(preset: Mapping[str, Any]) -> float:
    value = preset.get("last_used_at")
    normalized = _normalize_recent_timestamp(value)
    return normalized.timestamp() if normalized is not None else float("-inf")


def _normalize_recent_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return None
        if candidate.endswith("Z"):
            candidate = f"{candidate[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def _recent_preset_button_key(preset_id: str, *, key_suffix: str) -> str:
    digest = hashlib.sha1(str(preset_id).encode("utf-8")).hexdigest()[:12]
    return f"layout_preview_recent_preset_{digest}{key_suffix}"


def _recent_preset_item_key(preset_id: str, *, key_suffix: str) -> str:
    digest = hashlib.sha1(str(preset_id).encode("utf-8")).hexdigest()[:12]
    return f"layout_preview_recent_item_{digest}{key_suffix}"


def _recent_preset_delete_button_key(preset_id: str, *, key_suffix: str) -> str:
    digest = hashlib.sha1(str(preset_id).encode("utf-8")).hexdigest()[:12]
    return f"layout_preview_delete_recent_preset_{digest}{key_suffix}"


def _action_button_key(action: str, *, key_suffix: str) -> str:
    return f"layout_preview_{action}{key_suffix}"


def _workbench_row_key(name: str, *, key_suffix: str) -> str:
    return f"layout_preview_{name}{key_suffix}"


def _columns(ui, spec, **kwargs):
    columns = getattr(ui, "columns", None)
    if not callable(columns):
        return None
    try:
        return columns(spec, **kwargs)
    except TypeError:
        try:
            return columns(spec)
        except TypeError:
            return None


def trust_preview_html(
    value: str | None,
    *,
    width: int | None = None,
    height: int | None = None,
) -> TrustedPreviewHTML | None:
    if value is None:
        return None
    return TrustedPreviewHTML(html=str(value), width=width, height=height)


def _caption(ui, value: str) -> None:
    caption = getattr(ui, "caption", None)
    if callable(caption):
        caption(value)
        return
    ui.markdown(value)


def _info(ui, value: str) -> None:
    ui.markdown(value)


def _read_field(item: Mapping[str, Any] | object, field: str) -> Any:
    if isinstance(item, Mapping):
        return item.get(field)
    return getattr(item, field, None)


def _positive_int_field(item: Mapping[str, Any] | object, field: str) -> int:
    value = _read_field(item, field)
    if value is None:
        raise KeyError(field)
    normalized = int(value)
    if normalized <= 0:
        raise ValueError(f"{field} must be positive")
    return normalized


def _optional_text_field(item: Mapping[str, Any] | object, field: str) -> str | None:
    value = _read_field(item, field)
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


__all__ = [
    "DefaultLayoutSummary",
    "render_layout_preview_workbench",
    "trust_preview_html",
]
