from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from json import JSONDecodeError
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from pixelle_video.models.layered_template import LayeredTemplateSpec
from pixelle_video.models.template_preset import TemplatePreset

MANIFEST_VERSION = 1
PRESET_RECORD_REQUIRED_KEYS = frozenset(
    {
        "preset_id",
        "name",
        "source",
        "orientation",
        "template_type",
        "spec",
    }
)


class TemplatePresetRepository:
    def __init__(self, root_dir: str | os.PathLike[str]) -> None:
        self.root_dir = Path(root_dir)
        self.manifest_path = self.root_dir / "presets.json"

    def save(self, preset: TemplatePreset) -> TemplatePreset:
        self._validate_persistable_preset(preset)
        manifest = self._load_manifest()
        presets = list(manifest["presets"])
        now = _utc_now()
        existing_index = next(
            (
                index
                for index, item in enumerate(presets)
                if item["preset_id"] == preset.preset_id
            ),
            None,
        )
        created_at = (
            presets[existing_index].get("created_at")
            if existing_index is not None
            else preset.created_at
        ) or now
        saved = replace(preset, created_at=created_at, updated_at=now)
        payload = _preset_to_dict(saved)
        if existing_index is None:
            presets.append(payload)
        else:
            presets[existing_index] = payload
        manifest["presets"] = presets
        self._write_manifest(manifest)
        return saved

    def get(self, preset_id: str) -> TemplatePreset | None:
        for payload in self._load_manifest()["presets"]:
            if payload["preset_id"] == preset_id:
                return _preset_from_dict(payload)
        return None

    def list_all(self) -> list[TemplatePreset]:
        return [
            _preset_from_dict(payload)
            for payload in self._load_manifest()["presets"]
        ]

    def list_recent(self, limit: int = 5) -> list[TemplatePreset]:
        recent = [
            _preset_from_dict(payload)
            for payload in self._load_manifest()["presets"]
            if payload.get("last_used_at")
        ]
        recent.sort(key=lambda preset: preset.last_used_at or "", reverse=True)
        return [
            replace(preset, source="recent")
            for preset in recent[: max(0, limit)]
        ]

    def touch_last_used(self, preset_id: str) -> TemplatePreset:
        manifest = self._load_manifest()
        presets = list(manifest["presets"])
        now = _utc_now()
        for index, payload in enumerate(presets):
            if payload["preset_id"] != preset_id:
                continue
            updated = dict(payload)
            updated["last_used_at"] = now
            updated["updated_at"] = now
            presets[index] = updated
            manifest["presets"] = presets
            self._write_manifest(manifest)
            return _preset_from_dict(updated)
        raise KeyError(preset_id)

    def persist_asset(self, source_path: str | os.PathLike[str], preset_id: str) -> str:
        source = Path(source_path)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
        target_dir = self.root_dir / "assets" / _preset_asset_dir_name(preset_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{digest}{source.suffix}"
        shutil.copy2(source, target)
        return target.relative_to(self.root_dir).as_posix()

    def _load_manifest(self) -> dict[str, Any]:
        if not self.manifest_path.exists():
            return {"version": MANIFEST_VERSION, "presets": []}
        try:
            payload = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except JSONDecodeError as exc:
            raise ValueError(
                f"template preset manifest is invalid JSON: {self.manifest_path}"
            ) from exc
        if not isinstance(payload, dict):
            raise ValueError("template preset manifest must be a JSON object")
        version = payload.get("version", MANIFEST_VERSION)
        if version != MANIFEST_VERSION:
            raise ValueError(
                f"template preset manifest version must be {MANIFEST_VERSION}"
            )
        presets = payload.get("presets", [])
        if not isinstance(presets, list):
            raise ValueError("template preset manifest presets must be a list")
        for index, preset_payload in enumerate(presets):
            if not isinstance(preset_payload, dict):
                raise ValueError(
                    f"template preset manifest preset record {index} must be an object"
                )
            missing = PRESET_RECORD_REQUIRED_KEYS.difference(preset_payload)
            if missing:
                missing_fields = ", ".join(sorted(missing))
                raise ValueError(
                    "template preset manifest preset record "
                    f"{index} is missing required fields: {missing_fields}"
                )
        return {
            "version": version,
            "presets": list(presets),
        }

    def _write_manifest(self, manifest: Mapping[str, Any]) -> None:
        self.root_dir.mkdir(parents=True, exist_ok=True)
        temp_path = self.manifest_path.with_name(
            f"{self.manifest_path.name}.{uuid.uuid4().hex}.tmp"
        )
        try:
            temp_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            os.replace(temp_path, self.manifest_path)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

    def _validate_persistable_preset(self, preset: TemplatePreset) -> None:
        for layer in preset.spec.layers:
            if layer.source is None or layer.source.kind != "asset":
                continue
            if not self._is_owned_asset_ref(layer.source.ref, preset.preset_id):
                raise ValueError(
                    "asset layer source refs must use repository-owned assets/ keys"
                )
        if (
            preset.thumbnail_ref is not None
            and not self._is_owned_asset_ref(preset.thumbnail_ref, preset.preset_id)
        ):
            raise ValueError(
                "thumbnail_ref must use a repository-owned assets/ key for this preset"
            )

    def _is_owned_asset_ref(self, value: str, preset_id: str) -> bool:
        if not _is_repository_asset_key(value):
            return False
        expected_dir = PurePosixPath("assets") / _preset_asset_dir_name(preset_id)
        asset_path = PurePosixPath(value)
        if asset_path.parent != expected_dir:
            return False
        return (self.root_dir / Path(*asset_path.parts)).is_file()


def _preset_to_dict(preset: TemplatePreset) -> dict[str, Any]:
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


def _preset_from_dict(payload: Mapping[str, Any]) -> TemplatePreset:
    return TemplatePreset(
        preset_id=str(payload["preset_id"]),
        name=str(payload["name"]),
        source=payload["source"],
        orientation=str(payload["orientation"]),
        template_type=str(payload["template_type"]),
        spec=LayeredTemplateSpec.from_dict(payload["spec"]),
        thumbnail_ref=payload.get("thumbnail_ref"),
        editable=bool(payload.get("editable", True)),
        created_at=payload.get("created_at"),
        updated_at=payload.get("updated_at"),
        last_used_at=payload.get("last_used_at"),
    )


def _safe_path_part(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return safe or "preset"


def _preset_asset_dir_name(preset_id: str) -> str:
    digest = hashlib.sha256(preset_id.encode("utf-8")).hexdigest()[:12]
    return f"{_safe_path_part(preset_id)}-{digest}"


def _is_repository_asset_key(value: str) -> bool:
    if not isinstance(value, str) or "\\" in value:
        return False
    path = PurePosixPath(value)
    if path.is_absolute():
        return False
    parts = path.parts
    if len(parts) < 2 or parts[0] != "assets":
        return False
    return all(part not in {"", ".", ".."} for part in parts)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00",
        "Z",
    )
