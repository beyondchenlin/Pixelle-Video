from __future__ import annotations

from pathlib import Path


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"{label}: target block not found")
    return text.replace(old, new, 1)


def patch_service() -> None:
    path = Path("pixelle_video/services/series_visual_signature_projection_service.py")
    text = path.read_text(encoding="utf-8")

    text = replace_once(
        text,
        "    SeriesVisualSignatureRequest,\n"
        "    SeriesVisualSignatureRole,\n"
        "    SignatureReplacementPolicy,\n"
        "    VisualSignatureProfileSnapshot,\n",
        "    SeriesVisualSignatureRequest,\n"
        "    VisualSignatureProfileSnapshot,\n",
        label="imports",
    )

    old_loop = '''        frames: list[SeriesVisualSignatureFrameProjection] = []
        for index, frame_id in enumerate(frame_ids):
            base_prompt = str(base_prompts[index] or "")
            try:
                if _ip_already_in_prompt(base_prompt, profile):
                    frame = self._project_pass_through(
                        frame_id=frame_id,
                        base_prompt=base_prompt,
                        base_negative_prompt=base_negative_prompts[index],
                        profile=profile,
                        request=request,
                    )
                else:
                    frame = self.project_frame(
                        frame_id=frame_id,
                        base_prompt=base_prompt,
                        frame_context=frame_contexts[index],
                        request=request,
                        profile=profile,
                        article_plan=plans_by_frame.get(frame_id),
                        base_visual_brief=briefs.get(frame_id),
                        base_negative_prompt=base_negative_prompts[index],
                    )
'''
    new_loop = '''        frames: list[SeriesVisualSignatureFrameProjection] = []
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
'''
    text = replace_once(text, old_loop, new_loop, label="project_batch")

    method_start = text.index("    def _project_pass_through(\n")
    method_end = text.index("\ndef _projection_context(\n", method_start)
    new_method = '''    def _project_pass_through(
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
'''
    text = text[:method_start] + new_method + text[method_end:]

    old_presence = '''def _ip_already_in_prompt(
    prompt: str,
    profile: VisualSignatureProfileSnapshot,
) -> bool:
    if not profile.identity_traits:
        return False
    return all(
        prompt_contains_term(prompt, trait)
        for trait in profile.identity_traits
    )
'''
    new_presence = '''def _ip_already_in_prompt(
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
'''
    text = replace_once(text, old_presence, new_presence, label="identity presence")
    path.write_text(text, encoding="utf-8")


def patch_tests() -> None:
    path = Path("tests/services/test_series_visual_signature_projection_service.py")
    text = path.read_text(encoding="utf-8")

    old_import = '''from pixelle_video.services.series_visual_signature_projection_service import (
    SeriesVisualSignatureProjectionService,
)
'''
    new_import = '''from pixelle_video.services.series_visual_signature_projection_service import (
    SeriesVisualSignatureProjectionError,
    SeriesVisualSignatureProjectionService,
)
'''
    text = replace_once(text, old_import, new_import, label="test import")

    tests = '''


def test_pass_through_does_not_bypass_required_subject_gate() -> None:
    request = _request(series_visual_signature_role="guide")
    profile = SeriesVisualSignatureProfileSnapshotBuilder().build(
        request=request,
        ip_profile=_ip_profile(),
    )
    llm_prompt = (
        "Dalmatian with black spots, black sunglasses, red collar, and small round ears "
        "stands beside a timeline showing a production process"
    )

    with pytest.raises(SeriesVisualSignatureProjectionError) as exc_info:
        SeriesVisualSignatureProjectionService().project_batch(
            base_prompts=[llm_prompt],
            frame_ids=["frame-1"],
            frame_contexts=[{"primary_subject": "worker"}],
            request=request,
            profile=profile,
        )

    assert exc_info.value.reason_code == "final_prompt_gate_failed"


def test_pass_through_reuses_requested_role_and_subject_contract() -> None:
    request = _request(series_visual_signature_role="guide")
    profile = SeriesVisualSignatureProfileSnapshotBuilder().build(
        request=request,
        ip_profile=_ip_profile(),
    )
    llm_prompt = (
        "A worker operates the assembly machine while Dalmatian with black spots, "
        "black sunglasses, red collar, and small round ears points to the process path"
    )

    result = SeriesVisualSignatureProjectionService().project_batch(
        base_prompts=[llm_prompt],
        frame_ids=["frame-1"],
        frame_contexts=[{"primary_subject": "worker"}],
        request=request,
        profile=profile,
    )

    frame = result.frames[0]
    assert frame.required_subjects == ("worker",)
    assert frame.signature.role.value == "guide"
    assert frame.signature.max_area_ratio == pytest.approx(0.20)
    assert "worker" in frame.bundle.locked_constraints
    assert "Dalmatian" in frame.bundle.locked_constraints


def test_identity_presence_requires_display_name_before_pass_through() -> None:
    request = _request(series_visual_signature_role="guide")
    profile = SeriesVisualSignatureProfileSnapshotBuilder().build(
        request=request,
        ip_profile=_ip_profile(),
    )
    prompt_without_name = (
        "A spotted dog with black spots, black sunglasses, red collar, and small round ears "
        "points at a process diagram"
    )

    result = SeriesVisualSignatureProjectionService().project_batch(
        base_prompts=[prompt_without_name],
        frame_ids=["frame-1"],
        frame_contexts=[{}],
        request=request,
        profile=profile,
    )

    frame = result.frames[0]
    assert "Dalmatian" in frame.bundle.positive_prompt
    assert frame.signature.role.value == "guide"
    assert frame.signature.max_area_ratio == pytest.approx(0.20)
'''
    if "def test_pass_through_does_not_bypass_required_subject_gate" in text:
        raise RuntimeError("tests already patched")
    path.write_text(text + tests, encoding="utf-8")


def main() -> None:
    patch_service()
    patch_tests()


if __name__ == "__main__":
    main()
