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
