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

## 3. 两种 IP 能力层

### 3.1 Structured IP

适合 Stage 2A 的第一版资产事实源。

特点：

```text
不依赖参考图
不依赖 LoRA
不依赖图生图
通过 IPProfile / CharacterProfile / StyleProfile / SceneCast 约束角色和世界观
以资源 ID 进入 PromptPlan，不把自然语言提示当长期事实源
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

Stage 1A 只预留资源 ID 字段。Stage 2A 先做 Structured IP 和 AssetBible 草稿事实源，后续再扩展 reference 模式。

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
