# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

# ruff: noqa: E402
"""IP Design Workbench page for AssetBible and SceneCast authoring."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

_script_dir = Path(__file__).resolve().parent
_project_root = _script_dir.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st

from web.components.header import render_header
from web.components.ip_design_workbench import render_ip_design_workbench
from web.i18n import tr
from web.state.ip_design_client import resolve_ip_design_client
from web.state.session import get_pixelle_video, init_i18n, init_session_state
from web.state.workbench_client import resolve_workbench_client_mode

WorkbenchRenderer = Callable[..., None]


def render_ip_design_workbench_page(
    *,
    ui=st,
    translate=tr,
    workbench_renderer: WorkbenchRenderer = render_ip_design_workbench,
) -> None:
    ui.markdown(f"## {translate('ip_design.page.title')}")
    ui.caption(translate("ip_design.page.caption"))

    client_mode = resolve_workbench_client_mode(getattr(ui, "session_state", {}))
    pixelle_video = get_pixelle_video() if client_mode == "inprocess" else None
    ip_design_client = resolve_ip_design_client(
        getattr(ui, "session_state", {}),
        pixelle_video=pixelle_video,
    )
    workbench_renderer(
        ip_design_client=ip_design_client,
        ui=ui,
        translate=translate,
    )


def main() -> None:
    st.set_page_config(
        page_title=tr("ip_design.browser.title"),
        page_icon="🎭",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    init_session_state()
    init_i18n()
    render_header()
    render_ip_design_workbench_page()


if __name__ == "__main__":
    main()
