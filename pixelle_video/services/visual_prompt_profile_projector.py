from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping, Sequence

from pixelle_video.models.final_visual_prompt_contract import RenderedMediaPrompt
from pixelle_video.models.style_resolution import StyledImagePromptBatch
from pixelle_video.models.visual_profile import VisualProfile
from pixelle_video.services.visual_quality_gate import VisualQualityGate

VISUAL_PROFILE_PROMPT_MARKER = "Visual profile contract:"


def apply_visual_profile_to_batch(
    *,
    batch: StyledImagePromptBatch,
    profile: VisualProfile,
    frame_contexts: Sequence[Mapping[str, Any]],
    quality_gate: VisualQualityGate | None = None,
) -> tuple[StyledImagePromptBatch, dict[str, Any]]:
    """Apply a VisualProfile after base prompt generation and before persistence.

    This keeps style/prompt/QA policy out of ad-hoc prompt_prefix strings and
    guarantees prompt_plan artifacts represent the final provider-facing
    prompt.
    """

    contexts = list(frame_contexts or [])
    prompts = [
        apply_visual_profile_to_prompt(
            prompt,
            profile=profile,
            frame_context=contexts[index] if index < len(contexts) else {},
            frame_index=index,
        )
        for index, prompt in enumerate(batch.prompts)
    ]
    rendered_prompts = list(batch.rendered_prompts or [])
    if rendered_prompts:
        rendered_prompts = [
            apply_visual_profile_to_rendered_prompt(
                rendered,
                profile=profile,
                frame_context=contexts[index] if index < len(contexts) else {},
                frame_index=index,
                prompt_override=prompts[index] if index < len(prompts) else None,
            )
            for index, rendered in enumerate(rendered_prompts)
        ]

    quality_report = None
    if quality_gate is not None:
        quality_report = quality_gate.evaluate_prompts(
            prompts,
            profile=profile,
            frame_contexts=contexts,
        )
        prompts = _apply_repair_clauses(prompts, quality_report.repair_clauses_by_frame)
        if rendered_prompts:
            rendered_prompts = [
                rendered.with_prompt(prompts[index])
                for index, rendered in enumerate(rendered_prompts)
            ]

    negative_prompt = merge_negative_prompt(batch.negative_prompt, profile.negative_prompt_rules)
    updated_batch = StyledImagePromptBatch(
        prompts=prompts,
        negative_prompt=negative_prompt,
        resolved_style=batch.resolved_style,
        planning_snapshot=batch.planning_snapshot,
        prompt_plan_bundle=batch.prompt_plan_bundle,
        rendered_prompts=rendered_prompts,
    )
    snapshot = {"profile": profile.to_dict()}
    if quality_report is not None:
        snapshot["quality_gate"] = quality_report.to_dict()
    return updated_batch, snapshot


def apply_visual_profile_to_rendered_prompt(
    rendered: RenderedMediaPrompt,
    *,
    profile: VisualProfile,
    frame_context: Mapping[str, Any] | None = None,
    frame_index: int = 0,
    prompt_override: str | None = None,
) -> RenderedMediaPrompt:
    prompt = prompt_override or apply_visual_profile_to_prompt(
        rendered.prompt,
        profile=profile,
        frame_context=frame_context,
        frame_index=frame_index,
    )
    metadata = rendered.metadata_to_dict()
    metadata["visual_profile_id"] = profile.profile_id
    metadata["visual_profile_version"] = profile.version
    return replace(
        rendered,
        prompt=prompt,
        negative_prompt=merge_negative_prompt(rendered.negative_prompt, profile.negative_prompt_rules),
        prompt_contract=rendered.prompt_contract.with_negative_rules(profile.negative_prompt_rules),
        metadata=metadata,
    )


def apply_visual_profile_to_prompt(
    prompt: str,
    *,
    profile: VisualProfile,
    frame_context: Mapping[str, Any] | None = None,
    frame_index: int = 0,
) -> str:
    base = str(prompt or "").strip()
    if VISUAL_PROFILE_PROMPT_MARKER in base:
        return base
    clauses = list(profile.prompt_contract_clauses())
    frame_clause = _frame_context_clause(frame_context or {}, frame_index=frame_index)
    if frame_clause:
        clauses.append(frame_clause)
    if not clauses:
        return base
    return " ".join(
        part.strip()
        for part in (
            base,
            VISUAL_PROFILE_PROMPT_MARKER,
            "; ".join(clauses),
        )
        if part and part.strip()
    )


def merge_negative_prompt(existing: str | None, extra_rules: Sequence[str]) -> str | None:
    parts: list[str] = []
    if existing:
        parts.extend(part.strip() for part in str(existing).split(",") if part.strip())
    parts.extend(str(rule or "").strip() for rule in extra_rules if str(rule or "").strip())
    deduped: list[str] = []
    seen: set[str] = set()
    for part in parts:
        key = part.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(part)
    return ", ".join(deduped) if deduped else None


def _apply_repair_clauses(
    prompts: Sequence[str],
    repair_clauses_by_frame: Mapping[int, Sequence[str]],
) -> list[str]:
    result: list[str] = []
    for index, prompt in enumerate(prompts):
        clauses = [str(item or "").strip() for item in repair_clauses_by_frame.get(index, ())]
        clauses = [item for item in clauses if item]
        if not clauses:
            result.append(str(prompt))
            continue
        result.append(f"{prompt} {'; '.join(clauses)}")
    return result


def _frame_context_clause(frame_context: Mapping[str, Any], *, frame_index: int) -> str:
    focus_detail = str(frame_context.get("focus_detail") or "").strip()
    visual_goal = str(frame_context.get("visual_goal") or "").strip()
    prompt_intent = str(frame_context.get("prompt_intent") or "").strip()
    values = [value for value in (visual_goal, prompt_intent, focus_detail) if value]
    if not values:
        return ""
    return "Frame visual intent: " + "；".join(values[:3])


__all__ = [
    "VISUAL_PROFILE_PROMPT_MARKER",
    "apply_visual_profile_to_batch",
    "apply_visual_profile_to_prompt",
    "apply_visual_profile_to_rendered_prompt",
    "merge_negative_prompt",
]
