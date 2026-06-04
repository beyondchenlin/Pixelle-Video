# Review pass 2: 集成风险检查

## 兼容性

- 未传 `visual_profile_id` 时，不改变旧生成路径。
- `template_text_policy` 仍使用原有四个公开字符串。
- profile 负面规则会合并到 batch negative prompt，并去重。
- profile contract 会写入 planning_snapshot，便于回放和调试。

## 风险控制

- apply 脚本只改本地文件，并生成 `.pixelle_visual_fix_backup/`。
- 所有 patch 都基于明确锚点，找不到锚点会中止，不做半吊子修改。
- 新增测试覆盖策略路由、profile 投影、QA gate。

## 后续建议

- 第二阶段可以把 image-level QA 接到视觉模型，对真实生成图做“是否像 PPT/是否小黑执行核心动作/是否留白”检测。
- 第三阶段可以把 `visual_profile_id` 暴露到 WebUI 模板选择面板。
