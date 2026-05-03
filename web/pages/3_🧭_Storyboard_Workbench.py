# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

# ruff: noqa: E402
"""Storyboard Workbench page for generated storyboard review and overrides."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

_script_dir = Path(__file__).resolve().parent
_project_root = _script_dir.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st

from web.components.header import render_header
from web.components.storyboard_preview import render_storyboard_preview
from web.components.storyboard_workbench_stale import build_stale_panel_context
from web.i18n import tr
from web.state.session import init_i18n, init_session_state
from web.state.storyboard_preview import get_storyboard_preview_snapshot

PreviewRenderer = Callable[..., list[dict[str, Any]]]


def render_storyboard_workbench_page(
    *,
    ui=st,
    translate=tr,
    preview_renderer: PreviewRenderer = render_storyboard_preview,
) -> None:
    """Render the main storyboard workbench surface."""
    ui.markdown(f"## {translate('storyboard.workbench.page_title')}")
    ui.caption(translate("storyboard.workbench.page_caption"))

    preview_snapshot = get_storyboard_preview_snapshot(getattr(ui, "session_state", {}))
    if preview_snapshot is None:
        ui.info(translate("storyboard.workbench.empty_state"))
        return

    stale_context = build_stale_panel_context(getattr(ui, "session_state", {}))
    with ui.container():
        preview_renderer(
            preview_snapshot,
            stale_context=stale_context,
        )


def main() -> None:
    """Streamlit page entry point."""
    init_session_state()
    init_i18n()
    render_header()
    render_storyboard_workbench_page()


if __name__ == "__main__":
    main()
