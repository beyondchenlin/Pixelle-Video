# Dify 重建 Pixelle 文案到图片提示词完整流程规格

> 目标：在 Dify 中独立重建 Pixelle 当前的“用户一句话或一段文案到图片生成提示词”完整流程。该流程不调用 Pixelle API，不依赖 Pixelle 代码，只复刻 Pixelle 的产品链路、提示词策略、结构化输出契约和最终 prompt 组装思想。
>
> Superpowers 生成说明：本文按 `superpowers:writing-plans` 的方式组织为可执行规格；生成 Dify YAML 时使用 `superpowers:executing-plans` 逐项落地，并在交付前使用 `superpowers:verification-before-completion` 做证据化校验。
>
> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement the YAML task-by-task, then use `superpowers:verification-before-completion` before marking the workflow ready.

## 范围

本规格只覆盖：

- 用户输入一句话、主题或完整文案。
- 生成完整 `source_text`。
- 生成 `storyboard_plan`。
- 生成每帧的基础图片提示词。
- 融合世界观、风格、镜头、文章具象化、IP/视觉签名、文本渲染策略、模型能力。
- 输出可直接交给生图模型的 `final_prompts` 和 `negative_prompt`。

本规格不覆盖：

- 图片生成。
- TTS 音频生成。
- 字幕渲染。
- 图片结合音频生成视频。

## Pixelle 源流程参考

- 标准 pipeline：`D:\demo1\Pixelle\Pixelle\pixelle_video\pipelines\standard.py`
- 分镜生成：`D:\demo1\Pixelle\Pixelle\pixelle_video\services\storyboard_generation.py`
- 图片提示词编排：`D:\demo1\Pixelle\Pixelle\pixelle_video\services\image_prompt_composer.py`
- 图片提示词批量生成：`D:\demo1\Pixelle\Pixelle\pixelle_video\utils\content_generators.py`
- 风格解析：`D:\demo1\Pixelle\Pixelle\pixelle_video\utils\style_resolution.py`
- 世界观规划：`D:\demo1\Pixelle\Pixelle\pixelle_video\services\content_world_planner.py`
- IP 使用规划：`D:\demo1\Pixelle\Pixelle\pixelle_video\services\ip_usage_planner.py`
- 视觉提示词规划：`D:\demo1\Pixelle\Pixelle\pixelle_video\services\visual_prompt_planning_service.py`
- 最终 prompt 模板：`D:\demo1\Pixelle\Pixelle\pixelle_video\prompts\templates\final_visual_prompt.md`

## 提示词覆盖原则

本规格的节点提示词是 Dify 可直接使用的适配版：保留 Pixelle 源模板的任务目标、字段契约、禁止项、失败处理和 JSON-only 约束。Pixelle 源模板里的 `Return JSON only` 在 Dify 节点中统一表达为 `只返回 JSON` / `Return JSON only`；Pixelle 的 Jinja 条件片段改成 Dify 变量。生成 YAML 时以各节点章节里的 System Prompt 和 User Prompt 为准。

| Pixelle 源模板 | Dify 节点 | 覆盖方式 |
|---|---|---|
| `script_generation.md` | 节点 3：Script Generation | 完整保留短视频文案生成角色、结构、开头、口播、事实、禁用词和 JSON 输出约束 |
| `storyboard_generation.md` | 节点 6：Storyboard Generation | 完整保留 source_text 覆盖、sentence/source_span 索引、帧数控制和 JSON 输出约束 |
| `storyboard_repair.md` | 节点 8：Storyboard Repair | 完整保留原 prompt、失败原因、同 schema 修复和 JSON-only 约束 |
| `content_world.md` | 节点 11：Content World Planning | 完整保留世界 profile 字段、hint 优先级、hex/字段名禁用约束 |
| `style_resolution.md` | 节点 12：Style Resolution | 完整保留 style_kind、prompt_template、style_profile、visual_style_contract 约束 |
| `storyboard_planning.md` | 节点 13：Storyboard Frame Planning | 完整保留 frame plan 字段、frame_source_items、prompt_contexts、world_profile 和 scene_id 字符串约束 |
| `ip_role_selection.md` | 节点 15：IP Role Selection | 完整保留 protagonist/supporting/passerby/absent 角色、物理支撑、受保护主体和中文描述约束 |
| `image_generation.md` | 节点 17：Base Image Prompt Generation | 完整保留 subject-first base prompt 边界、frame-aware context、风格优先级和 JSON 数量约束 |
| `base_visual_brief.md` | 节点 18：Base Visual Brief | 完整保留先形成主体画面、禁止提前注入视觉锚点、brief 字段和可读性约束 |
| `visual_anchor_integration.md` | 节点 19：Visual Anchor Integration | 完整保留视觉身份自然融入、展示模式、枚举、质量分和最终 JSON schema 约束 |
| `final_visual_prompt.md` | 节点 20：Final Prompt Contract Assembly | 完整保留 `[Scene]`、`[Composition]`、`[Style Assignment]`、`[Character Layer Style]`、`[World Layer Style]`、`[Integration and Priority]`、`[Rendering Requirements]` |
| `final_visual_prompt_clauses.md` | 节点 21：Text Rendering Policy | 完整保留 no visible text、planned text、visible whitelist、style/world/camera clauses |
| `structured_json_object.md` / `structured_schema_output.md` | 所有 LLM 节点 | 在 Dify 中统一表现为 JSON-only 输出、schema 校验、禁止 Markdown fence |
| `visual_anchor_placement.md` | 不作为 YAML 主链路节点 | 源码中存在，但当前主链路由 `VisualAnchorIntegrationPlanner` 负责视觉签名融合，YAML 按节点 19 实现 |

## Dify 输入变量

所有节点必须存在。用户未提供某类配置时，该节点输出默认结构，而不是跳过。

```json
{
  "user_text": "用户输入的一句话、主题或完整文案",
  "input_mode": "auto | topic | source_text",
  "script_length_mode": "auto | short | medium | long | custom",
  "script_target_words": null,
  "storyboard_mode": "smart | sentence | punctuation",
  "storyboard_count_mode": "auto | manual",
  "storyboard_scene_count": null,
  "storyboard_max_scene_count": 12,
  "prompt_language": "zh-Hans | en",
  "min_image_prompt_words": 30,
  "max_image_prompt_words": 60,
  "world_hint": "",
  "style_prompt": "",
  "ip_profile_json": "{}",
  "article_concretization_json": "{}",
  "text_policy_json": "{}",
  "visual_profile_json": "{}",
  "model_capability_json": "{\"supports_negative_prompt\": false, \"provider_hint\": \"positive_only\"}"
}
```

## Dify 输出变量

```json
{
  "source_text": "最终完整文案",
  "storyboard_plan": {},
  "prompt_contexts": {},
  "content_world_profile": {},
  "resolved_style": {},
  "storyboard_frame_plans": [],
  "article_concretization_plans": [],
  "ip_role_plans": [],
  "base_image_prompts": [],
  "base_visual_briefs": [],
  "visual_anchor_integration_plans": [],
  "final_prompt_contracts": [],
  "final_prompts": [],
  "negative_prompt": "",
  "trace_json": {}
}
```

## 总体节点顺序

| 序号 | 节点名 | Dify 节点类型 | 必须存在 | 主要输出 |
|---:|---|---|---|---|
| 1 | Start | Start | 是 | 用户输入 |
| 2 | Input Normalize | Code | 是 | `normalized_request` |
| 3 | Script Generation | LLM | 是 | `source_text_candidate` |
| 4 | Source Select | Code | 是 | `source_text` |
| 5 | Source Sentence Split | Code | 是 | `sentences` |
| 6 | Storyboard Generation | LLM | 是 | `raw_storyboard_plan` |
| 7 | Storyboard Validation | Code | 是 | `storyboard_validation` |
| 8 | Storyboard Repair | LLM | 是 | `repaired_storyboard_plan` |
| 9 | Storyboard Finalize | Code | 是 | `storyboard_plan` |
| 10 | Prompt Context Build | Code | 是 | `prompt_contexts` |
| 11 | Content World Planning | LLM | 是 | `content_world_profile` |
| 12 | Style Resolution | LLM | 是 | `resolved_style` |
| 13 | Storyboard Frame Planning | LLM | 是 | `storyboard_frame_plans` |
| 14 | Article Concretization | LLM | 是 | `article_concretization_plans` |
| 15 | IP Role Selection | LLM | 是 | `ip_role_plans` |
| 16 | Prompt Context Enrichment | Code | 是 | `enriched_prompt_contexts` |
| 17 | Base Image Prompt Generation | LLM | 是 | `base_image_prompts` |
| 18 | Base Visual Brief | LLM | 是 | `base_visual_briefs` |
| 19 | Visual Anchor Integration | LLM | 是 | `visual_anchor_integration_plans` |
| 20 | Final Prompt Contract Assembly | Code | 是 | `final_prompt_contracts` |
| 21 | Text Rendering Policy | Code | 是 | `text_rendering_results` |
| 22 | Provider Projection | Code | 是 | `projected_prompts` |
| 23 | Visual Profile Quality Gate | LLM | 是 | `quality_gate_results` |
| 24 | Prompt Sanitization | Code | 是 | `final_prompts`, `negative_prompt` |
| 25 | End | End | 是 | 全部最终变量 |

## 节点 1：Start

类型：Start

目标：

- 接收用户的一句话、主题或完整文案。
- 接收所有会影响提示词链路的配置。
- 将配置作为普通变量交给节点 2，不在 Start 节点内做业务判断。

输入字段：

```json
{
  "user_text": "用户输入的一句话、主题或完整文案",
  "input_mode": "auto | topic | source_text",
  "script_length_mode": "auto | short | medium | long | custom",
  "script_target_words": null,
  "storyboard_mode": "smart | sentence | punctuation",
  "storyboard_count_mode": "auto | manual",
  "storyboard_scene_count": null,
  "storyboard_max_scene_count": 12,
  "prompt_language": "zh-Hans | en",
  "min_image_prompt_words": 30,
  "max_image_prompt_words": 60,
  "world_hint": "",
  "style_prompt": "",
  "ip_profile_json": "{}",
  "article_concretization_json": "{}",
  "text_policy_json": "{}",
  "visual_profile_json": "{}",
  "model_capability_json": "{\"supports_negative_prompt\": false, \"provider_hint\": \"positive_only\"}"
}
```

输出：

```json
{
  "start_payload": {
    "user_text": "{{user_text}}",
    "input_mode": "{{input_mode}}",
    "script_length_mode": "{{script_length_mode}}",
    "script_target_words": "{{script_target_words}}",
    "storyboard_mode": "{{storyboard_mode}}",
    "storyboard_count_mode": "{{storyboard_count_mode}}",
    "storyboard_scene_count": "{{storyboard_scene_count}}",
    "storyboard_max_scene_count": "{{storyboard_max_scene_count}}",
    "prompt_language": "{{prompt_language}}",
    "min_image_prompt_words": "{{min_image_prompt_words}}",
    "max_image_prompt_words": "{{max_image_prompt_words}}",
    "world_hint": "{{world_hint}}",
    "style_prompt": "{{style_prompt}}",
    "ip_profile_json": "{{ip_profile_json}}",
    "article_concretization_json": "{{article_concretization_json}}",
    "text_policy_json": "{{text_policy_json}}",
    "visual_profile_json": "{{visual_profile_json}}",
    "model_capability_json": "{{model_capability_json}}"
  }
}
```

## 节点 2：Input Normalize

类型：Code

目标：

- 统一用户输入。
- 解析 JSON 配置。
- 给所有缺省配置补默认值。
- 决定 `effective_input_mode`。

输出：

```json
{
  "normalized_request": {
    "user_text": "",
    "effective_input_mode": "topic | source_text",
    "prompt_language": "zh-Hans",
    "scene_count": null,
    "style_prompt": "",
    "world_hint": "",
    "ip_profile": {},
    "article_concretization": {},
    "text_policy": {},
    "visual_profile": {},
    "model_capability": {
      "supports_negative_prompt": false,
      "provider_hint": "positive_only"
    }
  }
}
```

规则：

- `input_mode=source_text` 时，后续 Script Generation 节点仍然运行，但 Source Select 节点丢弃它的输出，保留原文。
- `input_mode=topic` 时，Source Select 使用 Script Generation 的输出。
- `input_mode=auto` 时，文本少于 35 个中文字符且没有明显句群结构，按 `topic`；否则按 `source_text`。
- `ip_profile_json` 为空时，构造 `{"enabled": false}`。
- `style_prompt` 为空时，Style Resolution 输出默认通用插画风格。

## 节点 3：Script Generation

类型：LLM

Pixelle 对应模板：`script_generation.md`

即使用户输入是完整文案，此节点也必须存在。Source Select 会决定是否采用它的输出。

### System Prompt

```text
你是一位有 10 年经验的短视频编导、爆款文案策划、口播脚本专家，同时也是中文内容润色专家。

你擅长为抖音、视频号、小红书、快手生成自然、有节奏、适合真人口播的短视频文案。你的目标不是写一篇漂亮文章，而是写出一段观众愿意听下去、博主能直接开拍的口播脚本。

用户可能输入一个主题，也可能输入一句话。你不能追问用户，需要在内部完成判断，然后直接输出最终文案。

你需要先在内部判断：
1. 这个主题最可能面向哪类人；
2. 这类人真正关心的痛点、困惑、欲望或情绪是什么；
3. 这个主题适合用哪种内容结构：观点型、知识型、故事型、产品型、避坑型、干货型或情绪共鸣型；
4. 第一句话用哪种开头最容易抓住人；
5. 这段内容应该保持什么语气：犀利、温和、共情、专业、生活化、故事感，或轻微吐槽。

然后只输出一段最终可直接用于短视频口播和分镜的完整文案。

不要输出分析过程。
不要输出写作思路。
不要输出标题。
不要输出提纲。
不要解释你为什么这样写。
不要引导点赞、关注、收藏。
不能编造具体数据、机构、名人、实验、案例。

开头不能使用这些普通开场：
- 大家好
- 今天我们来聊聊
- 你知道吗
- 最近很多人问我
- 今天给大家分享
- 哈喽大家好

开头要直接，不要铺垫。第一句话要有冲击力，但不能夸张到失真。

内容必须按这个顺序推进：
开头钩子 -> 点出问题 -> 解释原因 -> 给出核心观点 -> 给出方法、例子或判断标准 -> 总结一句容易记住的话 -> 自然收尾。

文案必须适合真人口播：
1. 语言口语化，像一个懂行的人在认真说话；
2. 多用短句，每句话尽量控制在 10 到 25 个字；
3. 句子长短要有变化；
4. 可以有停顿感，但不要频繁使用破折号；
5. 允许真实表达里的转折、犹豫和判断；
6. 不要写得像论文、公众号长文或新闻稿；
7. 不要使用过于书面化、官方化、模板化的表达；
8. 每隔一小段设置一个小转折、小疑问或小结论。

生成文案时不能出现以下问题：
1. 不要过度拔高主题；
2. 不要空喊意义、价值、格局、未来；
3. 不要堆砌漂亮但没用的形容词；
4. 不要写成“正确但无聊”的说明文；
5. 不要使用宣传广告式夸张话术；
6. 不要用假大空结论；
7. 不要使用生硬的排比；
8. 不要频繁出现三段式工整句；
9. 不要写“这不仅仅是……更是……”；
10. 不要用“作为……”“充当……”这类生硬表达；
11. 不要反复换同义词；
12. 不要用模糊归因，比如“相关研究表明”“业内人士认为”，除非用户提供了来源；
13. 不要编造具体数据、机构、人物、实验、案例；
14. 不要用“挑战与未来展望”这类模板化结构；
15. 不要滥用粗体、表情符号、编号和标题；
16. 不要使用不符合中文习惯的翻译腔；
17. 不要用讨好式语气；
18. 不要输出免责声明、知识截止日期或 AI 身份相关内容。

全文尽量不要使用以下词语，能删除就删除，能替换就替换：
此外、至关重要、深入探讨、强调、持久的、增强、培养、获得、突出、相互作用、复杂、复杂性、格局、关键性的、展示、织锦、证明、宝贵的、充满活力的、赋能、闭环、抓手、基石、赛道、深耕。

如果用户没有提供来源，只能使用模糊但真实的表达，例如：
- 很多人会遇到这种情况
- 常见的问题是
- 你可能会发现
- 不少人第一步就做错了
- 现实里经常是这样
- 对普通人来说，最麻烦的地方在于

输出前在内部检查：
1. 第一句话有没有抓人；
2. 内容有没有按逻辑推进；
3. 有没有像真人口播；
4. 有没有编造数据或案例；
5. 结尾有没有自然收住；
6. 有没有出现点赞、关注、收藏引导。

只返回 JSON。
```

### User Prompt

```text
请根据以下输入生成完整短视频口播文案。

输入内容：
{{user_text}}

长度模式：
{{script_length_mode}}

目标字数：
{{script_target_words}}

输出要求：
- 返回 JSON 对象。
- 顶层只允许 source_text。
- source_text 是一段完整文案，不要拆分分镜。
- 不要生成图片提示词。

输出格式：
{
  "source_text": "完整短视频口播文案"
}
```

## 节点 4：Source Select

类型：Code

规则：

- `effective_input_mode=topic`：使用 `source_text_candidate.source_text`。
- `effective_input_mode=source_text`：使用 `user_text`。
- 输出前清洗空白、连续换行、字面量 `\n`。

输出：

```json
{
  "source_text": "最终进入分镜的完整文案"
}
```

## 节点 5：Source Sentence Split

类型：Code

规则：

- 按 `。！？.!?` 和闭合标点切句。
- 保留每句在 `source_text` 中的 `start` 和 `end`。
- 如果没有终止标点，整个文本作为一条 sentence。

输出：

```json
{
  "sentences": [
    {
      "index": 0,
      "text": "句子文本",
      "source_start": 0,
      "source_end": 12
    }
  ]
}
```

## 节点 6：Storyboard Generation

类型：LLM

Pixelle 对应模板：`storyboard_generation.md`

### System Prompt

```text
你是短视频分镜策划。你的任务是从完整 source_text 创建 storyboard plan。

你必须先理解完整 source_text，再决定每一帧覆盖哪些原文。
你不能改写、总结、重写口播文本。
你不能生成图片提示词。
你只规划分镜帧的语义边界和视觉目标。

必须返回 JSON，不要 Markdown，不要解释。
```

### User Prompt

```text
任务：create_storyboard_plan_from_complete_source_text

prompt_language:
{{prompt_language}}

完整 source_text:
{{source_text}}

句子列表：
{{sentences_json}}

分镜数量模式：
{{storyboard_count_mode}}

手动分镜数量：
{{storyboard_scene_count}}

自动分镜数量范围：
最少 1 帧，最多 {{storyboard_max_scene_count}} 帧。

要求：
- 返回 frames 数组。
- frames 必须覆盖整个 source_text，顺序一致。
- 不要遗漏有意义文本，只允许帧之间存在空白字符间隙。
- 不要重写或总结 voiceover text。
- 不要生成最终图片提示词。
- 每帧必须有 source_text、visual_goal、prompt_intent。
- 如果使用 sentence_indices，必须覆盖所有句子且无遗漏、无重叠。
- sentence_indices 必须是连续整数数组。
- source_start 和 source_end 可以省略；如果填写，必须同时存在。
- visual_goal 和 prompt_intent 使用中文。

输出 JSON schema：
{
  "frames": [
    {
      "source_text": "该帧覆盖的原文片段",
      "visual_goal": "这一帧需要传达的视觉重点",
      "prompt_intent": "给后续图片提示词组合的指导",
      "sentence_indices": [0],
      "source_start": 0,
      "source_end": 0
    }
  ]
}
```

## 节点 7：Storyboard Validation

类型：Code

校验规则：

- `frames` 必须非空。
- 自动模式下帧数必须在 1 到 `storyboard_max_scene_count` 之间。
- 手动模式下帧数必须等于 `storyboard_scene_count`。
- 每帧 `source_text`、`visual_goal`、`prompt_intent` 非空。
- 如果有 `sentence_indices`，必须覆盖所有句子，无重复、无遗漏、无交叉。
- 如果没有 `sentence_indices`，用 `source_text.find` 在原文中按顺序定位。
- 修复首尾空白造成的范围误差。
- 如果尾部原文没有被覆盖，将尾部并入最后一帧。

输出：

```json
{
  "valid": true,
  "reason": "",
  "normalized_frames": []
}
```

## 节点 8：Storyboard Repair

类型：LLM

Pixelle 对应模板：`storyboard_repair.md`

该节点始终存在。若 Validation 成功，User Prompt 中传入 `reason=validation_passed`，要求原样返回。

### System Prompt

```text
你是 storyboard JSON 修复器。
你只能修复 JSON 结构、帧覆盖、帧数、字段缺失问题。
不能改变 source_text 的真实含义。
不能生成图片提示词。
只能输出 JSON。
```

### User Prompt

```text
原始 Storyboard Prompt：
{{storyboard_generation_prompt}}

上一次 storyboard response：
{{raw_storyboard_plan_json}}

校验结果：
{{storyboard_validation_json}}

修复要求：
- 如果校验结果 valid=true，请原样返回上一次 storyboard response。
- 如果 valid=false，请返回满足同一 schema 的修复版 JSON。
- frames 必须覆盖完整 source_text。
- 帧顺序必须与 source_text 顺序一致。
- 每帧必须包含 source_text、visual_goal、prompt_intent。
- 不要输出 Markdown、解释、标题。

只输出 JSON：
{
  "frames": [...]
}
```

## 节点 9：Storyboard Finalize

类型：Code

目标：

- 在原文中解析最终帧范围。
- 为 plan 和 frame 生成稳定 ID。
- 生成 Pixelle 风格 `StoryboardPlan`。

输出：

```json
{
  "storyboard_plan": {
    "plan_id": "plan_sha256短码",
    "revision": 1,
    "mode": "smart",
    "count_mode": "auto",
    "requested_scene_count": null,
    "resolved_scene_count": 3,
    "source_text": "",
    "source_digest": "",
    "frames": [
      {
        "frame_id": "frame_001_sha短码",
        "index": 1,
        "source_text": "",
        "visual_goal": "",
        "prompt_intent": "",
        "source_start": 0,
        "source_end": 0,
        "metadata": {
          "strategy": "smart"
        }
      }
    ]
  }
}
```

## 节点 10：Prompt Context Build

类型：Code

Pixelle 对应函数：`ImagePromptComposer._build_prompt_contexts`

输出：

```json
{
  "prompt_contexts": {
    "plan_context": {
      "plan_id": "",
      "plan_revision": 1,
      "source_digest": "",
      "plan_source_text": ""
    },
    "frame_contexts": [
      {
        "frame_id": "",
        "frame_index": 1,
        "frame_source_text": "",
        "source_text": "",
        "visual_goal": "",
        "prompt_intent": "",
        "shot_type": null,
        "shot_purpose": null,
        "primary_subject": null,
        "secondary_subjects": [],
        "continuity_anchors": [],
        "world_elements": [],
        "focus_detail": null,
        "source_start": 0,
        "source_end": 0,
        "metadata": {}
      }
    ]
  }
}
```

## 节点 11：Content World Planning

类型：LLM

Pixelle 对应模板：`content_world.md`

### System Prompt

```text
你是内容世界观规划器。你的任务是从 source_text、用户世界观提示、IP 默认世界观提示和 world preset 中抽取当前生成任务的世界 profile。

你只描述当前这次生成的世界，不要创建和文案无关的新宇宙。
不要输出 Markdown。
不要输出 hex 色值。
不要把字段名复制进自然语言值。
只返回 JSON。
```

### User Prompt

```text
任务：extract_current_generation_world_profile

source_text:
{{source_text}}

generation_world_hint:
{{world_hint}}

ip_default_world_hint:
{{ip_profile.world_hint}}

world_preset:
{{world_preset_json}}

输出字段：
{
  "summary": "当前内容世界摘要",
  "time_space": "时空设定",
  "visual_environment": "视觉环境",
  "atmosphere": "氛围",
  "cultural_context": "文化语境",
  "story_constraints": "必须保护的原文主体、地标、人物、建筑、关系",
  "ip_integration_guidance": "如果有 IP，如何不破坏当前内容世界"
}

要求：
- generation_world_hint 优先级最高。
- ip_default_world_hint 只作为兼容提示，不替代当前故事世界。
- 如果信息不足，也要基于 source_text 生成简洁 profile。
- 只输出 JSON。
```

## 节点 12：Style Resolution

类型：LLM

Pixelle 对应模板：`style_resolution.md`

### System Prompt

```text
你是图片生成风格解析器。你的任务是把用户提供的风格描述解析成结构化、可被后续 prompt 组装使用的风格配置。

不要直接把原始风格描述拼到最终 prompt。
不要让风格替代文案主体。
只返回 JSON。
```

### User Prompt

```text
任务：resolve_style_prefix

raw_prefix:
{{style_prompt}}

如果 raw_prefix 为空，使用默认风格：
清晰、干净、主体优先的中文短视频解释型插画，构图可读，背景不杂乱。

要求：
- style_profile.style_kind 必须等于顶层 style_kind。
- style_kind 只能是 visual_only、ip_world、hybrid。
- prompt_template 如果非空，必须包含 {prompt} 且只出现一次。
- style_profile 每个字段必须非空。
- visual_only 必须保留主体语义。
- ip_world 可以描述目标世界，但不能删除原文主体。
- hybrid 表示既有风格化世界，又保留原文主体。
- negative_prompt 只写适合 negative prompt 的短语。
- negative_rules 写自然语言规则。
- 不要输出 Markdown。

输出 JSON：
{
  "style_kind": "visual_only",
  "prompt_template": "{prompt}",
  "negative_prompt": "",
  "style_profile": {
    "style_kind": "visual_only",
    "subject_policy": "preserve source subject semantics",
    "shape_language": "clean readable shapes",
    "material": "flat illustration surface",
    "palette": "restrained harmonious colors",
    "lighting": "soft clear lighting",
    "world_elements": "simple environment elements serving the source text",
    "consistency_anchor": "all frames share one coherent visual language",
    "negative_rules": "cluttered composition, unreadable subject, random text, watermark"
  },
  "visual_style_contract": null
}
```

## 节点 13：Storyboard Frame Planning

类型：LLM

Pixelle 对应模板：`storyboard_planning.md`

### System Prompt

```text
你是 storyboard frame planner。你需要为每个 frame 规划镜头、主体、世界元素和连续性锚点，供后续图片 prompt 生成使用。

你不能改写 frame_source_text。
你不能生成最终图片 prompt。
你只输出结构化 frame plan。
只返回 JSON。
```

### User Prompt

```text
任务：plan_storyboard_frames

prompt_language:
{{prompt_language}}

content_world_profile:
{{content_world_profile_json}}

resolved_style:
{{resolved_style_json}}

prompt_contexts:
{{prompt_contexts_json}}

storyboard_plan:
{{storyboard_plan_json}}

要求：
- 每个 storyboard frame 输出一个 frame plan。
- 顺序必须与 storyboard_plan.frames 一致。
- scene_id 必须使用对应 frame_id，不要用数字。
- 使用 plan_source_text 理解全局意义。
- 使用 frame_source_text、visual_goal、prompt_intent 一起判断画面。
- 补充 shot_type、shot_purpose、primary_subject、secondary_subjects、world_elements、continuity_anchors、focus_detail。
- array 字段只包含字符串。
- 如果没有明确主体，primary_subject 使用该帧核心概念。
- 不输出 Markdown。

输出 JSON：
{
  "frames": [
    {
      "scene_id": "frame_id",
      "narration_fragment": "该帧原文",
      "knowledge_goal": "这一帧要让观众理解什么",
      "shot_type": "medium shot | close up | wide shot | overhead | split composition | symbolic scene",
      "shot_purpose": "establish context | explain mechanism | show contrast | emotional emphasis | conclusion",
      "primary_subject": "主视觉主体",
      "secondary_subjects": ["辅助主体"],
      "world_elements": ["场景元素"],
      "continuity_anchors": ["跨帧连续元素"],
      "focus_detail": "本帧最重要的视觉细节",
      "prompt_intent": "后续图片提示词意图",
      "locked_fields": [],
      "frame_source": "llm_planned",
      "replan_scope": "full_frame",
      "planner_version": "dify-v1"
    }
  ]
}
```

## 节点 14：Article Concretization

类型：LLM

Pixelle 对应服务：`article_concretization_pipeline.py`、`article_concretization_planner.py`

该节点必须存在。没有文章具象化配置时，仍然输出每帧 `enabled=false` 的结构。

### System Prompt

```text
你是文章视觉具象化规划器。你的任务是把抽象观点、因果关系、认知状态、方法步骤、结构关系、冲突对比转化成可画的图像计划。

你不能生成最终图片 prompt。
你只生成每帧的视觉具象化计划，供后续基础图片 prompt 和最终 prompt 使用。
只返回 JSON。
```

### User Prompt

```text
任务：plan_article_concretization

article_concretization_config:
{{article_concretization_json}}

storyboard_plan:
{{storyboard_plan_json}}

storyboard_frame_plans:
{{storyboard_frame_plans_json}}

content_world_profile:
{{content_world_profile_json}}

要求：
- 每个 frame 都输出一个 plan。
- 如果配置未启用，输出 enabled=false，但保留 frame_id。
- 如果启用，给出 cognitive_anchor_kind、diagram_grammar、visual_metaphor、required_subjects、visible_text_policy。
- 具象化必须服务原文，不要创造无关图解。
- 如果 visible_text_policy=no_visible_text，用物体、构图、符号表达，不依赖文字。
- 不输出 Markdown。

输出 JSON：
{
  "article_concretization_plans": [
    {
      "frame_id": "frame_id",
      "enabled": true,
      "cognitive_anchor_kind": "judgment | causal_mechanism | process | structure | state | metaphor | contrast | relationship | evidence | decision_path",
      "diagram_grammar": "single_explanation_image | process_flow | relationship_map | metaphor_scene | contrast_board | structure_map",
      "visual_metaphor": "一个可画的核心视觉隐喻",
      "required_subjects": ["必须保留的主体"],
      "key_objects": ["关键物体"],
      "layout_logic": "构图逻辑",
      "visible_text_policy": "no_visible_text | sparse_approved_text",
      "approved_labels": [],
      "negative_constraints": ["不要变成 PPT", "不要密集文字", "不要复杂流程图"]
    }
  ]
}
```

## 节点 15：IP Role Selection

类型：LLM

Pixelle 对应模板：`ip_role_selection.md`

该节点必须存在。`ip_profile.enabled=false` 时输出每帧 `role_slot=absent`。

### System Prompt

```text
你是动画视频的 casting director 和 scene designer。一个 IP 角色可能需要被放进每一帧。

你要决定 IP 在每帧是否出现、扮演什么叙事角色、以什么可视程度出现，以及如何自然融入场景。

IP 绝不能破坏原文主体，不能替代受保护主体，不能像贴纸、水印或角标一样被贴上去。

只返回 JSON array。
```

### User Prompt

```text
IP Character Profile:
{{ip_profile_json}}

Frame Sequence:
{{storyboard_frame_plans_json}}

Content World Profile:
{{content_world_profile_json}}

Article Concretization:
{{article_concretization_plans_json}}

对每帧决定：
1. role_slot:
   - protagonist: IP 是主主体，只有原文或配置明确要求时使用。
   - supporting: IP 是陪伴者、助手、观察者，不替代主主体。
   - passerby: IP 是远景或边缘参与者，融入环境。
   - absent: IP 不出现。

2. role_label:
   用中文描述 IP 在本帧的功能，例如“导游讲解者”“情感陪伴者”“路人观察者”“画外不出镜”。

3. presence_level:
   只能使用“全身出镜”“半身出镜”“局部细节”“远景融入”“完全不出镜”。

4. appearance_description:
   - 必须读取 source_text、visual_goal、shot_type、primary_subject。
   - 必须把 IP 自然放进这个场景，不像贴纸或单独吉祥物。
   - 当本帧有历史人物、宗教人物、真实人物、地标、建筑、被讲解对象时，原主体必须保持叙事焦点。
   - IP 可以陪伴、观察、辅助、指向、反应、引导，但不能替代、合并、cosplay、变形成原主体。
   - 可见 IP 必须有物理支撑点：站在地面、坐在桌边、靠在墙边、站在屋顶、位于屏幕边缘、在人群边缘等。
   - 避免“背景中隐约可见一只兔子”这类没有支撑点的说法。
   - 如果 role_slot=absent，appearance_description 必须是空字符串。
   - 可见时写成 30 到 80 个中文字符的一句自然场景短语。

5. reason:
   一句话解释为什么这个选择适合本帧。

规则：
- 如果 ip_profile.enabled=false，所有帧 role_slot=absent。
- protected subjects 或严肃地标场景优先 passerby 或 absent。
- 情绪高潮帧可以 supporting，但不能抢主角。
- 不要所有帧都用同一种 role_slot。
- 不输出 Markdown。

输出 JSON array：
[
  {
    "frame_id": "frame_id",
    "frame_index": 0,
    "role_slot": "supporting",
    "role_label": "导游讲解者",
    "presence_level": "半身出镜",
    "appearance_description": "白色卡通兔子站在景点旁，戴着蓝色领结，长耳朵微微翘起，圆润脸型带着好奇的表情，正指向画面中的古迹",
    "reason": "..."
  }
]
```

## 节点 16：Prompt Context Enrichment

类型：Code

目标：

- 把 `content_world_profile` 写入 `plan_context.generation_world_profile`。
- 把 `storyboard_frame_plans` 合并到每帧 context。
- 把 `article_concretization_plan` 写入每帧 context。
- 把 `ip_role_plan` 写入每帧 context。
- 构造 `style_context`。

输出结构：

```json
{
  "enriched_prompt_contexts": {
    "plan_context": {
      "plan_id": "",
      "plan_revision": 1,
      "source_digest": "",
      "plan_source_text": "",
      "generation_world_profile": {}
    },
    "frame_contexts": [
      {
        "frame_id": "",
        "frame_source_text": "",
        "visual_goal": "",
        "prompt_intent": "",
        "shot_type": "",
        "shot_purpose": "",
        "primary_subject": "",
        "secondary_subjects": [],
        "continuity_anchors": [],
        "world_elements": [],
        "focus_detail": "",
        "article_concretization_plan": {},
        "ip_adaptation": {},
        "ip_scene_description": "",
        "ip_negative_constraints": [],
        "style_context": {}
      }
    ]
  }
}
```

## 节点 17：Base Image Prompt Generation

类型：LLM

Pixelle 对应模板：`image_generation.md`

### System Prompt

```text
你是专业视觉创意设计师，擅长为视频脚本创建有表现力、有象征性的图片生成提示词，把抽象概念转化为具体视觉场景。

你的任务是为每个 storyboard frame 生成 subject-first base image prompt。

这一阶段只生成基础主体画面。
不要加入 recurring IP、mascot、频道视觉锚点、logo、兔子、麻雀、椅子、石头、飞机或其他重复锚点，除非它们是该帧原文明确主体。

只返回 JSON。
```

### User Prompt

```text
任务：generate_base_image_prompts

prompt_language:
{{prompt_language}}

min_words:
{{min_image_prompt_words}}

max_words:
{{max_image_prompt_words}}

style_profile:
{{resolved_style.style_profile}}

input_payload:
{{enriched_prompt_contexts_json}}

要求：
- 输入中有 {{frame_count}} 个 storyboard frame，必须输出 {{frame_count}} 个 image_prompts。
- 使用 prompt_contexts 作为主要来源。
- 先阅读 plan_source_text 理解完整脚本。
- 每帧结合 frame_source_text、visual_goal、prompt_intent、focus_detail。
- 尊重 shot_type、shot_purpose、primary_subject、secondary_subjects、world_elements、continuity_anchors。
- 如果存在 generation_world_profile，使用它细化世界，但不能替代受保护原文主体。
- 如果存在 article_concretization_plan，把抽象观点具体化为可画的核心视觉。
- 不要输出字段名、JSON key、参数名、hex 色值、内部标签。
- 不要输出 negative prompt 语法。
- 如果需要约束，用自然语言视觉要求写入 prompt。
- 每个 prompt 必须是纯图片视觉描述。
- 中文输出。
- 不输出 Markdown。

输出 JSON：
{
  "image_prompts": [
    "详细中文图片提示词"
  ]
}
```

## 节点 18：Base Visual Brief

类型：LLM

Pixelle 对应模板：`base_visual_brief.md`

### System Prompt

```text
你是 visual director。你需要在任何 recurring channel motif 或 visual anchor 插入之前，把每个基础图片 prompt 规划成一个完整、高质量、主体优先的图像设计 brief。

不要加入 IP、mascot、频道符号、视觉锚点、logo、兔子、麻雀或其他重复元素，除非它已经是原文主体。

只返回 JSON。
```

### User Prompt

```text
Input Frames:
{{base_prompt_frames_json}}

Style Profile:
{{resolved_style.style_profile}}

Content World Profile:
{{content_world_profile_json}}

规则：
- 每帧输出一个 base_visual_brief。
- Focus on the best image for the narration itself.
- Describe one clear visual moment for each frame.
- Keep main subjects readable and visually distinct.
- Include spatial layout, camera plan, composition, lighting, visual style, key props, readability constraints.
- base_image_prompt 必须是纯 text-to-image visual prompt，不含内部字段名。
- 不输出 Markdown。

输出 JSON：
{
  "base_visual_briefs": [
    {
      "frame_id": "frame_id",
      "core_message": "该帧原文核心信息",
      "visual_moment": "基础图片 prompt 的视觉瞬间",
      "main_subjects": ["主主体"],
      "subject_identity_anchors": ["主体身份锚点"],
      "subject_relationship": "主体关系",
      "setting": "场景",
      "spatial_layout": "空间层次",
      "camera_plan": "镜头计划",
      "composition_rules": "构图规则",
      "lighting_mood": "光影氛围",
      "style_surface": "风格表面",
      "key_props_symbols": ["关键道具或符号"],
      "readability_constraints": ["可读性约束"],
      "anchor_affordances": ["可以自然承载视觉签名的位置或物体"],
      "anchor_forbidden_zones": ["不能放置视觉签名的位置"],
      "anchor_integration_notes": ["融合注意事项"],
      "base_image_prompt": "纯图片生成提示词"
    }
  ]
}
```

## 节点 19：Visual Anchor Integration

类型：LLM

Pixelle 对应模板：`visual_anchor_integration.md`

该节点必须存在。IP 未启用时，输出每帧 `visible=false` 和不改变基础画面的 integration plan。

### System Prompt

```text
你是 senior visual director。你接收基础视觉 brief、视觉身份 profile、展示策略和运行策略。你的任务是在保留原始视觉意图的前提下，让配置的视觉身份自然出现。

如果 IP 未启用，你仍然要输出每帧计划，但计划必须声明 visible=false，并且 integrated_scene_prompt 等于 base_image_prompt。

如果 IP 启用，则视觉身份必须自然融入场景。它不能像贴纸、水印、角标、UI overlay。它必须有真实场景位置和物理支撑点。

只返回 JSON。
```

### User Prompt

```text
Base Visual Briefs:
{{base_visual_briefs_json}}

Visual Identity Profile:
{{ip_profile_json}}

IP Role Plans:
{{ip_role_plans_json}}

Runtime Policy:
{
  "forbid_sticker": true,
  "forbid_watermark": true,
  "forbid_corner_badge": true,
  "preserve_source_subject": true,
  "require_physical_support": true
}

要求：
- 每个 frame 输出一个 visual_anchor_integration_plan。
- 如果 ip_profile.enabled=false 或对应 role_slot=absent：
  - visible=false
  - integrated_scene_prompt 使用 base_image_prompt
  - image_prompt_clause 为空字符串
- 如果 role_slot=supporting：
  - IP 是真实可见的小配角。
  - 不替代 source subject。
  - 放在地面、桌边、路边、墙边、屏幕边、场景物体旁等明确位置。
- 如果 role_slot=passerby：
  - IP 是边缘参与者，但仍然有物理支撑点。
- 如果 role_slot=protagonist：
  - 只有原文或配置明确要求时才让 IP 成为主主体。
- image_prompt_clause 必须是纯视觉句子，不能出现“IP角色”“视觉锚点”“role_slot”等内部词。
- integrated_scene_prompt 必须是最终可画的一句场景 prompt，保留 source intent。
- 不输出 Markdown。

输出 JSON：
{
  "visual_anchor_integration_plans": [
    {
      "frame_id": "frame_id",
      "visible": true,
      "carrier_type": "minor_supporting_character | embedded_mark | prop_object | background_extra | none",
      "anchor_function": "co_present_support | embedded_mark | micro_cameo | none",
      "prominence": "small_side_character | tiny_prop | embedded_mark | absent",
      "style_relation": "blended",
      "placement": "具体物理位置",
      "support_anchor": "地面、桌面、墙面、屏幕边缘等",
      "contact_relation": "站立、坐着、倚靠、贴附、印在表面等",
      "interaction_target": "它辅助或观察的对象",
      "occlusion_relation": "主主体保持可读",
      "visual_weight_clause": "可见但从属于主体",
      "image_prompt_clause": "纯视觉融合句",
      "integrated_scene_prompt": "融合后的完整场景 prompt",
      "integration_strategy": "supporting_integration | subject_replacement | absent",
      "manifestation_form": "small supporting character, scene-bound mark, prop, or absent",
      "manifestation_location": "具体位置",
      "manifestation_visibility": "clear | subtle | absent",
      "manifestation_relationship": "不替代原文主体",
      "scene_coherence_score": 9,
      "disruption_risk": 1,
      "identity_preservation_score": 9,
      "reason": "选择原因"
    }
  ]
}
```

## 节点 20：Final Prompt Contract Assembly

类型：Code

Pixelle 对应模板：`final_visual_prompt.md`

组装模板：

```text
[Scene]
{scene}

[Composition]
{composition}

[Style Assignment]
{style_assignment}

[Character Layer Style]
{character_layer_style}

[World Layer Style]
{world_layer_style}

[Integration and Priority]
{integration_priority}

Rendering requirements: {visual_suffix}

[Rendering Requirements]
{rendering_requirements}
```

每帧映射：

```json
{
  "scene": "visual_anchor_integrated_scene_prompt 或 base_image_prompt",
  "composition": "spatial_layout + camera_plan + composition_rules",
  "style_assignment": "subject_identity_anchors 或 resolved_style 风格描述",
  "character_layer_style": "image_prompt_clause 或 无额外频道视觉元素",
  "world_layer_style": "style_surface + content_world_profile.visual_environment",
  "integration_priority": "readability_constraints + protected subject rules",
  "negative_rules": []
}
```

输出：

```json
{
  "final_prompt_contracts": [
    {
      "frame_id": "frame_id",
      "scene": "",
      "composition": "",
      "style_assignment": "",
      "character_layer_style": "",
      "world_layer_style": "",
      "integration_priority": "",
      "negative_rules": [],
      "full_contract_prompt": "[Scene] ..."
    }
  ]
}
```

## 节点 21：Text Rendering Policy

类型：Code

Pixelle 对应模板：`final_visual_prompt_clauses.md`

默认无文字正向规则：

```text
no visible text, no Chinese characters, no English letters, no words, no subtitles, no captions, no watermark, no logo text, convey the idea through objects, symbols, composition, and scene elements instead of written text
```

默认文字负面规则：

```text
text, letters, words, typography, subtitles, captions, watermark, logo, Chinese characters, English letters, handwriting, calligraphy, printed text
```

白名单文字规则：

```text
画面文字只允许白名单内容：{visible_text_whitelist}；only whitelisted text may appear, no extra words.
```

处理规则：

- 默认 `suppress_unplanned_embedded_text=true`。
- 如果没有 native prompt text hint，则给每帧追加 no visible text 正向规则。
- 如果存在白名单文字，则追加白名单规则。
- 如果模型支持 negative prompt，文字负面规则进入 `negative_rules`。
- 如果模型不支持 negative prompt，文字负面规则转成正向 `Rendering requirements`。

## 节点 22：Provider Projection

类型：Code

目标：

- 根据模型能力投影最终 prompt。
- 支持 negative prompt 的模型：`final_prompt` 保持六段式 contract，`negative_prompt` 单独输出。
- positive-only 模型：把 negative rules 改写成正向要求并合入 `Rendering requirements`。

负面到正向改写示例：

| 负面规则 | 正向改写 |
|---|---|
| no visible text | 画面通过物体、构图和符号表达内容，表面保持干净完整 |
| blue rabbit | IP 保持白色身体，蓝色领结只是小面积识别点 |
| do not replace source subjects | 主要画面主体保持清晰可见，频道视觉元素只作为从属场景元素 |
| crowded composition | 构图简洁，主体和背景层次清楚 |

输出：

```json
{
  "projected_prompts": [
    {
      "frame_id": "frame_id",
      "positive_prompt": "",
      "negative_prompt": "",
      "provider_mode": "negative_capable | positive_only"
    }
  ]
}
```

## 节点 23：Visual Profile Quality Gate

类型：LLM

Pixelle 对应服务：`visual_prompt_profile_projector.py`、`visual_quality_gate.py`

该节点必须存在。没有 visual profile 时，使用默认质量规则。

### System Prompt

```text
你是图片 prompt 质量审查和修复器。你需要检查每帧最终 prompt 是否符合 visual profile、文案主体、构图可读性、文本安全和模型稳定性要求。

你不能重写整个 prompt 的创意方向。
你只能输出必要的 repair clauses、risk flags 和修复后的 prompt。
只返回 JSON。
```

### User Prompt

```text
Visual Profile:
{{visual_profile_json}}

Projected Prompts:
{{projected_prompts_json}}

Storyboard Plan:
{{storyboard_plan_json}}

Quality Rules:
- 每帧必须保留 source_text 的核心主体或核心观点。
- 主体必须可读，不能被 IP 或视觉签名抢占。
- 避免 PPT、信息图、UI 截图、密集文字、随机文字、水印。
- 如果是文章认知插画，必须一帧一个清晰认知锚点。
- 如果存在 protected subject，不能替代或遮挡。
- 如果 prompt 里出现内部字段名、JSON key、hex 色值，必须修复。
- 如果模型为 positive_only，不要依赖 negative_prompt 才能约束画面。

输出 JSON：
{
  "quality_gate_results": [
    {
      "frame_id": "frame_id",
      "passed": true,
      "risk_flags": [],
      "repair_clauses": [],
      "repaired_positive_prompt": "",
      "repaired_negative_prompt": ""
    }
  ]
}
```

## 节点 24：Prompt Sanitization

类型：Code

目标：

- 输出最终可交付生图模型的 prompt。
- 清理内部字段和不稳定符号。

清理规则：

- 移除 hex 色值：`#fff`、`#ffffff`、`#ffffffff`。
- 移除内部字段标签：
  - `summary_text`
  - `scene_text`
  - `title_hex`
  - `ip_presence_type`
  - `presence_mode`
  - `visible_text_whitelist`
  - `negative_constraints`
  - `identity_color_terms`
  - `identity_anchors_visible`
  - `identity_anchors_suppressed`
  - `semantic_reason`
  - `image_text_plan`
  - `ip_image_text_plan`
  - `text_safety_rules`
  - `must_not_replace`
  - `generation_world_profile`
  - `story_constraints`
  - `ip_integration_guidance`
  - `ip_adaptation`
- 压缩连续空白。
- 清理重复逗号、分号。
- 去除首尾逗号、分号。
- 去重 negative prompt 片段。

输出：

```json
{
  "final_prompts": [
    {
      "frame_id": "frame_id",
      "prompt": "最终正向提示词",
      "negative_prompt": "最终负向提示词"
    }
  ],
  "negative_prompt": "批量共享负向提示词",
  "trace_json": {
    "source_text": "",
    "storyboard_plan": {},
    "content_world_profile": {},
    "resolved_style": {},
    "ip_role_plans": [],
    "final_prompt_contracts": []
  }
}
```

## Dify End 输出

```json
{
  "source_text": "{{source_text}}",
  "storyboard_plan": "{{storyboard_plan}}",
  "prompt_contexts": "{{enriched_prompt_contexts}}",
  "content_world_profile": "{{content_world_profile}}",
  "resolved_style": "{{resolved_style}}",
  "storyboard_frame_plans": "{{storyboard_frame_plans}}",
  "article_concretization_plans": "{{article_concretization_plans}}",
  "ip_role_plans": "{{ip_role_plans}}",
  "base_image_prompts": "{{base_image_prompts}}",
  "base_visual_briefs": "{{base_visual_briefs}}",
  "visual_anchor_integration_plans": "{{visual_anchor_integration_plans}}",
  "final_prompt_contracts": "{{final_prompt_contracts}}",
  "final_prompts": "{{final_prompts}}",
  "negative_prompt": "{{negative_prompt}}",
  "trace_json": "{{trace_json}}"
}
```

## 默认策略

所有节点必须运行。

| 用户未提供 | 节点默认输出 |
|---|---|
| `style_prompt` | Style Resolution 输出默认清晰解释型插画风格 |
| `world_hint` | Content World Planning 从 `source_text` 自动抽取 |
| `ip_profile` | IP Role Selection 输出所有帧 `absent` |
| `article_concretization` | Article Concretization 输出所有帧 `enabled=false` |
| `visual_profile` | Quality Gate 使用默认可读性、安全性、主体保护规则 |
| 模型不支持 negative prompt | Provider Projection 把负面约束改写成正向要求 |

## 完整性检查清单

- 每个 LLM 节点都有明确 system prompt 和 user prompt。
- 每个 Code 节点都有输入、输出和规则。
- 每个节点都必须存在，没有“最小闭环”。
- 每个节点都有默认输出策略。
- 最终 prompt 保留 Pixelle 的六段式 final visual prompt contract。
- IP/视觉签名不在基础 prompt 阶段注入，只在 Base Visual Brief 之后融合。
- 文本渲染策略默认禁止随机文字、水印、字幕。
- positive-only 模型不会依赖 negative prompt。
- 输出 trace 能回看每个阶段的中间结果。

## Dify YAML 生成实施清单

- [ ] 在 Dify 中创建独立 Workflow，Start 输入字段与本文 `Dify 输入变量` 完全一致。
- [ ] 按 `总体节点顺序` 创建 25 个节点，所有节点都连接到主链路。
- [ ] 给所有 LLM 节点设置 JSON object 输出解析，并在失败路径进入对应校验或修复节点。
- [ ] 将节点 3、6、8、11、12、13、14、15、17、18、19、23 的 System Prompt 和 User Prompt 填入 Dify LLM 节点。
- [ ] 将节点 2、4、5、7、9、10、16、20、21、22、24 的规则实现为 Dify Code 节点。
- [ ] 在节点 7 和节点 9 中实现分镜覆盖校验，保证 `source_text` 从头到尾都被 frame 覆盖。
- [ ] 在节点 12 中实现空风格默认输出，不能让空 `style_prompt` 造成后续节点缺字段。
- [ ] 在节点 15 和节点 19 中实现无 IP 默认输出，让链路保持完整且不改写基础画面。
- [ ] 在节点 21 和节点 22 中实现 positive-only 模型投影，把负向约束改写为正向渲染要求。
- [ ] 在节点 24 输出 `final_prompts`、`negative_prompt`、`trace_json`，并把所有中间产物传到 End 节点。
- [ ] 用主题输入、完整文案输入、空风格、启用 IP、不支持 negative prompt 五组样例验证 YAML。

## Review 记录

### Review 1：链路完整性

结论：通过。

核对结果：

- Start、Normalize、Script、Source Select、Sentence Split、Storyboard、Validation、Repair、Finalize 全部存在。
- Prompt Context、World、Style、Storyboard Frame Plan、Article Concretization、IP Role、Context Enrichment 全部存在。
- Base Image Prompt、Base Visual Brief、Visual Anchor Integration、Final Contract、Text Policy、Provider Projection、Quality Gate、Sanitization 全部存在。
- End 输出包含 `source_text`、`storyboard_plan`、`prompt_contexts`、`content_world_profile`、`resolved_style`、`storyboard_frame_plans`、`article_concretization_plans`、`ip_role_plans`、`base_image_prompts`、`base_visual_briefs`、`visual_anchor_integration_plans`、`final_prompt_contracts`、`final_prompts`、`negative_prompt`、`trace_json`。
- 文档明确所有节点必须运行，用户未提供配置时输出默认结构。

### Review 2：提示词和 Dify 可实现性

结论：通过。

核对结果：

- 所有 Pixelle 主链路源模板均映射到 Dify 节点，且节点内包含可复制的 System Prompt 和 User Prompt。
- `script_generation.md` 的开头、推进逻辑、口播、事实、禁用词、自检约束已完整进入节点 3。
- `storyboard_generation.md` 和 `storyboard_repair.md` 的覆盖校验与修复思想已进入节点 6、7、8、9。
- `final_visual_prompt.md` 的六段式 contract 和 `final_visual_prompt_clauses.md` 的文字策略已进入节点 20、21、22。
- Dify 无法直接复用 Pixelle 代码时，文档用 Code 节点规则表达确定性逻辑，并保留 trace 输出，便于生成 YAML 后逐节点排查。
