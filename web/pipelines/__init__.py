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
Pipeline UI Package

Exports registry functions and automatically registers available pipelines.
"""

from importlib import import_module

from web.pipelines.base import (
    PipelineUI,
    get_all_pipeline_uis,
    get_pipeline_ui,
    register_pipeline_ui,
)

# The import order defines the tab order on Home; keep quick_create first.
for _pipeline_module in (
    "standard",
    "action_transfer",
    "asset_based",
    "digital_human",
    "i2v",
    "stage2_projection",
):
    import_module(f"web.pipelines.{_pipeline_module}")

del _pipeline_module

__all__ = [
    "PipelineUI",
    "register_pipeline_ui",
    "get_pipeline_ui",
    "get_all_pipeline_uis"
]
