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

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from loguru import logger

from api.file_access import (
    iter_file_range,
    media_type_for,
    parse_range_header,
    resolve_allowed_file_path,
)

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
    except Exception as e:
        logger.error(f"File stream error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/download/{file_path:path}")
async def download_file(file_path: str):
    """
    Download file by path as an attachment.
    """
    try:
        abs_path = resolve_allowed_file_path(file_path)
        return FileResponse(
            path=str(abs_path),
            media_type=media_type_for(abs_path),
            filename=abs_path.name,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"File download error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
    - "templates/1080x1920/default.html" → templates/1080x1920/default.html
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
    except Exception as e:
        logger.error(f"File access error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
