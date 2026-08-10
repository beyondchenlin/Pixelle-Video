from __future__ import annotations

import ast
from pathlib import Path

from pixelle_video.architecture.legacy_signature_field_guard import (
    DEPRECATED_RUNTIME_FIELD_NAMES,
    DEPRECATED_RUNTIME_MODULE_TOKENS,
    DEPRECATED_RUNTIME_SYMBOL_NAMES,
)

ROOT = Path(__file__).resolve().parents[2]

FORBIDDEN_RUNTIME_FILES = (
    "pixelle_video/models/visual_role_request.py",
    "pixelle_video/models/visual_role_strategy.py",
    "pixelle_video/services/visual_anchor_integration_planner.py",
    "pixelle_video/services/visual_role_prompt_projector.py",
    "pixelle_video/services/visual_role_scene_planner.py",
    "pixelle_video/services/visual_role_prompt_critic.py",
    "pixelle_video/services/visual_role_repair_loop.py",
    "pixelle_video/services/series_visual_signature_shadow_comparison.py",
    "web/components/ip_prompt_chain_controls.py",
    "web/components/content_ip_world_controls.py",
    "web/components/style_config_ip_controls.py",
)

FORBIDDEN_TOKENS = (
    *sorted(DEPRECATED_RUNTIME_FIELD_NAMES),
    *sorted(DEPRECATED_RUNTIME_MODULE_TOKENS),
    *sorted(DEPRECATED_RUNTIME_SYMBOL_NAMES),
)

SCAN_ROOTS = ("api", "pixelle_video", "web")
SCAN_SUFFIXES = (".py", ".json", ".yaml", ".yml", ".toml")
ALLOWLIST_PARTS = (
    "pixelle_video/architecture/asset_bible_persistence_compat.py",
    "pixelle_video/architecture/legacy_signature_field_guard.py",
    "tests/architecture/test_no_legacy_ip_runtime.py",
    "docs/migration/",
)
CANONICAL_SIGNATURE_REQUEST_MODULE = "pixelle_video/models/series_visual_signature.py"
SIGNATURE_REQUEST_ADAPTER_MODULE = "pixelle_video/models/series_visual_signature_request.py"
CANONICAL_FINAL_COMPILER_MODULE = "pixelle_video/services/final_visual_prompt_compiler.py"
COMPAT_FINAL_COMPILER_MODULE = "pixelle_video/services/article_concretization_prompt_compiler.py"
CANONICAL_VISUAL_PROMPT_COMPOSER_MODULE = "pixelle_video/services/visual_prompt_composer.py"
COMPAT_IMAGE_PROMPT_COMPOSER_MODULE = "pixelle_video/services/image_prompt_composer.py"
PIPELINE_VERSION_FACT_NAMES = frozenset(
    {
        "SERIES_VISUAL_SIGNATURE_LEGACY_PIPELINE_VERSION",
        "SERIES_VISUAL_SIGNATURE_PIPELINE_VERSION",
        "SUPPORTED_SERIES_VISUAL_SIGNATURE_PIPELINE_VERSIONS",
    }
)
PIPELINE_VERSION_FUNCTION_NAME = "is_supported_series_visual_signature_pipeline_version"
LEGACY_BASE_GENERATOR_DISABLED_KEYWORDS = {
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


def test_legacy_runtime_files_are_physically_removed() -> None:
    existing = [path for path in FORBIDDEN_RUNTIME_FILES if (ROOT / path).exists()]
    assert existing == []


def test_runtime_files_do_not_contain_deprecated_signature_tokens() -> None:
    violations: list[str] = []
    for relative in _runtime_files():
        if _is_allowlisted(relative):
            continue
        text = (ROOT / relative).read_text(encoding="utf-8", errors="ignore")
        for token in FORBIDDEN_TOKENS:
            if token in text:
                violations.append(f"{relative}:{token}")
    assert violations == []


def test_runtime_python_does_not_import_deprecated_modules() -> None:
    violations: list[str] = []
    for relative in _runtime_files():
        if not relative.endswith(".py") or _is_allowlisted(relative):
            continue
        tree = ast.parse(
            (ROOT / relative).read_text(encoding="utf-8-sig"),
            filename=relative,
        )
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if any(token in alias.name for token in FORBIDDEN_TOKENS):
                        violations.append(f"{relative}:{alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                if any(token in node.module for token in FORBIDDEN_TOKENS):
                    violations.append(f"{relative}:{node.module}")
    assert violations == []


def test_series_visual_signature_request_has_one_runtime_class_definition() -> None:
    definitions: list[str] = []
    for relative in _runtime_files():
        if not relative.endswith(".py"):
            continue
        tree = ast.parse(
            (ROOT / relative).read_text(encoding="utf-8-sig"),
            filename=relative,
        )
        if any(
            isinstance(node, ast.ClassDef)
            and node.name == "SeriesVisualSignatureRequest"
            for node in ast.walk(tree)
        ):
            definitions.append(relative)

    assert definitions == [CANONICAL_SIGNATURE_REQUEST_MODULE]


def test_pipeline_version_facts_have_one_runtime_definition() -> None:
    assignments_by_name: dict[str, list[str]] = {
        name: [] for name in PIPELINE_VERSION_FACT_NAMES
    }
    function_definitions: list[str] = []
    for relative in _runtime_files():
        if not relative.endswith(".py"):
            continue
        tree = ast.parse(
            (ROOT / relative).read_text(encoding="utf-8-sig"),
            filename=relative,
        )
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    for name in _assigned_names(target):
                        if name in assignments_by_name:
                            assignments_by_name[name].append(relative)
            elif isinstance(node, ast.AnnAssign):
                for name in _assigned_names(node.target):
                    if name in assignments_by_name:
                        assignments_by_name[name].append(relative)
            elif (
                isinstance(node, ast.FunctionDef)
                and node.name == PIPELINE_VERSION_FUNCTION_NAME
            ):
                function_definitions.append(relative)

    assert assignments_by_name == {
        name: [CANONICAL_SIGNATURE_REQUEST_MODULE]
        for name in PIPELINE_VERSION_FACT_NAMES
    }
    assert function_definitions == [CANONICAL_SIGNATURE_REQUEST_MODULE]


def test_legacy_request_module_is_adapter_not_second_runtime_model() -> None:
    adapter_path = ROOT / SIGNATURE_REQUEST_ADAPTER_MODULE
    tree = ast.parse(
        adapter_path.read_text(encoding="utf-8-sig"),
        filename=str(adapter_path),
    )
    assert not any(
        isinstance(node, ast.ClassDef)
        and node.name == "SeriesVisualSignatureRequest"
        for node in ast.walk(tree)
    )
    assert any(
        isinstance(node, ast.ImportFrom)
        and node.module == "pixelle_video.models.series_visual_signature"
        and any(alias.name == "SeriesVisualSignatureRequest" for alias in node.names)
        for node in ast.walk(tree)
    )
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module == "pixelle_video.models.series_visual_signature"
        for alias in node.names
    }
    assert PIPELINE_VERSION_FACT_NAMES.issubset(imported_names)
    assert PIPELINE_VERSION_FUNCTION_NAME in imported_names


def test_final_visual_prompt_compiler_has_one_semantic_implementation() -> None:
    definitions: list[str] = []
    for relative in _runtime_files():
        if not relative.endswith(".py"):
            continue
        tree = ast.parse(
            (ROOT / relative).read_text(encoding="utf-8-sig"),
            filename=relative,
        )
        if any(
            isinstance(node, ast.ClassDef)
            and node.name == "FinalVisualPromptCompiler"
            for node in ast.walk(tree)
        ):
            definitions.append(relative)
    assert definitions == [CANONICAL_FINAL_COMPILER_MODULE]

    compat_path = ROOT / COMPAT_FINAL_COMPILER_MODULE
    compat_tree = ast.parse(
        compat_path.read_text(encoding="utf-8-sig"),
        filename=str(compat_path),
    )
    compat_classes = [
        node
        for node in compat_tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "ArticleConcretizationPromptCompiler"
    ]
    assert len(compat_classes) == 1
    assert not any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        for node in compat_classes[0].body
    )


def test_visual_prompt_composer_has_one_semantic_implementation() -> None:
    canonical_path = ROOT / CANONICAL_VISUAL_PROMPT_COMPOSER_MODULE
    canonical_tree = ast.parse(
        canonical_path.read_text(encoding="utf-8-sig"),
        filename=str(canonical_path),
    )
    assert any(
        isinstance(node, ast.ClassDef) and node.name == "VisualPromptComposer"
        for node in canonical_tree.body
    )

    compat_path = ROOT / COMPAT_IMAGE_PROMPT_COMPOSER_MODULE
    compat_tree = ast.parse(
        compat_path.read_text(encoding="utf-8-sig"),
        filename=str(compat_path),
    )
    assert not any(
        isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        for node in compat_tree.body
    )
    assert any(
        isinstance(node, ast.ImportFrom)
        and node.module == "pixelle_video.services.visual_prompt_composer"
        and any(alias.name == "VisualPromptComposer" for alias in node.names)
        for node in compat_tree.body
    )


def test_visual_prompt_composer_hard_disables_legacy_signature_generator_inputs() -> None:
    path = ROOT / CANONICAL_VISUAL_PROMPT_COMPOSER_MODULE
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and _call_name(node.func) == "generate_styled_image_prompt_batch"
    ]
    assert len(calls) == 1
    keyword_values = {
        keyword.arg: keyword.value
        for keyword in calls[0].keywords
        if keyword.arg
    }
    for keyword, expected in LEGACY_BASE_GENERATOR_DISABLED_KEYWORDS.items():
        assert keyword in keyword_values, f"missing hard-disabled legacy keyword: {keyword}"
        value = keyword_values[keyword]
        assert isinstance(value, ast.Constant), f"{keyword} must be a literal constant"
        assert value.value is expected, f"{keyword} must stay hard-disabled"


def _call_name(value: ast.expr) -> str:
    if isinstance(value, ast.Name):
        return value.id
    if isinstance(value, ast.Attribute):
        return value.attr
    return ""


def _assigned_names(target: ast.expr) -> tuple[str, ...]:
    if isinstance(target, ast.Name):
        return (target.id,)
    if isinstance(target, (ast.Tuple, ast.List)):
        result: list[str] = []
        for item in target.elts:
            result.extend(_assigned_names(item))
        return tuple(result)
    return ()


def _runtime_files() -> list[str]:
    files: list[str] = []
    for root in SCAN_ROOTS:
        base = ROOT / root
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file() and path.suffix in SCAN_SUFFIXES:
                files.append(path.relative_to(ROOT).as_posix())
    return files


def _is_allowlisted(relative: str) -> bool:
    return any(part in relative for part in ALLOWLIST_PARTS)
