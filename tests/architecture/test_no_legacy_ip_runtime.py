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
    "pixelle_video/architecture/legacy_signature_field_guard.py",
    "tests/architecture/test_no_legacy_ip_runtime.py",
    "docs/migration/",
)


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
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8-sig"), filename=relative)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if any(token in alias.name for token in FORBIDDEN_TOKENS):
                        violations.append(f"{relative}:{alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                if any(token in node.module for token in FORBIDDEN_TOKENS):
                    violations.append(f"{relative}:{node.module}")
    assert violations == []


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
