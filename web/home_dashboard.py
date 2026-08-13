"""Pure state helpers for the Home video dashboard."""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

from web.pipelines.catalog import get_pipeline_catalog_entry

DEFAULT_HOME_PIPELINE = "quick_create"


def normalize_dashboard_page(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError, OverflowError):
        return 0


def change_dashboard_page(
    session_state: MutableMapping[str, Any],
    *,
    state_key: str,
    delta: int,
) -> None:
    current_page = normalize_dashboard_page(session_state.get(state_key))
    session_state[state_key] = max(0, current_page + int(delta))


def resolve_dashboard_warmup_target(value: Any) -> str | None:
    candidate = str(value or "")
    if get_pipeline_catalog_entry(candidate) is not None:
        return candidate
    if not candidate:
        return DEFAULT_HOME_PIPELINE
    return None


__all__ = [
    "DEFAULT_HOME_PIPELINE",
    "change_dashboard_page",
    "normalize_dashboard_page",
    "resolve_dashboard_warmup_target",
]
