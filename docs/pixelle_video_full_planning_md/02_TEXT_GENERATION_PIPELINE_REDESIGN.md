# 02 文本生成链路重构

## 1. 当前链路问题

当前链路大致是：

```text
用户输入主题
  ↓
generate_narrations_from_topic()
  ↓
得到 narrations 数组
  ↓
generate_image_prompts()
  ↓
得到 image_prompts 数组
  ↓
拼接 prompt_prefix
  ↓
进入图片/TTS/视频生成
```

问题：

1. 文案、旁白、图片提示词缺少中间结构。
2. 失败时难以知道是哪一次 LLM 调用出错。
3. 图片提示词只依赖 narration，不知道 IP、角色、场景和道具。
4. 缺少文案质检、修复、二次编辑。
5. 用户看不到大模型每一步返回了什么。
6. 当前链路偏“一键黑盒”，不适合做高质量视频工作台。

## 2. 推荐新链路

建议改成：

```text
用户主题
  ↓
视频策划 VideoPlan
  ↓
分镜结构 ScenePlan
  ↓
旁白生成 ScriptDraft
  ↓
旁白质检 ScriptValidation
  ↓
必要时自动修复 ScriptRepair
  ↓
视觉规划 VisualPlan
  ↓
角色/道具/场景分配 SceneCasting
  ↓
图片提示词生成 BaseImagePrompts
  ↓
IP/风格/世界观组装 FinalImagePrompts
  ↓
用户确认
  ↓
TTS / 图片 / 视频生产
```

## 3. 新数据结构

### VideoPlan

```python
class VideoPlan(BaseModel):
    plan_id: str
    topic: str
    title: str | None = None
    language: str
    target_audience: str
    tone: str
    core_message: str
    n_scenes: int
    structure: list["ScenePlan"]
```

### ScenePlan

```python
class ScenePlan(BaseModel):
    scene_id: int
    role: Literal["hook", "point", "example", "turn", "summary", "cta"]
    goal: str
    key_message: str
    visual_direction: str | None = None
    suggested_characters: list[str] = []
    suggested_assets: list[str] = []
```

### ScriptScene

```python
class ScriptScene(BaseModel):
    scene_id: int
    narration: str
    emotion: str | None = None
    pace: Literal["slow", "normal", "fast"] = "normal"
    issues: list[str] = []
    score: float | None = None
```

### VisualScene

```python
class VisualScene(BaseModel):
    scene_id: int
    visual_brief_zh: str
    base_image_prompt_en: str
    final_image_prompt_en: str | None = None
    negative_prompt_en: str | None = None
    character_ids: list[str] = []
    asset_ids: list[str] = []
    environment_id: str | None = None
```

## 4. Prompt 拆分

不要让一个 prompt 同时负责所有事情。建议拆成：

```text
video_plan_prompt
script_generation_prompt
script_validation_prompt
script_repair_prompt
visual_brief_prompt
image_prompt_generation_prompt
image_prompt_validation_prompt
```

## 5. 文案生成 Prompt 目标

### 5.1 视频策划 Prompt

职责：

- 判断目标受众
- 明确视频核心观点
- 规划几段结构
- 不生成最终旁白

输出：

```json
{
  "language": "zh-CN",
  "target_audience": "普通知识类短视频观众",
  "tone": "清晰、有启发、不过度鸡汤",
  "core_message": "...",
  "structure": [
    {
      "scene_id": 1,
      "role": "hook",
      "goal": "制造兴趣",
      "key_message": "...",
      "visual_direction": "..."
    }
  ]
}
```

### 5.2 旁白生成 Prompt

职责：

- 根据 ScenePlan 生成 TTS 友好的旁白
- 每段只表达一个核心意思
- 避免重复开头
- 避免过度抽象

输出：

```json
{
  "scenes": [
    {
      "scene_id": 1,
      "narration": "...",
      "emotion": "curious",
      "pace": "normal"
    }
  ]
}
```

### 5.3 旁白质检 Prompt

职责：

- 检查是否口语自然
- 是否过长
- 是否重复
- 是否空泛
- 是否适合 TTS
- 是否含有敏感或虚假表达

输出：

```json
{
  "passed": true,
  "overall_score": 0.86,
  "issues": [
    {
      "scene_id": 2,
      "severity": "medium",
      "issue": "表达过于抽象",
      "suggestion": "加入具体动作或画面"
    }
  ]
}
```

## 6. 文案阶段 API

建议新增：

```http
POST /api/v1/app/script-drafts
GET  /api/v1/app/script-drafts/{draft_id}
PATCH /api/v1/app/script-drafts/{draft_id}/scenes/{scene_id}
POST /api/v1/app/script-drafts/{draft_id}/validate
POST /api/v1/app/script-drafts/{draft_id}/repair
POST /api/v1/app/script-drafts/{draft_id}/generate-visual-prompts
```

## 7. 用户体验

生成视频前先展示：

| 场景 | 旁白 | 视觉摘要 | 角色 | 图片提示词 | 状态 |
|---|---|---|---|---|---|

用户可以：

```text
编辑某段旁白
重新生成某段旁白
锁定某段
重新生成图片提示词
确认进入媒体生成
```

## 8. 落地建议

第一阶段不需要完全推翻现有 StandardPipeline。可以：

1. 保留旧 `generate_narrations_from_topic()`。
2. 新增 `ScriptDraftService`。
3. 新增 `VisualPromptService`。
4. 在 StandardPipeline 中逐步替换文本阶段。
5. 增加 `text_review_mode`，允许生成到文案和视觉提示词后暂停。
