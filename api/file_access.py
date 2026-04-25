from collections.abc import Iterator
from pathlib import Path

from fastapi import HTTPException

ALLOWED_PREFIXES = [
    "output/",
    "workflows/",
    "templates/",
    "bgm/",
    "data/bgm/",
    "data/reference_audio/",
    "data/materials/",
    "data/templates/",
    "resources/",
]

MEDIA_TYPES = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".ogg": "audio/ogg",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".html": "text/html",
    ".json": "application/json",
}


def media_type_for(path: Path) -> str:
    return MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")


def resolve_allowed_file_path(file_path: str, *, cwd: Path | None = None) -> Path:
    root = (cwd or Path.cwd()).resolve()

    requested_path = None
    allowed_root = None
    for prefix in ALLOWED_PREFIXES:
        if file_path.startswith(prefix):
            requested_path = file_path
            allowed_root = (root / prefix.rstrip("/")).resolve()
            break
    if requested_path is None:
        requested_path = f"output/{file_path}"
        allowed_root = (root / "output").resolve()

    abs_path = (root / requested_path).resolve()
    if not (abs_path == allowed_root or abs_path.is_relative_to(allowed_root)):
        raise HTTPException(
            status_code=403,
            detail=f"Access denied: only {', '.join(p.rstrip('/') for p in ALLOWED_PREFIXES)} directories are accessible",
        )
    if not abs_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")
    if not abs_path.is_file():
        raise HTTPException(status_code=400, detail=f"Path is not a file: {file_path}")
    return abs_path


def parse_range_header(range_header: str | None, file_size: int) -> tuple[int, int, int, int]:
    if file_size <= 0:
        raise HTTPException(status_code=416, detail="Range not satisfiable")
    if not range_header:
        return 0, file_size - 1, file_size, 200
    if not range_header.startswith("bytes="):
        raise HTTPException(status_code=416, detail="Invalid Range header")

    value = range_header.removeprefix("bytes=")
    start_text, separator, end_text = value.partition("-")
    if separator != "-" or (start_text == "" and end_text == ""):
        raise HTTPException(status_code=416, detail="Invalid Range header")

    try:
        if start_text == "":
            suffix_length = int(end_text)
            if suffix_length <= 0:
                raise ValueError
            start = max(file_size - suffix_length, 0)
            end = file_size - 1
        else:
            start = int(start_text)
            end = int(end_text) if end_text else file_size - 1
    except ValueError:
        raise HTTPException(status_code=416, detail="Invalid Range header") from None

    if start < 0 or end >= file_size or start > end:
        raise HTTPException(status_code=416, detail="Range not satisfiable")
    return start, end, end - start + 1, 206


def iter_file_range(path: Path, *, start: int, length: int, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
    remaining = length
    with path.open("rb") as handle:
        handle.seek(start)
        while remaining > 0:
            chunk = handle.read(min(chunk_size, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def sanitize_upload_filename(filename: str) -> str:
    safe_name = (filename or "").replace("\\", "/").split("/")[-1].strip()
    if not safe_name or safe_name in {".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid filename")
    return safe_name
