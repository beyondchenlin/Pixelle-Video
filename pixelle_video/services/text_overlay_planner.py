from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from pixelle_video.models.text_overlay import (
    TextOverlayCandidate,
    TextOverlayPlan,
    TextRenderingPolicy,
)

_PUNCTUATION_RE = re.compile(r"[\s,，。.!！?？;；:：、]+")
_DENSITY_LIMITS = {
    "low": 1,
    "medium": 2,
    "high": 3,
}


@dataclass(frozen=True)
class TextOverlayPlanner:
    """Build semantic text overlay candidates from frame narrations."""

    def plan(
        self,
        *,
        narrations: Sequence[str],
        policy: TextRenderingPolicy,
    ) -> TextOverlayPlan:
        targets = tuple(policy.enabled_targets)
        if policy.image_text_mode == "suppress" or policy.max_items_per_frame == 0:
            return self._empty_plan(narrations=narrations, policy=policy)

        candidates: list[TextOverlayCandidate] = []
        native_prompt_enabled = (
            "native_prompt" in targets and policy.allow_native_text_in_image
        )
        role = "model_native_hint" if native_prompt_enabled else "keyword"
        suggested_slot = "native_prompt" if native_prompt_enabled else "center"

        for frame_index, narration in enumerate(narrations):
            phrases = (
                self._select_native_phrases(narration)
                if native_prompt_enabled
                else self._select_keyword_phrases(narration, self._candidate_limit(policy))
            )
            for phrase_index, phrase in enumerate(phrases):
                candidates.append(
                    TextOverlayCandidate(
                        id=f"text-{frame_index + 1}-{phrase_index + 1}",
                        text=phrase,
                        role=role,
                        suggested_slot=suggested_slot,
                        renderer_targets=targets,
                        importance=max(0.1, 1.0 - phrase_index * 0.1),
                        confidence=0.75,
                        source={
                            "kind": "narration",
                            "frame_index": frame_index,
                            "phrase_index": phrase_index,
                        },
                    )
                )

        return TextOverlayPlan(
            candidates=tuple(candidates),
            source_summary={
                "narration_count": len(narrations),
                "density": policy.density,
                "candidate_count": len(candidates),
            },
        )

    def _empty_plan(
        self,
        *,
        narrations: Sequence[str],
        policy: TextRenderingPolicy,
    ) -> TextOverlayPlan:
        return TextOverlayPlan(
            candidates=(),
            source_summary={
                "narration_count": len(narrations),
                "density": policy.density,
                "candidate_count": 0,
            },
        )

    def _candidate_limit(self, policy: TextRenderingPolicy) -> int:
        density_limit = _DENSITY_LIMITS.get(policy.density, policy.max_items_per_frame)
        return max(0, min(policy.max_items_per_frame, density_limit))

    def _select_keyword_phrases(self, narration: str, limit: int) -> list[str]:
        tokens = self._split_visible_tokens(narration)
        if not tokens:
            return []
        ranked = sorted(enumerate(tokens), key=lambda item: (-len(item[1]), item[0]))
        return [token for _, token in ranked[:limit]]

    def _select_native_phrases(self, narration: str) -> list[str]:
        cleaned = " ".join(self._split_visible_tokens(narration))
        return [cleaned] if cleaned else []

    def _split_visible_tokens(self, narration: str) -> list[str]:
        return [
            part.strip()
            for part in _PUNCTUATION_RE.split(narration or "")
            if part.strip()
        ]
