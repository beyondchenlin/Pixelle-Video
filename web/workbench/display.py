from __future__ import annotations

import mimetypes
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

from web.utils.artifact_display_urls import artifact_url_for_streamlit


def remote_image_display(*, url: str | None, api_base_url: str) -> dict[str, str] | None:
    display_url = artifact_url_for_streamlit(url, api_base_url=api_base_url)
    if not display_url:
        return None
    return {"kind": "url", "url": display_url}


def local_bytes_image_display(*, file_uri: str) -> dict[str, object]:
    path = _path_from_file_uri(file_uri)
    data = path.read_bytes()
    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return {"kind": "bytes", "data": data, "mime_type": mime_type}


def _path_from_file_uri(file_uri: str) -> Path:
    parsed = urlparse(str(file_uri))
    if parsed.scheme != "file":
        raise ValueError("local artifact display requires a file URI")
    return Path(url2pathname(parsed.path))


__all__ = ["local_bytes_image_display", "remote_image_display"]
