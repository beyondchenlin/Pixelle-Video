from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence

from pixelle_video.models.final_visual_prompt_contract import (
    FinalVisualPromptContract,
    RenderedMediaPrompt,
)
from pixelle_video.models.prompt_plan import (
    ImagePromptDraft,
    PromptPlan,
    PromptPlanBundle,
)
from pixelle_video.models.storyboard_plan import StoryboardPlan


def build_prompt_plan_bundle(
    *,
    storyboard_plan: StoryboardPlan,
    rendered_prompts: Sequence[RenderedMediaPrompt] | None = None,
    image_prompts: Sequence[str] | None = None,
    source_trace_id: str | None = None,
    source_trace_ids_by_frame: Mapping[str, str] | None = None,
    planning_snapshot: dict[str, object] | None = None,
) -> PromptPlanBundle:
    if rendered_prompts is not None and image_prompts is not None:
        raise ValueError("provide either rendered_prompts or image_prompts, not both")
    if rendered_prompts is None:
        if image_prompts is None:
            raise ValueError("rendered_prompts or image_prompts is required")
        prompt_items = tuple(image_prompts)
        if len(prompt_items) != len(storyboard_plan.frames):
            raise ValueError("image prompt count must match storyboard frame count")
        rendered_items = tuple(_rendered_prompt_from_text(prompt) for prompt in prompt_items)
    else:
        rendered_items = tuple(rendered_prompts)
        if len(rendered_items) != len(storyboard_plan.frames):
            raise ValueError("rendered prompt count must match storyboard frame count")

    drafts: list[ImagePromptDraft] = []
    plans: list[PromptPlan] = []
    ip_adaptations_by_frame = _ip_adaptations_by_frame(planning_snapshot)
    trace_ids_by_frame = _normalize_trace_ids_by_frame(source_trace_ids_by_frame)
    llm_trace_refs = _llm_trace_refs(planning_snapshot)
    final_prompt_template = _final_visual_prompt_template(planning_snapshot)
    for frame, rendered_prompt in zip(storyboard_plan.frames, rendered_items):
        prompt = _normalize_prompt(rendered_prompt.prompt)
        v45_fields = _series_visual_signature_v45_prompt_plan_fields(rendered_prompt)
        frame_source_trace_id = trace_ids_by_frame.get(frame.frame_id) or source_trace_id
        draft_id = _stable_id(
            "image_prompt_draft",
            storyboard_plan.plan_id,
            frame.frame_id,
            prompt,
        )
        prompt_plan_id = _stable_id(
            "prompt_plan",
            storyboard_plan.plan_id,
            frame.frame_id,
            draft_id,
            prompt,
            str(v45_fields.get("final_negative_prompt") or ""),
            str(v45_fields.get("contract_content_sha256") or ""),
        )
        draft = ImagePromptDraft(
            image_prompt_draft_id=draft_id,
            storyboard_plan_id=storyboard_plan.plan_id,
            frame_id=frame.frame_id,
            prompt_text=prompt,
            source_trace_id=frame_source_trace_id,
            metadata=_build_prompt_draft_metadata(
                frame_index=frame.index,
                llm_trace_refs=llm_trace_refs,
            ),
        )
        plan = PromptPlan(
            prompt_plan_id=prompt_plan_id,
            storyboard_plan_id=storyboard_plan.plan_id,
            frame_id=frame.frame_id,
            image_prompt_draft_id=draft.image_prompt_draft_id,
            prompt_sections=(
                v45_fields["prompt_sections"]
                if v45_fields
                else rendered_prompt.prompt_contract.prompt_sections()
            ),
            final_prompt=prompt,
            final_negative_prompt=v45_fields.get("final_negative_prompt"),
            identity_content_sha256=v45_fields.get("identity_content_sha256"),
            contract_content_sha256=v45_fields.get("contract_content_sha256"),
            contract_version=v45_fields.get("contract_version"),
            source_trace_id=frame_source_trace_id,
            metadata=_build_prompt_plan_metadata(
                frame_index=frame.index,
                ip_adaptation=ip_adaptations_by_frame.get(frame.frame_id),
                llm_trace_refs=llm_trace_refs,
                final_prompt_template=final_prompt_template,
                renderer_id=rendered_prompt.renderer_id,
                renderer_version=rendered_prompt.renderer_version,
            ),
        )
        drafts.append(draft)
        plans.append(plan)

    return PromptPlanBundle(
        storyboard_plan_id=storyboard_plan.plan_id,
        image_prompt_drafts=tuple(drafts),
        prompt_plans=tuple(plans),
        source_trace_id=source_trace_id or _first_trace_id(trace_ids_by_frame),
        metadata={"llm_trace_refs": llm_trace_refs} if llm_trace_refs else {},
    )


def _normalize_prompt(prompt: str) -> str:
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("image prompts must be non-empty strings")
    return prompt.strip()


def _series_visual_signature_v45_prompt_plan_fields(
    rendered_prompt: RenderedMediaPrompt,
) -> dict[str, object]:
    metadata = rendered_prompt.metadata_to_dict()
    raw = metadata.get("series_visual_signature_v45")
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise ValueError("series_visual_signature_v45 prompt metadata must be a mapping")
    prompt_sections = raw.get("prompt_sections")
    if not isinstance(prompt_sections, Mapping):
        raise ValueError(
            "series_visual_signature_v45.prompt_sections must be a mapping"
        )
    normalized_sections = {
        str(key).strip(): str(value).strip()
        for key, value in prompt_sections.items()
        if str(key).strip() and str(value).strip()
    }
    required_sections = {
        "main_content",
        "fixed_identity",
        "role",
        "placement",
        "scene_fusion",
        "style",
        "subject_protection",
    }
    if not required_sections.issubset(normalized_sections):
        missing = sorted(required_sections - set(normalized_sections))
        raise ValueError(
            "series_visual_signature_v45.prompt_sections is missing: "
            + ", ".join(missing)
        )
    for section_name, section_value in normalized_sections.items():
        if section_value not in rendered_prompt.prompt:
            raise ValueError(
                "series_visual_signature_v45.prompt_sections differs from final prompt: "
                + section_name
            )
    fields: dict[str, object] = {"prompt_sections": normalized_sections}
    negative_prompt = rendered_prompt.negative_prompt
    if not isinstance(negative_prompt, str) or not negative_prompt.strip():
        raise ValueError(
            "series_visual_signature_v45 final negative prompt must be non-empty"
        )
    fields["final_negative_prompt"] = negative_prompt.strip()
    for key in (
        "identity_content_sha256",
        "contract_content_sha256",
        "contract_version",
    ):
        value = raw.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"series_visual_signature_v45.{key} must be non-empty")
        fields[key] = value.strip()
    return fields


def _rendered_prompt_from_text(prompt: str) -> RenderedMediaPrompt:
    normalized = _normalize_prompt(prompt)
    contract = FinalVisualPromptContract(
        scene=normalized,
        composition="single unified image, readable composition",
        style_assignment="apply one coherent visual style to the whole image",
        character_layer_style="preserve scene subjects",
        world_layer_style="preserve a coherent readable world layer",
        integration_priority="source subjects and readability stay primary",
    )
    return RenderedMediaPrompt(
        prompt=normalized,
        negative_prompt=None,
        prompt_contract=contract,
        renderer_id="image_prompt_text_adapter",
        renderer_version="v1",
    )


def _normalize_trace_ids_by_frame(value: Mapping[str, str] | None) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(frame_id): str(trace_id).strip()
        for frame_id, trace_id in value.items()
        if str(frame_id).strip() and str(trace_id).strip()
    }


def _first_trace_id(trace_ids_by_frame: Mapping[str, str]) -> str | None:
    for trace_id in trace_ids_by_frame.values():
        if trace_id:
            return trace_id
    return None


def _ip_adaptations_by_frame(planning_snapshot: dict[str, object] | None) -> dict[str, dict[str, object]]:
    if not isinstance(planning_snapshot, dict):
        return {}
    payload = planning_snapshot.get("ip_adaptations_by_frame")
    if not isinstance(payload, dict):
        return {}
    return {
        str(frame_id): adaptation
        for frame_id, adaptation in payload.items()
        if isinstance(frame_id, str) and isinstance(adaptation, dict)
    }


def _llm_trace_refs(planning_snapshot: dict[str, object] | None) -> list[dict[str, str]]:
    if not isinstance(planning_snapshot, dict):
        return []
    refs: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def append_ref(value: object) -> None:
        if not isinstance(value, Mapping):
            return
        trace_id = str(value.get("trace_id") or "").strip()
        stage = str(value.get("stage") or "").strip()
        if not trace_id or not stage:
            return
        identity = (trace_id, stage)
        if identity in seen:
            return
        seen.add(identity)
        refs.append({"trace_id": trace_id, "stage": stage})

    llm_refs = planning_snapshot.get("llm_trace_refs")
    if isinstance(llm_refs, Sequence) and not isinstance(llm_refs, (str, bytes)):
        for ref in llm_refs:
            append_ref(ref)

    prompt_refs = planning_snapshot.get("prompt_generation_trace_refs_by_index")
    if isinstance(prompt_refs, Sequence) and not isinstance(prompt_refs, (str, bytes)):
        for ref in prompt_refs:
            append_ref(ref)

    return refs


def _final_visual_prompt_template(
    planning_snapshot: dict[str, object] | None,
) -> dict[str, str] | None:
    if not isinstance(planning_snapshot, dict):
        return None
    value = planning_snapshot.get("final_visual_prompt_template")
    if not isinstance(value, Mapping):
        return None
    metadata = {
        str(key): str(item).strip()
        for key, item in value.items()
        if str(key).strip() and str(item).strip()
    }
    return metadata or None


def _final_prompt_template_sections(
    final_prompt_template: dict[str, str] | None,
) -> dict[str, str]:
    if not final_prompt_template:
        return {}
    sections: dict[str, str] = {}
    for key in ("prompt_id", "version", "stage", "path"):
        value = final_prompt_template.get(key)
        if value:
            sections[f"final_prompt_template_{key}"] = value
    return sections


def _build_prompt_draft_metadata(
    *,
    frame_index: int,
    llm_trace_refs: list[dict[str, str]],
) -> dict[str, object]:
    metadata: dict[str, object] = {"frame_index": frame_index}
    if llm_trace_refs:
        metadata["llm_trace_refs"] = list(llm_trace_refs)
    return metadata


def _build_prompt_plan_metadata(
    *,
    frame_index: int,
    ip_adaptation: dict[str, object] | None,
    llm_trace_refs: list[dict[str, str]],
    final_prompt_template: dict[str, str] | None,
    renderer_id: str | None = None,
    renderer_version: str | None = None,
) -> dict[str, object]:
    metadata: dict[str, object] = {"frame_index": frame_index}
    if llm_trace_refs:
        metadata["llm_trace_refs"] = list(llm_trace_refs)
    if final_prompt_template:
        metadata["final_visual_prompt_template"] = dict(final_prompt_template)
    if renderer_id:
        metadata["prompt_renderer_id"] = renderer_id
    if renderer_version:
        metadata["prompt_renderer_version"] = renderer_version
    if not isinstance(ip_adaptation, dict):
        return metadata

    ip_presence_type = ip_adaptation.get("ip_presence_type")
    if isinstance(ip_presence_type, str) and ip_presence_type.strip():
        metadata["ip_presence_type"] = ip_presence_type.strip()

    image_text_plan = _summarize_image_text_plan(ip_adaptation.get("image_text_plan"))
    if image_text_plan:
        metadata["image_text_plan"] = image_text_plan

    visible_text_whitelist = _normalize_string_list(ip_adaptation.get("visible_text_whitelist"))
    if not visible_text_whitelist and image_text_plan:
        visible_text_whitelist = _normalize_string_list(
            image_text_plan.get("visible_text_whitelist")
        )
    if visible_text_whitelist:
        metadata["visible_text_whitelist"] = visible_text_whitelist

    return metadata


def _summarize_image_text_plan(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None

    summary: dict[str, object] = {}
    summary_text = value.get("summary_text")
    if isinstance(summary_text, str) and summary_text.strip():
        summary["summary_text"] = summary_text.strip()

    scene_text = _normalize_string_list(value.get("scene_text"))
    if scene_text:
        summary["scene_text"] = scene_text

    visible_text_whitelist = _normalize_string_list(value.get("visible_text_whitelist"))
    if visible_text_whitelist:
        summary["visible_text_whitelist"] = visible_text_whitelist

    return summary or None


def _normalize_string_list(value: object) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    normalized: list[str] = []
    for item in value:
        if isinstance(item, str):
            stripped = item.strip()
            if stripped:
                normalized.append(stripped)
    return normalized


def _stable_id(prefix: str, *parts: str) -> str:
    seed = "|".join(parts)
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


__all__ = ["build_prompt_plan_bundle"]
