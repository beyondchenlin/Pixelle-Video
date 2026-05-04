from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pixelle_video.models.asset_bible import AssetBible
from pixelle_video.models.asset_bible_preset import AssetBiblePreset

DEFAULT_ASSET_BIBLE_PRESET_ROOT = Path("resources/presets/asset_bibles")


class AssetBiblePresetRegistry:
    def __init__(self, root: str | Path = DEFAULT_ASSET_BIBLE_PRESET_ROOT) -> None:
        self.root = Path(root)

    def list_presets(self) -> list[AssetBiblePreset]:
        return sorted(self._load_all(), key=lambda preset: preset.display_name)

    def list_summaries(self) -> list[dict[str, Any]]:
        return [preset.to_summary_dict() for preset in self.list_presets()]

    def get_preset(self, preset_id: str) -> AssetBiblePreset:
        target_id = _require_text("preset_id", preset_id)
        for preset in self._load_all():
            if preset.preset_id == target_id:
                return preset
        raise KeyError(f"unknown asset bible preset: {target_id}")

    def build_project_asset_bible(
        self,
        *,
        preset_id: str,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str | None = None,
        imported_at: str | None = None,
    ) -> AssetBible:
        preset = self.get_preset(preset_id)
        payload = deepcopy(preset.asset_bible.to_dict())
        target_asset_bible_id = _require_text(
            "asset_bible_id",
            asset_bible_id or payload["asset_bible_id"],
        )
        target_workspace_id = _require_text("workspace_id", workspace_id)
        target_project_id = _require_text("project_id", project_id)
        payload["asset_bible_id"] = target_asset_bible_id
        payload["workspace_id"] = target_workspace_id
        payload["project_id"] = target_project_id
        for collection_name in (
            "ip_profiles",
            "character_profiles",
            "scene_assets",
            "prop_assets",
            "style_profiles",
        ):
            for item in payload.get(collection_name) or []:
                if isinstance(item, dict):
                    item["workspace_id"] = target_workspace_id
                    item["project_id"] = target_project_id
        metadata = dict(payload.get("metadata") or {})
        metadata.update(
            {
                "source_kind": "imported",
                "origin_preset_id": preset.preset_id,
                "origin_revision": preset.revision,
                "imported_at": imported_at or datetime.now(timezone.utc).isoformat(),
                "customized": False,
            }
        )
        payload["metadata"] = metadata
        return AssetBible.from_dict(payload)

    def _load_all(self) -> list[AssetBiblePreset]:
        if not self.root.exists():
            return []
        presets: list[AssetBiblePreset] = []
        for path in sorted(self.root.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid asset bible preset JSON: {path}") from exc
            presets.append(AssetBiblePreset.from_dict(payload))
        return presets


def _require_text(field_name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    return value.strip()


__all__ = ["AssetBiblePresetRegistry", "DEFAULT_ASSET_BIBLE_PRESET_ROOT"]
