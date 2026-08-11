from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pixelle_video.models.article_concretization import ArticleConcretizationPlan
from pixelle_video.models.final_visual_prompt_bundle import FinalVisualPromptBundle
from pixelle_video.models.final_visual_prompt_contract_v45 import FinalVisualPromptContractV45
from pixelle_video.models.series_visual_signature import (
    SeriesVisualSignatureContract,
    SeriesVisualSignatureRequest,
    VisualSignatureProfileSnapshot,
)
from pixelle_video.models.series_visual_signature_projection_policy import (
    DEFAULT_SERIES_VISUAL_SIGNATURE_PROJECTION_AUDIT_POLICY,
    DEFAULT_SERIES_VISUAL_SIGNATURE_PROJECTION_BUDGET,
    SeriesVisualSignatureProjectionAuditPolicy,
    SeriesVisualSignatureProjectionBudget,
    SeriesVisualSignatureProjectionMetrics,
)
from pixelle_video.services.final_visual_prompt_compiler import FinalVisualPromptCompiler
from pixelle_video.services.series_visual_signature_contract_builder import (
    SeriesVisualSignatureContractBuilder,
)
from pixelle_video.services.series_visual_signature_final_prompt_gate import (
    assert_series_visual_signature_final_prompt,
)
from pixelle_video.services.series_visual_signature_prompt_presence import (
    prompt_contains_term,
)


class SeriesVisualSignatureProjectionError(RuntimeError):
    """Fail-closed frame projection error with bounded operational metadata."""

    def __init__(
        self,
        *,
        failed_frame_id: str,
        failed_frame_index: int,
        metrics: SeriesVisualSignatureProjectionMetrics,
        cause: Exception,
        budget: SeriesVisualSignatureProjectionBudget,
        audit_policy: SeriesVisualSignatureProjectionAuditPolicy,
    ) -> None:
        self.failed_frame_id = failed_frame_id
        self.failed_frame_index = failed_frame_index
        self.metrics = metrics
        self.reason_code = _projection_reason_code(cause)
        self.exception_type = type(cause).__name__
        self.budget = budget
        self.audit_policy = audit_policy
        super().__init__(
            "visual signature projection failed "
            f"at frame {failed_frame_id} ({failed_frame_index}): {self.reason_code}"
        )

    def audit_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.audit_policy.schema_version,
            "status": "failed",
            "audit_policy": self.audit_policy.to_dict(),
            **self.metrics.to_dict(),
            "failed_frame_id": self.failed_frame_id,
            "failed_frame_index": self.failed_frame_index,
            "reason_code": self.reason_code,
            "exception_type": self.exception_type,
        }
        self.budget.assert_audit_size(payload)
        return payload


@dataclass(frozen=True)
class SeriesVisualSignatureFrameProjection:
    frame_id: str
    bundle: FinalVisualPromptBundle
    contract: FinalVisualPromptContractV45
    signature: SeriesVisualSignatureContract
    required_subjects: tuple[str, ...]

    def audit_dict(self) -> dict[str, Any]:
        """Return bounded observability without duplicating protected content."""

        return {
            "frame_id": self.frame_id,
            "contract_id": self.contract.contract_id,
            "signature_role": self.signature.role.value,
            "required_subject_count": len(self.required_subjects),
            "identity_trait_count": (
                len(self.signature.profile.identity_traits)
                if self.signature.profile is not None
                else 0
            ),
            "positive_prompt_chars": len(self.bundle.positive_prompt),
            "negative_prompt_chars": len(self.bundle.negative_prompt),
            "positive_prompt_sha256": _sha256(self.bundle.positive_prompt),
            "negative_prompt_sha256": _sha256(self.bundle.negative_prompt),
            "final_gate_passed": True,
        }


@dataclass(frozen=True)
class SeriesVisualSignatureProjectionBatch:
    frames: tuple[SeriesVisualSignatureFrameProjection, ...]
    expected_frame_count: int
    budget: SeriesVisualSignatureProjectionBudget = (
        DEFAULT_SERIES_VISUAL_SIGNATURE_PROJECTION_BUDGET
    )
    audit_policy: SeriesVisualSignatureProjectionAuditPolicy = (
        DEFAULT_SERIES_VISUAL_SIGNATURE_PROJECTION_AUDIT_POLICY
    )

    @property
    def prompts(self) -> list[str]:
        return [frame.bundle.positive_prompt for frame in self.frames]

    @property
    def metrics(self) -> SeriesVisualSignatureProjectionMetrics:
        count = len(self.frames)
        return SeriesVisualSignatureProjectionMetrics(
            expected_frame_count=self.expected_frame_count,
            attempted_frame_count=count,
            projected_frame_count=count,
            unique_frame_count=len({frame.frame_id for frame in self.frames}),
        )

    def audit_dict(self) -> dict[str, Any]:
        metrics = self.metrics
        payload = {
            "schema_version": self.audit_policy.schema_version,
            "status": "passed",
            "audit_policy": self.audit_policy.to_dict(),
            **metrics.to_dict(),
            "frames": [frame.audit_dict() for frame in self.frames],
        }
        self.budget.assert_audit_size(payload)
        return payload


@dataclass(frozen=True)
class SeriesVisualSignatureProjectionService:
    """Single production source for V4.5 visual-signature prompt projection."""

    budget: SeriesVisualSignatureProjectionBudget = (
        DEFAULT_SERIES_VISUAL_SIGNATURE_PROJECTION_BUDGET
    )
    audit_policy: SeriesVisualSignatureProjectionAuditPolicy = (
        DEFAULT_SERIES_VISUAL_SIGNATURE_PROJECTION_AUDIT_POLICY
    )

    def project_batch(
        self,
        *,
        base_prompts: Sequence[str],
        frame_ids: Sequence[str],
        frame_contexts: Sequence[Mapping[str, Any]],
        request: SeriesVisualSignatureRequest,
        profile: VisualSignatureProfileSnapshot,
        article_concretization_plans: Sequence[ArticleConcretizationPlan] = (),
        base_visual_briefs_by_frame: Mapping[str, Mapping[str, Any]] | None = None,
        base_negative_prompts: Sequence[str | None] | None = None,
    ) -> SeriesVisualSignatureProjectionBatch:
        count = len(frame_ids)
        if count <= 0:
            raise ValueError("visual signature projection requires at least one frame")
        if len(base_prompts) != count or len(frame_contexts) != count:
            raise ValueError(
                "visual signature projection requires prompt, frame id, and frame context counts to match"
            )
        if len(set(frame_ids)) != count:
            raise ValueError("visual signature projection requires unique frame ids")
        if base_negative_prompts is None:
            base_negative_prompts = tuple(None for _ in range(count))
        if len(base_negative_prompts) != count:
            raise ValueError("base negative prompt count must match frame count")
        if not request.enabled:
            raise ValueError("visual signature projection requires an enabled request")

        self.budget.assert_batch_inputs(
            frame_ids=frame_ids,
            base_prompts=base_prompts,
            base_negative_prompts=base_negative_prompts,
        )
        self.budget.assert_profile(profile)

        plans_by_frame = {plan.frame_id: plan for plan in article_concretization_plans}
        if len(plans_by_frame) != len(article_concretization_plans):
            raise ValueError("article concretization plans must have unique frame ids")
        briefs = dict(base_visual_briefs_by_frame or {})

        frames: list[SeriesVisualSignatureFrameProjection] = []
        for index, frame_id in enumerate(frame_ids):
            base_prompt = str(base_prompts[index] or "")
            frame_context = frame_contexts[index]
            article_plan = plans_by_frame.get(frame_id)
            base_visual_brief = briefs.get(frame_id)
            try:
                required_subjects = _required_subjects(
                    article_plan=article_plan,
                    frame_context=frame_context,
                    base_visual_brief=base_visual_brief,
                )
                self.budget.assert_required_subjects(required_subjects)
                if _ip_already_in_prompt(base_prompt, profile):
                    frame = self._project_pass_through(
                        frame_id=frame_id,
                        base_prompt=base_prompt,
                        base_negative_prompt=base_negative_prompts[index],
                        profile=profile,
                        request=request,
                        frame_context=frame_context,
                        article_plan=article_plan,
                        required_subjects=required_subjects,
                    )
                else:
                    frame = self.project_frame(
                        frame_id=frame_id,
                        base_prompt=base_prompt,
                        frame_context=frame_context,
                        request=request,
                        profile=profile,
                        article_plan=article_plan,
                        base_visual_brief=base_visual_brief,
                        base_negative_prompt=base_negative_prompts[index],
                    )
            except SeriesVisualSignatureProjectionError:
                raise
            except Exception as exc:
                metrics = SeriesVisualSignatureProjectionMetrics(
                    expected_frame_count=count,
                    attempted_frame_count=index + 1,
                    projected_frame_count=len(frames),
                    unique_frame_count=len({item.frame_id for item in frames}),
                )
                raise SeriesVisualSignatureProjectionError(
                    failed_frame_id=str(frame_id),
                    failed_frame_index=index,
                    metrics=metrics,
                    cause=exc,
                    budget=self.budget,
                    audit_policy=self.audit_policy,
                ) from exc
            frames.append(frame)

        batch = SeriesVisualSignatureProjectionBatch(
            frames=tuple(frames),
            expected_frame_count=count,
            budget=self.budget,
            audit_policy=self.audit_policy,
        )
        if not batch.metrics.all_frames_passed:
            raise RuntimeError(
                "visual signature projection produced incomplete batch coverage; "
                "partial projection must not be published"
            )
        # Validate persistence size before returning the production batch.
        batch.audit_dict()
        return batch

    def project_frame(
        self,
        *,
        frame_id: str,
        base_prompt: str,
        frame_context: Mapping[str, Any],
        request: SeriesVisualSignatureRequest,
        profile: VisualSignatureProfileSnapshot,
        article_plan: ArticleConcretizationPlan | None = None,
        base_visual_brief: Mapping[str, Any] | None = None,
        base_negative_prompt: str | None = None,
    ) -> SeriesVisualSignatureFrameProjection:
        frame_id = _text(frame_id)
        base_prompt = _text(base_prompt)
        if not frame_id:
            raise ValueError("visual signature projection requires frame_id")
        if not base_prompt:
            raise ValueError("visual signature projection requires a signature-free base prompt")
        if not request.enabled:
            raise ValueError("visual signature projection requires an enabled request")

        self.budget.assert_batch_inputs(
            frame_ids=(frame_id,),
            base_prompts=(base_prompt,),
            base_negative_prompts=(base_negative_prompt,),
        )
        self.budget.assert_profile(profile)

        required_subjects = _required_subjects(
            article_plan=article_plan,
            frame_context=frame_context,
            base_visual_brief=base_visual_brief,
        )
        self.budget.assert_required_subjects(required_subjects)

        article_payload, render_payload, visible_text_policy, task, role_context = (
            _projection_context(
                base_prompt=base_prompt,
                frame_context=frame_context,
                article_plan=article_plan,
                required_subjects=required_subjects,
            )
        )
        signature = SeriesVisualSignatureContractBuilder().build(
            request=request,
            profile=profile,
            role_context=role_context,
        )
        contract = FinalVisualPromptContractV45(
            contract_id=f"v45:{frame_id}",
            frame_id=frame_id,
            primary_visual_task=task,
            required_subjects=required_subjects,
            article_concretization=article_payload,
            series_visual_signature=signature,
            diagram_render=render_payload,
            visible_text_policy=visible_text_policy,
            projected_prompt_parts=(),
        )
        bundle = FinalVisualPromptCompiler().compile(
            final_contract=contract,
            base_negative_prompt=base_negative_prompt,
        )
        return SeriesVisualSignatureFrameProjection(
            frame_id=frame_id,
            bundle=bundle,
            contract=contract,
            signature=signature,
            required_subjects=required_subjects,
        )

    def _project_pass_through(
        self,
        *,
        frame_id: str,
        base_prompt: str,
        base_negative_prompt: str | None = None,
        profile: VisualSignatureProfileSnapshot,
        request: SeriesVisualSignatureRequest,
        frame_context: Mapping[str, Any],
        article_plan: ArticleConcretizationPlan | None,
        required_subjects: Sequence[str],
    ) -> SeriesVisualSignatureFrameProjection:
        """Preserve LLM text only after the complete frame contract passes.

        Pass-through is a text optimization, never an alternate constraint path.
        Required article subjects, requested role, area limit, identity, and text
        policy are resolved exactly as they are for compiled projection frames.
        """

        if profile.profile_id != request.profile_id:
            raise ValueError(
                "visual signature pass-through requires profile and request profile_id to match; "
                f"profile has {profile.profile_id!r}, request has {request.profile_id!r}"
            )

        article_payload, render_payload, visible_text_policy, task, role_context = (
            _projection_context(
                base_prompt=base_prompt,
                frame_context=frame_context,
                article_plan=article_plan,
                required_subjects=required_subjects,
            )
        )
        signature = SeriesVisualSignatureContractBuilder().build(
            request=request,
            profile=profile,
            role_context=role_context,
        )

        negative_parts: list[str] = (
            [p.strip() for p in str(base_negative_prompt or "").split(",") if p.strip()]
            if base_negative_prompt
            else []
        )
        negative_parts.extend(
            (
                "recurring visual signature rendered as a photorealistic mascot",
                "recurring visual signature rendered as a sticker overlay",
                "recurring visual signature rendered as a logo overlay",
                "recurring visual signature rendered as a watermark",
                "duplicate recurring visual signature instances",
            )
        )
        negative_prompt = ", ".join(_dedupe(negative_parts))

        assert_series_visual_signature_final_prompt(
            positive_prompt=base_prompt,
            negative_prompt=negative_prompt,
            required_subjects=required_subjects,
            signature=signature,
            visible_text_policy=visible_text_policy,
        )
        contract = FinalVisualPromptContractV45(
            contract_id=f"v45:{frame_id}",
            frame_id=frame_id,
            primary_visual_task=task,
            required_subjects=tuple(required_subjects),
            article_concretization=article_payload,
            series_visual_signature=signature,
            diagram_render=render_payload,
            visible_text_policy=visible_text_policy,
            projected_prompt_parts=(),
        )
        bundle = FinalVisualPromptBundle(
            positive_prompt=base_prompt,
            negative_prompt=negative_prompt,
            locked_constraints=_dedupe(
                [*required_subjects, profile.display_name, *profile.identity_traits]
            ),
        )
        return SeriesVisualSignatureFrameProjection(
            frame_id=frame_id,
            bundle=bundle,
            contract=contract,
            signature=signature,
            required_subjects=tuple(required_subjects),
        )

def _projection_context(
    *,
    base_prompt: str,
    frame_context: Mapping[str, Any],
    article_plan: ArticleConcretizationPlan | None,
    required_subjects: Sequence[str],
) -> tuple[dict[str, Any], dict[str, Any], str, str, dict[str, Any]]:
    if article_plan is not None:
        anchor = article_plan.anchor.to_dict()
        anchor["required_subjects"] = list(required_subjects)
        diagram = article_plan.diagram.to_dict()
        diagram["visual_metaphor"] = base_prompt
        return (
            {
                "plan_id": article_plan.plan_id,
                "anchor": anchor,
                "diagram": diagram,
            },
            article_plan.render.to_dict(),
            article_plan.diagram.visible_text.effective_policy.value,
            article_plan.diagram.primary_visual_task.value,
            {
                "effective_anchor_kind": article_plan.resolution.effective_anchor_kind.value,
                "effective_diagram_grammar": article_plan.resolution.effective_diagram_grammar.value,
                "primary_visual_task": article_plan.diagram.primary_visual_task.value,
            },
        )

    task = _first_text(
        frame_context.get("primary_visual_task"),
        frame_context.get("visual_task"),
        "cognitive_explanation",
    )
    visible_text_policy = _first_text(
        frame_context.get("visible_text_policy"),
        "preserve_base",
    )
    return (
        {
            "anchor": {
                "anchor_kind": "auto",
                "anchor_claim": _first_text(
                    frame_context.get("frame_source_text"),
                    frame_context.get("source_text"),
                    base_prompt,
                ),
                "required_subjects": list(required_subjects),
            },
            "diagram": {
                "grammar": "plain_scene",
                "primary_visual_task": task,
                "visual_metaphor": base_prompt,
            },
            "projection_source_kind": "signature_free_base_prompt",
        },
        {"render_style": "preserve_base"},
        visible_text_policy,
        task,
        {"primary_visual_task": task},
    )


def _required_subjects(
    *,
    article_plan: ArticleConcretizationPlan | None,
    frame_context: Mapping[str, Any],
    base_visual_brief: Mapping[str, Any] | None,
) -> tuple[str, ...]:
    values: list[Any] = []
    if article_plan is not None:
        values.extend(article_plan.anchor.required_subjects)
    if isinstance(base_visual_brief, Mapping):
        subjects = base_visual_brief.get("main_subjects")
        if isinstance(subjects, Sequence) and not isinstance(subjects, (str, bytes)):
            values.extend(subjects)
    primary = frame_context.get("primary_subject")
    if primary is not None:
        values.append(primary)
    secondary = frame_context.get("secondary_subjects")
    if isinstance(secondary, Sequence) and not isinstance(secondary, (str, bytes)):
        values.extend(secondary)
    explicit = frame_context.get("required_subjects")
    if isinstance(explicit, Sequence) and not isinstance(explicit, (str, bytes)):
        values.extend(explicit)
    return _dedupe(values)


def _dedupe(values: Sequence[Any]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _text(value)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return tuple(result)


def _ip_already_in_prompt(
    prompt: str,
    profile: VisualSignatureProfileSnapshot,
) -> bool:
    if not profile.display_name or not profile.identity_traits:
        return False
    if not prompt_contains_term(prompt, profile.display_name):
        return False
    return all(
        prompt_contains_term(prompt, trait)
        for trait in profile.identity_traits
    )


def _first_text(*values: Any) -> str:
    for value in values:
        raw = getattr(value, "value", value)
        text = _text(raw)
        if text:
            return text
    return ""


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _projection_reason_code(cause: Exception) -> str:
    message = str(cause).casefold()
    if "structured required subjects" in message:
        return "missing_required_subjects"
    if "runtime budget" in message or "persistence budget" in message:
        return "projection_budget_exceeded"
    if "protected visual prompt semantics exceed" in message:
        return "protected_prompt_budget_exceeded"
    if "profile" in message or "identity" in message:
        return "identity_contract_invalid"
    if "final" in message and "gate" in message:
        return "final_prompt_gate_failed"
    return "frame_projection_failed"


__all__ = [
    "SeriesVisualSignatureFrameProjection",
    "SeriesVisualSignatureProjectionBatch",
    "SeriesVisualSignatureProjectionError",
    "SeriesVisualSignatureProjectionService",
]
