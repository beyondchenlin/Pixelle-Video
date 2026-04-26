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

"""Disabled legacy custom pipeline boundary.

The standard video generation contract now requires a single source_text ->
StoryboardPlan -> CaptionSpeechPlan/master-track chain. The old custom pipeline
template performed per-frame TTS through FrameProcessor, so keeping it executable
would preserve a second speech/subtitle fact source. Private experiments should
subclass BasePipeline directly and explicitly choose their own contract instead
of reusing this removed template.
"""

from typing import Any

from pixelle_video.pipelines.base import BasePipeline


class CustomPipeline(BasePipeline):
    """Legacy custom pipeline placeholder kept only for import compatibility."""

    async def __call__(self, *args: Any, **kwargs: Any):
        raise RuntimeError(
            "CustomPipeline is disabled because it bypasses the standard pipeline "
            "source_text -> StoryboardPlan -> CaptionSpeechPlan/master-track contract. "
            "Use pipeline='standard' or implement a private BasePipeline subclass with "
            "an explicit speech/caption contract."
        )
