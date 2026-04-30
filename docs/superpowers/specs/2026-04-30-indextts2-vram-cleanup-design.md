# IndexTTS2 显存释放契约设计

## 背景

Pixelle 当前的 ComfyUI “生成前清理”配置只处理队列状态：

- `force` 会查询 `/queue`，必要时调用 `/interrupt` 和 `/queue {"clear": true}`，并等待队列空闲。
- 它不会调用 ComfyUI `/free`。
- Pixelle 的普通 post-generation `/free` 已被有意禁用，因为频繁卸载 selfhost/GGUF 模型曾导致稳定性问题。

这解释了两个工作流表现不同的原因：

- `workflows/selfhost/image_z_image_turbo_gguf.json` 使用 ComfyUI 标准 loader/model manager，右键“释放显存”触发 `/free` 后可以释放 GGUF/CLIP/VAE。
- `workflows/selfhost/tts_index2_8g.json` 使用 `ComfyUI-Index-TTS` 插件。该插件通过全局 `IndexTTS2Loader` 和 `_cache["tts"]` 持有 raw PyTorch 模型，模型没有注册到 ComfyUI model manager，ComfyUI `/free` 看不到这些对象。

因此，单纯设置 `keep_models_cached=false` 或只多调用 ComfyUI `/free` 都不是源头治理。前者会破坏长文案 TTS 批次内的热缓存，后者无法释放插件私有缓存。

## 目标

让 Pixelle 的本地 ComfyUI 清理在用户视角上和 z-image 一样可靠：当 Pixelle 执行强制清理、OOM 恢复、TTS 批次结束释放时，IndexTTS2 占用的显存也能被释放。

核心目标：

- 从源头释放 `ComfyUI-Index-TTS` 插件内部持有的 IndexTTS2 模型对象。
- 保留 `tts_index2_8g.json` 的 `keep_models_cached=true`，让同一 TTS 批次内仍能复用模型。
- 不修改 ComfyUI 核心 `/free` 实现，避免和 ComfyUI 升级产生长期冲突。
- 不依赖人工手改现场插件；所有插件变更都通过 `tools/patch_indextts2_plugin.py` 可重复应用。
- 给 Pixelle 维护端提供可测试的 HTTP 契约和日志反馈。

## 非目标

- 不把 IndexTTS2 改造成 ComfyUI 原生 model manager 模型。上游插件当前直接构造多个 PyTorch 子模块，这类重构应由插件上游或独立大版本完成。
- 不让每个 TTS 段生成后都卸载模型。同一长文案批次内需要缓存以避免反复加载。
- 不修改 ComfyUI 原生右键“释放显存”的核心行为。本设计优先保证 Pixelle 自己的清理链路可靠；如果后续必须让 ComfyUI 原生右键也释放 IndexTTS2，再单独设计前端扩展或 ComfyUI hook。

## 推荐方案

### 1. 在 IndexTTS2 插件内建立释放契约

通过 `tools/patch_indextts2_plugin.py` 扩展 `ComfyUI-Index-TTS`：

- Patch `indextts2/model_loader.py`：
  - 为 `IndexTTS2Loader` 增加 weak registry，记录当前进程内创建过且仍存活的 loader。
  - 保留现有 `unload_tts()` 语义，但强化释放逻辑。
  - 增加模块级 `unload_all_indextts2()`，遍历 registry 并释放所有 loader。
- 释放时不仅从 `_cache` pop `tts`，还要对已知大对象断引用：
  - `gpt`
  - `semantic_model`
  - `semantic_codec`
  - `s2mel`
  - `campplus_model`
  - `bigvgan`
  - `qwen_emo`
  - 其他插件版本中存在的 tokenizer、feature extractor、均值/方差 tensor 等 CUDA 相关字段
- 清理顺序：
  - 先断开 Python 引用。
  - `gc.collect()`。
  - 如果 CUDA 可用，执行 `torch.cuda.synchronize()`、`torch.cuda.empty_cache()`、`torch.cuda.ipc_collect()`。
- 返回结构化统计：
  - `loaders_seen`
  - `loaders_released`
  - `released`
  - `cuda_allocated_before`
  - `cuda_allocated_after`
  - `cuda_reserved_before`
  - `cuda_reserved_after`

### 2. 给插件暴露 Pixelle 专用 HTTP 端点

Patch 插件 `__init__.py` 或新增被 `__init__.py` 导入的 `pixelle_routes.py`：

- 注册 `POST /pixelle/indextts2/free`。
- 使用 ComfyUI custom node 标准方式：
  - `from aiohttp import web`
  - `from server import PromptServer`
  - `@PromptServer.instance.routes.post(...)`
- 端点调用 `unload_all_indextts2()` 并返回 JSON。
- 端点必须是幂等的：未加载模型时返回成功，`released=false`，不能报错。

这个端点是 Pixelle 与第三方插件私有缓存之间的正式维护契约。Pixelle 不直接猜测插件进程内对象路径，也不远程执行任意代码。

### 3. Pixelle 维护客户端支持扩展模型释放

扩展 `pixelle_video/services/comfyui_maintenance.py`：

- 保留现有队列清理方法 `cleanup_before_generation(mode)`。
- 保留标准 ComfyUI `/free` 方法 `free_memory(intensity)`。
- 新增扩展释放方法，例如 `free_extension_models(extensions=("indextts2",))`。
- 新增组合释放方法，例如 `free_memory_with_extensions(intensity="high", extensions=("indextts2",))`：
  - 先调用 ComfyUI `/free`，释放 z-image 这类标准模型。
  - 再调用 `/pixelle/indextts2/free`，释放 IndexTTS2 插件私有缓存。
- 对 404 的处理必须明确：
  - 普通 selfhost 环境中，404 记录清晰 warning，提示需要重新执行 `tools/patch_indextts2_plugin.py`。
  - OOM 恢复和用户显式强制清理路径中，缺失端点应返回失败结果或抛出带操作建议的错误，避免用户误以为清理已经完成。

### 4. Pixelle 生命周期调用点

`pixelle_video/service.py` 的本地 ComfyUI 生命周期按用途分层：

- 生成前 `force` 清理：
  - 先做队列清理。
  - 队列空闲后执行组合模型释放，覆盖标准 ComfyUI 模型和已知插件私有缓存。
- OOM recovery：
  - 使用组合模型释放，而不是只调用 ComfyUI `/free`。
  - 释放后重新执行 pre-workflow cleanup，再重试一次。
- TTS workflow session 结束：
  - 如果 session 内执行过 IndexTTS2 工作流，只释放 IndexTTS2 插件缓存。
  - 不对每个 TTS block 单独释放，避免破坏 `keep_models_cached=true` 的批次复用价值。
- 任务级 fallback：
  - 如果 workflow session 结束释放失败，在 task scope 退出时再尝试一次。
  - 失败要记录可操作日志，包含补丁脚本路径和目标插件路径。

这样对用户效果是：

- z-image 类模型通过 ComfyUI `/free` 释放。
- IndexTTS2 通过 `/pixelle/indextts2/free` 释放。
- Pixelle 的强制清理对两类模型都生效。

### 5. 配置与 UI 语义

需要避免继续让“生成前清理”这个名字承载过多隐藏含义。

配置层建议：

- 保留 `pre_generation_cleanup_mode: force|conservative`，定义为队列清理策略。
- 新增模型释放配置，例如：
  - `model_cleanup_mode: disabled|comfyui|comfyui_and_extensions`
  - 默认使用 `comfyui_and_extensions`，让强制清理符合用户对“释放显存”的直觉。
- 文档说明：
  - `force` 负责让队列回到可控状态。
  - `model_cleanup_mode` 负责释放模型显存。
  - IndexTTS2 释放依赖插件端点，缺失端点时需要执行补丁脚本。

UI 层建议：

- 中文帮助文案明确区分“队列清理”和“模型显存释放”。
- 不把 IndexTTS2 的问题描述成用户需要关闭缓存；应解释为插件私有缓存需要专用释放契约。

## 测试策略

### 插件补丁测试

更新 `tests/test_patch_indextts2_plugin.py`：

- 构造最小 `model_loader.py` 样本，验证补丁会加入 loader registry、`unload_all_indextts2()` 和强化 CUDA 清理。
- 构造最小插件 `__init__.py` 样本，验证补丁会注册 `/pixelle/indextts2/free`。
- 验证补丁幂等：第二次执行没有 diff。
- 验证缺失关键文件时给出明确错误。

### Pixelle 维护客户端测试

更新 `tests/test_comfyui_maintenance.py`：

- `free_memory_with_extensions("high")` 先调用 `/free`，再调用 `/pixelle/indextts2/free`。
- `/pixelle/indextts2/free` 返回 404 时，普通模式产生 warning 或结构化失败，不吞掉上下文。
- 非 404 错误保留 HTTP 错误信息。
- `cleanup_before_generation("force")` 的队列清理顺序保持不变。

### 生命周期测试

更新 `tests/test_generation_coordinator.py`：

- OOM recovery 调用组合释放，而不是只调用 `/free`。
- IndexTTS2 workflow session 结束后触发插件缓存释放。
- 同一 TTS session 内多个 block 只在 session 结束释放一次。
- RunningHub workflow 不触发本地 ComfyUI 清理。
- 保持现有并发 session 串行化语义不变。

### 配置与文档测试

- 更新配置 schema 测试，覆盖新 `model_cleanup_mode` 默认值和非法值。
- 更新 `config.example.yaml`、中英文配置文档、`workflows/down/tts_index2_8g_依赖与下载说明.md`。
- 更新 UI i18n 文案测试，确保“生成前清理”帮助文本不再暗示它只清队列或错误承诺。

## 风险与缓解

### 风险：插件上游结构变化导致补丁失效

缓解：

- 补丁脚本用 AST 或明确锚点定位函数，失败时抛出可读错误。
- 测试覆盖当前样本和已知上游变体。
- 文档要求重装或升级 `ComfyUI-Index-TTS` 后重新执行补丁脚本和测试。

### 风险：释放时仍有队列正在运行

缓解：

- Pixelle 只在队列空闲后调用模型释放。
- `force` 模式先中断并清空队列，再等待 idle。
- 插件端点保持幂等，但不承担抢占正在执行推理的职责。

### 风险：显存统计显示释放不彻底

缓解：

- 返回 allocated/reserved 前后值，帮助区分 PyTorch 已释放对象和 CUDA allocator 保留缓存。
- 同时调用 `empty_cache()` 和 `ipc_collect()`。
- 如果 Python 层仍有引用，测试和日志会暴露 loaders 数量与 released 数量。

### 风险：频繁释放影响性能

缓解：

- 不在每个 TTS block 后释放。
- 只在 workflow session 结束、OOM recovery、显式强制清理和生成前模型清理点释放。
- `keep_models_cached=true` 继续服务于同一批次内复用。

## 成功标准

- Pixelle 执行强制清理时，同时覆盖 ComfyUI 标准模型和 IndexTTS2 插件私有缓存。
- `tts_index2_8g.json` 继续保留 `keep_models_cached=true`。
- IndexTTS2 长文案批次内部不反复加载模型，批次结束后能释放显存。
- OOM recovery 能释放 IndexTTS2 后再重试。
- 所有新增释放行为都有单元测试、配置文档和插件补丁说明。
- 不需要手动修改 ComfyUI 核心文件，也不需要用户手动编辑第三方插件源码。
