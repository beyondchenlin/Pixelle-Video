from __future__ import annotations

from typing import Any

from web.components.prompt_plan_projection_preview import (
    render_prompt_plan_projection_preview,
)
from web.i18n import tr
from web.pipelines.base import PipelineUI, register_pipeline_ui


class Stage2ProjectionPipelineUI(PipelineUI):
    """Debug-only Stage 2 PromptPlan projection preview entry."""

    name = "stage2_prompt_plan_projection"
    icon = "🧭"

    @property
    def display_name(self):
        return tr("pipeline.stage2_projection.name")

    @property
    def description(self):
        return tr("pipeline.stage2_projection.description")

    def render(self, pixelle_video: Any):
        del pixelle_video
        return render_prompt_plan_projection_preview(translate=tr)


register_pipeline_ui(Stage2ProjectionPipelineUI)
