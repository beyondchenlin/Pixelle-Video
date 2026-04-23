# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Quick-create flow diagram component for the middle column.
"""

from html import escape

import streamlit as st

from web.i18n import tr

_TOP_ROW = (
    ("script_input", "input"),
    ("mode", "input"),
    ("scene_count", "input"),
    ("bgm", "input"),
)

_MIDDLE_ROW = (
    ("template", "config"),
    ("storyboard", "config"),
    ("render", "config"),
    ("voice", "config"),
)

_BOTTOM_ROW = (
    ("image", "config"),
    ("generate", "output"),
)

_TABLET_ROWS = (
    (
        (
            ("script_input", "input"),
            ("mode", "input"),
        ),
        "right",
        "right",
    ),
    (
        (
            ("bgm", "input"),
            ("scene_count", "input"),
        ),
        "left",
        "left",
    ),
    (
        (
            ("voice", "config"),
            ("render", "config"),
        ),
        "right",
        "right",
    ),
    (
        (
            ("template", "config"),
            ("storyboard", "config"),
        ),
        "left",
        "left",
    ),
    (
        (
            ("image", "config"),
            ("generate", "output"),
        ),
        "right",
        None,
    ),
)

_STEPPER_SEQUENCE = (
    ("script_input", "input"),
    ("mode", "input"),
    ("scene_count", "input"),
    ("bgm", "input"),
    ("voice", "config"),
    ("render", "config"),
    ("storyboard", "config"),
    ("template", "config"),
    ("image", "config"),
    ("generate", "output"),
)


def _join_classes(*classes: str) -> str:
    return " ".join(class_name for class_name in classes if class_name)


def _build_card_html(node_key: str, tone: str, *, extra_class: str = "") -> str:
    title = escape(tr(f"quick_create_flow.node.{node_key}.title"))
    description = escape(tr(f"quick_create_flow.node.{node_key}.description"))
    classes = _join_classes(
        "quick-create-flow-card",
        f"quick-create-flow-card-{tone}",
        extra_class,
    )
    return (
        f'<article class="{classes}" data-node="{node_key}">'
        f"<strong>{title}</strong>"
        f"<span>{description}</span>"
        "</article>"
    )


def _build_horizontal_arrow_html(direction: str, *, extra_class: str = "") -> str:
    classes = _join_classes(
        "quick-create-flow-arrow-horizontal",
        f"quick-create-flow-arrow-horizontal-{direction}",
        extra_class,
    )
    return f'<div class="{classes}" aria-hidden="true"></div>'


def _build_vertical_arrow_html(*, extra_class: str = "") -> str:
    classes = _join_classes("quick-create-flow-arrow-vertical", extra_class)
    return f'<div class="{classes}" aria-hidden="true"></div>'


def _build_row_html(items: tuple[tuple[str, str], ...], *, direction: str, row_class: str) -> str:
    row_items: list[str] = []
    for index, (node_key, tone) in enumerate(items):
        row_items.append(_build_card_html(node_key, tone))
        if index < len(items) - 1:
            row_items.append(_build_horizontal_arrow_html(direction))
    return (
        f'<div class="{_join_classes("quick-create-flow-row", f"quick-create-flow-row-{len(items)}", row_class)}">'
        f'{"".join(row_items)}'
        "</div>"
    )


def _build_drop_html(*, slot_count: int, active_side: str, extra_class: str = "") -> str:
    active_index = 0 if active_side == "left" else slot_count - 1
    slots: list[str] = []
    for index in range(slot_count):
        slot_classes = _join_classes(
            "quick-create-flow-drop-slot",
            "quick-create-flow-drop-slot-active" if index == active_index else "",
        )
        slot_content = _build_vertical_arrow_html() if index == active_index else ""
        slots.append(f'<div class="{slot_classes}">{slot_content}</div>')
    return (
        f'<div class="{_join_classes("quick-create-flow-drop", f"quick-create-flow-drop-{slot_count}", extra_class)}">'
        f'{"".join(slots)}'
        "</div>"
    )


def _build_desktop_board_html() -> str:
    return (
        f'<div class="{_join_classes("quick-create-flow-board", "quick-create-flow-desktop")}">'
        f'{_build_row_html(_TOP_ROW, direction="right", row_class="quick-create-flow-row-top")}'
        f'{_build_drop_html(slot_count=4, active_side="right", extra_class="quick-create-flow-drop-desktop")}'
        f'{_build_row_html(_MIDDLE_ROW, direction="left", row_class="quick-create-flow-row-middle")}'
        f'{_build_drop_html(slot_count=4, active_side="left", extra_class="quick-create-flow-drop-desktop")}'
        f'{_build_row_html(_BOTTOM_ROW, direction="right", row_class="quick-create-flow-row-desktop-bottom")}'
        "</div>"
    )


def _build_tablet_board_html() -> str:
    parts: list[str] = []
    for items, direction, active_side in _TABLET_ROWS:
        parts.append(
            _build_row_html(
                items,
                direction=direction,
                row_class="quick-create-flow-row-tablet",
            )
        )
        if active_side:
            parts.append(
                _build_drop_html(
                    slot_count=2,
                    active_side=active_side,
                    extra_class="quick-create-flow-drop-tablet",
                )
            )
    return (
        f'<div class="{_join_classes("quick-create-flow-board", "quick-create-flow-tablet")}">'
        f'{"".join(parts)}'
        "</div>"
    )


def _build_stepper_html() -> str:
    items: list[str] = []
    for index, (node_key, tone) in enumerate(_STEPPER_SEQUENCE):
        items.append(
            f'<div class="quick-create-flow-stepper-item">{_build_card_html(node_key, tone)}</div>'
        )
        if index < len(_STEPPER_SEQUENCE) - 1:
            items.append(
                '<div class="quick-create-flow-stepper-arrow">'
                f"{_build_vertical_arrow_html()}"
                "</div>"
            )
    return f'<div class="quick-create-flow-stepper">{"".join(items)}</div>'


def build_quick_create_flow_diagram_html() -> str:
    title = escape(tr("quick_create_flow.title"))
    caption = escape(tr("quick_create_flow.caption"))
    badge = escape(tr("quick_create_flow.badge"))
    note = escape(tr("quick_create_flow.note"))

    return f"""
<style>
.quick-create-flow {{
    --flow-gap: clamp(10px, 1.5vw, 16px);
    --flow-arrow-span: clamp(18px, 2.4vw, 28px);
    --flow-drop-gap: calc((var(--flow-gap) * 2) + var(--flow-arrow-span));
    --flow-card-pad-x: clamp(12px, 1.7vw, 16px);
    --flow-card-pad-y: clamp(12px, 1.5vw, 15px);
    --flow-radius: 12px;
    display: flex;
    flex-direction: column;
    gap: 16px;
    padding-bottom: 12px;
}}

.quick-create-flow-head {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 12px;
}}

.quick-create-flow-title {{
    margin: 0;
    font-size: clamp(1rem, 1vw, 1.08rem);
    font-weight: 700;
    color: #0f172a;
    line-height: 1.3;
}}

.quick-create-flow-caption {{
    margin-top: 6px;
    max-width: 44ch;
    font-size: 0.83rem;
    line-height: 1.55;
    color: #64748b;
}}

.quick-create-flow-badge {{
    flex-shrink: 0;
    border-radius: 999px;
    padding: 6px 10px;
    background: rgba(239, 68, 68, 0.08);
    color: #dc2626;
    font-size: 0.72rem;
    font-weight: 700;
}}

.quick-create-flow-boards {{
    display: flex;
    flex-direction: column;
    gap: var(--flow-gap);
}}

.quick-create-flow-board {{
    display: flex;
    flex-direction: column;
    gap: var(--flow-gap);
    padding-top: 4px;
}}

.quick-create-flow-tablet,
.quick-create-flow-stepper {{
    display: none;
}}

.quick-create-flow-row {{
    display: grid;
    gap: var(--flow-gap);
    align-items: center;
}}

.quick-create-flow-row-4 {{
    grid-template-columns:
        minmax(0, 1fr)
        var(--flow-arrow-span)
        minmax(0, 1fr)
        var(--flow-arrow-span)
        minmax(0, 1fr)
        var(--flow-arrow-span)
        minmax(0, 1fr);
}}

.quick-create-flow-row-2 {{
    grid-template-columns: minmax(0, 1fr) var(--flow-arrow-span) minmax(0, 1fr);
}}

.quick-create-flow-row-desktop-bottom {{
    width: min(100%, calc(50% - (var(--flow-gap) / 2)));
}}

.quick-create-flow-drop {{
    display: grid;
    align-items: center;
    min-height: clamp(24px, 4vw, 34px);
}}

.quick-create-flow-drop-4 {{
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: var(--flow-drop-gap);
}}

.quick-create-flow-drop-2 {{
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--flow-drop-gap);
}}

.quick-create-flow-drop-slot {{
    display: flex;
    justify-content: center;
}}

.quick-create-flow-card {{
    min-height: clamp(78px, 12vw, 94px);
    border-radius: var(--flow-radius);
    padding: var(--flow-card-pad-y) var(--flow-card-pad-x);
    border: 1px solid rgba(226, 232, 240, 0.96);
    background: linear-gradient(180deg, #ffffff, #fbfcfe);
    box-shadow: 0 10px 24px rgba(15, 23, 42, 0.04);
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: 6px;
}}

.quick-create-flow-card strong {{
    display: block;
    font-size: clamp(0.93rem, 0.95vw, 1rem);
    line-height: 1.2;
    color: #0f172a;
}}

.quick-create-flow-card span {{
    display: block;
    font-size: clamp(0.76rem, 0.82vw, 0.8rem);
    line-height: 1.45;
    color: #64748b;
}}

.quick-create-flow-card-input {{
    border-color: rgba(251, 191, 36, 0.46);
    background: linear-gradient(180deg, #fffaf1, #ffffff);
}}

.quick-create-flow-card-config {{
    border-color: rgba(96, 165, 250, 0.28);
    background: linear-gradient(180deg, #f8fbff, #ffffff);
}}

.quick-create-flow-card-output {{
    border-color: rgba(239, 68, 68, 0.34);
    background: linear-gradient(180deg, #fff6f6, #ffffff);
    box-shadow: 0 12px 28px rgba(239, 68, 68, 0.08);
}}

.quick-create-flow-arrow-horizontal {{
    position: relative;
    height: 2px;
    width: 100%;
    border-radius: 999px;
    background: linear-gradient(90deg, rgba(248, 113, 113, 0.22), #ef4444 70%, #ef4444);
}}

.quick-create-flow-arrow-horizontal::after {{
    content: "";
    position: absolute;
    top: 50%;
    width: 8px;
    height: 8px;
    border-top: 2px solid #ef4444;
    border-right: 2px solid #ef4444;
}}

.quick-create-flow-arrow-horizontal-right::after {{
    right: 0;
    transform: translate(18%, -50%) rotate(45deg);
}}

.quick-create-flow-arrow-horizontal-left::after {{
    left: 0;
    transform: translate(-18%, -50%) rotate(-135deg);
}}

.quick-create-flow-arrow-vertical {{
    width: 2px;
    height: clamp(26px, 5vw, 34px);
    background: linear-gradient(180deg, rgba(248, 113, 113, 0.18), #ef4444 68%, #ef4444);
    border-radius: 999px;
    position: relative;
}}

.quick-create-flow-arrow-vertical::after {{
    content: "";
    position: absolute;
    left: 50%;
    bottom: -1px;
    width: 8px;
    height: 8px;
    border-right: 2px solid #ef4444;
    border-bottom: 2px solid #ef4444;
    transform: translateX(-50%) rotate(45deg);
}}

.quick-create-flow-stepper {{
    padding-top: 4px;
}}

.quick-create-flow-stepper-arrow {{
    display: flex;
    justify-content: center;
    padding: 8px 0 10px;
}}

.quick-create-flow-note {{
    padding: 12px 13px;
    border-radius: var(--flow-radius);
    border: 1px solid rgba(226, 232, 240, 0.94);
    background: rgba(248, 250, 252, 0.94);
    color: #475569;
    font-size: 0.78rem;
    line-height: 1.6;
}}

@media (max-width: 980px) {{
    .quick-create-flow-head {{
        flex-direction: column;
    }}

    .quick-create-flow-caption {{
        max-width: none;
    }}

    .quick-create-flow-desktop {{
        display: none;
    }}

    .quick-create-flow-tablet {{
        display: flex;
    }}
}}

@media (max-width: 680px) {{
    .quick-create-flow-tablet {{
        display: none;
    }}

    .quick-create-flow-stepper {{
        display: flex;
        flex-direction: column;
    }}

    .quick-create-flow-card {{
        min-height: clamp(72px, 20vw, 90px);
    }}
}}
</style>
<div class="quick-create-flow">
  <div class="quick-create-flow-head">
    <div>
      <div class="quick-create-flow-title">{title}</div>
      <div class="quick-create-flow-caption">{caption}</div>
    </div>
    <div class="quick-create-flow-badge">{badge}</div>
  </div>
  <div class="quick-create-flow-boards">
    {_build_desktop_board_html()}
    {_build_tablet_board_html()}
    {_build_stepper_html()}
  </div>
  <div class="quick-create-flow-note">{note}</div>
</div>
"""


def render_quick_create_flow_diagram() -> None:
    with st.container(border=True):
        st.markdown(build_quick_create_flow_diagram_html(), unsafe_allow_html=True)
