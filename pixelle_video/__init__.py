# ruff: noqa: E402
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

"""Pixelle-Video package facade.

Submodule imports such as ``pixelle_video.models.*`` should not eagerly import the
full runtime service stack.  Heavy providers are imported lazily when callers ask
for ``PixelleVideoCore`` or the singleton ``pixelle_video``.
"""

from pixelle_video.utils.os_util import configure_runtime_environment

configure_runtime_environment()

from pixelle_video._version import __version__
from pixelle_video.config import config_manager

__all__ = ["PixelleVideoCore", "pixelle_video", "config_manager", "__version__"]


def __getattr__(name: str):
    if name in {"PixelleVideoCore", "pixelle_video"}:
        from pixelle_video.service import PixelleVideoCore, pixelle_video

        return PixelleVideoCore if name == "PixelleVideoCore" else pixelle_video
    raise AttributeError(f"module 'pixelle_video' has no attribute {name!r}")
