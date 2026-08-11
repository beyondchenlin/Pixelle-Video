from __future__ import annotations

from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"{label}: target block not found")
    return text.replace(old, new, 1)


def patch_content_generators() -> None:
    path = Path("pixelle_video/utils/content_generators.py")
    text = path.read_text(encoding="utf-8")

    text = replace_once(
        text,
        "from pixelle_video.models.series_visual_signature import SERIES_VISUAL_SIGNATURE_NATURAL_ROLE_MAP\n",
        "from pixelle_video.models.series_visual_signature import (\n"
        "    SERIES_VISUAL_SIGNATURE_NATURAL_ROLE_MAP,\n"
        "    VisualSignatureProfileSnapshot,\n"
        ")\n",
        "canonical snapshot import",
    )

    old_signature_tail = '''    series_visual_signature_fallback_mode: str | None = None,
    series_visual_signature_min_visibility: str | None = None,
) -> StyledImagePromptBatch:
'''
    new_signature_tail = '''    series_visual_signature_fallback_mode: str | None = None,
    series_visual_signature_min_visibility: str | None = None,
    canonical_series_visual_signature_request: SeriesVisualSignatureRequest | None = None,
    canonical_series_visual_signature_profile_snapshot: VisualSignatureProfileSnapshot | None = None,
) -> StyledImagePromptBatch:
'''
    text = replace_once(text, old_signature_tail, new_signature_tail, "generator canonical parameters")

    old_resolution = '''    ip_prompt_chain_enabled = resolved_series_visual_signature_request.enabled
    resolved_series_visual_signature_profile = series_visual_signature_profile
    _sv_display_name = ""
    _sv_identity_traits = ""
    _sv_role_description = ""
    if ip_prompt_chain_enabled:
        if storyboard_plan is None:
            raise ValueError("storyboard_plan is required when series_visual_signature_enabled=True")
        ensure_ip_profile_ready_for_generation(ip_profile)
        if resolved_series_visual_signature_profile is None:
            resolved_series_visual_signature_profile = SeriesVisualSignatureProfileBuilder().build(ip_profile)
        if resolved_series_visual_signature_profile is not None:
            _sv_display_name = resolved_series_visual_signature_profile.display_name
            _sv_identity_traits = ", ".join(
                _derive_identity_traits_for_llm_prompt(
                    ip_profile,
                    resolved_series_visual_signature_profile,
                )
            )
            _sv_role_description = _signature_role_description(
                resolved_series_visual_signature_request,
                resolved_series_visual_signature_profile,
            )
'''
    new_resolution = '''    canonical_signature_request = (
        canonical_series_visual_signature_request
        if canonical_series_visual_signature_request is not None
        else SeriesVisualSignatureRequest.disabled()
    )
    llm_visual_signature_enabled, ip_prompt_chain_enabled = (
        _resolve_visual_signature_prompt_ownership(
            legacy_request=resolved_series_visual_signature_request,
            canonical_request=canonical_signature_request,
            canonical_profile_snapshot=canonical_series_visual_signature_profile_snapshot,
        )
    )
    resolved_series_visual_signature_profile = series_visual_signature_profile
    _sv_display_name = ""
    _sv_identity_traits = ""
    _sv_role_description = ""
    if canonical_signature_request.enabled:
        canonical_profile = canonical_series_visual_signature_profile_snapshot
        if canonical_profile is None:
            raise RuntimeError("canonical visual signature routing lost its validated profile snapshot")
        _sv_display_name = canonical_profile.display_name
        _sv_identity_traits = ", ".join(canonical_profile.identity_traits)
        _sv_role_description = _signature_role_description_from_identity(
            canonical_signature_request,
            display_name=canonical_profile.display_name,
            identity_traits=canonical_profile.identity_traits,
        )
    elif ip_prompt_chain_enabled:
        if storyboard_plan is None:
            raise ValueError("storyboard_plan is required when series_visual_signature_enabled=True")
        ensure_ip_profile_ready_for_generation(ip_profile)
        if resolved_series_visual_signature_profile is None:
            resolved_series_visual_signature_profile = SeriesVisualSignatureProfileBuilder().build(ip_profile)
        if resolved_series_visual_signature_profile is not None:
            _sv_display_name = resolved_series_visual_signature_profile.display_name
            _sv_identity_traits = ", ".join(
                _derive_identity_traits_for_llm_prompt(
                    ip_profile,
                    resolved_series_visual_signature_profile,
                )
            )
            _sv_role_description = _signature_role_description(
                resolved_series_visual_signature_request,
                resolved_series_visual_signature_profile,
            )
'''
    text = replace_once(text, old_resolution, new_resolution, "visual signature ownership resolution")

    text = text.replace(
        "            series_visual_signature_enabled=ip_prompt_chain_enabled,\n"
        "            series_visual_signature_display_name=_sv_display_name,\n",
        "            series_visual_signature_enabled=llm_visual_signature_enabled,\n"
        "            series_visual_signature_display_name=_sv_display_name,\n",
        2,
    )

    old_role_helper = '''def _signature_role_description(
    request: SeriesVisualSignatureRequest,
    profile: SeriesVisualSignatureProfile,
) -> str:
    role_text = str(request.role.value if request.role is not None else "auto")
    display_name = profile.display_name or ""
    traits = ", ".join(
        profile.identity_contract.required_identity_traits or profile.identity_kernel
    )
    default_desc = "a scene-bound participant"
    parts = [display_name] if display_name else []
    parts.append("appears in the scene")
    parts.append(f"recognizable by: {traits}" if traits else "")
    role_desc = SERIES_VISUAL_SIGNATURE_NATURAL_ROLE_MAP.get(role_text, default_desc)
    parts.append(f"acting as: {role_desc}")
    return "; ".join(p for p in parts if p)
'''
    new_role_helper = '''def _resolve_visual_signature_prompt_ownership(
    *,
    legacy_request: SeriesVisualSignatureRequest,
    canonical_request: SeriesVisualSignatureRequest,
    canonical_profile_snapshot: VisualSignatureProfileSnapshot | None,
) -> tuple[bool, bool]:
    if not isinstance(legacy_request, SeriesVisualSignatureRequest):
        raise TypeError("legacy visual signature request must use the canonical request type")
    if not isinstance(canonical_request, SeriesVisualSignatureRequest):
        raise TypeError("canonical visual signature request must use the canonical request type")

    legacy_enabled = legacy_request.enabled
    canonical_enabled = canonical_request.enabled
    if legacy_enabled and canonical_enabled:
        raise ValueError(
            "canonical visual signature context and legacy visual signature inputs are mutually exclusive"
        )
    if canonical_enabled:
        if canonical_profile_snapshot is None:
            raise ValueError(
                "canonical visual signature request requires a validated profile snapshot"
            )
        if canonical_profile_snapshot.profile_id != canonical_request.profile_id:
            raise ValueError(
                "canonical visual signature profile snapshot must match request profile_id"
            )
    elif canonical_profile_snapshot is not None:
        raise ValueError(
            "canonical visual signature profile snapshot requires an enabled canonical request"
        )

    return canonical_enabled or legacy_enabled, legacy_enabled


def _signature_role_description(
    request: SeriesVisualSignatureRequest,
    profile: SeriesVisualSignatureProfile,
) -> str:
    return _signature_role_description_from_identity(
        request,
        display_name=profile.display_name,
        identity_traits=(
            profile.identity_contract.required_identity_traits
            or profile.identity_kernel
        ),
    )


def _signature_role_description_from_identity(
    request: SeriesVisualSignatureRequest,
    *,
    display_name: str,
    identity_traits: Sequence[str],
) -> str:
    role_text = str(request.role.value if request.role is not None else "auto")
    traits = ", ".join(str(item).strip() for item in identity_traits if str(item).strip())
    default_desc = "a scene-bound participant"
    parts = [display_name] if display_name else []
    parts.append("appears in the scene")
    parts.append(f"recognizable by: {traits}" if traits else "")
    role_desc = SERIES_VISUAL_SIGNATURE_NATURAL_ROLE_MAP.get(role_text, default_desc)
    parts.append(f"acting as: {role_desc}")
    return "; ".join(p for p in parts if p)
'''
    text = replace_once(text, old_role_helper, new_role_helper, "role and ownership helpers")

    path.write_text(text, encoding="utf-8")


def patch_composer() -> None:
    path = Path("pixelle_video/services/visual_prompt_composer.py")
    text = path.read_text(encoding="utf-8")

    attach_block = '''        prompt_contexts = attach_visual_story_context(
            prompt_contexts,
            visual_story_context,
        )

        # Base generation owns scene/style/camera/reference-image/text planning.
'''
    snapshot_block = '''        prompt_contexts = attach_visual_story_context(
            prompt_contexts,
            visual_story_context,
        )

        profile_snapshot = series_visual_signature_profile_snapshot
        if signature_enabled:
            if profile_snapshot is None:
                profile_snapshot = SeriesVisualSignatureProfileSnapshotBuilder().build(
                    request=resolved_signature_request,
                    ip_profile=ip_profile,
                )
            elif profile_snapshot.profile_id != resolved_signature_request.profile_id:
                raise ValueError(
                    "series_visual_signature_profile_snapshot must match canonical request profile_id"
                )

        # Base generation owns scene/style/camera/reference-image/text planning.
'''
    text = replace_once(text, attach_block, snapshot_block, "pre-LLM canonical snapshot")

    old_call_tail = '''            native_prompt_hints_by_frame=native_prompt_hints_by_frame,
            series_visual_signature_enabled=signature_enabled,
            ip_profile=ip_profile if signature_enabled else None,
            series_visual_signature_request=resolved_signature_request if signature_enabled else None,
            scene_casts_by_frame=None,
            stage_callback=stage_callback,
'''
    new_call_tail = '''            native_prompt_hints_by_frame=native_prompt_hints_by_frame,
            series_visual_signature_enabled=False,
            ip_profile=None,
            series_visual_signature_expression_mode=None,
            series_visual_signature_structure_mode=None,
            series_visual_signature_participation_mode=None,
            series_visual_signature_request=None,
            series_visual_signature_profile=None,
            series_visual_signature_mode=None,
            series_visual_signature_consistency_mode=None,
            series_visual_signature_presentation_mode=None,
            series_visual_signature_enforcement=None,
            series_visual_signature_fallback_enabled=None,
            series_visual_signature_fallback_mode=None,
            series_visual_signature_min_visibility=None,
            scene_casts_by_frame=None,
            canonical_series_visual_signature_request=(
                resolved_signature_request if signature_enabled else None
            ),
            canonical_series_visual_signature_profile_snapshot=(
                profile_snapshot if signature_enabled else None
            ),
            stage_callback=stage_callback,
'''
    text = replace_once(text, old_call_tail, new_call_tail, "hard-disable legacy generator inputs")

    old_post_snapshot = '''        planning_snapshot = dict(batch.planning_snapshot or {})
        if signature_enabled:
            profile_snapshot = series_visual_signature_profile_snapshot
            if profile_snapshot is None:
                profile_snapshot = SeriesVisualSignatureProfileSnapshotBuilder().build(
                    request=resolved_signature_request,
                    ip_profile=ip_profile,
                )
            elif profile_snapshot.profile_id != resolved_signature_request.profile_id:
                raise ValueError(
                    "series_visual_signature_profile_snapshot must match canonical request profile_id"
                )
            briefs = dict(
'''
    new_post_snapshot = '''        planning_snapshot = dict(batch.planning_snapshot or {})
        if signature_enabled:
            if profile_snapshot is None:
                raise RuntimeError("enabled visual signature lost its canonical profile snapshot")
            briefs = dict(
'''
    text = replace_once(text, old_post_snapshot, new_post_snapshot, "reuse pre-LLM snapshot")

    path.write_text(text, encoding="utf-8")


def add_tests() -> None:
    path = Path("tests/architecture/test_visual_signature_runtime_single_owner.py")
    path.write_text(
        '''from __future__ import annotations

import ast
from pathlib import Path

import pytest

from pixelle_video.models.series_visual_signature import (
    SeriesVisualSignatureRequest,
    VisualSignatureProfileSnapshot,
)
from pixelle_video.utils.content_generators import (
    _resolve_visual_signature_prompt_ownership,
)


ROOT = Path(__file__).resolve().parents[2]


def _composer_generator_call() -> ast.Call:
    source = (ROOT / "pixelle_video/services/visual_prompt_composer.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "generate_styled_image_prompt_batch":
            return node
    raise AssertionError("generate_styled_image_prompt_batch call not found")


def _request(*, enabled: bool) -> SeriesVisualSignatureRequest:
    if not enabled:
        return SeriesVisualSignatureRequest.disabled()
    return SeriesVisualSignatureRequest.from_mapping(
        {
            "series_visual_signature_enabled": True,
            "series_visual_signature_profile_id": "dog_1",
            "series_visual_signature_role": "guide",
        }
    )


def _snapshot() -> VisualSignatureProfileSnapshot:
    return VisualSignatureProfileSnapshot(
        profile_id="dog_1",
        display_name="Dalmatian",
        identity_traits=("black spots", "red collar"),
    )


def test_canonical_prompt_routing_enables_llm_identity_without_legacy_projection() -> None:
    llm_enabled, legacy_enabled = _resolve_visual_signature_prompt_ownership(
        legacy_request=_request(enabled=False),
        canonical_request=_request(enabled=True),
        canonical_profile_snapshot=_snapshot(),
    )

    assert llm_enabled is True
    assert legacy_enabled is False


def test_legacy_prompt_routing_remains_compatible() -> None:
    llm_enabled, legacy_enabled = _resolve_visual_signature_prompt_ownership(
        legacy_request=_request(enabled=True),
        canonical_request=_request(enabled=False),
        canonical_profile_snapshot=None,
    )

    assert llm_enabled is True
    assert legacy_enabled is True


def test_prompt_routing_rejects_dual_ownership() -> None:
    with pytest.raises(ValueError, match="mutually exclusive"):
        _resolve_visual_signature_prompt_ownership(
            legacy_request=_request(enabled=True),
            canonical_request=_request(enabled=True),
            canonical_profile_snapshot=_snapshot(),
        )


def test_canonical_prompt_routing_requires_matching_validated_snapshot() -> None:
    wrong_snapshot = VisualSignatureProfileSnapshot(
        profile_id="other",
        display_name="Dalmatian",
        identity_traits=("black spots",),
    )
    with pytest.raises(ValueError, match="match request profile_id"):
        _resolve_visual_signature_prompt_ownership(
            legacy_request=_request(enabled=False),
            canonical_request=_request(enabled=True),
            canonical_profile_snapshot=wrong_snapshot,
        )


def test_composer_uses_canonical_context_while_hard_disabling_legacy_inputs() -> None:
    call = _composer_generator_call()
    keywords = {item.arg: item.value for item in call.keywords if item.arg}

    expected_legacy_constants = {
        "series_visual_signature_enabled": False,
        "ip_profile": None,
        "series_visual_signature_expression_mode": None,
        "series_visual_signature_structure_mode": None,
        "series_visual_signature_participation_mode": None,
        "series_visual_signature_request": None,
        "series_visual_signature_profile": None,
        "series_visual_signature_mode": None,
        "series_visual_signature_consistency_mode": None,
        "series_visual_signature_presentation_mode": None,
        "series_visual_signature_enforcement": None,
        "series_visual_signature_fallback_enabled": None,
        "series_visual_signature_fallback_mode": None,
        "series_visual_signature_min_visibility": None,
        "scene_casts_by_frame": None,
    }
    for name, expected in expected_legacy_constants.items():
        assert name in keywords
        assert isinstance(keywords[name], ast.Constant)
        assert keywords[name].value is expected

    assert ast.unparse(keywords["canonical_series_visual_signature_request"]) == (
        "resolved_signature_request if signature_enabled else None"
    )
    assert ast.unparse(
        keywords["canonical_series_visual_signature_profile_snapshot"]
    ) == "profile_snapshot if signature_enabled else None"
''',
        encoding="utf-8",
    )


def main() -> None:
    patch_content_generators()
    patch_composer()
    add_tests()


if __name__ == "__main__":
    main()
