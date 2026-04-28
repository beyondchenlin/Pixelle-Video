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
