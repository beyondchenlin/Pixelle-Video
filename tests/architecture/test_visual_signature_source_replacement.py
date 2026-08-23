from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

REMOVED_LEGACY_PROMPT_TEMPLATES = (
    "pixelle_video/prompts/templates/ip_route_compatibility.md",
    "pixelle_video/prompts/templates/style_harmonization.md",
    "pixelle_video/prompts/templates/frame_ip_fusion.md",
    "pixelle_video/prompts/templates/frame_ip_fusion_batch.md",
)
ARTICLE_MODEL = ROOT / "pixelle_video/models/article_concretization.py"
ARTICLE_RESOLUTION = ROOT / "pixelle_video/services/article_concretization_resolution.py"
VISUAL_STORY_MODEL = ROOT / "pixelle_video/models/visual_story_engine.py"
VISUAL_STORY_SERVICE = ROOT / "pixelle_video/services/visual_story_engine.py"
VISUAL_PROMPT_COMPOSER = ROOT / "pixelle_video/services/visual_prompt_composer.py"
IMAGE_PROMPT_COMPOSER = ROOT / "pixelle_video/services/image_prompt_composer.py"
IMAGE_GENERATION_PROMPT = ROOT / "pixelle_video/prompts/templates/image_generation.md"
VIDEO_GENERATION_PROMPT = ROOT / "pixelle_video/prompts/templates/video_generation.md"
PROJECTION_POLICY = ROOT / "pixelle_video/models/series_visual_signature_projection_policy.py"
VISUAL_STORY_PROMPT_MODULE = ROOT / "pixelle_video/prompts/visual_story_engine.py"
VISUAL_STORY_EXECUTION_PROMPT_MODULE = ROOT / "pixelle_video/prompts/visual_story_execution.py"

LEGACY_CORE_SIGNATURE_ARGUMENTS = {
    "series_visual_signature_enabled",
    "series_visual_signature_expression_mode",
    "series_visual_signature_structure_mode",
    "series_visual_signature_participation_mode",
    "series_visual_signature_mode",
    "series_visual_signature_consistency_mode",
    "series_visual_signature_presentation_mode",
    "series_visual_signature_enforcement",
    "series_visual_signature_fallback_enabled",
    "series_visual_signature_fallback_mode",
    "series_visual_signature_min_visibility",
    "series_visual_signature_profile",
    "scene_casts_by_frame",
}


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))


def _class(tree: ast.Module, name: str) -> ast.ClassDef:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f"missing class {name}")


def _method(class_node: ast.ClassDef, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    for node in class_node.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"missing method {class_node.name}.{name}")


def test_legacy_ip_prompt_templates_are_physically_removed() -> None:
    existing = [path for path in REMOVED_LEGACY_PROMPT_TEMPLATES if (ROOT / path).exists()]
    assert existing == []


def test_visual_story_prompt_module_exposes_content_route_analysis_only() -> None:
    tree = _parse(VISUAL_STORY_PROMPT_MODULE)
    functions = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert functions == {
        "render_article_visual_route_analysis_prompt",
        "render_article_visual_route_score_repair_prompt",
    }


def test_visual_story_execution_prompt_module_exposes_content_frame_planning_only() -> None:
    tree = _parse(VISUAL_STORY_EXECUTION_PROMPT_MODULE)
    functions = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert functions == {
        "render_frame_visual_plan_batch_prompt",
        "render_frame_visual_plan_batch_repair_prompt",
    }


def test_article_concretization_cannot_decide_visual_signature_role() -> None:
    tree = _parse(ARTICLE_RESOLUTION)
    function_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    forbidden_functions = {
        "_resolve_signature_role",
        "_auto_signature_role",
        "resolve_series_visual_signature_role",
    }
    assert function_names.isdisjoint(forbidden_functions)

    assignments = {
        target.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    assert "AUTO_SIGNATURE_ROLE_BY_GRAMMAR" not in assignments
    assert "AUTO_SIGNATURE_ROLE_BY_ANCHOR" not in assignments


def test_article_resolution_only_emits_none_compatibility_role() -> None:
    text = ARTICLE_RESOLUTION.read_text(encoding="utf-8-sig")
    assert "effective_signature_role=SeriesVisualSignatureRole.NONE" in text
    for role in ("OPERATOR", "GUIDE", "SILENT_WITNESS", "CORE_ACTOR"):
        assert f"SeriesVisualSignatureRole.{role}" not in text


def test_article_model_reexports_but_does_not_define_signature_runtime_types() -> None:
    tree = _parse(ARTICLE_MODEL)
    locally_defined = {
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef)
    }
    assert "SeriesVisualSignatureRole" not in locally_defined
    assert "SeriesVisualSignatureContract" not in locally_defined

    text = ARTICLE_MODEL.read_text(encoding="utf-8-sig")
    assert "from pixelle_video.models.series_visual_signature import" in text


def test_visual_route_score_cannot_read_external_final_or_ip_compatibility() -> None:
    tree = _parse(VISUAL_STORY_MODEL)
    score_class = _class(tree, "VisualRouteScores")
    computed_final = _method(score_class, "computed_final")
    self_attributes = {
        node.attr
        for node in ast.walk(computed_final)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
    }
    assert "final" not in self_attributes
    assert "ip_compatibility" not in self_attributes
    assert {
        "content_fit",
        "memorability",
        "channel_consistency",
        "production_reliability",
        "risk",
    }.issubset(self_attributes)


def test_visual_story_service_has_no_second_content_score_formula() -> None:
    tree = _parse(VISUAL_STORY_SERVICE)
    function_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "_content_route_score" not in function_names


def test_canonical_visual_prompt_composer_has_no_legacy_signature_controls() -> None:
    tree = _parse(VISUAL_PROMPT_COMPOSER)
    composer = _class(tree, "VisualPromptComposer")
    compose = _method(composer, "compose")
    argument_names = {
        argument.arg
        for argument in (*compose.args.args, *compose.args.kwonlyargs)
    }
    assert argument_names.isdisjoint(LEGACY_CORE_SIGNATURE_ARGUMENTS)
    assert "series_visual_signature_request" in argument_names
    assert "series_visual_signature_profile_snapshot" in argument_names


def test_base_prompt_boundary_cannot_receive_canonical_identity_facts() -> None:
    composer_text = VISUAL_PROMPT_COMPOSER.read_text(encoding="utf-8-sig")
    assert "_attach_canonical_visual_identity_context" not in composer_text
    for prompt_path in (IMAGE_GENERATION_PROMPT, VIDEO_GENERATION_PROMPT):
        prompt_text = prompt_path.read_text(encoding="utf-8-sig")
        assert "canonical_visual_identity" not in prompt_text
        assert "# Base Prompt Ownership" in prompt_text
        assert "Do not invent or insert a recurring identity" in prompt_text


def test_canonical_composer_persists_capability_specific_signature_observability() -> None:
    tree = _parse(VISUAL_PROMPT_COMPOSER)
    assigned_snapshot_keys: set[str] = set()
    for node in ast.walk(tree):
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets.extend(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets.append(node.target)
        for target in targets:
            if (
                isinstance(target, ast.Subscript)
                and isinstance(target.value, ast.Name)
                and target.value.id == "planning_snapshot"
                and isinstance(target.slice, ast.Constant)
                and isinstance(target.slice.value, str)
            ):
                assigned_snapshot_keys.add(target.slice.value)

    assert "series_visual_signature_request" not in assigned_snapshot_keys
    assert "series_visual_signature_profile_v45" not in assigned_snapshot_keys
    assert "series_visual_signature_request_audit" in assigned_snapshot_keys
    assert "series_visual_signature_profile_ref" in assigned_snapshot_keys
    assert "series_visual_signature_projection_audit" in assigned_snapshot_keys
    assert "visual_anchor_single_pass_prompt_policy" in assigned_snapshot_keys
    assert "visual_anchor_two_stage" not in assigned_snapshot_keys
    assert "visual_anchor_generation_request_by_frame" not in assigned_snapshot_keys
    assert "identity_reference_workflow_inspection" in assigned_snapshot_keys


def test_legacy_image_prompt_composer_is_adapter_not_second_prompt_runtime() -> None:
    tree = _parse(IMAGE_PROMPT_COMPOSER)
    classes = {
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef)
    }
    assert classes == {"ImagePromptComposer"}
    text = IMAGE_PROMPT_COMPOSER.read_text(encoding="utf-8-sig")
    assert "VisualPromptComposer().compose" in text
    assert "generate_styled_image_prompt_batch" not in text
    assert "SeriesVisualSignatureProjectionService" not in text


def test_projection_policy_forbids_raw_observability_and_independent_retention() -> None:
    text = PROJECTION_POLICY.read_text(encoding="utf-8-sig")
    assert 'schema_version: str = "series_visual_signature_projection_audit.v4"' in text
    assert 'payload_class: str = "bounded_hash_count_only"' in text
    assert 'retention_owner: str = "parent_planning_snapshot"' in text
    assert (
        'retention_mode: str = "inherit_parent_planning_snapshot_atomically"'
        in text
    )
    assert "independent_retention_allowed: bool = False" in text
    assert "independent_cleanup_allowed: bool = False" in text
    assert 'raw_prompt_retention: str = "forbidden"' in text
    assert 'raw_subject_retention: str = "forbidden"' in text
    assert 'raw_identity_trait_retention: str = "forbidden"' in text
    assert 'raw_request_hint_retention: str = "forbidden"' in text
