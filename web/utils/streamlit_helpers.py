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
