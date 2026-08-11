from __future__ import annotations

from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"{label}: target block not found")
    return text.replace(old, new, 1)


path = Path("pixelle_video/utils/content_generators.py")
text = path.read_text(encoding="utf-8")

text = replace_once(
    text,
    '''    # Base prompt generation is intentionally anchor-free. The recurring visual
    # anchor is placed only after the subject-first base scene exists.
''',
    '''    # Canonical V4.5 identity is already scene-integrated by the LLM from the
    # validated snapshot. Legacy anchor planning remains downstream-only and is
    # gated exclusively by ip_prompt_chain_enabled.
''',
    "ownership comment",
)

text = replace_once(
    text,
    '''    if canonical_enabled:
        if canonical_profile_snapshot is None:
            raise ValueError(
                "canonical visual signature request requires a validated profile snapshot"
            )
        if canonical_profile_snapshot.profile_id != canonical_request.profile_id:
''',
    '''    if canonical_enabled:
        if canonical_profile_snapshot is None:
            raise ValueError(
                "canonical visual signature request requires a validated profile snapshot"
            )
        if not isinstance(canonical_profile_snapshot, VisualSignatureProfileSnapshot):
            raise TypeError(
                "canonical visual signature profile snapshot must use the canonical snapshot type"
            )
        if canonical_profile_snapshot.profile_id != canonical_request.profile_id:
''',
    "canonical snapshot type guard",
)
path.write_text(text, encoding="utf-8")


test_path = Path("tests/architecture/test_visual_signature_runtime_single_owner.py")
tests = test_path.read_text(encoding="utf-8")
if "test_legacy_identity_planners_are_gated_only_by_legacy_projection_flag" in tests:
    raise RuntimeError("review tests already present")

tests += '''


def test_canonical_prompt_routing_rejects_noncanonical_snapshot_type() -> None:
    with pytest.raises(TypeError, match="canonical snapshot type"):
        _resolve_visual_signature_prompt_ownership(
            legacy_request=_request(enabled=False),
            canonical_request=_request(enabled=True),
            canonical_profile_snapshot=object(),  # type: ignore[arg-type]
        )


def _ancestor_if_tests(tree: ast.AST, target: ast.AST) -> list[str]:
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    result: list[str] = []
    current = target
    while current in parents:
        current = parents[current]
        if isinstance(current, ast.If):
            result.append(ast.unparse(current.test))
    return result


def test_legacy_identity_planners_are_gated_only_by_legacy_projection_flag() -> None:
    source = (ROOT / "pixelle_video/utils/content_generators.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    appearance_calls = []
    planning_calls = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr == "plan_batch" and isinstance(node.func.value, ast.Call):
            owner = node.func.value.func
            if isinstance(owner, ast.Name) and owner.id == "IPFrameAppearancePlanner":
                appearance_calls.append(node)
        if node.func.attr == "plan_image_prompts" and isinstance(node.func.value, ast.Call):
            owner = node.func.value.func
            if isinstance(owner, ast.Name) and owner.id == "VisualPromptPlanningService":
                planning_calls.append(node)

    assert len(appearance_calls) == 1
    assert "ip_prompt_chain_enabled" in _ancestor_if_tests(tree, appearance_calls[0])

    assert len(planning_calls) == 1
    keywords = {item.arg: item.value for item in planning_calls[0].keywords if item.arg}
    assert ast.unparse(keywords["visual_anchor_enabled"]) == "ip_prompt_chain_enabled"
    assert ast.unparse(keywords["anchor_profile"]) == (
        "ip_profile if ip_prompt_chain_enabled else None"
    )
    assert ast.unparse(keywords["series_visual_signature_request"]) == (
        "resolved_series_visual_signature_request if ip_prompt_chain_enabled else None"
    )
'''
test_path.write_text(tests, encoding="utf-8")
