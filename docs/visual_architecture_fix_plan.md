# 视觉架构修复方案 v2

## 目标

不再把某个风格写死成“小黑逻辑”，而是把视觉生成拆成稳定的四层：

1. Template text policy：决定正文、字幕、模板层谁拥有文本。
2. VisualProfile：决定画幅、模板、提示词规则、负面规则、QA 规则。
3. Prompt projection：把 VisualProfile 注入最终 provider prompt，而不是散落在 prompt_prefix。
4. Quality gate：在媒体生成前检查 contract 是否丢失，防止问题进入昂贵的 ComfyUI/RunningHub 阶段。

## 为什么这是源头修复

旧问题不是某个模板不够像，而是策略分散：

- `template_text_policy` 在多个文件重复定义。
- 风格靠 `generation_world_hint`/`prompt_prefix` 字符串传递，不能验证、不能持久化、不能复用。
- QA 只靠人看结果，失败后没有结构化修复信息。
- 模板显示、字幕显示、媒体 prompt 之间没有统一 contract。

本修复让视觉风格成为 first-class contract。小黑只是 `xiaohei_article_illustration` profile，后续可以继续增加“科学解释图”“历史隐喻图”“产品概念图”等，而不用改核心代码。

## 数据流

```text
request params
  -> StoryboardConfig.visual_profile_id / visual_profile
  -> ImagePromptComposer
  -> resolve_visual_profile
  -> generate_styled_image_prompt_batch
  -> apply_visual_profile_to_batch
  -> VisualQualityGate
  -> prompt_plan_bundle / rendered_media_prompts / media_negative_prompt
  -> FrameProcessor / TemplateVisualMaterializer
```

## 不留技术债的原则

- 策略枚举集中到单个模块。
- profile 是数据，不是 if/else 风格分支。
- 所有新增行为都有最小单元测试覆盖。
- 失败信息进入 planning_snapshot，方便追踪。
- 默认兼容旧参数；没有传 visual_profile 时不改变现有行为。
