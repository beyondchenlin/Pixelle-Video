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
FastAPI Dependencies

Provides dependency injection for PixelleVideoCore and shared platform services.
"""

from typing import Annotated

from fastapi import Depends
from loguru import logger

from api.config import api_config
from api.platform_dependencies import (
    PlatformDependencies,
    attach_platform_dependencies,
    build_platform_dependencies,
)
from pixelle_video.service import PixelleVideoCore

_pixelle_video_instance: PixelleVideoCore | None = None
_platform_dependencies: PlatformDependencies | None = None


async def get_pixelle_video() -> PixelleVideoCore:
    """Get the API-scoped PixelleVideoCore instance."""
    global _pixelle_video_instance

    if _pixelle_video_instance is None:
        _pixelle_video_instance = PixelleVideoCore()
        attach_platform_dependencies(
            _pixelle_video_instance,
            get_or_create_platform_dependencies(),
        )
        await _pixelle_video_instance.initialize()
        logger.info("Pixelle-Video initialized for API")

    return _pixelle_video_instance


async def shutdown_pixelle_video() -> None:
    """Shutdown Pixelle-Video instance and cleanup resources."""
    global _pixelle_video_instance, _platform_dependencies
    if _pixelle_video_instance:
        logger.info("Shutting down Pixelle-Video...")
        await _pixelle_video_instance.shutdown()
        _pixelle_video_instance = None
    _platform_dependencies = None

    from pixelle_video.services.frame_html import HTMLFrameGenerator

    await HTMLFrameGenerator.close_browser()


def get_or_create_platform_dependencies() -> PlatformDependencies:
    global _platform_dependencies
    if _platform_dependencies is None:
        # API fallback for tests and direct dependency use. Streamlit local mode
        # owns its task runtime in web.state.session.
        _platform_dependencies = build_platform_dependencies(api_config)
    return _platform_dependencies


def set_platform_dependencies(dependencies: PlatformDependencies) -> None:
    global _platform_dependencies
    _platform_dependencies = dependencies


PixelleVideoDep = Annotated[PixelleVideoCore, Depends(get_pixelle_video)]

