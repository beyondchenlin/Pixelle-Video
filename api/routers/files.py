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
File service endpoints

Provides access to generated files (videos, images, audio) and resource files.
"""

import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from loguru import logger

from api.file_access import (
    iter_file_range,
    media_type_for,
    parse_range_header,
    resolve_allowed_file_path,
    sanitize_upload_filename,
)
from pixelle_video.services.video_cover import ensure_video_cover

router = APIRouter(prefix="/files", tags=["Files"])


@router.get("/stream/{file_path:path}")
async def stream_file(file_path: str, request: Request):
    """
    Stream file by path with HTTP Range support.
    """
    try:
        abs_path = resolve_allowed_file_path(file_path)
        file_size = abs_path.stat().st_size
        start, end, length, status_code = parse_range_header(request.headers.get("Range"), file_size)
        response = StreamingResponse(
            iter_file_range(abs_path, start=start, length=length),
            media_type=media_type_for(abs_path),
            status_code=status_code,
        )
        response.headers["Accept-Ranges"] = "bytes"
        response.headers["Content-Length"] = str(length)
        if status_code == 206:
            response.headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
        return response
    except HTTPException:
        raise
    except Exception:
        logger.exception("File stream failed")
        raise HTTPException(status_code=500, detail="File service failed") from None


@router.get("/download/{file_path:path}")
async def download_file(file_path: str, filename: str | None = None):
    """
    Download file by path as an attachment.
    """
    try:
        abs_path = resolve_allowed_file_path(file_path)
        download_name = abs_path.name
        if filename and len(filename) <= 180 and not any(
            separator in filename for separator in ("/", "\\")
        ):
            try:
                safe_name = sanitize_upload_filename(filename)
            except HTTPException:
                pass
            else:
                requested_stem = Path(safe_name).stem[:120].strip()
                if requested_stem:
                    download_name = f"{requested_stem}{abs_path.suffix}"
        return FileResponse(
            path=str(abs_path),
            media_type=media_type_for(abs_path),
            filename=download_name,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("File download failed")
        raise HTTPException(status_code=500, detail="File service failed") from None


@router.get("/cover/{file_path:path}")
async def get_video_cover(file_path: str):
    """Return a cached, bounded preview cover for a generated video."""
    try:
        video_path = resolve_allowed_file_path(file_path)
        cover_path = await asyncio.to_thread(
            ensure_video_cover,
            video_path,
            output_root=Path.cwd() / "output",
        )
        if cover_path is None:
            raise HTTPException(status_code=404, detail="Video cover is unavailable")
        response = FileResponse(
            path=str(cover_path),
            media_type="image/jpeg",
            filename=cover_path.name,
            content_disposition_type="inline",
        )
        response.headers["Cache-Control"] = "private, max-age=3600"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response
    except HTTPException:
        raise
    except Exception:
        logger.exception("Video cover access failed")
        raise HTTPException(status_code=500, detail="File service failed") from None


@router.get("/{file_path:path}")
async def get_file(file_path: str):
    """
    Get file by path
    
    Serves files from allowed directories:
    - output/ - Generated files (videos, images, audio)
    - workflows/ - ComfyUI workflow files
    - templates/ - HTML templates
    - bgm/ - Background music
    - data/bgm/ - Custom background music
    - data/templates/ - Custom templates
    - resources/ - Other resources (images, fonts, etc.)
    
    - **file_path**: File path relative to allowed directories
    
    Examples:
    - "abc123.mp4" → output/abc123.mp4
    - "workflows/runninghub/image_flux.json" → workflows/runninghub/image_flux.json
    - "templates/1080x1920/image_default.html" → templates/1080x1920/image_default.html
    - "bgm/default.mp3" → bgm/default.mp3
    - "resources/example.png" → resources/example.png
    
    Returns file for download or preview.
    """
    try:
        abs_path = resolve_allowed_file_path(file_path)
        return FileResponse(
            path=str(abs_path),
            media_type=media_type_for(abs_path),
            filename=abs_path.name,
            content_disposition_type="inline",
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception("File access failed")
        raise HTTPException(status_code=500, detail="File service failed") from None
