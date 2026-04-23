# AGENTS Git 推送策略 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将仓库默认 Git 行为补充为“每次原子提交后必须立即推送到 GitHub”，并保留用户明确要求仅本地提交时的例外。

**Architecture:** 这是一次纯文档规则变更，只修改仓库根目录 `AGENTS.md` 的“Git 提交与推送规则”章节，不改动其他 Git、分支、PR、CI 相关条款。实施后通过文本核对与 `git diff` 验证，确保规则语义与设计文档一致。

**Tech Stack:** Markdown, Git

---

### Task 1: 更新 AGENTS Git 推送规则

**Files:**
- Modify: `AGENTS.md`
- Reference: `docs/superpowers/specs/2026-04-20-agents-git-push-policy-design.md`

- [ ] **Step 1: 修改 `AGENTS.md` 中的 Git 提交与推送规则**

在 `## Git 提交与推送规则` 章节现有条目后新增一条规则，语义必须同时覆盖以下三点：

```md
- 默认每次完成原子化 `git commit` 后，必须立即推送到 GitHub。
- 如果用户明确要求“只本地提交、暂不推送”，则允许该次提交不推送。
- 如果因网络、权限、远端拒绝、分支保护或其他外部条件导致无法推送，必须明确说明阻塞原因，不能默认视为任务完成。
```

- [ ] **Step 2: 核对文档内容**

Run: `Get-Content -Path 'AGENTS.md' -Encoding utf8`
Expected: 在“Git 提交与推送规则”章节可见新增条目，且不影响既有规则内容。

- [ ] **Step 3: 检查本次 diff**

Run: `git diff -- AGENTS.md`
Expected: diff 仅包含本次新增的 Git 推送默认策略文本，不混入无关改动。

- [ ] **Step 4: 提交文档变更**

Run:

```bash
git add AGENTS.md
git commit -m "docs: require push after each atomic commit"
```

Expected: 生成仅包含 `AGENTS.md` 变更的原子提交。

- [ ] **Step 5: 推送到 GitHub**

Run: `git push origin dev`
Expected: 当前分支推送成功；若失败，明确记录阻塞原因。
