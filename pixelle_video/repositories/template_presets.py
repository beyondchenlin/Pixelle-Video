from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any

from pixelle_video.models.template_preset import TemplatePreset


class TemplatePresetRepository:
    def __init__(self, root: str | Path = "data/template_presets") -> None:
        self.root = Path(root)
        self.index_path = self.root / "presets.json"
        self.assets_dir = self.root / "assets"
        self.thumbnails_dir = self.root / "thumbnails"

    def persist_asset(self, *, source_path: str | Path, preset_id: str) -> str:
        return self._persist_file(
            source_path=source_path,
            preset_id=preset_id,
            target_root=self.assets_dir,
            key_prefix="assets",
        )

    def persist_thumbnail(self, *, source_path: str | Path, preset_id: str) -> str:
        return self._persist_file(
            source_path=source_path,
            preset_id=preset_id,
            target_root=self.thumbnails_dir,
            key_prefix="thumbnails",
        )

    def save(self, preset: TemplatePreset) -> None:
        self._ensure_dirs()
        self._validate_persistable_preset(preset)
        records = {item.preset_id: item for item in self.list_all()}
        records[preset.preset_id] = preset
        self._write_all(list(records.values()))

    def get(self, preset_id: str) -> TemplatePreset | None:
        for preset in self.list_all():
            if preset.preset_id == preset_id:
                return preset
        return None

    def list_all(self, *, source: str | None = None) -> list[TemplatePreset]:
        if not self.index_path.exists():
            return []
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid template preset index: {self.index_path}") from exc
        if not isinstance(payload, list):
            raise ValueError("template preset index must be a list")
        presets = [self._from_record(item) for item in payload]
        if source is None:
            return presets
        return [preset for preset in presets if preset.source == source]

    def list_recent(self, limit: int = 5) -> list[TemplatePreset]:
        recent = [preset for preset in self.list_all() if preset.last_used_at]
        return sorted(recent, key=lambda preset: preset.last_used_at or "", reverse=True)[:limit]

    def touch_last_used(self, preset_id: str, used_at: str) -> TemplatePreset:
        records = {item.preset_id: item for item in self.list_all()}
        preset = records.get(preset_id)
        if preset is None:
            raise KeyError(f"unknown template preset id: {preset_id}")
        updated = replace(preset, last_used_at=used_at)
        records[preset_id] = updated
        self._write_all(list(records.values()))
        return updated

    def save_recent_snapshot(self, preset: TemplatePreset, used_at: str) -> TemplatePreset:
        updated = replace(preset, last_used_at=used_at)
        self._ensure_dirs()
        records = {item.preset_id: item for item in self.list_all()}
        records[updated.preset_id] = updated
        self._write_all(list(records.values()))
        return updated

    def _persist_file(
        self,
        *,
        source_path: str | Path,
        preset_id: str,
        target_root: Path,
        key_prefix: str,
    ) -> str:
        source = Path(source_path)
        if not source.exists() or not source.is_file():
            raise FileNotFoundError(f"template file not found: {source}")
        safe_preset_id = _safe_storage_segment(preset_id)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
        suffix = source.suffix.lower()
        target = target_root / safe_preset_id / f"{digest}{suffix}"
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copy2(source, target)
        return f"{key_prefix}/{safe_preset_id}/{target.name}"

    def _ensure_dirs(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self.thumbnails_dir.mkdir(parents=True, exist_ok=True)

    def _validate_persistable_preset(self, preset: TemplatePreset) -> None:
        if preset.source == "user":
            self._validate_thumbnail_ref(preset.thumbnail_ref)
        for layer in preset.spec.layers:
            if layer.source and layer.source.kind == "asset":
                ref = str(layer.source.ref)
                if not ref.startswith("assets/"):
                    raise ValueError("asset layers must reference repository asset keys before saving")

    def _validate_thumbnail_ref(self, thumbnail_ref: str | None) -> None:
        if not thumbnail_ref or not thumbnail_ref.startswith("thumbnails/"):
            raise ValueError("user presets must reference persisted thumbnails before saving")

    def _write_all(self, presets: list[TemplatePreset]) -> None:
        self._ensure_dirs()
        payload = [self._to_record(preset) for preset in presets]
        temp_path = self.index_path.with_suffix(".json.tmp")
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_path.replace(self.index_path)

    def _to_record(self, preset: TemplatePreset) -> dict[str, Any]:
        return {
            "preset_id": preset.preset_id,
            "name": preset.name,
            "source": preset.source,
            "orientation": preset.orientation,
            "template_type": preset.template_type,
            "spec": preset.spec.to_dict(),
            "thumbnail_ref": preset.thumbnail_ref,
            "editable": preset.editable,
            "created_at": preset.created_at,
            "updated_at": preset.updated_at,
            "last_used_at": preset.last_used_at,
        }

    def _from_record(self, record: Any) -> TemplatePreset:
        if not isinstance(record, dict):
            raise ValueError("template preset record must be a mapping")
        from pixelle_video.models.layered_template import LayeredTemplateSpec

        return TemplatePreset(
            preset_id=str(record["preset_id"]),
            name=str(record["name"]),
            source=record["source"],
            orientation=str(record["orientation"]),
            template_type=str(record["template_type"]),
            spec=LayeredTemplateSpec.from_dict(record["spec"]),
            thumbnail_ref=record.get("thumbnail_ref"),
            editable=bool(record.get("editable", True)),
            created_at=record.get("created_at"),
            updated_at=record.get("updated_at"),
            last_used_at=record.get("last_used_at"),
        )


def _safe_storage_segment(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)
