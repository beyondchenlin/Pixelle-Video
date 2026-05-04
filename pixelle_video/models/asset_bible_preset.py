from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pixelle_video.models.asset_bible import AssetBible

_MISSING = object()


@dataclass(frozen=True)
class AssetBiblePreset:
    preset_id: str
    revision: str
    source: str
    display_name: str
    description: str
    tags: tuple[str, ...]
    preview_asset_path: str | None
    asset_bible: AssetBible

    def __post_init__(self) -> None:
        object.__setattr__(self, "preset_id", _require_text("preset_id", self.preset_id))
        object.__setattr__(self, "revision", _require_text("revision", self.revision))
        object.__setattr__(self, "source", _require_text("source", self.source))
        if self.source != "builtin":
            raise ValueError("asset bible preset source must be builtin")
        object.__setattr__(self, "display_name", _require_text("display_name", self.display_name))
        object.__setattr__(self, "description", _optional_text(self.description) or "")
        object.__setattr__(self, "tags", _normalize_tags(self.tags))
        object.__setattr__(self, "preview_asset_path", _optional_text(self.preview_asset_path))
        if not isinstance(self.asset_bible, AssetBible):
            raise ValueError("asset_bible must be an AssetBible")

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> AssetBiblePreset:
        if not isinstance(payload, Mapping):
            raise ValueError("asset bible preset payload must be a mapping")
        raw_tags = payload.get("tags", _MISSING)
        return cls(
            preset_id=payload.get("preset_id", ""),
            revision=payload.get("revision", ""),
            source=payload.get("source", ""),
            display_name=payload.get("display_name", ""),
            description=payload.get("description", ""),
            tags=() if raw_tags is _MISSING else _normalize_tags(raw_tags),
            preview_asset_path=payload.get("preview_asset_path"),
            asset_bible=AssetBible.from_dict(payload.get("asset_bible") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.to_summary_dict(),
            "asset_bible": self.asset_bible.to_dict(),
        }

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "preset_id": self.preset_id,
            "revision": self.revision,
            "source": self.source,
            "display_name": self.display_name,
            "description": self.description,
            "tags": list(self.tags),
            "preview_asset_path": self.preview_asset_path,
        }


def _require_text(field_name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    return value.strip()


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("optional text values must be strings")
    return value.strip() or None


def _normalize_tags(value: Any) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise ValueError("tags must be a list or tuple")
    tags = tuple(_require_text("tags", item) for item in value)
    if len(set(tags)) != len(tags):
        raise ValueError("tags must not contain duplicates")
    return tags


__all__ = ["AssetBiblePreset"]
