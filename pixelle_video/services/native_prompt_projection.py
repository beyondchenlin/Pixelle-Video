from __future__ import annotations

from collections import defaultdict

from pixelle_video.models.native_prompt import NativePromptHint
from pixelle_video.models.text_overlay import TextOverlayPlan, TextRenderingPolicy


class NativePromptProjection:
    def project(
        self,
        *,
        plan: TextOverlayPlan,
        policy: TextRenderingPolicy,
    ) -> dict[int, tuple[NativePromptHint, ...]]:
        if "native_prompt" not in policy.enabled_targets:
            return {}
        if not policy.allow_native_text_in_image:
            return {}

        grouped: dict[int, list[NativePromptHint]] = defaultdict(list)
        for candidate in plan.candidates:
            if (
                candidate.role != "model_native_hint"
                and "native_prompt" not in candidate.renderer_targets
            ):
                continue

            frame_index = int(candidate.source.get("frame_index", 0))
            if len(grouped[frame_index]) >= policy.max_items_per_frame:
                continue

            grouped[frame_index].append(
                NativePromptHint(
                    prompt_fragment=f'render the planned text "{candidate.text}"',
                    source_candidate_ids=(candidate.id,),
                )
            )

        return {frame_index: tuple(hints) for frame_index, hints in sorted(grouped.items())}
