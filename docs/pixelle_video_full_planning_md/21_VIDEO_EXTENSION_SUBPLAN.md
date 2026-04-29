# 21 视频扩展分方案

用途：定义从图文分镜工作台扩展到视频片段和最终成片的路线。  
上级文档：`MASTER_PIXELLE_AI_DRAMA_COMIC_PLATFORM_PLAN.md`

---

## 1. 定位

视频扩展必须建立在图文分镜、Artifact、Trace、Worker 和 Provider 稳定之后。

早期不要把图生视频、转场分析和最终成片放入主路径，否则会拖慢第一阶段工作台闭环。

---

## 2. 核心能力

```text
first frame
last frame
motion prompt
transition analysis
video segment artifact
segment audio alignment
final render artifact
```

---

## 3. 领域模型

```text
VideoSegmentPlan
  frame_id
  source_image_artifact_version_id
  motion_prompt
  duration_seconds
  provider_requirements

VideoSegmentArtifact
  artifact_id
  frame_id
  segment_index
  current_selected_version_id

FinalRenderArtifact
  artifact_id
  project_id
  selected_segment_version_ids
  render_manifest_id
```

---

## 4. 数据流

```text
StoryboardPanel
  -> selected image ArtifactVersion
  -> VideoSegmentPlan
  -> video segment ArtifactVersion
  -> final render ArtifactVersion
```

视频扩展不能绕过图片分镜工作台。图片分镜是视频片段生成的稳定输入。

---

## 5. Provider

视频 Provider 可能包括：

- 本地图生视频工作流。
- 云视频模型。
- RunningHub 类远程工作流。
- 后续商业 API。

业务层只依赖 VideoProvider 接口。

---

## 6. Trace

每段视频必须记录：

- 输入图片版本。
- motion prompt。
- provider。
- seed 或 provider request id。
- 生成耗时。
- 失败原因。
- 输出视频 artifact_version_id。

---

## 7. 验收标准

- 已选分镜图可以生成视频片段。
- 视频片段可以重跑且不覆盖旧版本。
- 最终视频能追踪到每个 segment。
- 修改图片后相关视频片段标记 stale。
- 不修改上游 AssetBible / StoryboardPanel / PromptPlan 合同。

---

## 8. 阶段边界

阶段 9 才进入视频扩展。

阶段 1 只处理图片分镜和最终现有视频生成兼容，不新增复杂视频片段工作台。

---

## 9. 非目标

- 不在阶段 1 做复杂镜头运动系统。
- 不在阶段 1 做首尾帧转场分析。
- 不在阶段 1 承诺电影级连续性。
