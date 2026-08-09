from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from pixelle_video.platform_defaults import normalize_api_base_url
from pixelle_video.utils.os_util import get_output_path


@dataclass(frozen=True)
class OutputMediaUrls:
    stream_url: str
    download_url: str
    storage_path: str


def build_output_media_urls(
    video_path: str | Path,
    *,
    api_base_url: str,
    output_root: str | Path | None = None,
    download_name: str | None = None,
) -> OutputMediaUrls | None:
    """Build API-backed URLs only for an existing regular file under output/."""
    root = Path(output_root or get_output_path()).resolve()
    raw_path = Path(str(video_path))
    if raw_path.is_absolute():
        candidate = raw_path
    else:
        parts = raw_path.parts
        if parts and parts[0].casefold() == "output":
            raw_path = Path(*parts[1:])
        candidate = root / raw_path

    try:
        resolved = candidate.resolve(strict=True)
    except (FileNotFoundError, OSError, RuntimeError):
        return None
    if not resolved.is_file() or not resolved.is_relative_to(root):
        return None

    relative_path = resolved.relative_to(root).as_posix()
    storage_path = f"output/{relative_path}"
    encoded_path = quote(storage_path, safe="/")
    try:
        base_url = normalize_api_base_url(
            api_base_url,
            setting_name="Home output media API base URL",
        ).rstrip("/")
    except ValueError:
        return None
    download_url = f"{base_url}/files/download/{encoded_path}"
    if download_name:
        download_url = f"{download_url}?filename={quote(str(download_name)[:180], safe='')}"
    return OutputMediaUrls(
        stream_url=f"{base_url}/files/stream/{encoded_path}",
        download_url=download_url,
        storage_path=storage_path,
    )


__all__ = ["OutputMediaUrls", "build_output_media_urls"]
