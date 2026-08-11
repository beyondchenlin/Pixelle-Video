from __future__ import annotations

from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"{label}: target block not found")
    return text.replace(old, new, 1)


service_path = Path("pixelle_video/services/series_visual_signature_projection_service.py")
text = service_path.read_text(encoding="utf-8")

text = replace_once(
    text,
    "from pixelle_video.services.series_visual_signature_prompt_presence import (\n"
    "    prompt_contains_term,\n"
    ")\n"
    "from pixelle_video.services.visible_text_prompt_rewriter import (\n"
    "    NO_VISIBLE_TEXT_NEGATIVE_PROMPT,\n"
    ")\n",
    "from pixelle_video.services.series_visual_signature_prompt_presence import (\n"
    "    prompt_contains_term,\n"
    ")\n",
    "remove duplicate negative-protection import",
)

text = replace_once(
    text,
    "                if _ip_already_in_prompt(base_prompt, profile):\n",
    "                if _prompt_satisfies_pass_through_contract(\n"
    "                    base_prompt, profile, required_subjects\n"
    "                ):\n",
    "full pass-through predicate",
)

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
        The canonical compiler still owns negative protections, locked constraints,
        budget validation, and provider-neutral contract semantics; only its
        generated positive text is replaced by the already-valid LLM prompt.
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

        compiled_bundle = FinalVisualPromptCompiler().compile(
            final_contract=contract,
            base_negative_prompt=base_negative_prompt,
        )
        assert_series_visual_signature_final_prompt(
            positive_prompt=base_prompt,
            negative_prompt=compiled_bundle.negative_prompt,
            required_subjects=required_subjects,
            signature=signature,
            visible_text_policy=visible_text_policy,
        )
        metadata = compiled_bundle.to_dict()["metadata"]
        metadata["pass_through_preserved_positive_prompt"] = True
        bundle = FinalVisualPromptBundle(
            positive_prompt=base_prompt,
            negative_prompt=compiled_bundle.negative_prompt,
            locked_constraints=compiled_bundle.locked_constraints,
            metadata=metadata,
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

presence_start = text.index("def _ip_already_in_prompt(\n")
presence_end = text.index("\ndef _first_text(\n", presence_start)
new_presence = '''def _prompt_satisfies_pass_through_contract(
    prompt: str,
    profile: VisualSignatureProfileSnapshot,
    required_subjects: Sequence[str],
) -> bool:
    if not _identity_already_in_prompt(prompt, profile):
        return False
    return all(
        prompt_contains_term(prompt, subject)
        for subject in required_subjects
        if _text(subject)
    )


def _identity_already_in_prompt(
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
text = text[:presence_start] + new_presence + text[presence_end:]
service_path.write_text(text, encoding="utf-8")


test_path = Path("tests/services/test_series_visual_signature_projection_service.py")
tests = test_path.read_text(encoding="utf-8")
tests = replace_once(
    tests,
    "from pixelle_video.services.series_visual_signature_projection_service import (\n"
    "    SeriesVisualSignatureProjectionError,\n"
    "    SeriesVisualSignatureProjectionService,\n"
    ")\n",
    "from pixelle_video.services.series_visual_signature_projection_service import (\n"
    "    SeriesVisualSignatureProjectionService,\n"
    ")\n",
    "remove obsolete projection error test import",
)

old_test_start = tests.index("def test_pass_through_does_not_bypass_required_subject_gate() -> None:\n")
old_test_end = tests.index("\ndef test_pass_through_reuses_requested_role_and_subject_contract() -> None:\n", old_test_start)
new_test = '''def test_missing_required_subject_uses_compiled_repair_instead_of_pass_through() -> None:
    request = _request(series_visual_signature_role="guide")
    profile = SeriesVisualSignatureProfileSnapshotBuilder().build(
        request=request,
        ip_profile=_ip_profile(),
    )
    llm_prompt = (
        "Dalmatian with black spots, black sunglasses, red collar, and small round ears "
        "stands beside a timeline showing a production process"
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
    assert "worker" in frame.bundle.positive_prompt
    assert frame.bundle.positive_prompt != llm_prompt
    assert (
        frame.bundle.to_dict()["metadata"].get("pass_through_preserved_positive_prompt")
        is None
    )

'''
tests = tests[:old_test_start] + new_test + tests[old_test_end + 1:]

needle = '''    assert frame.signature.max_area_ratio == pytest.approx(0.20)
    assert "worker" in frame.bundle.locked_constraints
    assert "Dalmatian" in frame.bundle.locked_constraints
'''
replacement = '''    assert frame.signature.max_area_ratio == pytest.approx(0.20)
    assert frame.bundle.positive_prompt == llm_prompt
    assert frame.bundle.to_dict()["metadata"]["pass_through_preserved_positive_prompt"] is True
    assert any("required source subject" in item for item in frame.bundle.locked_constraints)
    assert any("recurring visual identity" in item for item in frame.bundle.locked_constraints)
'''
tests = replace_once(tests, needle, replacement, "pass-through contract assertions")

test_path.write_text(tests, encoding="utf-8")
