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
Async helper functions for web UI
"""

from pixelle_video import __version__
from web.state.async_runtime import get_async_runtime


def run_async(coro):
    """Run async coroutine in sync context"""
    return get_async_runtime().run(coro)


def get_project_version():
    """Return the runtime version from the package's single version source."""

    return __version__
