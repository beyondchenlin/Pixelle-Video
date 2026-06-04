# Review pass 1: 架构债检查

## 发现

1. 文本策略重复定义，存在 drift 风险。
2. 视觉风格缺少一等公民模型，只能通过字符串 hint 传递。
3. 模板、prompt、QA 三者没有共同 contract。
4. `template_text_policy="none"` 在 layered template caption 分支下可能失效。
5. 旧方案把小黑当成代码路径，会把项目带向风格 hard-code。

## 本轮修复

- 新增 `template_text_policy.py`。
- 新增 `VisualProfile` 和 registry。
- 新增 provider prompt projector。
- 新增 prompt-level quality gate。
- 用 profile 数据表达小黑和通用认知插图。
