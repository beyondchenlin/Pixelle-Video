from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import streamlit as st

from web.i18n import tr
from web.utils.streamlit_helpers import first_text

Translate = Callable[..., str]


def render_visual_story_route_selector(
    *,
    ui=st,
    translate: Translate = tr,
    recommendation: Mapping[str, Any] | None = None,
    key_prefix: str = "visual_story_route",
    auto_select_seconds: int = 10,
) -> dict[str, Any]:
    """Render recommended visual route cards with non-blocking timeout semantics.

    Streamlit cannot reliably run a background countdown without an autorefresh
    dependency. This component therefore stores a deadline in session_state and uses
    the recommended route as the default immediately. If the page reruns after the
    deadline, the selection_source becomes auto_timeout. Generation can proceed even
    when the user never touches this component.
    """
    payload = dict(recommendation or {})
    routes = [dict(item) for item in payload.get("candidate_routes") or [] if isinstance(item, Mapping)]
    selected_payload = dict(payload.get("selected_visual_route") or {})
    default_route_id = first_text(
        selected_payload.get("route_id"),
        payload.get("default_route_id"),
        (routes[0].get("route_id") if routes else ""),
    )
    if not routes:
        return {
            "visual_story_engine_enabled": True,
            "visual_story_selected_route_id": default_route_id,
            "visual_story_selection_source": "api_auto",
        }

    started_key = f"{key_prefix}_started_at"
    selected_key = f"{key_prefix}_selected_route_id"
    source_key = f"{key_prefix}_selection_source"
    if started_key not in ui.session_state:
        ui.session_state[started_key] = time.time()
    if selected_key not in ui.session_state:
        ui.session_state[selected_key] = default_route_id
        ui.session_state[source_key] = "model_recommended"

    elapsed = time.time() - float(ui.session_state[started_key])
    remaining = max(0, int(auto_select_seconds - elapsed))
    if remaining <= 0 and ui.session_state.get(source_key) == "model_recommended":
        ui.session_state[source_key] = "auto_timeout"

    ui.markdown("### AI 推荐的文章视觉路线")
    ui.caption(
        f"默认路线：{_route_name(routes, default_route_id)}。"
        f"{remaining} 秒后自动按默认路线继续；你也可以手动切换。"
        if remaining > 0
        else f"已自动使用默认路线：{_route_name(routes, default_route_id)}。"
    )

    option_ids = [first_text(route.get("route_id")) for route in routes]
    option_ids = [item for item in option_ids if item]
    selected = ui.radio(
        "选择视觉路线",
        options=option_ids,
        index=option_ids.index(ui.session_state[selected_key]) if ui.session_state[selected_key] in option_ids else 0,
        key=selected_key,
        format_func=lambda route_id: _route_name(routes, route_id),
        horizontal=False,
    )
    if selected != default_route_id:
        ui.session_state[source_key] = "user_selected"

    for route in routes:
        with ui.container(border=True):
            ui.markdown(f"**{route.get('route_name') or route.get('route_id')}**")
            ui.caption(first_text(route.get("route_type"), route.get("style_family")))
            ui.write(first_text(route.get("visual_premise")))
            ui.caption("推荐理由：" + first_text(route.get("why_it_fits_article")))
            ip_role = first_text(route.get("recommended_ip_role"))
            if ip_role:
                ui.caption("IP 适配：" + ip_role + " — " + first_text(route.get("ip_fit_reason")))
            scores = route.get("scores") if isinstance(route.get("scores"), Mapping) else {}
            if scores:
                ui.caption("综合分：" + str(scores.get("final", "")))

    return {
        "visual_story_engine_enabled": True,
        "visual_story_selected_route_id": first_text(selected),
        "visual_story_selection_source": first_text(ui.session_state.get(source_key)) or "model_recommended",
        "visual_story_auto_select_seconds": int(auto_select_seconds),
    }


def _route_name(routes: Sequence[Mapping[str, Any]], route_id: str) -> str:
    for route in routes:
        if first_text(route.get("route_id")) == first_text(route_id):
            return first_text(route.get("route_name"), route_id)
    return first_text(route_id)


__all__ = ["render_visual_story_route_selector"]
