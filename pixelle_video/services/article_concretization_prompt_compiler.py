from __future__ import annotations

from pixelle_video.services.final_visual_prompt_compiler import FinalVisualPromptCompiler


class ArticleConcretizationPromptCompiler(FinalVisualPromptCompiler):
    """Compatibility import for callers migrating to FinalVisualPromptCompiler.

    This class intentionally contains no prompt semantics. The provider-neutral
    FinalVisualPromptCompiler is the single implementation source.
    """


__all__ = ["ArticleConcretizationPromptCompiler"]
