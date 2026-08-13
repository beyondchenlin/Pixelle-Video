"""Pure state helpers for the Home video dashboard."""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

from web.pipelines.catalog import get_pipeline_catalog_entry

DEFAULT_HOME_PIPELINE = "quick_create"
DEFAULT_HOME_DASHBOARD_INITIAL_COUNT = 24
DEFAULT_HOME_DASHBOARD_BATCH_SIZE = 24


def normalize_dashboard_visible_count(
    value: Any,
    *,
    initial_count: int = DEFAULT_HOME_DASHBOARD_INITIAL_COUNT,
) -> int:
    normalized_initial = max(1, int(initial_count))
    if isinstance(value, bool):
        return normalized_initial
    try:
        return max(normalized_initial, int(value))
    except (TypeError, ValueError, OverflowError):
        return normalized_initial


def increase_dashboard_visible_count(
    session_state: MutableMapping[str, Any],
    *,
    state_key: str,
    batch_size: int = DEFAULT_HOME_DASHBOARD_BATCH_SIZE,
    initial_count: int = DEFAULT_HOME_DASHBOARD_INITIAL_COUNT,
) -> None:
    if isinstance(batch_size, bool) or int(batch_size) <= 0:
        raise ValueError("batch_size must be a positive integer")
    current_count = normalize_dashboard_visible_count(
        session_state.get(state_key),
        initial_count=initial_count,
    )
    session_state[state_key] = current_count + int(batch_size)


def reset_dashboard_visible_count(
    session_state: MutableMapping[str, Any],
    *,
    state_key: str,
    initial_count: int = DEFAULT_HOME_DASHBOARD_INITIAL_COUNT,
) -> None:
    session_state[state_key] = max(1, int(initial_count))


def resolve_dashboard_warmup_target(value: Any) -> str | None:
    candidate = str(value or "")
    if get_pipeline_catalog_entry(candidate) is not None:
        return candidate
    if not candidate:
        return DEFAULT_HOME_PIPELINE
    return None


__all__ = [
    "DEFAULT_HOME_DASHBOARD_BATCH_SIZE",
    "DEFAULT_HOME_DASHBOARD_INITIAL_COUNT",
    "DEFAULT_HOME_PIPELINE",
    "increase_dashboard_visible_count",
    "normalize_dashboard_visible_count",
    "reset_dashboard_visible_count",
    "resolve_dashboard_warmup_target",
]
