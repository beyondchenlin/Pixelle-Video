from __future__ import annotations

from dataclasses import dataclass, field

from pixelle_video.models.llm_interaction_trace import (
    LLMTraceContext,
    trace_context_with_prompt_template,
)
from pixelle_video.models.script_generation import ScriptGenerationResponse
from pixelle_video.models.script_generation_limits import (
    SCRIPT_TARGET_WORDS_MAX,
    script_generation_max_tokens,
)
from pixelle_video.models.storyboard_plan import ScriptLengthMode
from pixelle_video.prompts.script_generation import render_script_generation_prompt
from pixelle_video.services.llm_interaction_recorder import LLMInteractionRecorder

DEFAULT_SCRIPT_LENGTH_WORDS = {
    ScriptLengthMode.SHORT: 120,
    ScriptLengthMode.MEDIUM: 240,
    ScriptLengthMode.LONG: 420,
}


@dataclass
class ScriptGenerationService:
    length_words: dict[ScriptLengthMode, int] = field(
        default_factory=lambda: dict(DEFAULT_SCRIPT_LENGTH_WORDS)
    )

    async def generate(
        self,
        *,
        llm_service,
        topic: str,
        script_length_mode: ScriptLengthMode | str = ScriptLengthMode.AUTO,
        script_target_words: int | None = None,
        trace_context: LLMTraceContext | None = None,
        trace_recorder: LLMInteractionRecorder | None = None,
    ) -> str:
        if llm_service is None:
            raise ValueError("script generation requires llm_service")

        normalized_topic = topic.strip()
        if not normalized_topic:
            raise ValueError("topic must not be empty")

        length_mode = ScriptLengthMode(script_length_mode)
        target_words = self._target_words(
            length_mode=length_mode,
            script_target_words=script_target_words,
        )
        rendered_prompt = render_script_generation_prompt(
            topic=normalized_topic,
            length_mode=length_mode.value,
            target_words=target_words,
        )

        prompt_trace_context = (
            trace_context_with_prompt_template(
                trace_context,
                rendered_prompt=rendered_prompt,
                attempt=1,
                stage="script_generation",
            )
            if trace_context is not None
            else None
        )
        response: ScriptGenerationResponse = await llm_service(
            prompt=rendered_prompt.text,
            response_type=ScriptGenerationResponse,
            temperature=0.7,
            max_tokens=script_generation_max_tokens(target_words),
            trace_context=prompt_trace_context,
            trace_recorder=trace_recorder,
        )
        return response.source_text

    def _target_words(
        self,
        *,
        length_mode: ScriptLengthMode,
        script_target_words: int | None,
    ) -> int | None:
        if length_mode == ScriptLengthMode.CUSTOM:
            if (
                type(script_target_words) is not int
                or script_target_words < 1
                or script_target_words > SCRIPT_TARGET_WORDS_MAX
            ):
                raise ValueError(
                    "script_target_words must be a positive integer "
                    f"no greater than {SCRIPT_TARGET_WORDS_MAX}"
                )
            return script_target_words
        if script_target_words is not None:
            raise ValueError("script_target_words is only valid with custom script length mode")
        return self.length_words.get(length_mode)

__all__ = ["ScriptGenerationService"]
