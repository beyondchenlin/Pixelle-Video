from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def config_section_to_dict(section: Any) -> dict[str, Any] | None:
    """Return a plain dict for mapping or Pydantic config sections."""

    if isinstance(section, Mapping):
        return dict(section)
    if hasattr(section, "model_dump"):
        dumped = section.model_dump()
        return dict(dumped) if isinstance(dumped, Mapping) else {}
    return None


def config_section_get(config: Any, key: str, default: Any = None) -> Any:
    """Read a top-level config section from dict-like or typed config objects."""

    if isinstance(config, Mapping):
        return config.get(key, default)
    return getattr(config, key, default)
