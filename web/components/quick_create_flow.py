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


def _build_card_html(node_key: str, tone: str) -> str:
    title = escape(tr(f"quick_create_flow.node.{node_key}.title"))
    description = escape(tr(f"quick_create_flow.node.{node_key}.description"))
    return (
        f'<div class="quick-create-flow-card quick-create-flow-card-{tone}">'
        f"<strong>{title}</strong>"
        f"<span>{description}</span>"
        "</div>"
    )


def _build_horizontal_arrow_html(direction: str) -> str:
    return (
        '<div class="quick-create-flow-arrow-horizontal '
        f'quick-create-flow-arrow-horizontal-{direction}" aria-hidden="true"></div>'
    )


def _build_row_html(items: tuple[tuple[str, str], ...], *, direction: str, row_class: str) -> str:
    row_items: list[str] = []
    for index, (node_key, tone) in enumerate(items):
        row_items.append(_build_card_html(node_key, tone))
        if index < len(items) - 1:
            row_items.append(_build_horizontal_arrow_html(direction))
    return f'<div class="quick-create-flow-row {row_class}">{"".join(row_items)}</div>'


def build_quick_create_flow_diagram_html() -> str:
    title = escape(tr("quick_create_flow.title"))
    caption = escape(tr("quick_create_flow.caption"))
    badge = escape(tr("quick_create_flow.badge"))
    note = escape(tr("quick_create_flow.note"))

    return f"""
<style>
.quick-create-flow {{
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
    font-size: 1.02rem;
    font-weight: 700;
    color: #0f172a;
    line-height: 1.3;
}}

.quick-create-flow-caption {{
    margin-top: 6px;
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

.quick-create-flow-board {{
    display: flex;
    flex-direction: column;
    gap: 16px;
    padding-top: 4px;
    min-height: 440px;
    justify-content: space-between;
}}

.quick-create-flow-row {{
    display: grid;
    grid-template-columns: minmax(0, 1fr) 24px minmax(0, 1fr) 24px minmax(0, 1fr) 24px minmax(0, 1fr);
    gap: 10px;
    align-items: center;
}}

.quick-create-flow-row-bottom {{
    grid-template-columns: minmax(0, 1fr) 24px minmax(0, 1fr) 1fr 1fr 1fr 1fr;
}}

.quick-create-flow-card {{
    min-height: 84px;
    border-radius: 8px;
    padding: 12px 12px 11px;
    border: 1px solid rgba(226, 232, 240, 0.96);
    background: linear-gradient(180deg, #ffffff, #fbfcfe);
    box-shadow: 0 10px 24px rgba(15, 23, 42, 0.04);
    display: flex;
    flex-direction: column;
    justify-content: center;
}}

.quick-create-flow-card strong {{
    display: block;
    margin-bottom: 6px;
    font-size: 0.96rem;
    line-height: 1.2;
    color: #0f172a;
}}

.quick-create-flow-card span {{
    display: block;
    font-size: 0.77rem;
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
    right: -1px;
    transform: translateY(-50%) rotate(45deg);
}}

.quick-create-flow-arrow-horizontal-left::after {{
    left: -1px;
    transform: translateY(-50%) rotate(-135deg);
}}

.quick-create-flow-drop {{
    display: grid;
    grid-template-columns: minmax(0, 1fr) 24px minmax(0, 1fr) 24px minmax(0, 1fr) 24px minmax(0, 1fr);
    align-items: center;
    min-height: 28px;
}}

.quick-create-flow-drop-left {{
    justify-items: stretch;
}}

.quick-create-flow-drop-right {{
    justify-items: stretch;
}}

.quick-create-flow-arrow-vertical {{
    width: 2px;
    height: 28px;
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

.quick-create-flow-drop-right .quick-create-flow-arrow-vertical {{
    grid-column: 7;
    justify-self: center;
}}

.quick-create-flow-drop-left .quick-create-flow-arrow-vertical {{
    grid-column: 1;
    justify-self: center;
}}

.quick-create-flow-note {{
    padding: 12px 13px;
    border-radius: 8px;
    border: 1px solid rgba(226, 232, 240, 0.94);
    background: rgba(248, 250, 252, 0.94);
    color: #475569;
    font-size: 0.78rem;
    line-height: 1.6;
}}

@media (max-width: 560px) {{
    .quick-create-flow {{
        min-height: auto;
    }}

    .quick-create-flow-head {{
        flex-direction: column;
    }}

    .quick-create-flow-board {{
        min-height: auto;
        justify-content: flex-start;
    }}

    .quick-create-flow-row,
    .quick-create-flow-row-bottom {{
        grid-template-columns: 1fr;
    }}

    .quick-create-flow-drop,
    .quick-create-flow-arrow-horizontal {{
        display: none;
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
  <div class="quick-create-flow-board">
    {_build_row_html(_TOP_ROW, direction="right", row_class="quick-create-flow-row-top")}
    <div class="quick-create-flow-drop quick-create-flow-drop-right">
      <div class="quick-create-flow-arrow-vertical" aria-hidden="true"></div>
    </div>
    {_build_row_html(_MIDDLE_ROW, direction="left", row_class="quick-create-flow-row-middle")}
    <div class="quick-create-flow-drop quick-create-flow-drop-left">
      <div class="quick-create-flow-arrow-vertical" aria-hidden="true"></div>
    </div>
    {_build_row_html(_BOTTOM_ROW, direction="right", row_class="quick-create-flow-row-bottom")}
  </div>
  <div class="quick-create-flow-note">{note}</div>
</div>
"""


def render_quick_create_flow_diagram() -> None:
    with st.container(border=True):
        st.markdown(build_quick_create_flow_diagram_html(), unsafe_allow_html=True)
