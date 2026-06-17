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

from __future__ import annotations

import hashlib
import json
import re
import secrets
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError

from pixelle_video.services.resource_resolver import (
    RESOURCE_ID_PATTERN,
    ResourceIdInvalidError,
    ResourceNotFoundError,
    ResourceResolverError,
)

REFERENCE_IMAGE_UPLOAD_SCHEMA = "pixelle.reference_image_upload.v1"
DEFAULT_REFERENCE_IMAGE_UPLOAD_DIR = "_runtime/reference_image_uploads"
DEFAULT_REFERENCE_IMAGE_MAX_UPLOAD_SIZE_MB = 20
_ALLOWED_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp"})
_DISPLAY_NAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class ReferenceImageUploadRecord:
    upload_id: str
    artifact_id: str
    local_path: str
    sha256: str
    mime_type: str
    width: int
    height: int
    byte_size: int
    original_display_name: str

    def to_response_dict(self) -> dict[str, Any]:
        return {
            "upload_id": self.upload_id,
            "artifact_id": self.artifact_id,
            "sha256": self.sha256,
            "mime_type": self.mime_type,
            "width": self.width,
            "height": self.height,
            "byte_size": self.byte_size,
            "original_display_name": self.original_display_name,
        }

    def to_trace_dict(self) -> dict[str, Any]:
        return {
            "upload_id": self.upload_id,
            "artifact_id": self.artifact_id,
            "sha256": self.sha256,
            "mime_type": self.mime_type,
            "width": self.width,
            "height": self.height,
            "byte_size": self.byte_size,
            "source_kind": "api_upload",
        }


class ReferenceImageUploadStore:
    """Controlled local upload store for public API reference images.

    The store never resolves arbitrary server paths. Public generation requests
    may only reference an upload/artifact ID that has a metadata record under
    this store's root directory.
    """

    def __init__(
        self,
        *,
        base_dir: str | Path = DEFAULT_REFERENCE_IMAGE_UPLOAD_DIR,
        max_upload_size_mb: int = DEFAULT_REFERENCE_IMAGE_MAX_UPLOAD_SIZE_MB,
        allowed_extensions: set[str] | None = None,
    ) -> None:
        self.base_dir = Path(base_dir).resolve()
        self.max_upload_size_mb = max(1, int(max_upload_size_mb))
        self.allowed_extensions = {
            _normalize_extension(ext)
            for ext in (allowed_extensions or set(_ALLOWED_EXTENSIONS))
        }
        self.base_dir.mkdir(parents=True, exist_ok=True)

    async def store_upload(self, upload: UploadFile) -> ReferenceImageUploadRecord:
        display_name = _sanitize_display_name(upload.filename or "reference_image")
        extension = _normalize_extension(Path(display_name).suffix or ".png")
        if extension not in self.allowed_extensions:
            raise ResourceResolverError(
                "unsupported reference image extension; allowed extensions: "
                + ", ".join(sorted(self.allowed_extensions))
            )

        max_bytes = self.max_upload_size_mb * 1024 * 1024
        content = await upload.read(max_bytes + 1)
        if len(content) > max_bytes:
            raise ResourceResolverError(
                f"reference image upload exceeds {self.max_upload_size_mb} MB"
            )
        if not content:
            raise ResourceResolverError("reference image upload is empty")

        width, height, detected_mime = _probe_image(content)
        sha256 = hashlib.sha256(content).hexdigest()
        upload_id = _new_public_upload_id()
        artifact_id = upload_id
        target_dir = (self.base_dir / upload_id).resolve()
        target_dir.mkdir(parents=True, exist_ok=False)
        target_path = target_dir / f"upload{extension}"
        metadata_path = target_dir / "metadata.json"
        target_path.write_bytes(content)

        record = ReferenceImageUploadRecord(
            upload_id=upload_id,
            artifact_id=artifact_id,
            local_path=str(target_path),
            sha256=sha256,
            mime_type=detected_mime or _mime_type_for_extension(extension),
            width=width,
            height=height,
            byte_size=len(content),
            original_display_name=display_name,
        )
        metadata_path.write_text(
            json.dumps(
                {
                    "schema": REFERENCE_IMAGE_UPLOAD_SCHEMA,
                    "record": record.to_response_dict(),
                    "file_name": target_path.name,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return record

    def resolve_upload_id(self, upload_id: str) -> ReferenceImageUploadRecord:
        _validate_public_reference_id(upload_id)
        return self._resolve_record(upload_id)

    def resolve_artifact_id(self, artifact_id: str) -> ReferenceImageUploadRecord:
        _validate_public_reference_id(artifact_id)
        return self._resolve_record(artifact_id)

    def resolve_reference_image_request(
        self,
        reference_image: Mapping[str, Any],
    ) -> ReferenceImageUploadRecord:
        upload_id = reference_image.get("upload_id")
        artifact_id = reference_image.get("artifact_id")
        if upload_id and artifact_id:
            raise ResourceResolverError("reference_image must include exactly one of upload_id or artifact_id")
        if upload_id:
            return self.resolve_upload_id(str(upload_id))
        if artifact_id:
            return self.resolve_artifact_id(str(artifact_id))
        raise ResourceResolverError("reference_image must include upload_id or artifact_id")

    def _resolve_record(self, record_id: str) -> ReferenceImageUploadRecord:
        record_root = (self.base_dir / record_id).resolve()
        try:
            record_root.relative_to(self.base_dir)
        except ValueError as exc:
            raise ResourceIdInvalidError("reference image ID escaped upload store") from exc

        metadata_path = record_root / "metadata.json"
        if not metadata_path.is_file():
            raise ResourceNotFoundError(f"reference image upload is not found: {record_id}")
        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ResourceResolverError("reference image upload metadata could not be read") from exc
        if payload.get("schema") != REFERENCE_IMAGE_UPLOAD_SCHEMA:
            raise ResourceResolverError("reference image upload metadata schema is invalid")
        record_payload = payload.get("record")
        file_name = payload.get("file_name")
        if not isinstance(record_payload, Mapping) or not isinstance(file_name, str):
            raise ResourceResolverError("reference image upload metadata is invalid")

        candidate_path = (record_root / file_name).resolve()
        try:
            candidate_path.relative_to(record_root)
        except ValueError as exc:
            raise ResourceResolverError("reference image upload file escaped record directory") from exc
        if not candidate_path.is_file():
            raise ResourceNotFoundError(f"reference image upload file is missing: {record_id}")
        return ReferenceImageUploadRecord(
            upload_id=str(record_payload.get("upload_id") or record_id),
            artifact_id=str(record_payload.get("artifact_id") or record_id),
            local_path=str(candidate_path),
            sha256=str(record_payload.get("sha256") or ""),
            mime_type=str(record_payload.get("mime_type") or ""),
            width=int(record_payload.get("width") or 0),
            height=int(record_payload.get("height") or 0),
            byte_size=int(record_payload.get("byte_size") or candidate_path.stat().st_size),
            original_display_name=str(record_payload.get("original_display_name") or "reference_image"),
        )

    def cleanup(self) -> None:
        if self.base_dir.is_dir():
            shutil.rmtree(self.base_dir)


def _new_public_upload_id() -> str:
    return "rimg_" + secrets.token_urlsafe(12).replace("-", "_").replace("=", "")


def _validate_public_reference_id(value: str) -> None:
    if not isinstance(value, str) or not RESOURCE_ID_PATTERN.fullmatch(value):
        raise ResourceIdInvalidError("reference image ID must be a public resource ID")


def _sanitize_display_name(name: str) -> str:
    sanitized = _DISPLAY_NAME_PATTERN.sub("_", Path(name).name).strip("._")
    return sanitized or "reference_image"


def _normalize_extension(extension: str) -> str:
    normalized = str(extension or "").strip().lower()
    if not normalized:
        return ""
    if not normalized.startswith("."):
        normalized = f".{normalized}"
    return normalized


def _mime_type_for_extension(extension: str) -> str:
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(extension.lower(), "application/octet-stream")


def _probe_image(content: bytes) -> tuple[int, int, str]:
    try:
        from io import BytesIO

        with Image.open(BytesIO(content)) as image:
            image.verify()
        with Image.open(BytesIO(content)) as image:
            image.load()
            width, height = image.size
            image_format = str(image.format or "").upper()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ResourceResolverError("reference image upload is not a valid image") from exc
    mime_type = {
        "JPEG": "image/jpeg",
        "PNG": "image/png",
        "WEBP": "image/webp",
    }.get(image_format, "application/octet-stream")
    return width, height, mime_type
