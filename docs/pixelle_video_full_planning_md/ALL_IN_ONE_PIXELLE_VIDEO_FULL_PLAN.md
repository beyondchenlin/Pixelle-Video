# Pixelle-Video 全量规划合并版




---

# 01_PROJECT_TARGET_AND_SYSTEM_BOUNDARY.md


# 01 项目目标与系统边界

## 1. 当前项目定位

Pixelle-Video 当前已经具备一个完整 AI 短视频生成系统的雏形：

```text
用户输入主题 / 文案
  ↓
LLM 生成旁白
  ↓
LLM 生成图片提示词
  ↓
TTS 生成音频
  ↓
ComfyUI / RunningHub / 本地模型生成图片或视频素材
  ↓
HTML 模板渲染帧画面
  ↓
FFmpeg 合成视频
  ↓
输出最终短视频
```

当前更像一个本地工具或本地 Web Demo，但未来目标应是：

```text
多用户
多 IP
多工作流
多机器
多 Provider
可计费
可追踪
可重生成
可对外提供 API
```

## 2. 未来目标

最终建议拆成四层产品：

### 2.1 Pixelle Core

核心生成引擎，不关心前端，也不直接关心会员系统。

职责：

- 文案生成
- 分镜生成
- 视觉提示词生成
- IP 上下文组装
- TTS
- 图片/视频生成
- 帧渲染
- 视频合成
- 产物版本管理

### 2.2 Pixelle Studio

你自己的网页端产品，可以用 Vue / Next.js / Nuxt / React 等重做。

职责：

- 用户登录
- 创建项目
- 选择 IP
- 输入主题
- 生成文案
- 编辑分镜
- 查看生成过程
- 每帧重抽卡
- 试听音频
- 合成视频
- 管理历史项目

### 2.3 Pixelle API

对外提供的开发者 API。

职责：

- API Key 调用
- 一键生成视频
- 创建 IP
- 查询任务
- 下载结果
- Webhook 回调
- 按套餐限制功能

### 2.4 Pixelle Workers

分布式执行层。

职责：

- 文案 Worker
- 提示词 Worker
- TTS Worker
- 图片 Worker
- 帧渲染 Worker
- 视频合成 Worker
- 上传 Worker
- 监控和心跳

## 3. 系统边界原则

### 原则 1：UI 不直接绑定生成逻辑

Streamlit 当前只是临时本地 UI。未来 Vue / Next.js 前端应该只调用 API，不应直接调用核心 Python 对象。

### 原则 2：FastAPI 不直接长时间生成视频

FastAPI 应主要负责：

```text
鉴权
参数校验
额度检查
创建任务
查询任务
返回结果
```

长时间任务交给 Worker。

### 原则 3：本地文件路径不能作为长期产物地址

多机器部署后，不能依赖：

```text
output/task_xxx/final.mp4
```

必须改成：

```text
object_key
url
artifact_id
```

例如使用 MinIO / S3 / R2 / OSS。

### 原则 4：所有生成产物都应版本化

图片、音频、提示词、单帧视频、最终视频都可能被重新生成，因此不能覆盖旧结果。

### 原则 5：所有对外参数都要强控制

外部 API 不能直接让用户传：

```text
workflow 文件路径
本地模板路径
任意 prompt_prefix
任意 bgm_path
```

应该改成：

```text
workflow_id
template_id
style_id
ip_id
voice_id
bgm_id
```

由后端根据套餐和权限做白名单过滤。

## 4. 推荐阶段路线

### 阶段 1：本地增强版

目标：

```text
IP 库
Prompt Composer
生成过程 Trace
帧级重抽卡
基础 API v1
```

### 阶段 2：多机器 Worker 版

目标：

```text
FastAPI + Redis + Postgres + MinIO
多机器 Worker
按队列分发任务
24G GPU 机器专职图片生成
M4 机器负责文案、提示词、合成
```

### 阶段 3：SaaS/API 版

目标：

```text
用户系统
会员系统
API Key
额度计费
资源权限
任务持久化
对象存储
Webhook
```

### 阶段 4：混合云版

目标：

```text
本地 GPU + 云 GPU
本地 TTS + 云 TTS
本地图像模型 + 在线图像服务
自动 Provider fallback
```



---

# 02_TEXT_GENERATION_PIPELINE_REDESIGN.md


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



---

# 03_IP_LIBRARY_AND_VISUAL_CONSISTENCY.md


# 03 IP 库与视觉一致性设计

## 1. 为什么需要 IP 库

当前项目依赖 `prompt_prefix` 统一风格，但它只是一个字符串前缀，无法稳定解决：

```text
主角一致
多角色一致
道具一致
世界观一致
场景连续
系列化视觉元素
```

对于 AI 短剧、AI 漫剧、知识类 IP 视频来说，必须引入 IP 库。

## 2. IP 库的定位

IP 库不只是人物库，而是一套视觉身份系统：

```text
IPProfile
  ├─ CharacterProfile
  ├─ AssetProfile
  ├─ WorldProfile
  ├─ StyleProfile
  └─ PreviewArtifacts
```

## 3. 两种 IP 模式

### 3.1 Prompt-only IP

适合当前本地 Z-Image 文生图模式。

特点：

```text
不依赖参考图
不依赖 LoRA
不依赖图生图
只通过结构化提示词约束角色
```

### 3.2 Reference-augmented IP

未来升级模式。

特点：

```text
角色预览图
多视图
参考图
LoRA
Embedding
ControlNet / IP-Adapter / 其他参考机制
```

第一阶段先做 Prompt-only IP，但数据结构要为未来 reference 模式预留字段。

## 4. 核心模型

### IPProfile

```python
class IPProfile(BaseModel):
    ip_id: str
    user_id: str
    workspace_id: str
    name: str
    description: str | None = None
    mode: Literal["prompt_only", "reference_augmented"] = "prompt_only"
    default_style_id: str | None = None
    default_world_id: str | None = None
    main_character_id: str | None = None
    character_ids: list[str] = []
    asset_ids: list[str] = []
    tags: list[str] = []
    visibility: Literal["private", "workspace", "public"] = "private"
    created_at: datetime
    updated_at: datetime
```

### CharacterProfile

```python
class CharacterProfile(BaseModel):
    character_id: str
    ip_id: str
    name: str
    role: Literal["main", "support", "npc", "villain", "narrator"]
    species: str | None = None
    visual_summary: str
    signature_traits: list[str]
    outfit_traits: list[str] = []
    fixed_colors: list[str] = []
    props: list[str] = []
    personality_visuals: list[str] = []
    must_include: list[str] = []
    must_avoid: list[str] = []
    style_override: str | None = None
    reference_images: list[str] = []
```

### AssetProfile

```python
class AssetProfile(BaseModel):
    asset_id: str
    ip_id: str
    name: str
    type: Literal["prop", "symbol", "vehicle", "weapon", "book", "background_item"]
    visual_summary: str
    must_include: list[str] = []
    must_avoid: list[str] = []
    reference_images: list[str] = []
```

### WorldProfile

```python
class WorldProfile(BaseModel):
    world_id: str
    ip_id: str
    name: str
    description: str
    visual_rules: list[str]
    environment_defaults: list[str]
    common_props: list[str]
    forbidden_elements: list[str]
```

### StyleProfile

```python
class StyleProfile(BaseModel):
    style_id: str
    name: str
    prompt_prefix: str
    prompt_suffix: str = ""
    negative_prompt: str = ""
    consistency_rules: list[str] = []
```

## 5. 示例：植物老师 IP

```json
{
  "ip_id": "plant_teacher_universe",
  "name": "植物老师宇宙",
  "mode": "prompt_only",
  "default_style_id": "simple_cartoon",
  "default_world_id": "plant_school_world",
  "main_character_id": "plant_teacher"
}
```

主角：

```json
{
  "character_id": "plant_teacher",
  "name": "植物老师",
  "role": "main",
  "visual_summary": "cute anthropomorphic green plant teacher with round eyes and a red necktie",
  "signature_traits": [
    "green leaf-shaped head",
    "round expressive eyes",
    "red necktie",
    "simple cartoon face"
  ],
  "outfit_traits": [
    "white shirt",
    "red tie"
  ],
  "must_avoid": [
    "photorealistic human face",
    "horror style",
    "overly complex armor"
  ]
}
```

## 6. IP 库 API

```http
POST /api/v1/app/ip-profiles
GET  /api/v1/app/ip-profiles
GET  /api/v1/app/ip-profiles/{ip_id}
PATCH /api/v1/app/ip-profiles/{ip_id}
DELETE /api/v1/app/ip-profiles/{ip_id}
```

角色：

```http
POST /api/v1/app/ip-profiles/{ip_id}/characters
GET  /api/v1/app/ip-profiles/{ip_id}/characters
PATCH /api/v1/app/ip-profiles/{ip_id}/characters/{character_id}
DELETE /api/v1/app/ip-profiles/{ip_id}/characters/{character_id}
```

预览：

```http
POST /api/v1/app/ip-profiles/{ip_id}/preview
GET  /api/v1/app/ip-profiles/{ip_id}/preview-jobs/{job_id}
```

## 7. 前端功能

新增页面：

```text
IP 库
角色库
道具库
世界观库
风格预设
IP 预览
```

生成页新增：

```text
选择 IP
选择主角
选择配角策略
选择风格：IP 默认 / 手动覆盖
选择是否保持场景连续
```

## 8. 版权与产品建议

对于已有知名 IP，例如植物大战僵尸、愤怒的小鸟，不建议直接做官方角色复刻。

建议做：

```text
塔防植物灵感风
弹射小鸟灵感风
卡通植物学院
搞笑怪物教室
```

以“灵感风格 + 原创角色”方式降低风险。



---

# 04_PROMPT_COMPOSER_AND_SCENE_CASTING.md


# 04 Prompt Composer 与 Scene Casting

## 1. 当前问题

当前系统大致是：

```text
narration
  ↓
base image prompt
  ↓
prompt_prefix + base prompt
  ↓
final image prompt
```

这无法保证：

```text
主角固定
配角正确出现
道具稳定
场景连续
世界观统一
不同主题复用同一 IP
```

## 2. 目标结构

新增 Prompt Composer：

```text
base image prompt
+ style profile
+ world profile
+ character profiles
+ asset profiles
+ scene cast
+ continuity memory
= final image prompt
```

## 3. Scene Casting

Scene Casting 负责判断每一帧：

```text
谁出场
在哪个场景
需要哪些道具
是否延续上一帧
镜头类型是什么
```

### SceneCast 模型

```python
class SceneCast(BaseModel):
    frame_index: int
    scene_goal: str
    character_ids: list[str]
    asset_ids: list[str] = []
    environment_id: str | None = None
    shot_type: str | None = None
    continuity_from_previous: bool = True
    notes: str | None = None
```

## 4. Prompt Composer 输入

```python
class PromptComposeInput(BaseModel):
    base_prompt: str
    narration: str
    ip_profile: IPProfile | None = None
    style_profile: StyleProfile | None = None
    world_profile: WorldProfile | None = None
    characters: list[CharacterProfile] = []
    assets: list[AssetProfile] = []
    scene_cast: SceneCast | None = None
    continuity_memory: dict | None = None
```

## 5. Prompt Composer 输出

```python
class PromptComposeResult(BaseModel):
    final_prompt: str
    negative_prompt: str | None = None
    debug_parts: dict
```

`debug_parts` 用于前端展示和排查：

```json
{
  "style_block": "...",
  "world_block": "...",
  "character_block": "...",
  "asset_block": "...",
  "scene_block": "...",
  "continuity_block": "...",
  "final_prompt": "..."
}
```

## 6. Prompt 拼接顺序

建议顺序：

```text
1. Style Block
2. World Block
3. Main Character Block
4. Supporting Character Block
5. Asset Block
6. Scene Action Block
7. Camera / Composition Block
8. Continuity Block
9. Negative Constraints
```

## 7. 示例最终 Prompt

```text
simple clean cartoon line art, flat colors, clear readable composition,
in a playful plant-school universe with simplified game-like backgrounds,
main character: cute anthropomorphic green plant teacher, leaf-shaped head, round expressive eyes, white shirt, red necktie, calm teacher expression,
supporting character: small confused zombie student sitting at a desk,
the plant teacher stands beside a chalkboard explaining how to read Mao's selected works, holding a red book,
medium shot, educational classroom composition, warm daylight,
keep the same protagonist design, same red necktie, same leaf-shaped head, consistent cartoon face,
no photorealism, no realistic human face, no horror style
```

## 8. 文件建议

新增：

```text
pixelle_video/services/prompt_composer.py
pixelle_video/services/scene_casting.py
pixelle_video/models/ip_profile.py
pixelle_video/models/scene_cast.py
```

## 9. Pipeline 接入点

当前：

```text
generate_image_prompts()
  ↓
build_image_prompt(base_prompt, prompt_prefix)
```

建议改成：

```text
generate_base_image_prompts()
  ↓
resolve_ip_context()
  ↓
scene_casting()
  ↓
prompt_composer.compose()
  ↓
ctx.image_prompts = final_prompts
```

## 10. 前端展示

每一帧展示：

```text
旁白
场景目的
出场角色
道具
base prompt
final prompt
negative prompt
当前图片
重抽卡按钮
```

## 11. 注意事项

对于文生图模型，角色一致性不能 100% 保证。Prompt Composer 的目标是：

```text
显著提升一致性
提供可调试结构
为未来 reference 模式预留接口
```



---

# 05_GENERATION_TRACE_AND_LOGGING.md


# 05 生成过程 Trace 与日志系统

## 1. 当前问题

当前系统主要依赖普通 logger 和任务状态，用户难以知道：

```text
哪一步失败
大模型 prompt 是什么
原始 response 是什么
JSON 解析哪里失败
第几帧出错
第几次 retry 成功
最终 prompt 为什么这样拼
```

这对产品化和调试都不够。

## 2. 目标

新增 Generation Trace 系统，使整个生成过程像“大模型对话流 + 工程日志”一样可视化。

前端可以展示：

```text
用户输入主题
系统生成视频策划
LLM 返回文案
质检发现问题
自动修复
生成图片提示词
组装 IP prompt
生成图片
重抽卡
合成视频
```

## 3. GenerationEvent 模型

```python
class GenerationEvent(BaseModel):
    event_id: str
    task_id: str
    project_id: str | None = None
    storyboard_id: str | None = None
    frame_id: str | None = None
    timestamp: datetime
    stage: str
    role: Literal["user", "system", "llm", "validator", "worker", "tool", "error"]
    title: str
    content: str | dict
    status: Literal["started", "success", "warning", "failed", "retrying"]
    attempt: int = 1
    raw_prompt_object_key: str | None = None
    raw_response_object_key: str | None = None
    error_message: str | None = None
    debug: dict = {}
```

## 4. Trace 文件结构

本地 MVP 可以先落盘：

```text
output/{task_id}/trace/
  events.jsonl
  001_video_plan_prompt.txt
  001_video_plan_response.json
  002_script_prompt.txt
  002_script_response.json
  003_script_validation.json
  004_image_prompt_prompt.txt
  004_image_prompt_response.json
  005_prompt_composer_debug.json
```

SaaS 阶段转成：

```text
PostgreSQL: generation_events
Object Storage: raw prompt / raw response / debug payload
```

## 5. API

```http
GET /api/v1/app/jobs/{job_id}/events
GET /api/v1/app/jobs/{job_id}/trace
GET /api/v1/app/storyboards/{storyboard_id}/frames/{frame_id}/trace
```

实时流：

```http
GET /api/v1/app/jobs/{job_id}/events/stream
```

第一阶段可用轮询，后面再加 SSE / WebSocket。

## 6. 前端显示方式

推荐分三层：

### 6.1 普通用户视图

```text
正在生成文案
正在生成第 3 张图片
正在合成视频
```

### 6.2 高级用户视图

```text
每段旁白
每帧图片提示词
角色与道具分配
重抽卡历史
```

### 6.3 管理员 Debug 视图

```text
raw prompt
raw response
workflow payload
error stack
worker id
provider latency
token usage
```

## 7. Trace 与权限

不要默认对外暴露所有 prompt 和 workflow。  
这些可能是商业资产。

建议：

```text
Free: 只看进度
Pro: 看 storyboard 和 final prompt
Admin: 看 raw prompt / raw response / stacktrace
API 客户: 可选 debug=false/true，根据套餐开放
```

## 8. Codex 实现建议

新增：

```text
pixelle_video/services/generation_trace.py
pixelle_video/models/generation_event.py
api/routers/generation_trace.py
web/components/generation_trace.py
```

服务方法：

```python
record_event()
record_llm_call()
record_validation()
record_retry()
record_worker_event()
load_events()
```

## 9. 和任务系统结合

每个任务阶段都记录：

```text
stage started
LLM prompt sent
LLM response received
validation result
retry reason
stage completed
stage failed
```

这样失败时前端可以精确提示：

```text
图片提示词第 2 批 JSON 解析失败，已重试 2 次，最终失败。
```



---

# 06_API_FIRST_SAAS_ARCHITECTURE.md


# 06 API-first SaaS 架构

## 1. 为什么要 API-first

未来会有：

```text
Vue / Next.js 前端
管理后台
第三方开发者 API
会员系统
批量生成
企业客户
移动端
```

所以不能把能力写死在 Streamlit 或本地脚本里。

核心原则：

```text
所有能力先 service 化
所有 service 再 API 化
UI 只是 API 客户端
```

## 2. API 分层

建议分四类：

```text
/api/v1/public/*
/api/v1/app/*
/api/v1/admin/*
/api/v1/internal/*
```

### 2.1 Public API

给第三方开发者或普通 API 客户。

特点：

```text
参数少
强控制
稳定
不暴露内部 workflow
按 API Key 计费
```

### 2.2 App API

给你自己的 Web 产品前端。

特点：

```text
功能完整
支持编辑
支持分镜
支持 trace
支持重抽卡
```

### 2.3 Admin API

给后台。

特点：

```text
用户管理
套餐管理
任务监控
成本统计
Worker 状态
Provider 状态
```

### 2.4 Internal API

给 Worker 和内部服务。

特点：

```text
心跳
任务领取
任务状态上报
artifact 上传回调
```

## 3. 对外一键生成 API

```http
POST /api/v1/public/videos/generate
```

请求：

```json
{
  "topic": "如何读懂毛选",
  "ip_id": "plant_teacher_universe",
  "style": "ip_default",
  "duration_level": "short",
  "bgm": true
}
```

返回：

```json
{
  "job_id": "job_xxx",
  "status": "queued",
  "estimated_credit_cost": 8
}
```

查询：

```http
GET /api/v1/public/jobs/{job_id}
```

返回：

```json
{
  "job_id": "job_xxx",
  "status": "completed",
  "video_url": "https://...",
  "thumbnail_url": "https://...",
  "duration": 42.5,
  "credit_cost": 8
}
```

## 4. App API

### 项目

```http
POST /api/v1/app/projects
GET  /api/v1/app/projects
GET  /api/v1/app/projects/{project_id}
DELETE /api/v1/app/projects/{project_id}
```

### 文案草稿

```http
POST /api/v1/app/script-drafts
GET  /api/v1/app/script-drafts/{draft_id}
PATCH /api/v1/app/script-drafts/{draft_id}/scenes/{scene_id}
POST /api/v1/app/script-drafts/{draft_id}/validate
```

### Storyboard

```http
POST /api/v1/app/storyboards
GET  /api/v1/app/storyboards/{storyboard_id}
PATCH /api/v1/app/storyboards/{storyboard_id}/frames/{frame_id}
```

### 帧级重生成

```http
POST /api/v1/app/storyboards/{storyboard_id}/frames/{frame_id}/regenerate-image-prompt
POST /api/v1/app/storyboards/{storyboard_id}/frames/{frame_id}/regenerate-image
POST /api/v1/app/storyboards/{storyboard_id}/frames/{frame_id}/regenerate-audio
POST /api/v1/app/storyboards/{storyboard_id}/frames/{frame_id}/render-segment
POST /api/v1/app/storyboards/{storyboard_id}/render-final
```

## 5. 强控制参数原则

外部用户不应直接传：

```text
media_workflow
tts_workflow
frame_template
prompt_prefix
本地 bgm_path
本地文件路径
```

应改成：

```text
workflow_id
template_id
style_id
voice_id
bgm_id
ip_id
```

后端负责：

```text
根据用户套餐过滤可用资源
根据 workflow_id 映射真实 workflow
根据 template_id 映射真实模板
根据 style_id 映射 prompt prefix
```

## 6. FastAPI 依赖设计

建议新增依赖：

```python
CurrentUserDep
CurrentWorkspaceDep
RequirePermissionDep
RequirePlanDep
QuotaDep
RateLimitDep
UsageRecorderDep
```

示例：

```python
@router.post("/videos")
async def create_video(
    request: VideoCreateRequest,
    user: CurrentUserDep,
    workspace: CurrentWorkspaceDep,
    permission = Depends(require_permission("video.generate")),
):
    ...
```

## 7. API 版本化

从一开始使用：

```text
/api/v1
```

未来 breaking change 时新增：

```text
/api/v2
```

## 8. SDK 预留

未来可以做：

```text
Python SDK
JavaScript SDK
Webhook
OpenAPI 文档
```

API 请求尽量保持：

```text
资源 ID 化
异步任务化
状态可查询
结果 URL 化
错误码标准化
```

## 9. 错误码建议

```text
AUTH_REQUIRED
PERMISSION_DENIED
QUOTA_EXCEEDED
PLAN_REQUIRED
RESOURCE_NOT_AVAILABLE
INVALID_IP_PROFILE
JOB_NOT_FOUND
WORKER_UNAVAILABLE
PROVIDER_ERROR
GENERATION_FAILED
```



---

# 07_AUTH_PERMISSION_BILLING_AND_RESOURCE_POLICY.md


# 07 用户、权限、计费与资源策略

## 1. 为什么要提前设计

未来商业化需要：

```text
用户登录
工作区
会员套餐
API Key
生成额度
重抽卡扣费
资源白名单
并发限制
水印控制
存储期限
```

这些必须由后端控制，不能只靠前端隐藏按钮。

## 2. 用户与工作区

建议支持：

```text
User
Workspace
WorkspaceMember
APIKey
Subscription
UsageLedger
```

### User

```python
class User(BaseModel):
    user_id: str
    email: str
    name: str | None
    status: Literal["active", "disabled"]
```

### Workspace

```python
class Workspace(BaseModel):
    workspace_id: str
    owner_user_id: str
    name: str
    plan_id: str
```

## 3. 套餐策略

### Free

```text
每天 3 次
最多 5 个分镜
默认 IP
带水印
低优先级队列
不能调用 Public API
不能自定义 workflow
```

### Basic

```text
每天 30 次
最多 8 个分镜
允许创建 3 个 IP
允许基础 BGM
720p
普通队列
```

### Pro

```text
每天 300 次
最多 20 个分镜
允许创建 50 个 IP
无水印
允许 API Key
高级模板
高优先级队列
```

### Enterprise

```text
独立队列
自定义 workflow
团队空间
专属模型
Webhook
白标
更长存储
```

## 4. 权限点

```text
video.generate
video.batch_generate
video.no_watermark
video.high_resolution
video.priority_queue

ip.create
ip.max_count
ip.reference_mode

frame.regenerate_image
frame.regenerate_audio
frame.edit_prompt

api.public_access
api.webhook
api.debug_trace

workflow.custom
template.premium
provider.cloud
```

## 5. 额度和扣费

### 完整视频

```text
基础文案生成：1 credit
每张图片：1 credit
每段 TTS：0.5 credit
最终合成：1 credit
高级模型倍率：x2/x3
```

### 重抽卡

```text
重新生成一张图片：1 credit
重新生成一段音频：0.5 credit
重新生成最终视频：1 credit
重新生成文案：1 credit
```

## 6. 资源白名单

资源不要直接用本地路径暴露。

建议资源表：

```text
resource_presets
workflow_presets
template_presets
bgm_assets
voice_presets
style_presets
```

每个资源有：

```text
resource_id
resource_type
display_name
internal_path
required_plan
enabled
cost_multiplier
```

## 7. PlanPolicy

新增服务：

```text
pixelle_video/services/plan_policy.py
```

职责：

```python
validate_video_request()
validate_ip_create()
validate_regenerate_request()
resolve_allowed_resources()
estimate_credit_cost()
reserve_credits()
commit_usage()
refund_on_failure()
```

## 8. 并发限制

按套餐限制：

```text
Free: 同时 1 个任务
Basic: 同时 2 个任务
Pro: 同时 5 个任务
Enterprise: 自定义
```

按资源限制：

```text
image.high 队列只有 Pro 以上可用
cloud_provider 只有 Pro / Enterprise 可用
custom workflow 只有 Enterprise 可用
```

## 9. 水印策略

不要在前端决定是否加水印。  
后端根据套餐在合成阶段决定：

```text
Free: 强制水印
Basic: 可付费去水印
Pro: 默认无水印
Enterprise: 白标
```

## 10. Debug Trace 策略

```text
Free: 无 raw prompt
Basic: 可看最终 storyboard
Pro: 可看 final prompt
Admin: 可看 raw prompt 和 raw response
API: 根据 debug 权限
```

## 11. 计费安全

必须支持：

```text
预估 cost
预扣 credits
成功后结算
失败后按实际消耗扣费或退款
防止重复扣费
幂等 key
```



---

# 08_DISTRIBUTED_DEPLOYMENT_AND_WORKERS.md


# 08 分布式部署与 Worker 架构

## 1. 当前硬件条件

当前本地资源：

```text
4 台 Apple M4 小主机
2 台 Windows 主机：
  - NVIDIA 16G 显存 / 64G 内存
  - NVIDIA 24G 显存 / 32G 内存
```

目标：

```text
多机协同
局域网部署
不同机器按能力执行不同任务
用户少时单机即可
用户多时多机并发
未来可扩展到云端
```

## 2. 不建议一开始上 K8S

当前更适合：

```text
Docker Compose 多机部署
中央 Redis/RabbitMQ
中央 PostgreSQL
中央 MinIO
多类型 Worker
```

K8S / k3s 适合未来阶段：

```text
需要自动扩缩容
多副本 API
节点故障迁移
云端 GPU
统一滚动升级
```

## 3. 推荐第一阶段架构

```text
FastAPI API 节点
  ↓
Redis / RabbitMQ 队列
  ↓
不同 Worker 消费不同队列
  ↓
PostgreSQL 保存元数据
  ↓
MinIO 保存图片/音频/视频/trace
```

## 4. 机器分工

### M4-1：控制节点

运行：

```text
FastAPI
PostgreSQL
Redis / RabbitMQ
MinIO
管理后台
调度器
```

### M4-2 / M4-3 / M4-4：轻任务节点

运行：

```text
script-worker
prompt-worker
scene-cast-worker
trace-worker
frame-render-worker
compose-worker
tts-worker-lite
```

适合：

```text
文案生成
图片提示词生成
IP prompt 组装
HTML 渲染
FFmpeg 合成
BGM 混音
封面生成
```

### Windows 24G：主图像生成节点

运行：

```text
ComfyUI / Z-Image
image-worker-high
image-regenerate-worker
```

适合：

```text
高质量图片生成
批量图片抽卡
高优先级图像任务
未来视频模型
```

### Windows 16G：副图像/TTS节点

运行：

```text
image-worker-fast
image-worker-preview
tts-worker
backup-compose-worker
```

适合：

```text
预览图
低优先级图片
TTS
备用任务
```

## 5. 队列拆分

建议队列：

```text
queue.script
queue.prompt
queue.scene_cast
queue.tts
queue.image.fast
queue.image.high
queue.image.regenerate
queue.frame_render
queue.compose
queue.upload
queue.review
```

## 6. Worker 环境变量

### M4 文案节点

```env
NODE_NAME=m4-text-01
ENABLE_WORKER=true
WORKER_QUEUES=script,prompt,scene_cast,trace
WORKER_CONCURRENCY=8
```

### M4 合成节点

```env
NODE_NAME=m4-compose-01
ENABLE_WORKER=true
WORKER_QUEUES=frame_render,compose,upload
WORKER_CONCURRENCY=3
```

### Windows 24G

```env
NODE_NAME=win-gpu-24g
ENABLE_WORKER=true
ENABLE_COMFYUI=true
WORKER_QUEUES=image.high,image.regenerate
WORKER_CONCURRENCY=1
IMAGE_PROVIDER=local_comfyui
COMFYUI_URL=http://127.0.0.1:8188
GPU_VRAM_GB=24
```

### Windows 16G

```env
NODE_NAME=win-gpu-16g
ENABLE_WORKER=true
ENABLE_COMFYUI=true
WORKER_QUEUES=image.fast,image.preview,tts
WORKER_CONCURRENCY=1
IMAGE_PROVIDER=local_comfyui
GPU_VRAM_GB=16
```

## 7. Docker Compose Profiles

同一套代码镜像，通过 profile 启动不同角色：

```yaml
services:
  api:
    image: pixelle-video:latest
    profiles: ["api"]
    command: ["python", "-m", "api.app"]

  worker:
    image: pixelle-video:latest
    profiles: ["worker"]
    command: ["python", "-m", "pixelle_video.workers.worker_app"]
    environment:
      WORKER_QUEUES: "${WORKER_QUEUES}"
      WORKER_CONCURRENCY: "${WORKER_CONCURRENCY}"

  postgres:
    image: postgres:16
    profiles: ["control"]

  redis:
    image: redis:7
    profiles: ["control"]

  minio:
    image: minio/minio
    profiles: ["control"]
```

## 8. Worker Registry

每个 Worker 启动后向中心注册：

```json
{
  "node_id": "win-gpu-24g",
  "status": "online",
  "capabilities": {
    "image_generation": true,
    "tts": false,
    "frame_render": false,
    "gpu": {
      "vendor": "nvidia",
      "vram_gb": 24
    },
    "providers": ["local_zimage", "comfyui"]
  },
  "queues": ["image.high", "image.regenerate"],
  "max_concurrency": {
    "image": 1
  },
  "last_heartbeat": "..."
}
```

API：

```http
GET /api/v1/admin/workers
GET /api/v1/admin/workers/{node_id}
POST /api/v1/internal/workers/heartbeat
```

## 9. 并发建议

图像生成不要盲目高并发：

```text
24G GPU: IMAGE_CONCURRENCY=1 起步，测试稳定后可尝试 2
16G GPU: IMAGE_CONCURRENCY=1
M4 文案/提示词: 6-10 并发
M4 合成: 2-3 并发
```

## 10. 任务超时

```text
文案生成：60s
图片提示词：60s
TTS：180s
图片生成：300s
视频合成：600s
上传：180s
```

## 11. 失败重试

```text
文案/prompt：最多 3 次
TTS：最多 2 次
图片生成：最多 2 次
视频合成：最多 1 次
```

## 12. 本地到云端演进

### 阶段 1

```text
局域网多机
Docker Compose
Redis
PostgreSQL
MinIO
```

### 阶段 2

```text
Worker Registry
资源监控
自动 fallback
```

### 阶段 3

```text
k3s / K8S
GPU 节点标签
云 GPU
对象存储上云
```

### 阶段 4

```text
混合云调度
本地低成本产能
云端高峰兜底
```



---

# 09_ARTIFACT_VERSIONING_AND_REGENERATION.md


# 09 产物版本化与二次生成

## 1. 为什么要版本化

AI 生成图片天然存在抽卡问题。用户需要：

```text
重新生成某张图片
编辑某张图片提示词后重生成
重新生成某段音频
重新生成某段旁白
重新渲染某帧
重新合成最终视频
```

因此不能覆盖旧产物，必须支持版本。

## 2. 项目结构

```text
Project
  ↓
ScriptDraft
  ↓
Storyboard
  ↓
StoryboardFrame
  ↓
ArtifactVersion
```

## 3. Frame 数据结构

```python
class StoryboardFrame(BaseModel):
    frame_id: str
    storyboard_id: str
    index: int
    narration: str
    scene_goal: str | None = None

    base_image_prompt: str | None = None
    final_image_prompt: str | None = None
    negative_prompt: str | None = None

    selected_image_version_id: str | None = None
    selected_audio_version_id: str | None = None
    selected_segment_version_id: str | None = None

    ip_id: str | None = None
    character_ids: list[str] = []
    asset_ids: list[str] = []
    environment_id: str | None = None
    style_id: str | None = None
```

## 4. ArtifactVersion

```python
class ArtifactVersion(BaseModel):
    artifact_id: str
    project_id: str
    storyboard_id: str | None
    frame_id: str | None
    artifact_type: Literal[
        "script",
        "image_prompt",
        "image",
        "audio",
        "frame_segment",
        "final_video",
        "thumbnail",
        "trace"
    ]
    version: int
    status: Literal["pending", "running", "candidate", "selected", "rejected", "failed"]
    provider: str | None = None
    prompt: str | None = None
    seed: int | None = None
    object_key: str | None = None
    url: str | None = None
    metadata: dict = {}
    created_at: datetime
```

## 5. 图片重抽卡

用户点击“重新生成图片”：

```text
保留原图
创建新的 image artifact version
提交 image.regenerate 队列
生成完成后状态 candidate
用户选择其中一个 selected
```

不要覆盖旧图。

## 6. 依赖关系

### 改文案

影响：

```text
narration
image prompt
TTS
image
frame segment
final video
```

### 改图片提示词

影响：

```text
image
frame segment
final video
```

### 重新生成图片

影响：

```text
image
frame segment
final video
```

不影响：

```text
narration
audio
其他帧
```

### 重新生成音频

影响：

```text
audio
frame segment
final video
```

### 重新生成 BGM

影响：

```text
final video
```

## 7. API

### 图片提示词

```http
PATCH /api/v1/app/storyboards/{storyboard_id}/frames/{frame_id}/prompt
POST  /api/v1/app/storyboards/{storyboard_id}/frames/{frame_id}/regenerate-image-prompt
```

### 图片

```http
POST /api/v1/app/storyboards/{storyboard_id}/frames/{frame_id}/regenerate-image
GET  /api/v1/app/storyboards/{storyboard_id}/frames/{frame_id}/image-versions
POST /api/v1/app/storyboards/{storyboard_id}/frames/{frame_id}/image-versions/{version_id}/select
```

### 音频

```http
POST /api/v1/app/storyboards/{storyboard_id}/frames/{frame_id}/regenerate-audio
GET  /api/v1/app/storyboards/{storyboard_id}/frames/{frame_id}/audio-versions
POST /api/v1/app/storyboards/{storyboard_id}/frames/{frame_id}/audio-versions/{version_id}/select
```

### 渲染

```http
POST /api/v1/app/storyboards/{storyboard_id}/frames/{frame_id}/render-segment
POST /api/v1/app/storyboards/{storyboard_id}/render-final
```

## 8. 前端交互

每一帧展示：

```text
旁白
音频试听
图片提示词
当前图片
候选图片历史
重新抽卡
选择该图
重新生成音频
重新渲染本帧
重新合成最终视频
```

## 9. 计费

重抽卡应计费：

```text
重新生成图片：1 credit
重新生成音频：0.5 credit
重新渲染单帧：0.2 credit
重新合成最终视频：1 credit
```

管理员可配置不扣费。

## 10. 实现建议

新增：

```text
pixelle_video/models/artifact.py
pixelle_video/services/artifact_service.py
pixelle_video/services/regeneration_service.py
api/routers/artifacts.py
api/routers/frame_regeneration.py
```

核心方法：

```python
create_artifact_version()
select_artifact_version()
mark_artifact_failed()
list_frame_versions()
resolve_selected_artifacts()
compute_downstream_invalidations()
```



---

# 10_PROVIDER_ABSTRACTION_LOCAL_AND_CLOUD.md


# 10 Provider 抽象：本地与云端混合

## 1. 背景

当前文本类多使用在线大模型，图片/TTS/合成偏本地。未来可能出现：

```text
本地 Z-Image
ComfyUI
RunningHub
云图像 API
云 TTS API
本地 TTS
云视频模型
```

所以需要 Provider 抽象。

## 2. Provider 总体类型

```text
TextProvider
ImageProvider
TTSProvider
VideoProvider
BGMProvider
RenderProvider
StorageProvider
```

## 3. ImageProvider

```python
class ImageGenerateRequest(BaseModel):
    prompt: str
    negative_prompt: str | None = None
    width: int
    height: int
    seed: int | None = None
    workflow_id: str | None = None
    style_id: str | None = None
    metadata: dict = {}

class ImageGenerateResult(BaseModel):
    artifact_id: str
    object_key: str
    url: str
    seed: int | None = None
    provider: str
    metadata: dict = {}
```

接口：

```python
class ImageProvider(Protocol):
    provider_id: str

    async def generate(self, request: ImageGenerateRequest) -> ImageGenerateResult:
        ...
```

实现：

```text
LocalComfyUIImageProvider
ZImageLocalProvider
RunningHubImageProvider
CloudImageAPIProvider
```

## 4. TTSProvider

```python
class TTSRequest(BaseModel):
    text: str
    voice_id: str
    speed: float | None = None
    emotion: str | None = None
    metadata: dict = {}

class TTSResult(BaseModel):
    artifact_id: str
    object_key: str
    url: str
    duration: float
    provider: str
```

实现：

```text
EdgeTTSProvider
LocalTTSProvider
ComfyUITTSProvider
CloudTTSProvider
```

## 5. Provider 选择策略

新增：

```text
ProviderRouter
```

职责：

```python
select_image_provider(user, request, job_context)
select_tts_provider(user, request, job_context)
fallback_provider_on_failure()
```

选择依据：

```text
用户套餐
当前队列长度
GPU 是否忙
任务优先级
成本
质量要求
是否允许云端
```

## 6. 示例策略

```text
Free 用户：
  image.fast -> Windows 16G 本地低优先级

Pro 用户：
  image.high -> Windows 24G 本地高优先级

Enterprise：
  cloud image provider 或专用队列

GPU 忙：
  如果用户套餐允许，则 fallback 到 cloud provider
```

## 7. Provider Registry

```python
class ProviderInfo(BaseModel):
    provider_id: str
    provider_type: Literal["text", "image", "tts", "video"]
    display_name: str
    enabled: bool
    local: bool
    required_plan: str | None = None
    cost_multiplier: float = 1.0
    capabilities: dict = {}
```

## 8. API

管理员：

```http
GET /api/v1/admin/providers
PATCH /api/v1/admin/providers/{provider_id}
```

内部：

```http
GET /api/v1/internal/providers/available
```

用户资源：

```http
GET /api/v1/app/resources/providers
```

返回时根据用户权限过滤。

## 9. 本地 ComfyUI 节点

每个 GPU 节点可以暴露：

```text
COMFYUI_URL=http://win-gpu-24g:8188
PROVIDER_ID=local_zimage_24g
```

Worker 从队列取 image 任务后，调用本地 ComfyUI，再上传结果到对象存储。

## 10. 未来扩展

以后接云端时，不改 pipeline，只新增 provider：

```text
CloudImageAPIProvider
```

然后在 provider router 里选择即可。



---

# 11_DATABASE_QUEUE_STORAGE_SCHEMA.md


# 11 数据库、队列与对象存储设计

## 1. 数据库选择

建议：

```text
PostgreSQL：主数据库
Redis/RabbitMQ：任务队列和状态缓存
MinIO：本地对象存储
```

未来上云：

```text
PostgreSQL 云数据库
Redis 云服务
S3 / R2 / OSS 对象存储
```

## 2. 核心表

### 用户与权限

```text
users
workspaces
workspace_members
plans
subscriptions
api_keys
usage_ledger
credit_transactions
```

### IP 与资源

```text
ip_profiles
ip_characters
ip_assets
ip_worlds
style_presets
resource_presets
workflow_presets
template_presets
bgm_assets
voice_presets
```

### 项目与分镜

```text
projects
script_drafts
script_scenes
storyboards
storyboard_frames
artifact_versions
generation_jobs
generation_events
```

### Worker

```text
worker_nodes
worker_heartbeats
provider_status
queue_snapshots
```

## 3. projects

```sql
CREATE TABLE projects (
    project_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    title TEXT,
    status TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
```

## 4. storyboards

```sql
CREATE TABLE storyboards (
    storyboard_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    title TEXT,
    status TEXT NOT NULL,
    ip_id TEXT,
    style_id TEXT,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
```

## 5. storyboard_frames

```sql
CREATE TABLE storyboard_frames (
    frame_id TEXT PRIMARY KEY,
    storyboard_id TEXT NOT NULL,
    frame_index INT NOT NULL,
    narration TEXT,
    scene_goal TEXT,
    base_image_prompt TEXT,
    final_image_prompt TEXT,
    negative_prompt TEXT,
    selected_image_version_id TEXT,
    selected_audio_version_id TEXT,
    selected_segment_version_id TEXT,
    ip_id TEXT,
    style_id TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
```

## 6. artifact_versions

```sql
CREATE TABLE artifact_versions (
    artifact_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    storyboard_id TEXT,
    frame_id TEXT,
    artifact_type TEXT NOT NULL,
    version INT NOT NULL,
    status TEXT NOT NULL,
    provider TEXT,
    prompt TEXT,
    seed BIGINT,
    object_key TEXT,
    url TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP NOT NULL
);
```

## 7. generation_jobs

```sql
CREATE TABLE generation_jobs (
    job_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    project_id TEXT,
    storyboard_id TEXT,
    frame_id TEXT,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL,
    priority INT DEFAULT 0,
    queue_name TEXT,
    estimated_credit_cost NUMERIC,
    actual_credit_cost NUMERIC,
    error_message TEXT,
    created_at TIMESTAMP NOT NULL,
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);
```

## 8. generation_events

```sql
CREATE TABLE generation_events (
    event_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    project_id TEXT,
    storyboard_id TEXT,
    frame_id TEXT,
    stage TEXT NOT NULL,
    role TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    content JSONB,
    raw_prompt_object_key TEXT,
    raw_response_object_key TEXT,
    error_message TEXT,
    created_at TIMESTAMP NOT NULL
);
```

## 9. worker_nodes

```sql
CREATE TABLE worker_nodes (
    node_id TEXT PRIMARY KEY,
    host TEXT,
    status TEXT NOT NULL,
    capabilities JSONB DEFAULT '{}',
    queues JSONB DEFAULT '[]',
    last_heartbeat TIMESTAMP,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
```

## 10. 对象存储结构

```text
workspaces/{workspace_id}/
  projects/{project_id}/
    scripts/
    storyboards/
    frames/
      frame_001/
        prompts/
        images/
        audio/
        segments/
      frame_002/
        ...
    final/
      final_v1.mp4
      final_v2.mp4
    thumbnails/
    traces/
```

## 11. 队列消息结构

```json
{
  "job_id": "job_xxx",
  "job_type": "regenerate_image",
  "workspace_id": "ws_xxx",
  "project_id": "proj_xxx",
  "storyboard_id": "sb_xxx",
  "frame_id": "frame_001",
  "artifact_id": "art_xxx",
  "priority": 10,
  "payload": {
    "provider_id": "local_zimage_24g",
    "prompt": "...",
    "width": 1080,
    "height": 1920,
    "seed": 123
  },
  "idempotency_key": "..."
}
```

## 12. 幂等设计

每个任务都要有：

```text
job_id
artifact_id
idempotency_key
```

避免：

```text
Worker 重启后重复扣费
重复生成多个无主文件
重复上传
重复改 selected version
```

## 13. MVP 过渡方案

第一阶段可以先：

```text
PostgreSQL 暂缓
用 SQLite / JSON 文件
Redis 队列
MinIO 对象存储
```

但数据结构按上面设计，后面迁移数据库更容易。



---

# 12_MVP_IMPLEMENTATION_PLAN_FOR_CODEX.md


# 12 MVP 实施计划：给 Codex 的开发任务拆分

## 1. 第一阶段目标

不要一次性做完整 SaaS。第一阶段目标：

```text
本地增强版
支持 IP 库
支持 Prompt Composer
支持生成过程 Trace
支持帧级重抽卡
支持基础 API v1
为多机器 Worker 预留结构
```

## 2. 任务 1：新增模型

新增文件：

```text
pixelle_video/models/ip_profile.py
pixelle_video/models/scene_cast.py
pixelle_video/models/generation_event.py
pixelle_video/models/artifact.py
pixelle_video/models/script_plan.py
```

实现：

```text
IPProfile
CharacterProfile
AssetProfile
WorldProfile
StyleProfile
SceneCast
GenerationEvent
ArtifactVersion
VideoPlan
ScenePlan
ScriptScene
VisualScene
```

## 3. 任务 2：新增 IP Library Service

新增：

```text
pixelle_video/services/ip_library.py
```

第一版用本地 JSON 文件：

```text
data/ip_library/
  ips/
  characters/
  assets/
  worlds/
  styles/
  previews/
```

实现方法：

```python
create_ip_profile()
list_ip_profiles()
get_ip_profile()
update_ip_profile()
delete_ip_profile()

create_character()
list_characters()
update_character()

resolve_ip_context()
```

## 4. 任务 3：新增 Prompt Composer

新增：

```text
pixelle_video/services/prompt_composer.py
```

实现：

```python
compose_scene_prompt(input: PromptComposeInput) -> PromptComposeResult
```

要求输出：

```text
final_prompt
negative_prompt
debug_parts
```

## 5. 任务 4：新增 Scene Casting

新增：

```text
pixelle_video/services/scene_casting.py
```

第一版可以基于规则：

```text
每帧默认主角出现
如果旁白包含“学生/对手/第三个人”，加入配角
如果视觉方向包含“书/黑板/太阳”，加入对应道具
```

后面再用 LLM 做自动 scene casting。

## 6. 任务 5：改造 StandardPipeline 的视觉阶段

当前逻辑：

```text
generate_image_prompts()
build_image_prompt(base_prompt, prompt_prefix)
```

改成：

```text
generate_image_prompts()
resolve_ip_context()
scene_casting()
prompt_composer.compose()
ctx.image_prompts = final_prompts
ctx.prompt_debugs = debug_parts
```

同时扩展 StoryboardFrame：

```text
base_image_prompt
final_image_prompt
prompt_debug
ip_id
character_ids
asset_ids
style_id
environment_id
```

## 7. 任务 6：新增 Generation Trace

新增：

```text
pixelle_video/services/generation_trace.py
api/routers/generation_trace.py
```

第一版落盘：

```text
output/{task_id}/trace/events.jsonl
```

方法：

```python
record_event()
record_llm_call()
record_validation()
record_retry()
load_events()
```

API：

```http
GET /api/v1/app/jobs/{job_id}/events
```

## 8. 任务 7：新增帧级 Artifact 版本

新增：

```text
pixelle_video/services/artifact_service.py
pixelle_video/services/regeneration_service.py
api/routers/frame_regeneration.py
```

第一版可以把版本存在：

```text
output/{task_id}/artifacts.json
```

接口：

```http
POST /api/v1/app/storyboards/{storyboard_id}/frames/{frame_id}/regenerate-image
POST /api/v1/app/storyboards/{storyboard_id}/frames/{frame_id}/image-versions/{version_id}/select
POST /api/v1/app/storyboards/{storyboard_id}/render-final
```

## 9. 任务 8：API v1 路由分层

新增：

```text
api/v1/app/
api/v1/public/
api/v1/admin/
api/v1/internal/
```

第一版先实现 app：

```text
api/v1/app/ip_profiles.py
api/v1/app/script_drafts.py
api/v1/app/storyboards.py
api/v1/app/generation_trace.py
api/v1/app/frame_regeneration.py
```

## 10. 任务 9：部署预留

新增：

```text
pixelle_video/workers/worker_app.py
pixelle_video/workers/tasks.py
pixelle_video/services/provider_router.py
```

第一版可以不接 Celery，只先把接口和目录留好。

第二阶段再接：

```text
Celery + Redis
```

## 11. 任务 10：前端最小改造

当前 Streamlit 增加：

```text
IP 选择器
每帧 prompt_debug 展示
生成过程 events 展示
每帧重新生成图片按钮
图片版本选择
```

后续 Vue/Next.js 再重写。

## 12. 推荐开发顺序

```text
1. models/ip_profile.py
2. services/ip_library.py
3. services/prompt_composer.py
4. services/scene_casting.py
5. 修改 StoryboardFrame
6. 修改 StandardPipeline.plan_visuals()
7. services/generation_trace.py
8. api/v1/app/ip_profiles.py
9. api/v1/app/generation_trace.py
10. artifact_service + frame_regeneration
11. worker 架构预留
```

## 13. 验收标准

第一阶段完成后，应支持：

```text
创建一个植物老师 IP
输入主题“如何读懂毛选”
生成 5 段旁白
生成每帧图片提示词
每帧 final prompt 都包含主角固定特征
前端可查看每帧 prompt_debug
可以重新生成某一帧图片
可以选择历史图片版本
可以重新合成最终视频
```
