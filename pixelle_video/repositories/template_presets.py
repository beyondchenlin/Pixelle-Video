from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from json import JSONDecodeError
from math import isfinite
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
PRESET_RECORD_STRING_FIELDS = (
    "preset_id",
    "name",
    "source",
    "orientation",
    "template_type",
)
PRESET_RECORD_OPTIONAL_STRING_FIELDS = (
    "thumbnail_ref",
    "created_at",
    "updated_at",
    "last_used_at",
)
SPEC_STRING_FIELDS = (
    "version",
    "template_id",
    "template_name",
    "template_type",
)
SPEC_INT_FIELDS = (
    "canvas_width",
    "canvas_height",
    "media_width",
    "media_height",
)
RECT_NUMBER_FIELDS = ("x", "y", "width", "height")
LAYER_STRING_FIELDS = ("id", "type", "name")
LAYER_NUMBER_FIELDS = ("opacity", "rotation")


@dataclass(frozen=True)
class _Manifest:
    version: int
    presets: tuple[TemplatePreset, ...]


class TemplatePresetRepository:
    def __init__(self, root_dir: str | os.PathLike[str]) -> None:
        self.root_dir = Path(root_dir)
        self.manifest_path = self.root_dir / "presets.json"

    def save(self, preset: TemplatePreset) -> TemplatePreset:
        self._validate_persistable_preset(preset)
        manifest = self._load_manifest()
        presets = list(manifest.presets)
        now = _utc_now()
        existing_index = next(
            (
                index
                for index, item in enumerate(presets)
                if item.preset_id == preset.preset_id
            ),
            None,
        )
        created_at = (
            presets[existing_index].created_at
            if existing_index is not None
            else preset.created_at
        ) or now
        saved = replace(preset, created_at=created_at, updated_at=now)
        if existing_index is None:
            presets.append(saved)
        else:
            presets[existing_index] = saved
        self._write_manifest(_manifest_to_dict(presets))
        return saved

    def get(self, preset_id: str) -> TemplatePreset | None:
        for preset in self._load_manifest().presets:
            if preset.preset_id == preset_id:
                return preset
        return None

    def list_all(self) -> list[TemplatePreset]:
        return list(self._load_manifest().presets)

    def list_recent(self, limit: int = 5) -> list[TemplatePreset]:
        recent = [
            preset
            for preset in self._load_manifest().presets
            if preset.last_used_at
        ]
        recent.sort(key=lambda preset: preset.last_used_at or "", reverse=True)
        return [
            replace(preset, source="recent")
            for preset in recent[: max(0, limit)]
        ]

    def touch_last_used(self, preset_id: str) -> TemplatePreset:
        manifest = self._load_manifest()
        presets = list(manifest.presets)
        now = _utc_now()
        for index, preset in enumerate(presets):
            if preset.preset_id != preset_id:
                continue
            updated = replace(preset, last_used_at=now, updated_at=now)
            presets[index] = updated
            self._write_manifest(_manifest_to_dict(presets))
            return updated
        raise KeyError(preset_id)

    def persist_asset(self, source_path: str | os.PathLike[str], preset_id: str) -> str:
        source = Path(source_path)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
        target_dir = self.root_dir / "assets" / _preset_asset_dir_name(preset_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{digest}{source.suffix}"
        shutil.copy2(source, target)
        return target.relative_to(self.root_dir).as_posix()

    def _load_manifest(self) -> _Manifest:
        if not self.manifest_path.exists():
            return _Manifest(version=MANIFEST_VERSION, presets=())
        try:
            payload = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except JSONDecodeError as exc:
            raise ValueError(
                f"template preset manifest is invalid JSON: {self.manifest_path}"
            ) from exc
        if not isinstance(payload, dict):
            raise ValueError("template preset manifest must be a JSON object")
        if "version" not in payload:
            raise ValueError(
                f"template preset manifest version must be {MANIFEST_VERSION}"
            )
        version = payload["version"]
        if (
            not isinstance(version, int)
            or isinstance(version, bool)
            or version != MANIFEST_VERSION
        ):
            raise ValueError(
                f"template preset manifest version must be {MANIFEST_VERSION}"
            )
        if "presets" not in payload:
            raise ValueError("template preset manifest presets must be a list")
        presets = payload["presets"]
        if not isinstance(presets, list):
            raise ValueError("template preset manifest presets must be a list")
        decoded_presets = tuple(
            _decode_manifest_preset_record(index, preset_payload)
            for index, preset_payload in enumerate(presets)
        )
        return _Manifest(version=version, presets=decoded_presets)

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


def _manifest_to_dict(presets: list[TemplatePreset]) -> dict[str, Any]:
    return {
        "version": MANIFEST_VERSION,
        "presets": [_preset_to_dict(preset) for preset in presets],
    }


def _decode_manifest_preset_record(index: int, payload: Any) -> TemplatePreset:
    _validate_manifest_preset_record(index, payload)
    spec = _decode_manifest_spec(index, payload["spec"])
    return TemplatePreset(
        preset_id=payload["preset_id"],
        name=payload["name"],
        source=payload["source"],
        orientation=payload["orientation"],
        template_type=payload["template_type"],
        spec=spec,
        thumbnail_ref=payload.get("thumbnail_ref"),
        editable=payload.get("editable", True),
        created_at=payload.get("created_at"),
        updated_at=payload.get("updated_at"),
        last_used_at=payload.get("last_used_at"),
    )


def _validate_manifest_preset_record(index: int, payload: Any) -> None:
    if not isinstance(payload, dict):
        raise ValueError(
            f"template preset manifest preset record {index} must be an object"
        )
    missing = PRESET_RECORD_REQUIRED_KEYS.difference(payload)
    if missing:
        missing_fields = ", ".join(sorted(missing))
        raise ValueError(
            "template preset manifest preset record "
            f"{index} is missing required fields: {missing_fields}"
        )
    for field in PRESET_RECORD_STRING_FIELDS:
        _require_manifest_string_field(index, payload, field)
    for field in PRESET_RECORD_OPTIONAL_STRING_FIELDS:
        _require_manifest_optional_string_field(index, payload, field)
    if "editable" in payload and not isinstance(payload["editable"], bool):
        raise ValueError(
            "template preset manifest preset record "
            f"{index} field editable must be a boolean"
        )
    if not isinstance(payload["spec"], Mapping):
        raise ValueError(
            "template preset manifest preset record "
            f"{index} field spec must be an object"
        )


def _decode_manifest_spec(
    preset_index: int,
    payload: Mapping[str, Any],
) -> LayeredTemplateSpec:
    _validate_manifest_spec_schema(preset_index, payload)
    try:
        return LayeredTemplateSpec.from_dict(payload)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            f"template preset manifest preset record {preset_index} field spec is invalid"
        ) from exc


def _validate_manifest_spec_schema(
    preset_index: int,
    payload: Mapping[str, Any],
) -> None:
    for field in SPEC_STRING_FIELDS:
        _require_spec_string_field(preset_index, payload, f"spec.{field}")
    for field in SPEC_INT_FIELDS:
        _require_spec_int_field(preset_index, payload, f"spec.{field}")
    _require_spec_rect_field(preset_index, payload, "spec.safe_area")
    _require_spec_layers_field(preset_index, payload)
    if "metadata" in payload and not isinstance(payload["metadata"], Mapping):
        _raise_spec_schema_error(preset_index, "spec.metadata", "an object")


def _require_spec_layers_field(
    preset_index: int,
    payload: Mapping[str, Any],
) -> None:
    if "layers" not in payload:
        _raise_spec_schema_error(preset_index, "spec.layers", "a list")
    layers = payload["layers"]
    if not isinstance(layers, list):
        _raise_spec_schema_error(preset_index, "spec.layers", "a list")
    for layer_index, layer in enumerate(layers):
        _require_spec_layer_field(preset_index, layer, layer_index)


def _require_spec_layer_field(
    preset_index: int,
    payload: Any,
    layer_index: int,
) -> None:
    layer_path = f"spec.layers[{layer_index}]"
    if not isinstance(payload, Mapping):
        _raise_spec_schema_error(preset_index, layer_path, "an object")
    for field in LAYER_STRING_FIELDS:
        _require_spec_string_field(preset_index, payload, f"{layer_path}.{field}")
    _require_spec_rect_field(preset_index, payload, f"{layer_path}.rect")
    _require_spec_int_field(preset_index, payload, f"{layer_path}.z_index")
    for field in LAYER_NUMBER_FIELDS:
        _require_spec_number_field(preset_index, payload, f"{layer_path}.{field}")
    if "locked" not in payload or not isinstance(payload["locked"], bool):
        _raise_spec_schema_error(preset_index, f"{layer_path}.locked", "a boolean")
    if "source" not in payload:
        _raise_spec_schema_error(preset_index, f"{layer_path}.source", "an object or null")
    if payload["source"] is not None:
        _require_spec_layer_source_field(
            preset_index,
            payload["source"],
            f"{layer_path}.source",
        )
    if "style" not in payload or not isinstance(payload["style"], Mapping):
        _raise_spec_schema_error(preset_index, f"{layer_path}.style", "an object")
    if (
        "role" in payload
        and payload["role"] is not None
        and not isinstance(payload["role"], str)
    ):
        _raise_spec_schema_error(preset_index, f"{layer_path}.role", "a string or null")


def _require_spec_layer_source_field(
    preset_index: int,
    payload: Any,
    field_path: str,
) -> None:
    if not isinstance(payload, Mapping):
        _raise_spec_schema_error(preset_index, field_path, "an object or null")
    _require_spec_string_field(preset_index, payload, f"{field_path}.kind")
    _require_spec_string_field(preset_index, payload, f"{field_path}.ref")
    if "metadata" in payload and not isinstance(payload["metadata"], Mapping):
        _raise_spec_schema_error(preset_index, f"{field_path}.metadata", "an object")


def _require_spec_rect_field(
    preset_index: int,
    payload: Mapping[str, Any],
    field_path: str,
) -> None:
    field = field_path.rsplit(".", 1)[-1]
    if field not in payload or not isinstance(payload[field], Mapping):
        _raise_spec_schema_error(preset_index, field_path, "an object")
    rect = payload[field]
    for rect_field in RECT_NUMBER_FIELDS:
        _require_spec_number_field(preset_index, rect, f"{field_path}.{rect_field}")
    if "unit" in rect and not isinstance(rect["unit"], str):
        _raise_spec_schema_error(preset_index, f"{field_path}.unit", "a string")


def _require_spec_string_field(
    preset_index: int,
    payload: Mapping[str, Any],
    field_path: str,
) -> None:
    field = field_path.rsplit(".", 1)[-1]
    if field not in payload or not isinstance(payload[field], str) or not payload[field]:
        _raise_spec_schema_error(preset_index, field_path, "a non-empty string")


def _require_spec_int_field(
    preset_index: int,
    payload: Mapping[str, Any],
    field_path: str,
) -> None:
    field = field_path.rsplit(".", 1)[-1]
    if field not in payload or not _is_strict_int(payload[field]):
        _raise_spec_schema_error(preset_index, field_path, "an integer")


def _require_spec_number_field(
    preset_index: int,
    payload: Mapping[str, Any],
    field_path: str,
) -> None:
    field = field_path.rsplit(".", 1)[-1]
    if field not in payload or not _is_strict_number(payload[field]):
        _raise_spec_schema_error(preset_index, field_path, "a finite number")


def _is_strict_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_strict_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        try:
            float(value)
        except OverflowError:
            return False
        return True
    if not isinstance(value, float):
        return False
    return isfinite(value)


def _raise_spec_schema_error(
    preset_index: int,
    field_path: str,
    expected: str,
) -> None:
    raise ValueError(
        "template preset manifest preset record "
        f"{preset_index} field {field_path} must be {expected}"
    )


def _require_manifest_string_field(
    index: int,
    payload: Mapping[str, Any],
    field: str,
) -> None:
    value = payload[field]
    if not isinstance(value, str) or not value:
        raise ValueError(
            "template preset manifest preset record "
            f"{index} field {field} must be a non-empty string"
        )


def _require_manifest_optional_string_field(
    index: int,
    payload: Mapping[str, Any],
    field: str,
) -> None:
    if field not in payload or payload[field] is None:
        return
    if not isinstance(payload[field], str):
        raise ValueError(
            "template preset manifest preset record "
            f"{index} field {field} must be a string or null"
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
