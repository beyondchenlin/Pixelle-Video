from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from pixelle_video.models.article_concretization import ArticleConcretizationPlan
from pixelle_video.models.content_bound_ip import (
    ContentBoundIPPresencePlan,
    IPParticipationMechanism,
)
from pixelle_video.models.final_visual_prompt_bundle import FinalVisualPromptBundle
from pixelle_video.models.final_visual_prompt_contract_v46 import (
    FinalVisualPromptContractV46,
)
from pixelle_video.models.mandatory_content_bound_visual_anchor import (
    MandatoryContentBoundVisualAnchorContract,
    SemanticRemovalMode,
    SemanticRemovalTest,
    build_subject_anchors,
)
from pixelle_video.models.series_visual_signature import (
    SeriesVisualSignatureContract,
    SeriesVisualSignatureRequest,
    SeriesVisualSignatureRole,
    VisualSignatureProfileSnapshot,
)
from pixelle_video.models.series_visual_signature_projection_policy import (
    DEFAULT_SERIES_VISUAL_SIGNATURE_PROJECTION_AUDIT_POLICY,
    DEFAULT_SERIES_VISUAL_SIGNATURE_PROJECTION_BUDGET,
    SeriesVisualSignatureProjectionAuditPolicy,
    SeriesVisualSignatureProjectionBudget,
    SeriesVisualSignatureProjectionMetrics,
)
from pixelle_video.services.content_bound_ip_planner import ContentBoundIPPlanner
from pixelle_video.services.final_visual_prompt_compiler import FinalVisualPromptCompiler
from pixelle_video.services.series_visual_signature_base_prompt_gate import (
    assert_series_visual_signature_base_prompt_is_identity_isolated,
)
from pixelle_video.services.series_visual_signature_contract_builder import (
    SeriesVisualSignatureContractBuilder,
)
from pixelle_video.services.series_visual_signature_profile_snapshot_builder import (
    validate_series_visual_signature_profile_snapshot,
)
from pixelle_video.services.visual_entity_placement_planner import (
    VisualEntityPlacementPlanner,
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
    contract: FinalVisualPromptContractV46
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
            "identity_content_sha256": (
                self.signature.profile.identity_content_sha256
                if self.signature.profile is not None
                else ""
            ),
            "contract_content_sha256": self.contract.contract_content_sha256,
            "contract_version": self.contract.contract_version,
            # Compatibility alias retained for existing trace readers. This gate
            # validates provider prompts, not rendered pixels.
            "final_gate_passed": True,
            "prompt_contract_gate_passed": True,
            "rendered_output_gate_passed": None,
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
    """Single production source for V4.6 mandatory-anchor prompt projection.

    Every frame receives one complete identity, placement and scene-fusion
    contract before the shared final compiler and provider boundary run.
    """

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
        normalized_frame_ids = tuple(_text(frame_id) for frame_id in frame_ids)
        count = len(normalized_frame_ids)
        if count <= 0:
            raise ValueError("visual signature projection requires at least one frame")
        if any(not frame_id for frame_id in normalized_frame_ids):
            raise ValueError("visual signature projection requires non-empty frame ids")
        if len(base_prompts) != count or len(frame_contexts) != count:
            raise ValueError(
                "visual signature projection requires prompt, frame id, and frame context counts to match"
            )
        if len(set(normalized_frame_ids)) != count:
            raise ValueError("visual signature projection requires unique frame ids")
        if base_negative_prompts is None:
            base_negative_prompts = tuple(None for _ in range(count))
        if len(base_negative_prompts) != count:
            raise ValueError("base negative prompt count must match frame count")
        if not request.enabled:
            raise ValueError("visual signature projection requires an enabled request")
        profile = validate_series_visual_signature_profile_snapshot(
            profile,
            expected_profile_id=request.profile_id,
        )

        self.budget.assert_batch_inputs(
            frame_ids=normalized_frame_ids,
            base_prompts=base_prompts,
            base_negative_prompts=base_negative_prompts,
        )
        self.budget.assert_profile(profile)

        plans_by_frame = {
            _text(plan.frame_id): plan for plan in article_concretization_plans
        }
        if len(plans_by_frame) != len(article_concretization_plans):
            raise ValueError("article concretization plans must have unique frame ids")
        briefs = {
            _text(frame_id): brief
            for frame_id, brief in dict(base_visual_briefs_by_frame or {}).items()
        }
        if len(briefs) != len(dict(base_visual_briefs_by_frame or {})):
            raise ValueError("base visual briefs must have unique normalized frame ids")

        frames: list[SeriesVisualSignatureFrameProjection] = []
        for index, frame_id in enumerate(normalized_frame_ids):
            try:
                frame = self.project_frame(
                    frame_id=frame_id,
                    base_prompt=str(base_prompts[index] or ""),
                    frame_context=frame_contexts[index],
                    request=request,
                    profile=profile,
                    article_plan=plans_by_frame.get(frame_id),
                    base_visual_brief=briefs.get(frame_id),
                    base_negative_prompt=base_negative_prompts[index],
                    previous_frame_summary=(
                        _frame_summary(
                            frame_contexts[index - 1],
                            str(base_prompts[index - 1] or ""),
                        )
                        if index > 0
                        else ""
                    ),
                    next_frame_summary=(
                        _frame_summary(
                            frame_contexts[index + 1],
                            str(base_prompts[index + 1] or ""),
                        )
                        if index + 1 < count
                        else ""
                    ),
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
        previous_frame_summary: str = "",
        next_frame_summary: str = "",
    ) -> SeriesVisualSignatureFrameProjection:
        frame_id = _text(frame_id)
        base_prompt = _text(base_prompt)
        if not frame_id:
            raise ValueError("visual signature projection requires frame_id")
        if not base_prompt:
            raise ValueError("visual signature projection requires a non-empty visual prompt")
        if not request.enabled:
            raise ValueError("visual signature projection requires an enabled request")
        profile = validate_series_visual_signature_profile_snapshot(
            profile,
            expected_profile_id=request.profile_id,
        )

        self.budget.assert_batch_inputs(
            frame_ids=(frame_id,),
            base_prompts=(base_prompt,),
            base_negative_prompts=(base_negative_prompt,),
        )
        self.budget.assert_profile(profile)

        required_subject_anchors, subject_source_resolution = _required_subjects(
            frame_id=frame_id,
            article_plan=article_plan,
            frame_context=frame_context,
            base_visual_brief=base_visual_brief,
        )
        required_subjects = tuple(
            subject.label for subject in required_subject_anchors
        )
        self.budget.assert_required_subjects(required_subjects)
        assert_series_visual_signature_base_prompt_is_identity_isolated(
            base_prompt=base_prompt,
            required_subjects=required_subjects,
            profile=profile,
        )

        article_payload, render_payload, visible_text_policy, task, role_context = (
            _projection_context(
                base_prompt=base_prompt,
                frame_context=frame_context,
                article_plan=article_plan,
                required_subjects=required_subjects,
            )
        )
        article_payload["subject_source_resolution"] = subject_source_resolution
        content_claim = _first_text(
            frame_context.get("local_claim"),
            frame_context.get("frame_source_text"),
            frame_context.get("source_text"),
            article_payload.get("anchor", {}).get("anchor_claim")
            if isinstance(article_payload.get("anchor"), Mapping)
            else "",
            base_prompt,
        )
        planner_payload = ContentBoundIPPlanner().plan_for_frame(
            {
                **dict(frame_context),
                "frame_id": frame_id,
                "local_claim": content_claim,
                "visual_task": task,
                "physical_metaphor": base_prompt,
            },
            selected_visual_route=role_context,
            article_summary={
                "core_claim": content_claim,
                "required_subjects": list(required_subjects),
            },
            required_subjects=required_subjects,
            previous_frame_summary=previous_frame_summary,
            next_frame_summary=next_frame_summary,
            ip_profile=profile.to_dict(),
        )
        participation_plan = ContentBoundIPPresencePlan.from_mapping(
            planner_payload.get("content_bound_ip_presence_plan") or planner_payload,
            frame_id=frame_id,
        )
        signature = SeriesVisualSignatureContractBuilder().build(
            request=request,
            profile=profile,
            role_context=role_context,
            suggested_area_ratio=participation_plan.recommended_area_ratio,
            suggested_role=_signature_role(participation_plan.participation_mechanism),
        )
        placement, fusion = VisualEntityPlacementPlanner().plan(
            frame_id=frame_id,
            base_prompt=base_prompt,
            frame_context=frame_context,
            base_visual_brief=base_visual_brief,
            article_concretization=article_payload,
            required_subjects=required_subjects,
            signature=signature,
            participation_plan=participation_plan,
        )
        anchor_subject_overlap = _anchor_subject_overlap(
            profile=profile,
            required_subjects=required_subject_anchors,
        )
        removal_test = SemanticRemovalTest(
            mode=(
                SemanticRemovalMode.ANCHOR_IS_ARTICLE_SUBJECT
                if anchor_subject_overlap
                else SemanticRemovalMode.ANCHOR_DISTINCT_FROM_SUBJECT
            ),
            content_survives_without_anchor_or_brand_identity=True,
            anchor_contribution_is_meaningful=True,
            content_survival_evidence=(
                "Removing brand-specific identity traits preserves the named article subject, action, and event."
                if anchor_subject_overlap
                else "All structured article subjects remain protected independently of the recurring identity."
            ),
            anchor_contribution_evidence=participation_plan.semantic_necessity,
        )
        mandatory_contract = MandatoryContentBoundVisualAnchorContract(
            frame_id=frame_id,
            content_claim=content_claim,
            required_subjects=required_subject_anchors,
            visual_thesis=base_prompt,
            participation_plan=participation_plan,
            identity_contract=signature,
            placement=placement,
            scene_fusion=fusion,
            semantic_removal_test=removal_test,
            final_scene_description=base_prompt,
            forbidden_compositions=fusion.forbidden_compositions,
            anchor_subject_overlap=anchor_subject_overlap,
        )
        contract = FinalVisualPromptContractV46(
            contract_id=f"v46:{frame_id}",
            frame_id=frame_id,
            primary_visual_task=task,
            mandatory_anchor_contract=mandatory_contract,
            article_concretization=article_payload,
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
    grammar = _first_text(
        frame_context.get("effective_diagram_grammar"),
        frame_context.get("explanation_diagram_grammar"),
        frame_context.get("diagram_grammar"),
        "plain_scene",
    )
    return (
        {
            "anchor": {
                "anchor_kind": "auto",
                "anchor_claim": _first_text(
                    frame_context.get("visual_goal"),
                    frame_context.get("prompt_intent"),
                    frame_context.get("shot_purpose"),
                    frame_context.get("frame_source_text"),
                    frame_context.get("source_text"),
                    base_prompt,
                ),
                "required_subjects": list(required_subjects),
            },
            "diagram": {
                "grammar": grammar,
                "primary_visual_task": task,
                "visual_metaphor": base_prompt,
            },
            "projection_source_kind": "identity_aware_visual_prompt",
        },
        {
            "render_style": "preserve_base",
            "style_already_projected": True,
        },
        visible_text_policy,
        task,
        {
            "effective_diagram_grammar": grammar,
            "primary_visual_task": task,
        },
    )


def _required_subjects(
    *,
    frame_id: str,
    article_plan: ArticleConcretizationPlan | None,
    frame_context: Mapping[str, Any],
    base_visual_brief: Mapping[str, Any] | None,
) -> tuple[tuple[Any, ...], dict[str, Any]]:
    sources: list[tuple[str, Sequence[Any]]] = []
    explicit = frame_context.get("required_subjects")
    if isinstance(explicit, Sequence) and not isinstance(explicit, (str, bytes)):
        locked_fields = frame_context.get("locked_fields")
        is_user_override = (
            isinstance(locked_fields, Sequence)
            and not isinstance(locked_fields, (str, bytes))
            and "required_subjects" in locked_fields
        )
        sources.append(
            (
                "user_frame_override" if is_user_override else "frame_article_evidence",
                explicit,
            )
        )
    if article_plan is not None:
        sources.append(("frame_article_evidence", article_plan.anchor.required_subjects))
    if isinstance(base_visual_brief, Mapping):
        subjects = base_visual_brief.get("main_subjects")
        if isinstance(subjects, Sequence) and not isinstance(subjects, (str, bytes)):
            sources.append(("article_level_evidence", subjects))
    inferred: list[Any] = []
    primary = frame_context.get("primary_subject")
    if primary is not None:
        inferred.append(primary)
    secondary = frame_context.get("secondary_subjects")
    if isinstance(secondary, Sequence) and not isinstance(secondary, (str, bytes)):
        inferred.extend(secondary)
    if inferred:
        sources.append(("storyboard_subject", inferred))

    subjects: list[Any] = []
    subject_sources: list[str] = []
    selected_by_id: dict[str, int] = {}
    selected_by_label: dict[str, int] = {}
    overridden: list[dict[str, str]] = []
    source_candidates = [
        (
            source_name,
            build_subject_anchors(
                frame_id=frame_id,
                values=values,
                evidence_source=source_name,
            ),
        )
        for source_name, values in sources
    ]
    for source_name, candidates in source_candidates:
        for candidate in candidates:
            existing_index = selected_by_id.get(candidate.subject_id)
            if existing_index is None:
                existing_index = selected_by_label.get(candidate.label.casefold())
            if existing_index is not None:
                existing = subjects[existing_index]
                evidence_ids = tuple(
                    dict.fromkeys(
                        (*existing.evidence_span_ids, *candidate.evidence_span_ids)
                    )
                )
                subjects[existing_index] = replace(
                    existing,
                    evidence_span_ids=evidence_ids,
                    loss_policy=(
                        "must_keep"
                        if "must_keep"
                        in {existing.loss_policy, candidate.loss_policy}
                        else existing.loss_policy
                    ),
                )
                overridden.append(
                    {
                        "subject_id": existing.subject_id,
                        "retained_source": subject_sources[existing_index],
                        "ignored_source": source_name,
                        "reason": "higher_priority_source_retained_and_evidence_merged",
                    }
                )
                continue
            index = len(subjects)
            subjects.append(candidate)
            subject_sources.append(source_name)
            selected_by_id[candidate.subject_id] = index
            selected_by_label[candidate.label.casefold()] = index

    if not subjects:
        raise ValueError(
            f"frame {frame_id}: structured required subjects must not be empty"
        )
    return (
        tuple(subjects),
        {
            "priority_order": [
                "user_frame_override",
                "frame_article_evidence",
                "article_level_evidence",
                "storyboard_subject",
            ],
            "selected": [
                {"subject_id": subject.subject_id, "source": source}
                for subject, source in zip(subjects, subject_sources)
            ],
            "overridden": overridden,
        },
    )


def _signature_role(
    mechanism: IPParticipationMechanism,
) -> SeriesVisualSignatureRole:
    if mechanism is IPParticipationMechanism.ACTION_EXECUTOR:
        return SeriesVisualSignatureRole.OPERATOR
    if mechanism is IPParticipationMechanism.READER_PROXY:
        return SeriesVisualSignatureRole.CORE_ACTOR
    return SeriesVisualSignatureRole.GUIDE


def _anchor_subject_overlap(
    *,
    profile: VisualSignatureProfileSnapshot,
    required_subjects: Sequence[Any],
) -> bool:
    identity_names = {
        value.casefold()
        for value in (profile.display_name, profile.profile_id)
        if str(value or "").strip()
    }
    for subject in required_subjects:
        values = (
            str(getattr(subject, "label", "")),
            str(getattr(subject, "source_phrase", "")),
        )
        if any(
            identity in value.casefold()
            for identity in identity_names
            for value in values
        ):
            return True
    return False


def _frame_summary(frame_context: Mapping[str, Any], base_prompt: str) -> str:
    return _first_text(
        frame_context.get("local_claim"),
        frame_context.get("frame_source_text"),
        frame_context.get("source_text"),
        frame_context.get("visual_goal"),
        base_prompt,
    )


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
    if "signature-free base prompt gate failed" in message:
        return "base_prompt_identity_leak"
    if "structured required subjects" in message:
        return "missing_required_subjects"
    if "runtime budget" in message or "persistence budget" in message:
        return "projection_budget_exceeded"
    if (
        "protected visual prompt semantics exceed" in message
        or "prompt budget" in message
        or ("exceeds" in message and "character" in message)
    ):
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
