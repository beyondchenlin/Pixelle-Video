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
Reference image assetization service.

This PR intentionally supports trusted local ``ref_image`` paths for Python
SDK / local CLI callers only. Public API upload/artifact IDs must be resolved
to a controlled temporary file by the API layer before reaching this service.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import warnings
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

from pixelle_video.models.reference_image import ReferenceImageAsset

DEFAULT_ALLOWED_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
DEFAULT_MAX_UPLOAD_SIZE_MB = 20
DEFAULT_MAX_VISION_EDGE_PX = 1024
DEFAULT_MAX_WORKFLOW_EDGE_PX = 2048
REFERENCE_IMAGE_ARTIFACT_VERSION = "reference_image_asset/v1"

_DISPLAY_NAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")
_EXTENSION_TO_FORMAT = {
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
    ".webp": "WEBP",
}
_FORMAT_TO_MIME = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}
_RESAMPLE_LANCZOS = (
    Image.Resampling.LANCZOS
    if hasattr(Image, "Resampling")
    else Image.LANCZOS
)


def _config_value(config: Any, key: str, default: Any = None) -> Any:
    if isinstance(config, Mapping):
        return config.get(key, default)
    return getattr(config, key, default)


def _normalize_allowed_extensions(value: Any) -> tuple[str, ...]:
    if not value:
        return DEFAULT_ALLOWED_EXTENSIONS
    extensions: list[str] = []
    for item in value:
        extension = str(item or "").strip().lower()
        if not extension:
            continue
        if not extension.startswith("."):
            extension = f".{extension}"
        extensions.append(extension)
    return tuple(extensions) or DEFAULT_ALLOWED_EXTENSIONS


def _sanitize_display_name(name: str) -> str:
    sanitized = _DISPLAY_NAME_PATTERN.sub("_", Path(name).name).strip("._")
    return sanitized or "reference_image"


def _path_relative_to(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root).as_posix())
    except ValueError as exc:
        raise ValueError("reference image asset path escaped task directory") from exc


def _image_format_for_extension(extension: str) -> str:
    normalized = extension.lower()
    try:
        return _EXTENSION_TO_FORMAT[normalized]
    except KeyError as exc:
        raise ValueError(f"unsupported reference image extension: {extension}") from exc


def _mime_type_for_format(image_format: str) -> str:
    return _FORMAT_TO_MIME.get(image_format.upper(), "application/octet-stream")


def _looks_like_remote_or_inline_media(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized.startswith("data:") or "://" in normalized


def _coerce_positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, parsed)


def resolve_reference_image_input(params: Mapping[str, Any] | None) -> Any | None:
    """Resolve reference image input from pipeline params.

    ``ref_image`` is the only filesystem-path compatibility entry point. The
    structured ``reference_image`` field is reserved for API-safe upload or
    artifact identifiers and deliberately rejects server-local path keys.
    """

    if not isinstance(params, Mapping):
        return None

    structured_input = params.get("reference_image")
    if isinstance(structured_input, Mapping):
        local_path_keys = (
            "path",
            "local_path",
            "source_path",
            "server_path",
            "ref_image",
        )
        if any(structured_input.get(key) for key in local_path_keys):
            raise ValueError(
                "reference_image must not contain server-local paths; "
                "use a controlled upload_id/artifact_id or trusted local ref_image"
            )
        if structured_input.get("upload_id") or structured_input.get("artifact_id"):
            return structured_input
        return None
    if structured_input not in (None, "", {}, []):
        raise ValueError("reference_image must be an object with upload_id or artifact_id")

    raw_ref_image = params.get("ref_image")
    if raw_ref_image in (None, "", {}, []):
        return None
    return raw_ref_image


class ReferenceImageAssetService:
    """Prepare a reference image as task-local, trace-safe assets."""

    def __init__(
        self,
        config: Any | None = None,
        *,
        enabled: bool | None = None,
    ) -> None:
        self.enabled = (
            bool(_config_value(config, "enabled", False))
            if enabled is None
            else bool(enabled)
        )
        self.allowed_extensions = _normalize_allowed_extensions(
            _config_value(config, "allowed_extensions", DEFAULT_ALLOWED_EXTENSIONS)
        )
        self.max_upload_size_mb = _coerce_positive_int(
            _config_value(config, "max_upload_size_mb", DEFAULT_MAX_UPLOAD_SIZE_MB),
            DEFAULT_MAX_UPLOAD_SIZE_MB,
        )
        self.max_vision_edge_px = _coerce_positive_int(
            _config_value(config, "max_vision_edge_px", DEFAULT_MAX_VISION_EDGE_PX),
            DEFAULT_MAX_VISION_EDGE_PX,
        )
        self.max_workflow_edge_px = _coerce_positive_int(
            _config_value(config, "max_workflow_edge_px", DEFAULT_MAX_WORKFLOW_EDGE_PX),
            DEFAULT_MAX_WORKFLOW_EDGE_PX,
        )
        self.strip_exif = bool(_config_value(config, "strip_exif", True))
        self.convert_to_png_for_workflow = bool(
            _config_value(config, "convert_to_png_for_workflow", False)
        )

    def prepare(self, raw_input: Any, *, task_dir: str | Path) -> ReferenceImageAsset:
        """Validate and materialize a reference image under ``task_dir``."""

        if not self.enabled:
            raise ValueError("reference image feature is disabled")

        source_path = self._resolve_local_source_path(raw_input)
        task_root = Path(task_dir).resolve()
        asset_dir = task_root / "reference_image"
        asset_dir.mkdir(parents=True, exist_ok=True)

        source_bytes = source_path.read_bytes()
        byte_size = len(source_bytes)
        max_bytes = self.max_upload_size_mb * 1024 * 1024
        if byte_size > max_bytes:
            raise ValueError(
                "reference image exceeds configured max_upload_size_mb "
                f"({self.max_upload_size_mb} MB)"
            )

        sha256 = hashlib.sha256(source_bytes).hexdigest()
        sha8 = sha256[:8]
        extension = source_path.suffix.lower()
        source_format = _image_format_for_extension(extension)
        mime_type = _mime_type_for_format(source_format)

        image = self._open_verified_image(source_path)
        try:
            width, height = image.size
            original_path = asset_dir / f"original_{sha8}{extension}"
            vision_path = asset_dir / f"vision_{sha8}.jpg"

            workflow_format = "PNG" if self.convert_to_png_for_workflow else source_format
            workflow_extension = ".png" if workflow_format == "PNG" else extension
            workflow_path = asset_dir / f"workflow_{sha8}{workflow_extension}"

            if self.strip_exif:
                self._save_image_variant(
                    image,
                    original_path,
                    image_format=source_format,
                    max_edge_px=None,
                )
            else:
                shutil.copyfile(source_path, original_path)

            self._save_image_variant(
                image,
                vision_path,
                image_format="JPEG",
                max_edge_px=self.max_vision_edge_px,
                jpeg_quality=85,
            )
            normalized_width, normalized_height = self._save_image_variant(
                image,
                workflow_path,
                image_format=workflow_format,
                max_edge_px=self.max_workflow_edge_px,
            )
        finally:
            image.close()

        asset = ReferenceImageAsset(
            source_kind="local_path",
            original_display_name=_sanitize_display_name(source_path.name),
            task_asset_path=str(original_path),
            task_asset_relative_path=_path_relative_to(original_path, task_root),
            vision_asset_path=str(vision_path),
            vision_asset_relative_path=_path_relative_to(vision_path, task_root),
            workflow_asset_path=str(workflow_path),
            workflow_asset_relative_path=_path_relative_to(workflow_path, task_root),
            sha256=sha256,
            mime_type=mime_type,
            width=width,
            height=height,
            byte_size=byte_size,
            workflow_sha256=_file_sha256(workflow_path),
            workflow_mime_type=_mime_type_for_format(workflow_format),
            workflow_width=normalized_width,
            workflow_height=normalized_height,
            workflow_byte_size=workflow_path.stat().st_size,
            normalized_width=normalized_width,
            normalized_height=normalized_height,
            metadata={
                "artifact_version": REFERENCE_IMAGE_ARTIFACT_VERSION,
                "strip_exif": self.strip_exif,
                "workflow_format": workflow_format.lower(),
                "vision_format": "jpeg",
            },
        )
        (asset_dir / "asset.json").write_text(
            json.dumps(asset.to_asset_json(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return asset

    def _resolve_local_source_path(self, raw_input: Any) -> Path:
        if isinstance(raw_input, Mapping):
            if raw_input.get("upload_id") or raw_input.get("artifact_id"):
                raise ValueError(
                    "reference_image upload_id/artifact_id resolution is not implemented "
                    "in this PR; resolve it to a controlled local file before assetization"
                )
            raise ValueError("reference image mapping input is not supported for assetization")

        source_text = str(raw_input or "").strip()
        if not source_text:
            raise ValueError("reference image path is empty")
        if _looks_like_remote_or_inline_media(source_text):
            raise ValueError("reference image must be a local file, not a remote URL or data URL")

        source_path = Path(source_text).expanduser()
        if source_path.is_symlink():
            raise ValueError("reference image symlink is not allowed")
        if not source_path.is_file():
            raise ValueError("reference image file does not exist")

        extension = source_path.suffix.lower()
        if extension not in self.allowed_extensions:
            raise ValueError(
                "unsupported reference image extension; allowed extensions: "
                f"{', '.join(self.allowed_extensions)}"
            )
        return source_path.resolve()

    @staticmethod
    def _open_verified_image(source_path: Path) -> Image.Image:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(source_path) as probe:
                    probe.verify()
                image = Image.open(source_path)
                image.load()
                return image
        except Image.DecompressionBombWarning as exc:
            raise ValueError("reference image dimensions are too large") from exc
        except UnidentifiedImageError as exc:
            raise ValueError("reference image is not a valid image") from exc
        except OSError as exc:
            raise ValueError("reference image could not be opened") from exc

    @staticmethod
    def _image_for_format(image: Image.Image, image_format: str) -> Image.Image:
        normalized_format = image_format.upper()
        if normalized_format == "JPEG":
            if image.mode in {"RGBA", "LA"}:
                rgba = image.convert("RGBA")
                background = Image.new("RGB", rgba.size, (255, 255, 255))
                background.paste(rgba, mask=rgba.split()[-1])
                return background
            return image.convert("RGB")
        if normalized_format == "PNG":
            if image.mode not in {"RGB", "RGBA", "L"}:
                return image.convert("RGBA")
            return image.copy()
        if normalized_format == "WEBP":
            if image.mode not in {"RGB", "RGBA"}:
                return image.convert("RGBA")
            return image.copy()
        return image.copy()

    def _save_image_variant(
        self,
        image: Image.Image,
        target_path: Path,
        *,
        image_format: str,
        max_edge_px: int | None,
        jpeg_quality: int = 92,
    ) -> tuple[int, int]:
        variant = image.copy()
        try:
            if max_edge_px and max(variant.size) > max_edge_px:
                variant.thumbnail((max_edge_px, max_edge_px), _RESAMPLE_LANCZOS)

            prepared = self._image_for_format(variant, image_format)
            try:
                save_kwargs: dict[str, Any] = {}
                if image_format.upper() == "JPEG":
                    save_kwargs.update({"quality": jpeg_quality, "optimize": True})
                prepared.save(target_path, format=image_format, **save_kwargs)
                return prepared.size
            finally:
                prepared.close()
        finally:
            variant.close()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
