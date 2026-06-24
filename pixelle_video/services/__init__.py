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

"""Pixelle-Video service facade.

The service package is used by light-weight model and prompt tests, so provider
modules are loaded lazily. Import concrete modules directly when a caller needs a
specific implementation.
"""

_SERVICE_IMPORTS = {
    "ComfyBaseService": ("pixelle_video.services.comfy_base_service", "ComfyBaseService"),
    "FrameProcessor": ("pixelle_video.services.frame_processor", "FrameProcessor"),
    "HistoryManager": ("pixelle_video.services.history_manager", "HistoryManager"),
    "LLMService": ("pixelle_video.services.llm_service", "LLMService"),
    "MediaService": ("pixelle_video.services.media", "MediaService"),
    "ImageService": ("pixelle_video.services.media", "MediaService"),
    "PersistenceService": ("pixelle_video.services.persistence", "PersistenceService"),
    "ReferenceImageAnalysisService": ("pixelle_video.services.reference_image_analysis", "ReferenceImageAnalysisService"),
    "ReferenceImageVisualContextAdapter": ("pixelle_video.services.reference_image_visual_context_adapter", "ReferenceImageVisualContextAdapter"),
    "TTSService": ("pixelle_video.services.tts_service", "TTSService"),
    "VideoService": ("pixelle_video.services.video", "VideoService"),
    "VisionLLMService": ("pixelle_video.services.vision_llm_service", "VisionLLMService"),
}

__all__ = list(_SERVICE_IMPORTS)


def __getattr__(name: str):
    if name not in _SERVICE_IMPORTS:
        raise AttributeError(f"module 'pixelle_video.services' has no attribute {name!r}")
    import importlib

    module_name, attr_name = _SERVICE_IMPORTS[name]
    module = importlib.import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
