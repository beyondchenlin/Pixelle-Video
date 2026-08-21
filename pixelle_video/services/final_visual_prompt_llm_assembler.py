from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from pydantic import ValidationError

from pixelle_video.models.final_visual_prompt_assembly import (
    FinalVisualPromptAssemblyResponse,
)
from pixelle_video.models.final_visual_prompt_bundle import FinalVisualPromptBundle
from pixelle_video.models.llm_interaction_trace import (
    LLMTraceContext,
    trace_context_with_prompt_template,
)
from pixelle_video.models.visual_entity_placement import VisualSceneType
from pixelle_video.prompts.template_loader import render_prompt_template
from pixelle_video.services.series_visual_signature_final_prompt_gate import (
    SeriesVisualSignatureFinalPromptGateError,
    assert_series_visual_signature_final_prompt,
)
from pixelle_video.services.series_visual_signature_projection_service import (
    SeriesVisualSignatureFrameProjection,
    SeriesVisualSignatureProjectionBatch,
)

_ASSEMBLY_SCHEMA_VERSION = "final_visual_prompt_assembly.v1"
_ASSEMBLY_STAGE = "final_visual_prompt_assembly"
_DEFAULT_MAX_CONCURRENCY = 4
_MAX_MAX_CONCURRENCY = 8


@dataclass(frozen=True)
class FinalVisualPromptAssemblyBatchResult:
    batch: SeriesVisualSignatureProjectionBatch
    audit: Mapping[str, Any]


@dataclass(frozen=True)
class _FrameAssemblyResult:
    frame: SeriesVisualSignatureFrameProjection
    audit: Mapping[str, Any]


@dataclass(frozen=True)
class FinalVisualPromptLLMAssembler:
    """Use an LLM for semantic assembly while keeping deterministic gates authoritative."""

    max_repair_attempts: int = 1

    async def assemble_batch(
        self,
        *,
        llm_service,
        batch: SeriesVisualSignatureProjectionBatch,
        trace_context: LLMTraceContext | None,
        trace_recorder,
        max_concurrency: int | None = None,
    ) -> FinalVisualPromptAssemblyBatchResult:
        if not batch.frames:
            raise ValueError("final visual prompt assembly requires at least one frame")
        if llm_service is None or trace_context is None or trace_recorder is None:
            return deterministic_prompt_assembly_result(
                batch,
                reason_code="llm_trace_unavailable",
            )

        concurrency = _normalized_concurrency(max_concurrency)
        semaphore = asyncio.Semaphore(concurrency)

        async def assemble(
            frame: SeriesVisualSignatureFrameProjection,
        ) -> _FrameAssemblyResult:
            async with semaphore:
                return await self._assemble_frame(
                    llm_service=llm_service,
                    frame=frame,
                    trace_context=trace_context,
                    trace_recorder=trace_recorder,
                )

        frame_results = await asyncio.gather(*(assemble(frame) for frame in batch.frames))
        assembled_batch = replace(
            batch,
            frames=tuple(result.frame for result in frame_results),
        )
        frame_audits = [dict(result.audit) for result in frame_results]
        llm_count = sum(item["source"] == "llm" for item in frame_audits)
        fallback_count = sum(item["source"] == "deterministic_fallback" for item in frame_audits)
        return FinalVisualPromptAssemblyBatchResult(
            batch=assembled_batch,
            audit={
                "schema_version": _ASSEMBLY_SCHEMA_VERSION,
                "mode": "llm",
                "status": "passed" if fallback_count == 0 else "completed_with_fallback",
                "frame_count": len(frame_audits),
                "llm_frame_count": llm_count,
                "deterministic_frame_count": fallback_count,
                "fallback_frame_count": fallback_count,
                "frames": frame_audits,
            },
        )

    async def _assemble_frame(
        self,
        *,
        llm_service,
        frame: SeriesVisualSignatureFrameProjection,
        trace_context: LLMTraceContext,
        trace_recorder,
    ) -> _FrameAssemblyResult:
        validation_feedback: dict[str, str] | None = None
        attempt_count = 0
        last_reason_code = "llm_assembly_failed"
        repair_attempts = max(0, int(self.max_repair_attempts))

        for attempt in range(1, repair_attempts + 2):
            attempt_count = attempt
            rendered_prompt = _render_assembly_prompt(
                frame=frame,
                validation_feedback=validation_feedback,
            )
            try:
                response = await llm_service(
                    prompt=rendered_prompt.text,
                    response_type=FinalVisualPromptAssemblyResponse,
                    temperature=0.1,
                    max_tokens=1800,
                    trace_context=trace_context_with_prompt_template(
                        trace_context,
                        rendered_prompt=rendered_prompt,
                        attempt=attempt,
                        stage=_ASSEMBLY_STAGE,
                        frame_id=frame.frame_id,
                        metadata={"assembly_mode": "llm"},
                    ),
                    trace_recorder=trace_recorder,
                )
                normalized = FinalVisualPromptAssemblyResponse.model_validate(response)
                bundle = _validated_llm_bundle(
                    frame=frame,
                    response=normalized,
                    attempt_count=attempt,
                )
                return _FrameAssemblyResult(
                    frame=replace(frame, bundle=bundle),
                    audit=_frame_audit(
                        frame_id=frame.frame_id,
                        bundle=bundle,
                        source="llm",
                        attempt_count=attempt,
                        repaired=attempt > 1,
                    ),
                )
            except Exception as exc:
                last_reason_code = _reason_code(exc)
                if attempt <= repair_attempts and _is_repairable(exc):
                    validation_feedback = {
                        "reason_code": last_reason_code,
                        "message": _bounded_validation_message(exc),
                    }
                    continue
                break

        fallback = _annotated_bundle(
            frame.bundle,
            source="deterministic_fallback",
            attempt_count=attempt_count,
            reason_code=last_reason_code,
        )
        return _FrameAssemblyResult(
            frame=replace(frame, bundle=fallback),
            audit=_frame_audit(
                frame_id=frame.frame_id,
                bundle=fallback,
                source="deterministic_fallback",
                attempt_count=attempt_count,
                reason_code=last_reason_code,
            ),
        )


def deterministic_prompt_assembly_result(
    batch: SeriesVisualSignatureProjectionBatch,
    *,
    reason_code: str = "user_disabled_llm_assembly",
) -> FinalVisualPromptAssemblyBatchResult:
    frames: list[SeriesVisualSignatureFrameProjection] = []
    frame_audits: list[dict[str, Any]] = []
    for frame in batch.frames:
        bundle = _annotated_bundle(
            frame.bundle,
            source="deterministic",
            attempt_count=0,
            reason_code=reason_code,
        )
        frames.append(replace(frame, bundle=bundle))
        frame_audits.append(
            _frame_audit(
                frame_id=frame.frame_id,
                bundle=bundle,
                source="deterministic",
                attempt_count=0,
                reason_code=reason_code,
            )
        )
    return FinalVisualPromptAssemblyBatchResult(
        batch=replace(batch, frames=tuple(frames)),
        audit={
            "schema_version": _ASSEMBLY_SCHEMA_VERSION,
            "mode": "deterministic",
            "status": "passed",
            "frame_count": len(frames),
            "llm_frame_count": 0,
            "deterministic_frame_count": len(frames),
            "fallback_frame_count": 0,
            "frames": frame_audits,
        },
    )


def _render_assembly_prompt(
    *,
    frame: SeriesVisualSignatureFrameProjection,
    validation_feedback: Mapping[str, str] | None,
):
    deterministic_bundle = frame.bundle.to_dict()
    input_payload = {
        "frame_id": frame.frame_id,
        "final_visual_contract": frame.contract.to_dict(),
        "deterministic_prompt_draft": {
            "positive_prompt": deterministic_bundle["positive_prompt"],
            "negative_prompt": deterministic_bundle["negative_prompt"],
            "prompt_sections": deterministic_bundle["metadata"].get("prompt_sections", {}),
        },
        "required_positive_fact_verbatim": _required_positive_facts(frame),
        "required_negative_fact_verbatim": _required_negative_facts(frame),
    }
    return render_prompt_template(
        "final_visual_prompt_assembly",
        {
            "assembly_input_json": json.dumps(
                input_payload,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            "validation_feedback_json": json.dumps(
                dict(validation_feedback or {}),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
        },
    )


def _required_positive_facts(
    frame: SeriesVisualSignatureFrameProjection,
) -> list[str]:
    contract = frame.contract
    signature = frame.signature
    placement = contract.entity_placement
    fusion = contract.scene_fusion
    metadata = frame.bundle.to_dict()["metadata"]
    sections = dict(metadata.get("prompt_sections") or {})
    facts: list[str] = []
    for section_name in ("main_content", "subject_protection", "fixed_identity"):
        _append_unique(facts, sections.get(section_name))
    for fact in (
        "Exactly one recurring identity exists in the whole frame",
        "one body",
        "one head",
        "one location",
        "visually subordinate to the main content",
        signature.role.value,
    ):
        _append_unique(facts, fact)
    if placement is not None:
        for fact in (
            "Same identity:",
            placement.horizontal_position.value,
            placement.depth_position.value,
            placement.relative_size.value.replace("_", "-"),
            placement.relation_target,
            placement.spatial_relation,
            placement.support_relation,
            placement.action,
            placement.orientation,
            placement.visible_extent.value.replace("_", "-"),
            "defining traits visible",
        ):
            _append_unique(facts, fact)
    if fusion is not None:
        fusion_fields = [fusion.occlusion_relation, fusion.style_relation]
        if fusion.scene_type is VisualSceneType.PHYSICAL_SCENE:
            fusion_fields[1:1] = [
                fusion.perspective_relation,
                fusion.contact_relation,
                fusion.lighting_relation,
                fusion.shadow_relation,
            ]
        for fact in fusion_fields:
            _append_unique(facts, fact)
    return facts


def _required_negative_facts(
    frame: SeriesVisualSignatureFrameProjection,
) -> list[str]:
    facts = [
        "sticker",
        "corner badge",
        "logo",
        "watermark",
        "floating",
        "mismatched style",
        "centered or oversized",
        "unrelated display platform",
        "duplicate recurring visual signature",
    ]
    profile = frame.signature.profile
    if profile is not None:
        facts.extend(profile.forbidden_traits)
    fusion = frame.contract.scene_fusion
    if fusion is not None:
        facts.extend(fusion.forbidden_compositions)
    if frame.contract.visible_text_policy == "no_visible_text":
        facts.append("readable text")
    result: list[str] = []
    for fact in facts:
        _append_unique(result, fact)
    return result


def _validated_llm_bundle(
    *,
    frame: SeriesVisualSignatureFrameProjection,
    response: FinalVisualPromptAssemblyResponse,
    attempt_count: int,
) -> FinalVisualPromptBundle:
    contract = frame.contract
    assert_series_visual_signature_final_prompt(
        positive_prompt=response.positive_prompt,
        negative_prompt=response.negative_prompt,
        required_subjects=frame.required_subjects,
        signature=frame.signature,
        visible_text_policy=contract.visible_text_policy,
        placement=contract.entity_placement,
        scene_fusion=contract.scene_fusion,
        frame_id=frame.frame_id,
    )
    return FinalVisualPromptBundle(
        positive_prompt=response.positive_prompt,
        negative_prompt=response.negative_prompt,
        locked_constraints=frame.bundle.locked_constraints,
        metadata={
            **frame.bundle.to_dict()["metadata"],
            "prompt_assembly": {
                "mode": "llm",
                "source": "llm",
                "attempt_count": attempt_count,
                "repaired": attempt_count > 1,
            },
        },
    )


def _annotated_bundle(
    bundle: FinalVisualPromptBundle,
    *,
    source: str,
    attempt_count: int,
    reason_code: str,
) -> FinalVisualPromptBundle:
    return FinalVisualPromptBundle(
        positive_prompt=bundle.positive_prompt,
        negative_prompt=bundle.negative_prompt,
        locked_constraints=bundle.locked_constraints,
        metadata={
            **bundle.to_dict()["metadata"],
            "prompt_assembly": {
                "mode": "deterministic" if source == "deterministic" else "llm",
                "source": source,
                "attempt_count": attempt_count,
                "reason_code": reason_code,
            },
        },
    )


def _frame_audit(
    *,
    frame_id: str,
    bundle: FinalVisualPromptBundle,
    source: str,
    attempt_count: int,
    repaired: bool = False,
    reason_code: str = "",
) -> dict[str, Any]:
    return {
        "frame_id": frame_id,
        "source": source,
        "attempt_count": attempt_count,
        "repaired": repaired,
        "reason_code": reason_code,
        "positive_prompt_chars": len(bundle.positive_prompt),
        "negative_prompt_chars": len(bundle.negative_prompt),
        "positive_prompt_sha256": _sha256(bundle.positive_prompt),
        "negative_prompt_sha256": _sha256(bundle.negative_prompt),
    }


def _append_unique(values: list[str], value: Any) -> None:
    text = " ".join(str(value or "").strip().split())
    if not text:
        return
    keys = {item.casefold() for item in values}
    if text.casefold() not in keys:
        values.append(text)


def _normalized_concurrency(value: int | None) -> int:
    if value is None:
        return _DEFAULT_MAX_CONCURRENCY
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("final prompt assembly max_concurrency must be a positive integer")
    return min(value, _MAX_MAX_CONCURRENCY)


def _is_repairable(exc: Exception) -> bool:
    return isinstance(
        exc,
        (
            SeriesVisualSignatureFinalPromptGateError,
            ValidationError,
            ValueError,
        ),
    )


def _reason_code(exc: Exception) -> str:
    if isinstance(exc, SeriesVisualSignatureFinalPromptGateError):
        return "business_gate_validation_failed"
    if isinstance(exc, ValidationError):
        return "structured_output_validation_failed"
    if isinstance(exc, ValueError):
        return "structured_output_parse_failed"
    return "llm_provider_failed"


def _bounded_validation_message(exc: Exception) -> str:
    message = " ".join(str(exc or type(exc).__name__).strip().split())
    return message[:500]


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


__all__ = [
    "FinalVisualPromptAssemblyBatchResult",
    "FinalVisualPromptLLMAssembler",
    "deterministic_prompt_assembly_result",
]
