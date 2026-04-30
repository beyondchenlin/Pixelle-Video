from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ACTIVE_PLAN_FILES = (
    ROOT / "docs/superpowers/plans/2026-04-30-stage1a-text-image-prompt-trace-implementation.md",
    ROOT / "docs/superpowers/plans/2026-04-29-storyboard-workbench-stage1-implementation.md",
    ROOT / "docs/superpowers/plans/2026-04-30-stage2-assetbible-ip-scenecast-implementation.md",
)

WORKTREE_POLICY_PLAN_FILES = (
    ROOT / "docs/superpowers/plans/2026-04-30-platform-foundation-zero-technical-debt-implementation.md",
    *ACTIVE_PLAN_FILES,
)

FORBIDDEN_PATTERNS = (
    "LocalJson",
    "LocalLLMTraceStore",
    "LocalAssetBibleService",
    "_runtime/trace",
)

FORBIDDEN_WORKTREE_POLICY_PATTERNS = (
    "AGENTS.md forbids git worktree",
    "AGENTS.md forbids `git worktree`",
)


def test_active_stage_plans_do_not_reintroduce_local_runtime_contracts() -> None:
    violations: list[str] = []

    for plan_file in ACTIVE_PLAN_FILES:
        content = plan_file.read_text(encoding="utf-8")
        for pattern in FORBIDDEN_PATTERNS:
            if pattern in content:
                violations.append(f"{plan_file.relative_to(ROOT)} contains {pattern!r}")

    assert not violations, "Forbidden local runtime contracts found:\n" + "\n".join(violations)


def test_active_stage_plans_match_current_worktree_policy() -> None:
    violations: list[str] = []

    for plan_file in WORKTREE_POLICY_PLAN_FILES:
        content = plan_file.read_text(encoding="utf-8")
        for pattern in FORBIDDEN_WORKTREE_POLICY_PATTERNS:
            if pattern in content:
                violations.append(f"{plan_file.relative_to(ROOT)} contains {pattern!r}")

    assert not violations, "Outdated worktree policy found:\n" + "\n".join(violations)
