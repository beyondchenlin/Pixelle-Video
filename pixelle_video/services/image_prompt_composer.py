from __future__ import annotations

from pixelle_video.services.visual_prompt_composer import VisualPromptComposer

# Compatibility import for existing callers. There is no second implementation.
ImagePromptComposer = VisualPromptComposer

__all__ = ["ImagePromptComposer", "VisualPromptComposer"]
