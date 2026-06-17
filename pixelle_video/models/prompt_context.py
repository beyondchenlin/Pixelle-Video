from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, TypeAlias

_PLAN_CONTEXT_KEYS = frozenset(
    {
        "plan_id",
        "plan_revision",
        "source_digest",
        "plan_source_text",
    }
)

# Frame context fields that add no value to LLM prompt templates.
# Dropping them saves tokens with zero quality impact.
_LLM_DROP_FRAME_KEYS: frozenset[str] = frozenset({
    "source_text",      # duplicate of frame_source_text
    "frame_id",         # internal tracking key, not consumed by templates
    "source_start",     # text position metadata, not visual
    "source_end",       # same
    "metadata",         # generic dict; focus_detail is extracted as top-level key
    "override_source",  # internal override tracking, not consumed by templates
})

_LLM_DROP_PLAN_KEYS: frozenset[str] = frozenset()


@dataclass(frozen=True)
class PromptContextEnvelope:
    """Global plan context plus one frame-aware context per storyboard frame."""

    plan_context: Mapping[str, Any]
    frame_contexts: tuple[Mapping[str, Any], ...]

    def __init__(
        self,
        *,
        plan_context: Mapping[str, Any] | None = None,
        frame_contexts: Sequence[Mapping[str, Any]] | None = None,
    ) -> None:
        normalized_plan = dict(plan_context or {})
        normalized_frames = tuple(dict(context) for context in frame_contexts or ())
        object.__setattr__(self, "plan_context", normalized_plan)
        object.__setattr__(self, "frame_contexts", normalized_frames)

    def __len__(self) -> int:
        return len(self.frame_contexts)

    def slice(self, start_index: int, item_count: int) -> "PromptContextEnvelope":
        return PromptContextEnvelope(
            plan_context=self.plan_context,
            frame_contexts=self.frame_contexts[start_index:start_index + item_count],
        )

    def to_prompt_payload(self) -> dict[str, Any]:
        return {
            "plan_context": dict(self.plan_context),
            "prompt_contexts": [dict(context) for context in self.frame_contexts],
        }

    def to_llm_payload(self) -> dict[str, Any]:
        """Return payload trimmed to fields LLM templates actually consume.

        Strips internal-only and duplicate keys that waste input tokens.
        Python-side consumers that need the full envelope continue using
        ``self.frame_contexts``; only the serialised JSON shrinks.
        """
        return {
            "plan_context": {
                k: v
                for k, v in self.plan_context.items()
                if k not in _LLM_DROP_PLAN_KEYS
            },
            "prompt_contexts": [
                {
                    k: v
                    for k, v in context.items()
                    if k not in _LLM_DROP_FRAME_KEYS
                }
                for context in self.frame_contexts
            ],
        }


PromptContextInput: TypeAlias = PromptContextEnvelope | Sequence[Mapping[str, Any]]


def normalize_prompt_contexts(
    prompt_contexts: PromptContextInput | None,
    expected_count: int,
    *,
    error_prefix: str = "prompt_contexts",
) -> PromptContextEnvelope | None:
    if prompt_contexts is None:
        return None

    if isinstance(prompt_contexts, PromptContextEnvelope):
        envelope = prompt_contexts
    else:
        envelope = _compact_legacy_contexts(prompt_contexts, error_prefix=error_prefix)

    if len(envelope) != expected_count:
        raise ValueError(f"{error_prefix} must match storyboard frame count")
    return envelope


def slice_prompt_contexts(
    prompt_contexts: PromptContextEnvelope | None,
    start_index: int,
    item_count: int,
) -> PromptContextEnvelope | None:
    if prompt_contexts is None:
        return None
    return prompt_contexts.slice(start_index, item_count)


def prompt_context_payload(
    prompt_contexts: PromptContextInput | None,
    expected_count: int,
    *,
    error_prefix: str = "prompt_contexts",
) -> dict[str, Any] | None:
    envelope = normalize_prompt_contexts(
        prompt_contexts,
        expected_count,
        error_prefix=error_prefix,
    )
    if envelope is None:
        return None
    return envelope.to_prompt_payload()


def llm_prompt_context_payload(
    prompt_contexts: PromptContextInput | None,
    expected_count: int,
    *,
    error_prefix: str = "prompt_contexts",
) -> dict[str, Any] | None:
    """Like :func:`prompt_context_payload` but strips fields not needed by LLM templates."""
    envelope = normalize_prompt_contexts(
        prompt_contexts,
        expected_count,
        error_prefix=error_prefix,
    )
    if envelope is None:
        return None
    return envelope.to_llm_payload()


def _compact_legacy_contexts(
    prompt_contexts: Sequence[Mapping[str, Any]],
    *,
    error_prefix: str,
) -> PromptContextEnvelope:
    plan_context: dict[str, Any] = {}
    frame_contexts: list[dict[str, Any]] = []
    for context in prompt_contexts:
        if not isinstance(context, Mapping):
            raise ValueError(f"{error_prefix} must contain mapping objects")
        frame_contexts.append(dict(context))

    for key in _PLAN_CONTEXT_KEYS:
        values = [
            context.get(key)
            for context in frame_contexts
            if context.get(key) is not None
        ]
        if values and all(value == values[0] for value in values):
            plan_context[key] = values[0]
            for context in frame_contexts:
                context.pop(key, None)

    return PromptContextEnvelope(
        plan_context=plan_context,
        frame_contexts=frame_contexts,
    )


__all__ = [
    "PromptContextEnvelope",
    "PromptContextInput",
    "normalize_prompt_contexts",
    "prompt_context_payload",
    "llm_prompt_context_payload",
    "slice_prompt_contexts",
]
