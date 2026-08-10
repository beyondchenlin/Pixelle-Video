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
ARTICLE_RESOLUTION = ROOT / "pixelle_video/services/article_concretization_resolution.py"
VISUAL_STORY_PROMPT_MODULE = ROOT / "pixelle_video/prompts/visual_story_engine.py"
VISUAL_STORY_EXECUTION_PROMPT_MODULE = ROOT / "pixelle_video/prompts/visual_story_execution.py"


def test_legacy_ip_prompt_templates_are_physically_removed() -> None:
    existing = [path for path in REMOVED_LEGACY_PROMPT_TEMPLATES if (ROOT / path).exists()]
    assert existing == []


def test_visual_story_prompt_module_exposes_content_route_analysis_only() -> None:
    tree = ast.parse(
        VISUAL_STORY_PROMPT_MODULE.read_text(encoding="utf-8-sig"),
        filename=str(VISUAL_STORY_PROMPT_MODULE),
    )
    functions = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert functions == {"render_article_visual_route_analysis_prompt"}


def test_visual_story_execution_prompt_module_exposes_content_frame_planning_only() -> None:
    tree = ast.parse(
        VISUAL_STORY_EXECUTION_PROMPT_MODULE.read_text(encoding="utf-8-sig"),
        filename=str(VISUAL_STORY_EXECUTION_PROMPT_MODULE),
    )
    functions = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert functions == {"render_frame_visual_plan_batch_prompt"}


def test_article_concretization_cannot_decide_visual_signature_role() -> None:
    tree = ast.parse(
        ARTICLE_RESOLUTION.read_text(encoding="utf-8-sig"),
        filename=str(ARTICLE_RESOLUTION),
    )
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
