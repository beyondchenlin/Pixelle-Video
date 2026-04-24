# LongCat AudioDiT 接入开发总结

日期：2026-04-24

## 背景

Pixelle 已有 ComfyUI + IndexTTS2 音频生成链路。本次新增美团龙猫 LongCat AudioDiT，目标是把 LongCat 作为 ComfyUI TTS 工作流接入，并补齐声音克隆所需的参考音频文本参数。

## 调研结论

- 官方仓库：`https://github.com/meituan-longcat/LongCat-AudioDiT`
- ComfyUI 节点：`https://github.com/Saganaki22/ComfyUI-LongCat-AudioDIT-TTS`
- 节点提供 `LongCatTTS`、`LongCatVoiceCloneTTS`、`LongCatMultiSpeakerTTS` 三类节点。
- 节点默认模型目录为 ComfyUI 启动日志里的 `Models folder registered: <path>\audiodit`。
- 当前本机实际目录：`E:\comfyui-venv\models\audiodit`
- 节点会把不存在的模型项显示为 `(auto download)`，这些选项会触发 Hugging Face 下载。本项目要求优先 ModelScope，因此工作流默认值不能使用 `(auto download)`。

## ModelScope 下载与校验

已通过 ModelScope 下载：

- `meituan-longcat/LongCat-AudioDiT-1B`
- `google/umt5-base` tokenizer 文件

落地目录：

- `E:\comfyui-venv\models\audiodit\LongCat-AudioDiT-1B`
- `E:\comfyui-venv\models\audiodit\umt5-base-tokenizer`

1B 权重校验：

- 文件：`E:\comfyui-venv\models\audiodit\LongCat-AudioDiT-1B\model.safetensors`
- 大小：`5679831348` bytes
- SHA256：`7F41B20933E4466400B8487FD20CA195EFA65C5CA7C61F8E9BBA6316AA3EDCDE`

## 代码与工作流变更

新增工作流：

- `workflows/selfhost/tts_longcat_clone.json`

新增依赖文档：

- `workflows/down/tts_longcat_clone_依赖与下载说明.md`

新增参数通路：

- UI/请求侧使用 `ref_audio_text`
- ComfyUI workflow 执行时映射为 LongCat 节点需要的 `prompt_text`
- `StoryboardConfig`、持久化、标准 pipeline、custom pipeline、frame processor、digital human pipeline 均补了透传逻辑

工作流关键约定：

- `text` 使用 `$text.value!`
- `ref_audio` 使用 `$ref_audio.~audio!`
- `prompt_text` 使用 `$prompt_text.value`
- `LongCatVoiceCloneTTS.model_path` 默认 `LongCat-AudioDiT-1B`

## 本机验证

ComfyUI 节点加载：

- `LongCatAudioDiT` 注册 3 个节点
- `LongCatVoiceCloneTTS` 模型列表中本地项为 `LongCat-AudioDiT-1B`
- 其他 3.5B 选项仍显示 `(auto download)`，未作为默认值使用

普通 TTS 烟测：

- 输出：`E:\comfyui-venv\output\audio\longcat_smoke_zh_00001_.mp3`
- 结果：24kHz、mono、约 7.34 秒

声音克隆烟测：

- 参考音频：普通 TTS 烟测输出复制到 ComfyUI input
- 填写了对应 `prompt_text`
- 输出：`E:\comfyui-venv\output\audio\longcat_clone_smoke_00001_.mp3`
- 结果：24kHz、mono、约 3.67 秒

自动化验证：

- `pytest tests/test_selfhost_workflows.py tests/test_index_tts2_timing_profile.py tests/test_output_preview.py -q`
- 结果：34 passed
- i18n JSON 解析通过
- 相关 Python 文件 `py_compile` 通过

## 已知风险

- 当前仓库工作区混有其他 TTS 分段、VoxCPM2、渲染后端等未归属 LongCat 的变更，提交前需要按变更意图拆分。
- `ref_audio_text` 是声音克隆质量关键参数，但不是所有 TTS workflow 都消费它；非 LongCat workflow 会忽略该参数。
- 节点内置 Hugging Face 自动下载仍存在，只要用户手动把 workflow 模型项改成 `(auto download)` 就可能触发。
- 本次默认接入 1B 模型。3.5B FP32 在 ModelScope 可用但显存和磁盘成本更高，BF16/FP8 暂未验证到 ModelScope 可用清单。
- LongCat 节点日志在 Windows 控制台中会出现中文编码显示异常，但实际 HTTP prompt 与输出音频链路正常。

## 建议后续

1. UI 上可在选择 LongCat clone workflow 时才突出显示 `ref_audio_text`，减少非克隆 workflow 的认知负担。
2. 可以增加一个 ModelScope 下载辅助脚本，避免团队成员手工复制 Python 片段。
3. 如需默认更高质量，可补充 3.5B FP32 下载文档和显存准入提示。
4. 合并前建议先把 LongCat 变更和其他 TTS/渲染变更拆成独立提交。
