# Series Visual Signature Resilience v6

## 目标

从源头解决 Web 生成中视觉签名高级配置导致整条任务失败的问题。

## 原因

旧链路把视觉签名规划做成 mandatory hard-fail：LLM 多次没输出通过校验的计划后，整个视频失败。常见失败包括：

- supporting integration 被 LLM 写成替代主体；
- 实体陪衬角色没有被校验器识别为具体载体；
- 个别帧失败时整批结果被丢弃。

## v6 原则

1. 产品语义优先：新增 `series_visual_signature_presentation_mode`。
2. Prompt-first：先通过提示词约束 LLM 自然融入。
3. 校验器语义对齐：地面、前景、路边、主体旁等都是实体陪衬角色的合法载体。
4. 按帧 fallback：保留成功帧，只修失败帧。
5. Web 默认 soft：失败时自动修复并继续生成，strict 只用于开发/CI。
6. 保留身份：fallback 仍保留 `dog_1` 等具体身份，不退化成“频道识别轮廓”。
7. 可观测：fallback 写入 `VisualAnchorPlacementPlan.metadata` 和 planning snapshot。

## 推荐 Web 选择

- 视觉签名呈现方式：每帧可见实体角色
- 规划失败时自动修复并继续生成：开启
- 失败处理：自动修复并继续生成（推荐）
- 严格模式：关闭
