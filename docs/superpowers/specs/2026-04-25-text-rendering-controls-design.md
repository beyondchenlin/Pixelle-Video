# 文字渲染控制源头治理设计

## 背景

当前“启用文字层”位于“渲染后端”区块，“禁止图中文字”位于“分镜规划”区块。两者都影响最终画面中的文字表现，但分别挂在不同配置域下，导致语义分散：

- “启用文字层”控制程序化文字叠加，是渲染策略。
- “禁止图中文字”控制图片生成 prompt 是否抑制模型在图中生成文字，是图片提示词策略。
- 当前默认会把禁止文字规则注入图片 prompt，用户不一定意识到该约束来自哪里。
- 禁止文字规则是后端常量，前端不可编辑。

本次改造目标是从源头建立统一的“文字渲染”配置域，而不是只移动 UI 控件。

## 目标

1. 新增一级折叠区 `文字渲染`，位置在 `元素微动` 之后、`分镜规划` 之前。
2. 将“启用文字层”从“渲染后端”迁入 `文字渲染`。
3. 将“禁止图中文字”从“分镜规划”迁入 `文字渲染`。
4. `禁止图中文字` 默认不勾选。
5. `禁止图中文字提示词` 在前端始终显示并可编辑；未勾选时不生效。
6. 新请求主语义统一为 `text_rendering`，不再用旧顶层字段作为主接口。
7. 后端 prompt assembly 只读取归一化后的文字渲染配置，避免 UI、API、pipeline 各自维护默认值。

## 非目标

- 不重做文字层渲染引擎。
- 不改变分镜规划的世界预设、镜头预设、角色策略等能力。
- 不修改现有模板的文字层视觉样式。
- 不为历史任务回写新的 `text_rendering` 字段；历史详情继续按已有 metadata/storyboard 展示。

## 推荐数据结构

新请求字段：

```json
{
  "text_rendering": {
    "overlay": {
      "enabled": false,
      "mode": "programmatic_only",
      "renderer_targets": [],
      "density": "medium",
      "max_items_per_frame": 2
    },
    "image_text": {
      "suppress_embedded_text": false,
      "positive_prompt": "no visible text, no Chinese characters, no English letters, no words, no subtitles, no captions, no watermark, no logo text, convey the idea through objects, symbols, composition, and scene elements instead of written text",
      "negative_prompt": null
    }
  }
}
```

字段语义：

- `text_rendering.overlay`：程序化文字层配置。对应原 `text_layer`，但新主语义不再叫 `text_layer`。
- `text_rendering.image_text`：图片模型内嵌文字控制。对应原 `forbid_embedded_text_in_image`，但新主语义改为正向的“图片中文字策略”。
- `overlay.enabled=false` 时，不生成文字层配置 payload。
- `image_text.suppress_embedded_text=false` 时，不向图片 prompt 追加 `positive_prompt`，也不向 negative prompt 追加文字负面词。
- `image_text.positive_prompt` 允许用户编辑。为空时即使开启 `suppress_embedded_text` 也不追加正向禁字规则。
- `image_text.negative_prompt` 预留给支持 negative prompt 的工作流；为空时不追加额外负面词。

## UI 设计

新增一级折叠区：

```text
元素微动
文字渲染
分镜规划
分镜模板
插图生成
```

`文字渲染` 区块内容：

1. `启用文字层`
   - 默认不勾选。
   - 勾选后显示现有文字层详细设置：模式、渲染目标、密度、每帧最大数量。
   - 渲染目标默认仍根据当前渲染后端选择合理值，例如 legacy 默认 `ass`，HyperFrames 默认 `hyperframes`。

2. `禁止图中文字`
   - 默认不勾选。
   - 勾选后 `image_text.positive_prompt` 才参与图片 prompt 组装。

3. `禁止图中文字提示词`
   - 始终显示。
   - 始终可编辑。
   - 未勾选 `禁止图中文字` 时显示说明“当前不生效”。
   - 默认值使用当前后端常量 `no visible text...` 的完整文案。

原位置处理：

- “渲染后端”只保留渲染后端选择，不再显示 `启用文字层`。
- “分镜规划”只保留分镜规划能力，不再显示 `禁止图中文字`。

## API 设计

`VideoGenerateRequest` 新增强类型字段 `text_rendering`。

建议新增 schema：

- `TextRenderingRequest`
- `TextOverlayRequest`
- `ImageTextPolicyRequest`

新 UI 和新测试只生成 `text_rendering`。旧顶层字段：

- `text_layer`
- `forbid_embedded_text_in_image`

不再作为新请求字段。为了避免技术债，本设计要求直接移除旧字段并让旧请求校验失败。实施时不要保留 deprecated 兼容入口；外部调用方需要迁移到 `text_rendering`。

## 后端归一化

新增内部归一化模型，例如 `TextRenderingSettings`：

```text
TextRenderingSettings
  overlay: TextOverlaySettings
  image_text: ImageTextPromptPolicy
```

所有入口在进入 pipeline 前完成归一化：

- Web UI request builder 输出 `text_rendering`。
- API router 从 `request_body.text_rendering` 构造 generate_video 参数。
- `generate_video` / pipeline 只读取归一化后的 `text_rendering`。
- `build_text_rendering_policy()` 改为读取 `text_rendering.overlay`，不再依赖 `forbid_embedded_text_in_image` 推断 native hint 模式。
- `generate_styled_image_prompt_batch()` 改为读取 `text_rendering.image_text`，不再接收散落的 `forbid_embedded_text_in_image`。

## Prompt 组装规则

图片 prompt 组装顺序保持现有逻辑：

```text
世界预设
+ 镜头规划
+ LLM 基础画面描述
+ 风格约束
+ 文字渲染.image_text 正向规则
```

新规则：

- `suppress_embedded_text=false`：不追加禁止文字正向规则。
- `suppress_embedded_text=true` 且 `positive_prompt` 非空：追加用户配置的 `positive_prompt`。
- `suppress_embedded_text=true` 且 `negative_prompt` 非空且工作流支持 negative prompt：追加用户配置的 `negative_prompt`。
- 不再由默认值隐式追加 `NO_TEXT_POSITIVE_RULE`。

## 持久化与观测

metadata 中记录新字段：

```json
{
  "input": {
    "text_rendering": {
      "overlay": {},
      "image_text": {}
    }
  },
  "result": {
    "text_layer_summary": {}
  }
}
```

storyboard 的 `planning_snapshot.text_rendering_policy` 可继续记录最终展开后的文字策略，但来源应来自 `text_rendering`。

历史展示继续读取 `text_layer_summary`，因为这是结果摘要，不是请求字段。

## 测试范围

需要更新或新增测试：

- `web.components.style_config`
  - 渲染 `文字渲染` 区块。
  - 默认 `禁止图中文字=false`。
  - 提示词文本框始终显示并进入 payload。

- `web.components.output_preview`
  - 单视频 request 输出 `text_rendering`。
  - 批量 shared_config 输出 `text_rendering`。
  - 不再输出旧顶层 `text_layer` 和 `forbid_embedded_text_in_image`。

- `api.schemas.video`
  - `VideoGenerateRequest` 接收 `text_rendering`。
  - 旧字段 `text_layer` / `forbid_embedded_text_in_image` 被拒绝。

- `api.routers.video`
  - `build_video_generation_params()` 传递 `text_rendering`。

- `pixelle_video.models.text_overlay`
  - overlay 策略从 `text_rendering.overlay` 构造。

- `pixelle_video.utils.content_generators`
  - 默认不追加 `no visible text...`。
  - 开启 `suppress_embedded_text` 后追加用户自定义 `positive_prompt`。
  - 支持 negative prompt 的工作流接收用户配置的 `negative_prompt`。

- 标准 pipeline / custom pipeline
  - 只读取 `text_rendering`。
  - 持久化 metadata 中记录新结构。

## 风险与处理

- 破坏性 API 变更：旧调用方需要迁移到 `text_rendering`。这是方案 2 的预期成本。
- 旧测试大量依赖旧字段：应整体更新测试语义，不能只改断言让旧字段继续存在。
- 默认不禁图中文字后，模型可能在图里生成意外文字：这是产品默认行为的显式改变，用户可通过勾选恢复原约束。
- 清空 `positive_prompt` 后开启 `禁止图中文字` 不会追加正向禁字规则：UI 应显示提示，避免用户误以为仍有效。

## 验收标准

1. 前端主面板出现 `文字渲染` 一级折叠区，位置在 `元素微动` 后、`分镜规划` 前。
2. `渲染后端` 区块不再出现 `启用文字层`。
3. `分镜规划` 区块不再出现 `禁止图中文字`。
4. `禁止图中文字` 默认不勾选。
5. `禁止图中文字提示词` 始终可见、可编辑。
6. 新建视频请求只包含 `text_rendering`，不包含旧顶层 `text_layer` / `forbid_embedded_text_in_image`。
7. 默认生成的图片 prompt 不包含 `no visible text` 规则。
8. 开启 `禁止图中文字` 后，图片 prompt 包含用户编辑后的提示词。
9. 单视频和批量生成路径行为一致。
10. 相关单元测试通过。
