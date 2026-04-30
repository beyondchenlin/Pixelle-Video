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
    frame_id: str
    storyboard_plan_id: str
    image_prompt_draft_id: str
    prompt_sections: dict
    final_prompt: str
    asset_bible_id: str | None = None
    style_id: str | None = None
    character_ids: list[str] = []
    prop_ids: list[str] = []
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
PromptPlanBuilder
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
PromptPlan prompt_sections
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
