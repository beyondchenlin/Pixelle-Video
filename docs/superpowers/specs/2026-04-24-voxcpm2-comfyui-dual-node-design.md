# VoxCPM2 ComfyUI 双节点接入设计

## 目标

在 Pixelle 现有 ComfyUI TTS 工作流体系中同时加入两套 VoxCPM2 节点方案：

- `HM-RunningHub/ComfyUI_RH_VoxCPM`
- `Saganaki22/ComfyUI-VoxCPM2`

两套方案都作为本地 `selfhost` 工作流暴露给 Pixelle，模型文件统一优先从 ModelScope（魔搭）下载。

## 约束

- 不改动现有 IndexTTS2、EdgeTTS 行为。
- 不直接下载大模型；本次只补工作流、测试和依赖说明。
- 模型下载说明必须优先使用 ModelScope。
- 尽量避免重复存储 VoxCPM2 主模型。RunningHub 节点使用 `models/voxcpm/VoxCPM2`，Saganaki 节点使用 `models/tts/VoxCPM/VoxCPM2`，实际部署时可用 NTFS junction 指向同一份模型目录。
- 当前工作区已有其他未提交改动，本次只修改 VoxCPM2 相关文件。

## 架构

新增四个 `selfhost` TTS 工作流：

- `workflows/selfhost/tts_voxcpm2_rh.json`：RunningHub 节点的声音设计/普通 TTS。
- `workflows/selfhost/tts_voxcpm2_rh_clone.json`：RunningHub 节点的参考音频克隆。
- `workflows/selfhost/tts_voxcpm2_saganaki.json`：Saganaki 节点的声音设计/普通 TTS。
- `workflows/selfhost/tts_voxcpm2_saganaki_clone.json`：Saganaki 节点的参考音频克隆。

Pixelle 的 `TTSService` 已经按 `tts_*.json` 自动扫描工作流，并通过 ComfyKit 的 `$param.field` DSL 注入参数，因此新增工作流文件即可出现在 `/resources/workflows/tts` 与 Web UI 的 TTS 工作流列表中。

## 参数契约

所有新增工作流至少暴露必填 `text` 参数。克隆工作流额外暴露必填 `ref_audio` 参数。

可选参数：

- `voice_description`：声音描述或风格控制。
- `cfg_value`：VoxCPM2 引导强度。
- `inference_steps` / `inference_timesteps`：推理步数，按节点实际字段命名。
- `seed`：随机种子。
- `max_len` / `max_tokens`：生成长度上限，按节点实际字段命名。
- `normalize_text`：文本规范化开关。

## 依赖与下载

新增 `workflows/down/tts_voxcpm2_依赖与下载说明.md`，记录：

- 两个节点包的 GitHub 来源和安装命令。
- VoxCPM2 主模型从 ModelScope 下载到 `E:\comfyui\comfyui\models\voxcpm\VoxCPM2`。
- 可选 ASR 模型 `iic/SenseVoiceSmall`。
- 可选降噪模型 `iic/speech_zipenhancer_ans_multiloss_16k_base`。
- Saganaki 节点的模型路径兼容方式：创建 `models\tts\VoxCPM\VoxCPM2` 到 `models\voxcpm\VoxCPM2` 的 junction，或复制同一模型目录。

## 验证

- 新增测试确认四个工作流均可被 `WorkflowParser` 解析。
- 测试确认各工作流节点类型、参数映射、输出节点和模型目录约定符合预期。
- 运行目标测试：`uv run pytest tests/test_selfhost_workflows.py -v`。
