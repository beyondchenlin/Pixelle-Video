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
from web.state.session import get_pixelle_video, init_i18n, init_session_state
from web.state.storyboard_overrides import (
    build_storyboard_override_snapshot_identity,
    set_storyboard_override_draft,
)
from web.state.storyboard_preview import get_storyboard_preview_snapshot
from web.state.workbench_client import (
    resolve_storyboard_workbench_client,
    resolve_workbench_client_mode,
)

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
        set_storyboard_override_draft(getattr(ui, "session_state", {}), None)
        ui.info(translate("storyboard.workbench.empty_state"))
        return

    stale_context = build_stale_panel_context(getattr(ui, "session_state", {}))
    workbench_client_mode = resolve_workbench_client_mode(getattr(ui, "session_state", {}))
    pixelle_video = (
        get_pixelle_video()
        if workbench_client_mode == "inprocess"
        else None
    )
    workbench_client = resolve_storyboard_workbench_client(
        getattr(ui, "session_state", {}),
        pixelle_video=pixelle_video,
    )
    with ui.container():
        frame_overrides = preview_renderer(
            preview_snapshot,
            stale_context=stale_context,
            workbench_client=workbench_client,
        )
    set_storyboard_override_draft(
        getattr(ui, "session_state", {}),
        {
            "snapshot_identity": build_storyboard_override_snapshot_identity(preview_snapshot),
            "frame_overrides": frame_overrides,
        },
    )


def main() -> None:
    """Streamlit page entry point."""
    init_session_state()
    init_i18n()
    render_header()
    render_storyboard_workbench_page()


if __name__ == "__main__":
    main()
