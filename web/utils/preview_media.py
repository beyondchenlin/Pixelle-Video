"""
Helpers for loading preview media in the Streamlit UI.
"""

from pathlib import Path

import httpx


def load_preview_image_bytes(preview_media_path: str, timeout: float = 10.0) -> bytes:
    """
    Load preview image bytes from either a local file path or an HTTP(S) URL.
    """
    if preview_media_path.startswith(("http://", "https://")):
        response = httpx.get(preview_media_path, follow_redirects=True, timeout=timeout)
        response.raise_for_status()
        return response.content

    return Path(preview_media_path).read_bytes()
