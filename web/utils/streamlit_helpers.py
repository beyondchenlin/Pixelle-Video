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
Streamlit helper functions
"""

from collections.abc import Callable
from typing import Any, TypeVar

import streamlit as st

T = TypeVar("T")


def session_state_has_key(session_state: Any, key: str) -> bool:
    """Return whether a Streamlit-like session state already owns a widget key."""
    try:
        return key in session_state
    except TypeError:
        return False


def keyed_widget_default_kwargs(
    session_state: Any,
    key: str,
    **default_kwargs: Any,
) -> dict[str, Any]:
    """Return widget default kwargs only before Streamlit owns the widget key."""
    if session_state_has_key(session_state, key):
        return {}
    return dict(default_kwargs)


def normalize_keyed_option(
    session_state: Any,
    key: str,
    *,
    options: list[str] | tuple[str, ...],
    default: str,
) -> tuple[str, bool]:
    """Normalize a keyed option and report whether the key already existed."""
    has_session_value = session_state_has_key(session_state, key)
    getter = getattr(session_state, "get", None)
    value = getter(key, default) if callable(getter) else default
    normalized = str(value) if value in options else default
    if has_session_value and hasattr(session_state, "__setitem__"):
        session_state[key] = normalized
    return normalized, has_session_value


class RefreshableSlot:
    """Render dynamic Streamlit content in one placeholder with fresh widget keys."""

    def __init__(self, slot: Any, *, refresh_prefix: str = "_refresh") -> None:
        self._slot = slot
        self._refresh_prefix = refresh_prefix
        self._render_count = 0

    def render(self, renderer: Callable[[str], T], *, refresh: bool = False) -> T:
        """Run renderer inside the slot and provide a suffix for nested widget keys."""
        if refresh:
            self._slot.empty()

        self._render_count += 1
        key_suffix = (
            ""
            if self._render_count == 1
            else f"{self._refresh_prefix}_{self._render_count}"
        )
        with self._slot.container():
            return renderer(key_suffix)


def safe_rerun():
    """Safe rerun that works with both old and new Streamlit versions"""
    if hasattr(st, 'rerun'):
        st.rerun()
    else:
        st.experimental_rerun()
