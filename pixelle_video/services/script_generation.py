from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pixelle_video.models.script_generation import ScriptGenerationResponse
from pixelle_video.models.storyboard_plan import ScriptLengthMode
from pixelle_video.prompts.script_generation import build_script_generation_prompt


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
        length_instruction = self._length_instruction(
            length_mode=length_mode,
            target_words=target_words,
        )
        prompt = build_script_generation_prompt(
            topic=normalized_topic,
            length_instruction=length_instruction,
        )

        response: ScriptGenerationResponse = await llm_service(
            prompt=prompt,
            response_type=ScriptGenerationResponse,
            temperature=0.7,
            max_tokens=self._max_tokens(target_words),
        )
        return response.source_text

    def _target_words(
        self,
        *,
        length_mode: ScriptLengthMode,
        script_target_words: int | None,
    ) -> int | None:
        if length_mode == ScriptLengthMode.CUSTOM:
            if type(script_target_words) is not int or script_target_words < 1:
                raise ValueError("script_target_words must be a positive integer")
            return script_target_words
        if script_target_words is not None:
            raise ValueError("script_target_words is only valid with custom script length mode")
        return self.length_words.get(length_mode)

    @staticmethod
    def _length_instruction(
        *,
        length_mode: ScriptLengthMode,
        target_words: int | None,
    ) -> str:
        if length_mode == ScriptLengthMode.AUTO:
            return "Use a natural length for the topic."
        return f"Write about {target_words} words."

    @staticmethod
    def _max_tokens(target_words: int | None) -> int:
        if target_words is None:
            return 2000
        return max(1200, int(target_words * 4))


__all__ = ["ScriptGenerationService"]
