# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import unicodedata
from typing import Any

MAX_STORYBOARD_FRAME_ID_CHARS = 256


def normalize_storyboard_frame_id(
    value: Any,
    *,
    allow_empty: bool = False,
) -> str:
    """Return one canonical representation for frame identity across layers."""

    if not isinstance(value, str):
        raise ValueError("frame_id must be a string")
    normalized = unicodedata.normalize("NFC", " ".join(value.strip().split()))
    if not normalized:
        if allow_empty:
            return ""
        raise ValueError("frame_id must be a non-empty string")
    if len(normalized) > MAX_STORYBOARD_FRAME_ID_CHARS:
        raise ValueError(
            f"frame_id must be at most {MAX_STORYBOARD_FRAME_ID_CHARS} characters"
        )
    return normalized


__all__ = [
    "MAX_STORYBOARD_FRAME_ID_CHARS",
    "normalize_storyboard_frame_id",
]
