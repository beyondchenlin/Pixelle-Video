"""Storyboard Workbench client adapters."""

from web.workbench.client import StoryboardWorkbenchClient, StoryboardWorkbenchClientError
from web.workbench.http_client import HttpStoryboardWorkbenchClient
from web.workbench.inprocess_client import InProcessStoryboardWorkbenchClient

__all__ = [
    "HttpStoryboardWorkbenchClient",
    "InProcessStoryboardWorkbenchClient",
    "StoryboardWorkbenchClient",
    "StoryboardWorkbenchClientError",
]
