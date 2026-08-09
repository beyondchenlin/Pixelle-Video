# 分支工作流

## 基线

- 基线分支：`main`
- 开发分支：`dev`
- 任务分支前缀：`codex/`
- linked worktree 目录：`.worktrees`
- 默认任务来源或集成分支：`dev`

## 开始任务

```sh
git switch dev
git pull --ff-only origin dev
git worktree add .worktrees/<task-name> -b codex/<task-name> dev
cd .worktrees/<task-name>
```

进入 worktree 后，重新读取该 worktree 内的 `AGENTS.md`，再运行项目 worktree/bootstrap 初始化脚本。

## 工作中

- 保持一个 worktree 只处理一个变更意图。
- 只暂存当前任务拥有的文件。
- 提交前运行匹配验证命令，例如 `scripts/agent-verify.sh`、`scripts/agent-verify.ps1`、包管理器脚本或语言测试命令。
- 如果发现无关问题，记录并说明，不顺手扩散重构。

## 完成任务

默认只完成验证和任务分支的原子提交。仅当用户在当前任务中明确授权远程同步时，才执行下面的 `git push`。

```sh
<运行匹配验证命令>
git add -- <task-files>
git commit -m "fix(scope): <message following project policy>"
git push -u origin codex/<task-name>
```

## 合回集成分支

合入并推送共享开发分支会影响他人；只在当前任务明确授权时执行。

```sh
git switch dev
git pull --ff-only origin dev
git merge --no-ff -m "chore: 合并 <task-name>" codex/<task-name>
git push origin dev
```

## 禁止事项

- 不绕过仓库的受保护分支策略。
- 不强制推送。
- 不夹带无关文件。
- 不覆盖用户已有未提交改动。
- 不在未验证时声称完成。
