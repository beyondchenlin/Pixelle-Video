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
        '''from pixelle_video.services.series_visual_signature_profile_builder import (
    SeriesVisualSignatureProfileBuilder,
)
''',
        '''from pixelle_video.services.series_visual_signature_profile_builder import (
    SeriesVisualSignatureProfileBuilder,
)
from pixelle_video.services.series_visual_signature_profile_snapshot_builder import (
    validate_series_visual_signature_profile_snapshot,
)
''',
        "snapshot validator import",
    )

    old_block = '''    if canonical_signature_request.enabled:
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
'''
    new_block = '''    if canonical_signature_request.enabled:
        canonical_profile = validate_series_visual_signature_profile_snapshot(
            canonical_series_visual_signature_profile_snapshot,
            expected_profile_id=canonical_signature_request.profile_id,
        )
        _sv_display_name = canonical_profile.display_name
        _sv_identity_traits = ", ".join(canonical_profile.identity_traits)
        _sv_role_description = _signature_role_description_from_identity(
            canonical_signature_request,
            display_name=canonical_profile.display_name,
            identity_traits=canonical_profile.identity_traits,
        )
'''
    text = replace_once(text, old_block, new_block, "canonical generator snapshot revalidation")
    path.write_text(text, encoding="utf-8")


def patch_composer() -> None:
    path = Path("pixelle_video/services/visual_prompt_composer.py")
    text = path.read_text(encoding="utf-8")

    text = replace_once(
        text,
        '''from pixelle_video.services.series_visual_signature_profile_snapshot_builder import (
    SeriesVisualSignatureProfileSnapshotBuilder,
)
''',
        '''from pixelle_video.services.series_visual_signature_profile_snapshot_builder import (
    SeriesVisualSignatureProfileSnapshotBuilder,
    validate_series_visual_signature_profile_snapshot,
)
''',
        "composer snapshot validator import",
    )

    old_block = '''        profile_snapshot = series_visual_signature_profile_snapshot
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
'''
    new_block = '''        profile_snapshot = series_visual_signature_profile_snapshot
        if signature_enabled:
            if profile_snapshot is None:
                profile_snapshot = SeriesVisualSignatureProfileSnapshotBuilder().build(
                    request=resolved_signature_request,
                    ip_profile=ip_profile,
                )
            profile_snapshot = validate_series_visual_signature_profile_snapshot(
                profile_snapshot,
                expected_profile_id=resolved_signature_request.profile_id,
            )
'''
    text = replace_once(text, old_block, new_block, "composer pre-LLM snapshot revalidation")
    path.write_text(text, encoding="utf-8")


def patch_tests() -> None:
    path = Path("tests/architecture/test_visual_signature_runtime_single_owner.py")
    text = path.read_text(encoding="utf-8")
    if "test_composer_revalidates_snapshot_before_generator_call" in text:
        raise RuntimeError("second-review tests already present")

    text += '''


def _function_node(path: Path, function_name: str) -> ast.AsyncFunctionDef | ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            return node
    raise AssertionError(f"function {function_name} not found")


def _named_calls(function: ast.AST, name: str) -> list[ast.Call]:
    result: list[ast.Call] = []
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id == name:
            result.append(node)
    return result


def test_composer_revalidates_snapshot_before_generator_call() -> None:
    function = _function_node(
        ROOT / "pixelle_video/services/visual_prompt_composer.py",
        "compose",
    )
    validators = _named_calls(function, "validate_series_visual_signature_profile_snapshot")
    generators = _named_calls(function, "generate_styled_image_prompt_batch")

    assert len(validators) == 1
    assert len(generators) == 1
    assert validators[0].lineno < generators[0].lineno
    keywords = {item.arg: item.value for item in validators[0].keywords if item.arg}
    assert ast.unparse(keywords["expected_profile_id"]) == (
        "resolved_signature_request.profile_id"
    )


def test_generic_generator_revalidates_canonical_snapshot_before_identity_use() -> None:
    function = _function_node(
        ROOT / "pixelle_video/utils/content_generators.py",
        "generate_styled_image_prompt_batch",
    )
    validators = _named_calls(function, "validate_series_visual_signature_profile_snapshot")

    assert len(validators) == 1
    keywords = {item.arg: item.value for item in validators[0].keywords if item.arg}
    assert ast.unparse(validators[0].args[0]) == (
        "canonical_series_visual_signature_profile_snapshot"
    )
    assert ast.unparse(keywords["expected_profile_id"]) == (
        "canonical_signature_request.profile_id"
    )
'''
    path.write_text(text, encoding="utf-8")


def main() -> None:
    patch_content_generators()
    patch_composer()
    patch_tests()


if __name__ == "__main__":
    main()
