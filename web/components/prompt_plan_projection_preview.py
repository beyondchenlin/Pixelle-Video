from __future__ import annotations

from typing import Any, Callable

import streamlit as st

from web.components.asset_prompt_plan_projection import (
    render_asset_prompt_plan_projection_preview,
)


def render_prompt_plan_projection_preview(
    *,
    ui=st,
    translate: Callable[..., str] | None = None,
) -> dict[str, Any] | None:
    return render_asset_prompt_plan_projection_preview(ui=ui, translate=translate)
