from collections.abc import Iterator
from pathlib import Path

from fastapi import HTTPException

from api.runtime_context import get_api_runtime_context

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

WINDOWS_RESERVED_FILENAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "CONIN$",
    "CONOUT$",
    *{f"COM{index}" for index in range(1, 10)},
    *{f"LPT{index}" for index in range(1, 10)},
}

WINDOWS_ILLEGAL_FILENAME_CHARS = {'"', "<", ">", "|", "?", "*"}


def media_type_for(path: Path) -> str:
    return MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")


def resolve_allowed_file_path(
    file_path: str,
    *,
    project_root: str | Path | None = None,
    output_root: str | Path | None = None,
    cwd: str | Path | None = None,
) -> Path:
    """Resolve an allowed file against the API process's configured project root.

    ``cwd`` remains as a compatibility alias for callers that previously injected a
    test root. New callers should use ``project_root``. The process working directory
    is intentionally never used as an implicit filesystem authority.
    """
    if project_root is not None and cwd is not None:
        raise ValueError("project_root and cwd are mutually exclusive")

    explicit_root = project_root if project_root is not None else cwd
    if explicit_root is None:
        runtime_context = get_api_runtime_context()
        root = runtime_context.project_root
        default_output_root = runtime_context.output_root
    else:
        root = Path(explicit_root).resolve()
        default_output_root = (root / "output").resolve()
    resolved_output_root = (
        Path(output_root).resolve() if output_root is not None else default_output_root
    )

    requested_relative_path = None
    allowed_root = None
    for prefix in ALLOWED_PREFIXES:
        if file_path.startswith(prefix):
            requested_relative_path = file_path.removeprefix(prefix)
            allowed_root = (
                resolved_output_root
                if prefix == "output/"
                else (root / prefix.rstrip("/")).resolve()
            )
            break
    if requested_relative_path is None:
        requested_relative_path = file_path
        allowed_root = resolved_output_root

    abs_path = (allowed_root / requested_relative_path).resolve()
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
    if not range_header:
        return 0, max(file_size - 1, 0), file_size, 200

    content_range_header = {"Content-Range": f"bytes */{file_size}"}
    if file_size <= 0:
        raise HTTPException(status_code=416, detail="Range not satisfiable", headers=content_range_header)
    if not range_header.startswith("bytes="):
        raise HTTPException(status_code=416, detail="Invalid Range header", headers=content_range_header)

    value = range_header.removeprefix("bytes=")
    start_text, separator, end_text = value.partition("-")
    if separator != "-" or (start_text == "" and end_text == ""):
        raise HTTPException(status_code=416, detail="Invalid Range header", headers=content_range_header)

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
        raise HTTPException(status_code=416, detail="Invalid Range header", headers=content_range_header) from None

    if start < 0 or start >= file_size or start > end:
        raise HTTPException(status_code=416, detail="Range not satisfiable", headers=content_range_header)
    end = min(end, file_size - 1)
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
    safe_name = (filename or "").replace("\\", "/").split("/")[-1]
    if not safe_name or safe_name in {".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if any(ord(char) < 32 or ord(char) == 127 for char in safe_name):
        raise HTTPException(status_code=400, detail="Invalid filename")
    if ":" in safe_name or any(char in WINDOWS_ILLEGAL_FILENAME_CHARS for char in safe_name):
        raise HTTPException(status_code=400, detail="Invalid filename")
    if safe_name.endswith((" ", ".")):
        raise HTTPException(status_code=400, detail="Invalid filename")

    basename = safe_name.split(".", 1)[0].casefold()
    if basename in {reserved.casefold() for reserved in WINDOWS_RESERVED_FILENAMES}:
        raise HTTPException(status_code=400, detail="Invalid filename")
    return safe_name
