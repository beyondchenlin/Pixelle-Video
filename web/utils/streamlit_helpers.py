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

import json
import logging
import typing
from collections.abc import Callable, Mapping
from typing import Any, TypeVar

import streamlit as st
from pydantic import BaseModel

T = TypeVar("T")

logger = logging.getLogger(__name__)


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


# ── 新增通用辅助函数（替代 8 个文件中的重复拷贝） ──

def first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def list_of_dicts(value: Any) -> list[dict[str, Any]]:
    """Normalize list-like API/model values to plain dictionaries.

    Typed IP Design clients now return Pydantic response models whose list fields
    contain Pydantic item models. Older call sites still expect list[dict], so this
    helper accepts both dict-like items and BaseModel instances.
    """
    if isinstance(value, BaseModel):
        value = value.model_dump()
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, BaseModel):
            result.append(item.model_dump())
        elif isinstance(item, Mapping):
            result.append(dict(item))
    return result


def text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [first_text(item) for item in value if first_text(item)]


def split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def find_item(items: list[dict[str, Any]], field_name: str, value: str) -> dict[str, Any] | None:
    for item in items:
        if first_text(item.get(field_name)) == value:
            return item
    return None


def keyed_text_input(ui, label: str, *, key: str, value: str = "", help: str | None = None) -> str:
    kwargs = keyed_widget_default_kwargs(getattr(ui, "session_state", {}), key, value=value)
    if help:
        kwargs["help"] = help
    return ui.text_input(label, key=key, **kwargs)


def keyed_text_area(ui, label: str, *, key: str, value: str = "", height: int = 68, help: str | None = None) -> str:
    kwargs = keyed_widget_default_kwargs(getattr(ui, "session_state", {}), key, value=value)
    if help:
        kwargs["help"] = help
    return ui.text_area(label, key=key, height=height, **kwargs)


def _resolve_session_state(session_state: Any | None) -> Any:
    return st.session_state if session_state is None else session_state


def populate_form_from_model(model: BaseModel, key_group, *, session_state: Any | None = None) -> None:
    ss = _resolve_session_state(session_state)
    for field_name in model.__class__.model_fields:
        key = getattr(key_group, field_name, None)
        if key:
            value = getattr(model, field_name)
            if isinstance(value, list):
                value = ", ".join(value) if value else ""
            elif isinstance(value, dict):
                value = str(value) if value else ""
            ss[key] = value


def build_model_from_form(model_cls: type[BaseModel], key_group, *, session_state: Any | None = None) -> BaseModel:
    ss = _resolve_session_state(session_state)
    data: dict[str, Any] = {}
    for field_name, field_info in model_cls.model_fields.items():
        key = getattr(key_group, field_name, None)
        if key is None:
            continue
        raw = ss.get(key, "")
        data[field_name] = _deserialize_field(raw, field_info)
    return model_cls(**data)


def _deserialize_field(raw: Any, field_info) -> Any:
    origin = typing.get_origin(field_info.annotation)
    if origin is list:
        return split_csv(str(raw)) if raw else []
    if origin is dict:
        return _parse_json_dict(str(raw)) if raw else {}
    if origin is typing.Literal:
        val = str(raw) if raw else ""
        if val:
            return val
        default = field_info.default
        return default if isinstance(default, str) else ""
    return str(raw) if raw else ""


def _parse_json_dict(value: str) -> dict[str, Any]:
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        logger.warning("_parse_json_dict: non-JSON input '%s', returning {}", value)
        return {}


__all__ = [
    "session_state_has_key", "keyed_widget_default_kwargs",
    "normalize_keyed_option", "RefreshableSlot", "safe_rerun",
    "first_text", "list_of_dicts", "text_list", "split_csv",
    "find_item", "keyed_text_input", "keyed_text_area",
    "populate_form_from_model", "build_model_from_form",
]
