from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from pixelle_video.models.article_concretization import ArticleConcretizationPlan
from pixelle_video.models.final_visual_prompt_contract_v45 import FinalVisualPromptContractV45
from pixelle_video.models.series_visual_signature import (
    SeriesVisualSignatureContract,
    SeriesVisualSignatureRequest,
    VisualSignatureProfileSnapshot,
)
from pixelle_video.models.series_visual_signature_profile import SeriesVisualSignatureProfile
from pixelle_video.services.article_concretization_prompt_compiler import (
    ArticleConcretizationPromptCompiler,
)
from pixelle_video.services.provider_z_image_adapter import project_z_image_prompt_bundle
from pixelle_video.services.series_visual_signature_contract_builder import (
    SeriesVisualSignatureContractBuilder,
)
from pixelle_video.services.series_visual_signature_profile_builder import (
    SeriesVisualSignatureProfileBuilder,
)
from pixelle_video.services.series_visual_signature_prompt_presence import (
    prompt_presence_map,
)


@dataclass(frozen=True)
class SeriesVisualSignatureShadowFrameInput:
    frame_id: str
    source_kind: str
    primary_visual_task: str
    required_subjects: tuple[str, ...]
    article_concretization: Mapping[str, Any]
    diagram_render: Mapping[str, Any]
    visible_text_policy: str
    role_context: Mapping[str, Any]

    @classmethod
    def from_article_plan(
        cls,
        plan: ArticleConcretizationPlan,
    ) -> "SeriesVisualSignatureShadowFrameInput":
        return cls(
            frame_id=plan.frame_id,
            source_kind="article_concretization_plan",
            primary_visual_task=plan.diagram.primary_visual_task.value,
            required_subjects=tuple(plan.anchor.required_subjects),
            article_concretization={
                "plan_id": plan.plan_id,
                "anchor": plan.anchor.to_dict(),
                "diagram": plan.diagram.to_dict(),
            },
            diagram_render=plan.render.to_dict(),
            visible_text_policy=plan.diagram.visible_text.effective_policy.value,
            role_context={
                "effective_anchor_kind": plan.resolution.effective_anchor_kind.value,
                "effective_diagram_grammar": plan.resolution.effective_diagram_grammar.value,
                "primary_visual_task": plan.diagram.primary_visual_task.value,
            },
        )

    @classmethod
    def from_frame_context(
        cls,
        *,
        frame_id: str,
        production_prompt: str,
        context: Mapping[str, Any],
    ) -> "SeriesVisualSignatureShadowFrameInput":
        required_subjects = _required_subjects_from_frame_context(context)
        visual_summary = " ".join(str(production_prompt or "").split())
        if not visual_summary:
            visual_summary = _first_text(
                context.get("visual_goal"),
                context.get("prompt_intent"),
                context.get("frame_source_text"),
                context.get("source_text"),
                "one clear scene",
            )
        primary_visual_task = _first_text(
            context.get("primary_visual_task"),
            context.get("visual_task"),
            "cognitive_explanation",
        )
        visible_text_policy = _first_text(
            context.get("visible_text_policy"),
            "free_text_allowed",
        )
        return cls(
            frame_id=frame_id,
            source_kind="storyboard_frame_context",
            primary_visual_task=primary_visual_task,
            required_subjects=required_subjects,
            article_concretization={
                "anchor": {
                    "anchor_kind": "auto",
                    "anchor_claim": _first_text(
                        context.get("frame_source_text"),
                        context.get("source_text"),
                        visual_summary,
                    ),
                    "required_subjects": list(required_subjects),
                },
                "diagram": {
                    "grammar": "plain_scene",
                    "primary_visual_task": primary_visual_task,
                    "visual_metaphor": visual_summary,
                },
                "shadow_source_kind": "storyboard_frame_context",
            },
            diagram_render={"render_style": "preserve_base"},
            visible_text_policy=visible_text_policy,
            role_context={
                "primary_visual_task": primary_visual_task,
            },
        )


@dataclass(frozen=True)
class SeriesVisualSignatureShadowFrameResult:
    frame_id: str
    status: str
    production_prompt: str
    candidate_prompt: str = ""
    candidate_negative_prompt: str = ""
    required_subjects: tuple[str, ...] = ()
    candidate_source_kind: str = ""
    production_required_subjects_present: Mapping[str, bool] = field(default_factory=dict)
    candidate_required_subjects_present: Mapping[str, bool] = field(default_factory=dict)
    production_identity_terms_present: Mapping[str, bool] = field(default_factory=dict)
    candidate_identity_terms_present: Mapping[str, bool] = field(default_factory=dict)
    candidate_contract: Mapping[str, Any] | None = None
    final_gate_passed: bool = False
    provider_projection_passed: bool = False
    candidate_error: str | None = None
    production_render_result: Mapping[str, Any] | None = None
    candidate_render_result: Mapping[str, Any] | None = None

    @property
    def passed(self) -> bool:
        return (
            self.status == "passed"
            and self.final_gate_passed
            and self.provider_projection_passed
            and self.candidate_error is None
            and all(self.candidate_required_subjects_present.values())
            and all(self.candidate_identity_terms_present.values())
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_id": self.frame_id,
            "status": self.status,
            "passed": self.passed,
            "candidate_source_kind": self.candidate_source_kind,
            "production_prompt": self.production_prompt,
            "candidate_prompt": self.candidate_prompt,
            "candidate_negative_prompt": self.candidate_negative_prompt,
            "required_subjects": list(self.required_subjects),
            "production_required_subjects_present": dict(self.production_required_subjects_present),
            "candidate_required_subjects_present": dict(self.candidate_required_subjects_present),
            "production_identity_terms_present": dict(self.production_identity_terms_present),
            "candidate_identity_terms_present": dict(self.candidate_identity_terms_present),
            "candidate_contract": dict(self.candidate_contract) if self.candidate_contract is not None else None,
            "final_gate_passed": self.final_gate_passed,
            "provider_projection_passed": self.provider_projection_passed,
            "candidate_error": self.candidate_error,
            "production_render_result": dict(self.production_render_result) if self.production_render_result is not None else None,
            "candidate_render_result": dict(self.candidate_render_result) if self.candidate_render_result is not None else None,
        }


@dataclass(frozen=True)
class SeriesVisualSignatureShadowReport:
    enabled: bool
    expected_frame_count: int
    frame_results: tuple[SeriesVisualSignatureShadowFrameResult, ...] = ()
    global_errors: tuple[str, ...] = ()
    comparison_level: str = "prompt_contract_shadow"
    candidate_provider: str = "z_image"
    candidate_media_generation: str = "disabled"

    @property
    def attempted_frame_count(self) -> int:
        return sum(1 for item in self.frame_results if item.status != "blocked")

    @property
    def passed_frame_count(self) -> int:
        return sum(1 for item in self.frame_results if item.passed)

    @property
    def failed_frame_count(self) -> int:
        return sum(1 for item in self.frame_results if not item.passed)

    @property
    def coverage_rate(self) -> float:
        if self.expected_frame_count <= 0:
            return 0.0
        return self.attempted_frame_count / self.expected_frame_count

    @property
    def candidate_pass_rate(self) -> float:
        if self.attempted_frame_count <= 0:
            return 0.0
        return self.passed_frame_count / self.attempted_frame_count

    @property
    def ready_for_cutover(self) -> bool:
        if not self.enabled or self.expected_frame_count <= 0 or self.global_errors:
            return False
        return (
            len(self.frame_results) == self.expected_frame_count
            and self.coverage_rate == 1.0
            and self.candidate_pass_rate == 1.0
            and self.failed_frame_count == 0
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "series_visual_signature_shadow.v1",
            "enabled": self.enabled,
            "comparison_level": self.comparison_level,
            "candidate_provider": self.candidate_provider,
            "candidate_media_generation": self.candidate_media_generation,
            "expected_frame_count": self.expected_frame_count,
            "attempted_frame_count": self.attempted_frame_count,
            "passed_frame_count": self.passed_frame_count,
            "failed_frame_count": self.failed_frame_count,
            "coverage_rate": self.coverage_rate,
            "candidate_pass_rate": self.candidate_pass_rate,
            "ready_for_cutover": self.ready_for_cutover,
            "global_errors": list(self.global_errors),
            "frames": [item.to_dict() for item in self.frame_results],
        }


def build_series_visual_signature_shadow_report(
    *,
    production_prompts: Sequence[str],
    frame_ids: Sequence[str],
    article_concretization_plans: Sequence[ArticleConcretizationPlan],
    request: SeriesVisualSignatureRequest | None,
    legacy_profile: SeriesVisualSignatureProfile | None = None,
    ip_profile: Any = None,
    enabled_fallback: bool = False,
    fallback_frame_contexts: Mapping[str, Mapping[str, Any]] | None = None,
) -> SeriesVisualSignatureShadowReport:
    """Run the V4.5 signature path beside production without changing output.

    Article frames consume the article-concretization plan. Other frames consume
    the existing storyboard/prompt context while reusing the production base
    scene text as the visual summary. This isolates the visual-signature source
    replacement from unrelated base-scene generation changes.

    Every exception is converted into an observational failure report. The
    shadow path never issues a second provider media request.
    """

    normalized_frame_ids = tuple(str(value or "").strip() for value in frame_ids)
    normalized_prompts = tuple(str(value or "") for value in production_prompts)
    try:
        return _build_shadow_report(
            production_prompts=normalized_prompts,
            frame_ids=normalized_frame_ids,
            article_concretization_plans=article_concretization_plans,
            request=request,
            legacy_profile=legacy_profile,
            ip_profile=ip_profile,
            enabled_fallback=enabled_fallback,
            fallback_frame_contexts=fallback_frame_contexts or {},
        )
    except Exception as exc:
        enabled = bool(request.enabled if request is not None else enabled_fallback)
        error = f"unexpected shadow comparison failure: {type(exc).__name__}: {exc}"
        return SeriesVisualSignatureShadowReport(
            enabled=enabled,
            expected_frame_count=len(normalized_frame_ids),
            frame_results=tuple(
                SeriesVisualSignatureShadowFrameResult(
                    frame_id=frame_id,
                    status="blocked",
                    production_prompt=(
                        normalized_prompts[index]
                        if index < len(normalized_prompts)
                        else ""
                    ),
                    candidate_error=error,
                )
                for index, frame_id in enumerate(normalized_frame_ids)
            ),
            global_errors=(error,),
        )


def _build_shadow_report(
    *,
    production_prompts: Sequence[str],
    frame_ids: Sequence[str],
    article_concretization_plans: Sequence[ArticleConcretizationPlan],
    request: SeriesVisualSignatureRequest | None,
    legacy_profile: SeriesVisualSignatureProfile | None,
    ip_profile: Any,
    enabled_fallback: bool,
    fallback_frame_contexts: Mapping[str, Mapping[str, Any]],
) -> SeriesVisualSignatureShadowReport:
    expected_count = len(frame_ids)
    if len(production_prompts) != expected_count:
        return SeriesVisualSignatureShadowReport(
            enabled=bool(request.enabled if request is not None else enabled_fallback),
            expected_frame_count=expected_count,
            global_errors=(
                "shadow comparison requires production prompt count to match frame id count",
            ),
        )

    resolved_request = request or SeriesVisualSignatureRequest.from_mapping(
        {
            "series_visual_signature_enabled": enabled_fallback,
            "series_visual_signature_profile_id": getattr(
                ip_profile,
                "series_visual_signature_profile_id",
                None,
            ),
            "series_visual_signature_role": "auto",
        }
    )
    if not resolved_request.enabled:
        return SeriesVisualSignatureShadowReport(
            enabled=False,
            expected_frame_count=expected_count,
        )

    try:
        resolved_legacy_profile = legacy_profile
        if resolved_legacy_profile is None and ip_profile is not None:
            resolved_legacy_profile = SeriesVisualSignatureProfileBuilder().build(ip_profile)
        profile_snapshot = _profile_snapshot(resolved_request, resolved_legacy_profile)
    except Exception as exc:
        error = f"shadow profile preparation failed: {type(exc).__name__}: {exc}"
        return SeriesVisualSignatureShadowReport(
            enabled=True,
            expected_frame_count=expected_count,
            frame_results=tuple(
                SeriesVisualSignatureShadowFrameResult(
                    frame_id=frame_id,
                    status="blocked",
                    production_prompt=production_prompts[index],
                    candidate_error=error,
                )
                for index, frame_id in enumerate(frame_ids)
            ),
            global_errors=(error,),
        )

    inputs_by_frame = {
        plan.frame_id: SeriesVisualSignatureShadowFrameInput.from_article_plan(plan)
        for plan in article_concretization_plans
    }
    results: list[SeriesVisualSignatureShadowFrameResult] = []
    for index, frame_id in enumerate(frame_ids):
        production_prompt = production_prompts[index]
        frame_input = inputs_by_frame.get(frame_id)
        if frame_input is None:
            fallback_context = fallback_frame_contexts.get(frame_id)
            if isinstance(fallback_context, Mapping):
                frame_input = SeriesVisualSignatureShadowFrameInput.from_frame_context(
                    frame_id=frame_id,
                    production_prompt=production_prompt,
                    context=fallback_context,
                )
        if frame_input is None:
            results.append(
                SeriesVisualSignatureShadowFrameResult(
                    frame_id=frame_id,
                    status="blocked",
                    production_prompt=production_prompt,
                    production_identity_terms_present=_presence_map(
                        production_prompt,
                        _identity_terms(profile_snapshot),
                    ),
                    candidate_error=(
                        "V4.5 shadow candidate requires either an article concretization "
                        "plan or a same-frame storyboard context"
                    ),
                )
            )
            continue
        results.append(
            _build_frame_result(
                production_prompt=production_prompt,
                frame_input=frame_input,
                request=resolved_request,
                profile=profile_snapshot,
            )
        )

    return SeriesVisualSignatureShadowReport(
        enabled=True,
        expected_frame_count=expected_count,
        frame_results=tuple(results),
    )


def _profile_snapshot(
    request: SeriesVisualSignatureRequest,
    profile: SeriesVisualSignatureProfile | None,
) -> VisualSignatureProfileSnapshot:
    if profile is None:
        raise ValueError("resolved SeriesVisualSignatureProfile is required")
    if request.profile_id is None:
        raise ValueError("series_visual_signature_profile_id is required")
    if profile.profile_id != request.profile_id:
        raise ValueError(
            "shadow profile does not match request profile_id: "
            f"requested={request.profile_id}, resolved={profile.profile_id}"
        )
    identity_contract = profile.identity_contract
    traits = tuple(identity_contract.required_identity_traits)
    if not traits:
        traits = tuple(profile.identity_kernel)
    return VisualSignatureProfileSnapshot(
        profile_id=profile.profile_id,
        display_name=profile.display_name,
        identity_traits=traits,
        style_safe_traits=(),
        forbidden_traits=(),
        source_asset_ids=tuple(profile.reference_assets),
    )


def _build_frame_result(
    *,
    production_prompt: str,
    frame_input: SeriesVisualSignatureShadowFrameInput,
    request: SeriesVisualSignatureRequest,
    profile: VisualSignatureProfileSnapshot,
) -> SeriesVisualSignatureShadowFrameResult:
    required_subjects = frame_input.required_subjects
    identity_terms = _identity_terms(profile)
    production_subject_presence = _presence_map(production_prompt, required_subjects)
    production_identity_presence = _presence_map(production_prompt, identity_terms)

    if frame_input.source_kind == "storyboard_frame_context" and not required_subjects:
        return SeriesVisualSignatureShadowFrameResult(
            frame_id=frame_input.frame_id,
            status="blocked",
            production_prompt=production_prompt,
            candidate_source_kind=frame_input.source_kind,
            production_required_subjects_present=production_subject_presence,
            production_identity_terms_present=production_identity_presence,
            candidate_error=(
                "non-article shadow candidate requires structured subject facts from "
                "the storyboard frame or base visual brief"
            ),
        )

    candidate_prompt = ""
    candidate_negative_prompt = ""
    candidate_contract_payload: Mapping[str, Any] | None = None
    try:
        signature = SeriesVisualSignatureContractBuilder().build(
            request=request,
            profile=profile,
            strict_user_mode=True,
            role_context=frame_input.role_context,
        )
        final_contract = FinalVisualPromptContractV45(
            contract_id=f"shadow:{frame_input.frame_id}",
            frame_id=frame_input.frame_id,
            primary_visual_task=frame_input.primary_visual_task,
            required_subjects=required_subjects,
            article_concretization=frame_input.article_concretization,
            series_visual_signature=signature,
            diagram_render=frame_input.diagram_render,
            visible_text_policy=frame_input.visible_text_policy,
            projected_prompt_parts=(),
        )
        candidate_contract_payload = final_contract.to_dict()
        bundle = ArticleConcretizationPromptCompiler().compile_for_z_image(
            final_contract=final_contract
        )
        provider_payload = project_z_image_prompt_bundle(bundle=bundle)
        candidate_prompt = str(provider_payload.get("prompt") or "")
        candidate_negative_prompt = str(provider_payload.get("negative_prompt") or "")
        candidate_subject_presence = _presence_map(candidate_prompt, required_subjects)
        candidate_identity_presence = _presence_map(candidate_prompt, identity_terms)
        provider_passed = bool(candidate_prompt) and candidate_prompt == bundle.positive_prompt
        status = (
            "passed"
            if provider_passed
            and all(candidate_subject_presence.values())
            and all(candidate_identity_presence.values())
            else "failed"
        )
        error = None
        if status != "passed":
            reasons: list[str] = []
            if not provider_passed:
                reasons.append("provider projection changed or removed candidate prompt")
            if not all(candidate_subject_presence.values()):
                reasons.append("candidate prompt lost required subjects")
            if not all(candidate_identity_presence.values()):
                reasons.append("candidate prompt lost identity terms")
            error = "; ".join(reasons)
        return SeriesVisualSignatureShadowFrameResult(
            frame_id=frame_input.frame_id,
            status=status,
            production_prompt=production_prompt,
            candidate_prompt=candidate_prompt,
            candidate_negative_prompt=candidate_negative_prompt,
            required_subjects=required_subjects,
            candidate_source_kind=frame_input.source_kind,
            production_required_subjects_present=production_subject_presence,
            candidate_required_subjects_present=candidate_subject_presence,
            production_identity_terms_present=production_identity_presence,
            candidate_identity_terms_present=candidate_identity_presence,
            candidate_contract=candidate_contract_payload,
            final_gate_passed=True,
            provider_projection_passed=provider_passed,
            candidate_error=error,
        )
    except Exception as exc:
        return SeriesVisualSignatureShadowFrameResult(
            frame_id=frame_input.frame_id,
            status="failed",
            production_prompt=production_prompt,
            candidate_prompt=candidate_prompt,
            candidate_negative_prompt=candidate_negative_prompt,
            required_subjects=required_subjects,
            candidate_source_kind=frame_input.source_kind,
            production_required_subjects_present=production_subject_presence,
            candidate_required_subjects_present=_presence_map(candidate_prompt, required_subjects),
            production_identity_terms_present=production_identity_presence,
            candidate_identity_terms_present=_presence_map(candidate_prompt, identity_terms),
            candidate_contract=candidate_contract_payload,
            final_gate_passed=False,
            provider_projection_passed=False,
            candidate_error=f"{type(exc).__name__}: {exc}",
        )


def _required_subjects_from_frame_context(context: Mapping[str, Any]) -> tuple[str, ...]:
    values: list[Any] = []
    primary = context.get("primary_subject")
    if primary is not None:
        values.append(primary)
    secondary = context.get("secondary_subjects")
    if isinstance(secondary, Sequence) and not isinstance(secondary, (str, bytes)):
        values.extend(secondary)
    explicit = context.get("required_subjects")
    if isinstance(explicit, Sequence) and not isinstance(explicit, (str, bytes)):
        values.extend(explicit)
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = " ".join(str(value or "").strip().split())
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return tuple(result)


def _identity_terms(profile: VisualSignatureProfileSnapshot) -> tuple[str, ...]:
    return (profile.display_name, *tuple(profile.identity_traits[:3]))


def _presence_map(text: str, terms: Sequence[str]) -> dict[str, bool]:
    return prompt_presence_map(text, terms)


def _first_text(*values: Any) -> str:
    for value in values:
        raw = getattr(value, "value", value)
        text = " ".join(str(raw or "").strip().split())
        if text:
            return text
    return ""


__all__ = [
    "SeriesVisualSignatureShadowFrameInput",
    "SeriesVisualSignatureShadowFrameResult",
    "SeriesVisualSignatureShadowReport",
    "build_series_visual_signature_shadow_report",
]
