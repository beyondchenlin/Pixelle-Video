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


@dataclass(frozen=True)
class SeriesVisualSignatureShadowFrameResult:
    frame_id: str
    status: str
    production_prompt: str
    candidate_prompt: str = ""
    candidate_negative_prompt: str = ""
    required_subjects: tuple[str, ...] = ()
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
) -> SeriesVisualSignatureShadowReport:
    """Run the V4.5 prompt path beside production without changing production output.

    The shadow path is intentionally prompt/contract-only. It does not issue a
    second provider media request, so enabling observation cannot double image
    generation cost. Optional render-result fields are reserved for a later
    explicit A/B experiment.
    """

    normalized_frame_ids = tuple(str(value or "").strip() for value in frame_ids)
    normalized_prompts = tuple(str(value or "") for value in production_prompts)
    expected_count = len(normalized_frame_ids)
    if len(normalized_prompts) != expected_count:
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
                    production_prompt=normalized_prompts[index],
                    candidate_error=error,
                )
                for index, frame_id in enumerate(normalized_frame_ids)
            ),
            global_errors=(error,),
        )

    plans_by_frame = {plan.frame_id: plan for plan in article_concretization_plans}
    results: list[SeriesVisualSignatureShadowFrameResult] = []
    for index, frame_id in enumerate(normalized_frame_ids):
        production_prompt = normalized_prompts[index]
        plan = plans_by_frame.get(frame_id)
        if plan is None:
            results.append(
                SeriesVisualSignatureShadowFrameResult(
                    frame_id=frame_id,
                    status="blocked",
                    production_prompt=production_prompt,
                    production_identity_terms_present=_presence_map(
                        production_prompt,
                        _identity_terms(profile_snapshot),
                    ),
                    candidate_error="V4.5 shadow candidate requires an article concretization plan for the same frame",
                )
            )
            continue
        results.append(
            _build_frame_result(
                production_prompt=production_prompt,
                plan=plan,
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
    # The V4.5 profile snapshot is deliberately identity-only. Legacy profile
    # appearance/forbidden-role fields are prompt-policy material, not identity
    # facts, and copying them here can reintroduce prompt instructions as traits.
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
    plan: ArticleConcretizationPlan,
    request: SeriesVisualSignatureRequest,
    profile: VisualSignatureProfileSnapshot,
) -> SeriesVisualSignatureShadowFrameResult:
    required_subjects = tuple(plan.anchor.required_subjects)
    identity_terms = _identity_terms(profile)
    production_subject_presence = _presence_map(production_prompt, required_subjects)
    production_identity_presence = _presence_map(production_prompt, identity_terms)

    candidate_prompt = ""
    candidate_negative_prompt = ""
    candidate_contract_payload: Mapping[str, Any] | None = None
    try:
        signature = _signature_contract(request=request, profile=profile, plan=plan)
        final_contract = _final_contract(plan=plan, signature=signature)
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
            frame_id=plan.frame_id,
            status=status,
            production_prompt=production_prompt,
            candidate_prompt=candidate_prompt,
            candidate_negative_prompt=candidate_negative_prompt,
            required_subjects=required_subjects,
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
            frame_id=plan.frame_id,
            status="failed",
            production_prompt=production_prompt,
            candidate_prompt=candidate_prompt,
            candidate_negative_prompt=candidate_negative_prompt,
            required_subjects=required_subjects,
            production_required_subjects_present=production_subject_presence,
            candidate_required_subjects_present=_presence_map(candidate_prompt, required_subjects),
            production_identity_terms_present=production_identity_presence,
            candidate_identity_terms_present=_presence_map(candidate_prompt, identity_terms),
            candidate_contract=candidate_contract_payload,
            final_gate_passed=False,
            provider_projection_passed=False,
            candidate_error=f"{type(exc).__name__}: {exc}",
        )


def _signature_contract(
    *,
    request: SeriesVisualSignatureRequest,
    profile: VisualSignatureProfileSnapshot,
    plan: ArticleConcretizationPlan,
) -> SeriesVisualSignatureContract:
    return SeriesVisualSignatureContractBuilder().build(
        request=request,
        profile=profile,
        strict_user_mode=True,
        role_context={
            "effective_anchor_kind": plan.resolution.effective_anchor_kind.value,
            "effective_diagram_grammar": plan.resolution.effective_diagram_grammar.value,
            "primary_visual_task": plan.diagram.primary_visual_task.value,
        },
    )


def _final_contract(
    *,
    plan: ArticleConcretizationPlan,
    signature: SeriesVisualSignatureContract,
) -> FinalVisualPromptContractV45:
    return FinalVisualPromptContractV45(
        contract_id=f"shadow:{plan.plan_id}",
        frame_id=plan.frame_id,
        primary_visual_task=plan.diagram.primary_visual_task.value,
        required_subjects=tuple(plan.anchor.required_subjects),
        article_concretization={
            "plan_id": plan.plan_id,
            "anchor": plan.anchor.to_dict(),
            "diagram": plan.diagram.to_dict(),
        },
        series_visual_signature=signature,
        diagram_render=plan.render.to_dict(),
        visible_text_policy=plan.diagram.visible_text.effective_policy.value,
        projected_prompt_parts=(),
    )


def _identity_terms(profile: VisualSignatureProfileSnapshot) -> tuple[str, ...]:
    return (profile.display_name, *tuple(profile.identity_traits[:3]))


def _presence_map(text: str, terms: Sequence[str]) -> dict[str, bool]:
    haystack = " ".join(str(text or "").split()).casefold()
    return {
        str(term): str(term).casefold() in haystack
        for term in terms
        if str(term or "").strip()
    }


__all__ = [
    "SeriesVisualSignatureShadowFrameResult",
    "SeriesVisualSignatureShadowReport",
    "build_series_visual_signature_shadow_report",
]
