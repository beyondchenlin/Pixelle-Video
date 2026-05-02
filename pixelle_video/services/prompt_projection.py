from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pixelle_video.models.prompt_plan import PromptPlan, PromptProjection


def build_prompt_projection(
    prompt_plan: PromptPlan,
    *,
    metadata: Mapping[str, Any] | None = None,
) -> PromptProjection:
    return PromptProjection.from_prompt_plan(
        prompt_plan,
        metadata=metadata,
    )


__all__ = ["build_prompt_projection"]
