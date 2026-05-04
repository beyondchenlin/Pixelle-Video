from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from loguru import logger

from pixelle_video.tts_workflow_family import infer_tts_workflow_family

VOICE_PROFILE_ROOT = Path("data/reference_audio")
VOICE_PROFILE_MANIFEST = VOICE_PROFILE_ROOT / "voice_profiles.json"
ALLOWED_AUDIO_SUFFIXES = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg"}


def infer_tts_model_slug(workflow_key: str | None) -> str:
    family = infer_tts_workflow_family(workflow_key)
    if family != "generic":
        return family

    workflow_name = Path(str(workflow_key or "")).stem.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", workflow_name).strip("-")
    return slug or "tts"


def build_voice_profile_name(base_name: str, workflow_key: str | None) -> str:
    cleaned_name = str(base_name or "").strip()
    if not cleaned_name:
        raise ValueError("voice profile name is required")

    model_slug = infer_tts_model_slug(workflow_key)
    suffix = f"-{model_slug}"
    if cleaned_name.lower().endswith(suffix.lower()):
        return cleaned_name
    return f"{cleaned_name}{suffix}"


def _safe_filename_stem(name: str) -> str:
    safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", name).strip(" ._")
    return safe_name or "voice"


def _upload_bytes(upload: object) -> bytes:
    if hasattr(upload, "getbuffer"):
        return bytes(upload.getbuffer())
    if hasattr(upload, "getvalue"):
        return bytes(upload.getvalue())
    if isinstance(upload, bytes):
        return upload
    raise TypeError("upload must provide getbuffer(), getvalue(), or bytes")


def _upload_suffix(upload: object) -> str:
    filename = str(getattr(upload, "name", "") or "")
    suffix = Path(filename).suffix.lower()
    if not suffix:
        return ".wav"
    if suffix not in ALLOWED_AUDIO_SUFFIXES:
        raise ValueError(f"unsupported reference audio file type: {suffix}")
    return suffix


def _backup_malformed_manifest(manifest_path: Path, reason: str) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    backup_path = manifest_path.with_name(f"{manifest_path.name}.corrupt-{timestamp}")
    index = 1
    while backup_path.exists():
        backup_path = manifest_path.with_name(f"{manifest_path.name}.corrupt-{timestamp}-{index}")
        index += 1
    manifest_path.replace(backup_path)
    logger.warning(
        f"TTS voice profile manifest is malformed ({reason}); backed it up to {backup_path}"
    )
    return backup_path


def _load_manifest(manifest_path: Path) -> dict:
    if not manifest_path.exists():
        return {"version": 1, "profiles": []}

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _backup_malformed_manifest(manifest_path, f"invalid JSON: {exc}")
        return {"version": 1, "profiles": []}

    if not isinstance(data, dict):
        _backup_malformed_manifest(manifest_path, "top-level value is not an object")
        return {"version": 1, "profiles": []}

    profiles = data.get("profiles")
    if not isinstance(profiles, list):
        _backup_malformed_manifest(manifest_path, "profiles is not a list")
        return {"version": 1, "profiles": []}
    return {"version": 1, "profiles": profiles}


def _write_manifest(manifest_path: Path, manifest: dict) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = manifest_path.with_name(f".{manifest_path.name}.tmp")
    temp_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(manifest_path)


def _audio_path_for_manifest(audio_path: Path, root_dir: Path) -> str:
    if not root_dir.is_absolute():
        return audio_path.as_posix()

    try:
        return audio_path.relative_to(root_dir.parent).as_posix()
    except ValueError:
        return audio_path.as_posix()


def _resolve_manifest_audio_path(audio_path: str, root_dir: Path) -> Path:
    stored_path = Path(audio_path)
    if stored_path.is_absolute():
        return stored_path

    resolved_root = root_dir.resolve()
    cwd_candidate = stored_path.resolve()
    if cwd_candidate == resolved_root or cwd_candidate.is_relative_to(resolved_root):
        return cwd_candidate
    return (resolved_root.parent / stored_path).resolve()


def _delete_replaced_audio(existing_profile: dict, new_audio_path: Path, root_dir: Path) -> None:
    old_audio_path = existing_profile.get("audio_path")
    if not isinstance(old_audio_path, str) or not old_audio_path:
        return

    resolved_root = root_dir.resolve()
    resolved_old_path = _resolve_manifest_audio_path(old_audio_path, root_dir)
    resolved_new_path = new_audio_path.resolve()
    if resolved_old_path == resolved_new_path:
        return
    if not (resolved_old_path == resolved_root or resolved_old_path.is_relative_to(resolved_root)):
        return
    if resolved_old_path.exists() and resolved_old_path.is_file():
        resolved_old_path.unlink()


def load_voice_profiles(*, manifest_path: Path = VOICE_PROFILE_MANIFEST) -> list[dict]:
    manifest = _load_manifest(manifest_path)
    return [
        profile
        for profile in manifest["profiles"]
        if isinstance(profile, dict) and profile.get("name") and profile.get("audio_path")
    ]


def list_voice_profiles(
    workflow_key: str | None,
    *,
    manifest_path: Path = VOICE_PROFILE_MANIFEST,
) -> list[dict]:
    model_slug = infer_tts_model_slug(workflow_key)
    return [
        profile
        for profile in load_voice_profiles(manifest_path=manifest_path)
        if profile.get("model_slug") == model_slug
    ]


def save_voice_profile(
    *,
    upload: object,
    base_name: str,
    workflow_key: str | None,
    ref_audio_text: str | None = None,
    root_dir: Path = VOICE_PROFILE_ROOT,
    manifest_path: Path = VOICE_PROFILE_MANIFEST,
) -> dict:
    model_slug = infer_tts_model_slug(workflow_key)
    profile_name = build_voice_profile_name(base_name, workflow_key)
    profile_id = f"{model_slug}:{profile_name}"

    manifest = _load_manifest(manifest_path)
    existing = next(
        (
            profile
            for profile in manifest["profiles"]
            if isinstance(profile, dict)
            and profile.get("model_slug") == model_slug
            and profile.get("name") == profile_name
        ),
        {},
    )

    model_dir = root_dir / model_slug
    model_dir.mkdir(parents=True, exist_ok=True)
    audio_path = model_dir / f"{_safe_filename_stem(profile_name)}{_upload_suffix(upload)}"
    audio_path.write_bytes(_upload_bytes(upload))
    _delete_replaced_audio(existing, audio_path, root_dir)

    existing_profiles = [
        profile
        for profile in manifest["profiles"]
        if not (
            isinstance(profile, dict)
            and profile.get("model_slug") == model_slug
            and profile.get("name") == profile_name
        )
    ]
    now = datetime.now(timezone.utc).isoformat()
    profile = {
        "id": str(existing.get("id") or profile_id or uuid4()),
        "name": profile_name,
        "base_name": str(base_name or "").strip(),
        "model_slug": model_slug,
        "workflow_key": str(workflow_key or ""),
        "audio_path": _audio_path_for_manifest(audio_path, root_dir),
        "original_filename": str(getattr(upload, "name", "") or ""),
        "ref_audio_text": str(ref_audio_text or "").strip(),
        "created_at": str(existing.get("created_at") or now),
        "updated_at": now,
    }

    existing_profiles.append(profile)
    manifest["profiles"] = sorted(existing_profiles, key=lambda item: item.get("name", ""))
    _write_manifest(manifest_path, manifest)
    return profile
