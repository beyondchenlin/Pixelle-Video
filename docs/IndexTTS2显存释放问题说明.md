# IndexTTS2 显存释放问题说明

## 1. 问题背景

当前 Pixelle 使用本地 ComfyUI 执行工作流。标准视频生成流程里，TTS 阶段使用 `ComfyUI-Index-TTS` 插件执行 IndexTTS2 语音合成，后续阶段还会继续使用 ComfyUI 执行图片或视频生成工作流。

为了避免 TTS 模型和后续图片/视频模型同时驻留显存，Pixelle 在 IndexTTS2 工作流结束后会执行显存释放，并要求释放结果可确认。现在遇到的问题是：IndexTTS2 工作流执行完成后，Pixelle 在释放确认阶段中止，导致后续视频生成无法继续。

## 2. 现象

报错文件：`11.md`

核心错误：

```text
RuntimeError: ComfyUI post-index-tts2-workflow memory release was not confirmed; stopping before the next Pixelle stage to avoid mixed model residency.
```

日志显示：

```text
HTTP Request: POST http://127.0.0.1:8000/pixelle/indextts2/free "HTTP/1.1 200 OK"
ComfyUI post-index-tts2-workflow memory release completed
Pipeline execution failed: ComfyUI post-index-tts2-workflow memory release was not confirmed
```

这里的关键矛盾是：接口调用成功返回 200，但 Pixelle 仍然认为“释放没有被确认”。

## 3. 当前环境和接口状态

当前 Pixelle 配置：

```yaml
comfyui:
  comfyui_url: http://127.0.0.1:8000
  pre_generation_cleanup_mode: force
  model_cleanup_mode: comfyui_and_extensions
```

ComfyUI 当前队列状态：

```json
{
  "queue_running": [],
  "queue_pending": []
}
```

ComfyUI 当前显存状态示例：

```json
{
  "devices": [
    {
      "name": "cuda:0 NVIDIA GeForce RTX 4090 : cudaMallocAsync",
      "type": "cuda",
      "vram_total": 25756696576,
      "vram_free": 24032014016,
      "torch_vram_total": 167772160,
      "torch_vram_free": 158035648
    }
  ]
}
```

IndexTTS2 健康检查接口正常：

```json
{
  "ok": true,
  "extension": "indextts2",
  "release_endpoint": "/pixelle/indextts2/free",
  "loaders_seen": 1
}
```

手动调用释放接口返回：

```json
{
  "released": false,
  "loaders_seen": 1,
  "loaders_released": 0,
  "errors": [],
  "cuda_allocated_before": 9736512,
  "cuda_allocated_after": 9736512,
  "cuda_reserved_before": 167772160,
  "cuda_reserved_after": 167772160
}
```

这说明接口存在且可达，但释放端点没有释放任何 loader 中的 TTS 对象，显存数值也没有变化。

## 4. 相关代码位置

Pixelle 释放逻辑：

- `pixelle_video/service.py`
  - `release_comfyui_after_index_tts2_workflow`
  - `_release_local_comfyui_after_workflow_session`
- `pixelle_video/services/comfyui_maintenance.py`
  - `free_memory`
  - `free_memory_with_extensions`
  - `free_memory_with_extensions_when_idle`
  - `_wait_for_memory_release_confirmation`
  - `_is_memory_release_confirmed`

IndexTTS2 插件补丁脚本：

- `tools/patch_indextts2_plugin.py`

本机实际插件文件：

- `E:\ComfyUIData\custom_nodes\ComfyUI-Index-TTS\pixelle_routes.py`
- `E:\ComfyUIData\custom_nodes\ComfyUI-Index-TTS\indextts2\model_loader.py`
- `E:\ComfyUIData\custom_nodes\ComfyUI-Index-TTS\index_tts2_mode_nodes.py`

相关工作流：

- `workflows/selfhost/tts_index2_8g.json`
- `workflows/selfhost/tts_index2.json`

## 5. 初步根因判断

当前问题不是 ComfyUI 未启动，也不是 IndexTTS2 释放端点缺失。

更可能的根因是释放协议和成功判定语义不完整：

1. ComfyUI 标准 `/free` 只管理 ComfyUI model manager 中的模型。IndexTTS2 插件通过自己的全局 loader/cache 持有 PyTorch 模型对象，标准 `/free` 不一定能释放这部分私有缓存。

2. 当前 Pixelle 先调用 ComfyUI 标准 `/free` 并观察 `/system_stats` 中显存是否变化，再调用 `/pixelle/indextts2/free`。如果标准 `/free` 没观察到显存变化，即使插件端点存在，也会被判定为释放未确认。

3. 当前 IndexTTS2 插件释放接口只返回 `released: true/false`。这个字段语义不够明确：
   - `false` 可能表示“没有 TTS 对象需要释放，当前已经安全”。
   - 也可能表示“存在 loader，但模型对象没有释放成功”。
   - 现在无法区分这两种状态。

4. 本机返回 `loaders_seen: 1, loaders_released: 0`，说明至少存在 loader 注册对象，但 `loader.unload_tts()` 没有释放到 `_cache["tts"]`。原因可能包括：
   - TTS 对象已被工作流节点提前卸载，但 PyTorch allocator 仍保留 reserved memory；
   - 模型对象不在 `_cache["tts"]`，而在其他缓存、全局变量或子模块引用中；
   - 插件内部对象生命周期和 Pixelle 释放端点的假设不一致；
   - 当前释放端点没有返回足够信息说明是否仍有残留模型引用。

## 6. 为什么不建议简单绕过

不建议直接采用以下做法：

- 关闭 `model_cleanup_mode`。
- 把 `released=false` 当作成功。
- 放宽显存变化阈值后继续跑。
- 只重启 ComfyUI 作为固定流程。
- 每次阶段切换都冷启动两个 ComfyUI 进程。

这些做法要么会留下混驻显存风险，要么会明显增加启动时间，不适合本机单 GPU 连续生成视频的使用场景。

## 7. 更合理的解决方向

推荐采用“热进程优先，失败时降级”的方案：

1. 保留单 ComfyUI 热进程作为默认路径，避免正常流程增加冷启动时间。

2. 增强 `/pixelle/indextts2/free` 协议，让插件返回明确的结构化状态，而不是只返回 `released`：

   ```json
   {
     "protocol_version": 2,
     "safe_to_continue": true,
     "loaders_seen": 1,
     "objects_seen": ["tts"],
     "objects_released": ["tts"],
     "residual_objects": [],
     "errors": [],
     "cuda_allocated_before": 0,
     "cuda_allocated_after": 0,
     "cuda_reserved_before": 0,
     "cuda_reserved_after": 0
   }
   ```

3. Pixelle 的判定逻辑应改成：
   - 插件明确返回 `safe_to_continue: true`，则 IndexTTS2 私有缓存释放通过；
   - ComfyUI 标准 `/free` 已执行且无 HTTP 错误；
   - 再根据下一阶段 workflow 的显存需求做“准入检查”，而不是只看显存是否比释放前增加。

4. 如果释放协议报告残留对象，或下一阶段显存准入检查失败，再执行降级策略：
   - 先重试一次释放；
   - 仍失败时提示或自动重启 ComfyUI；
   - 重启只作为异常路径，不作为正常路径。

## 8. 需要朋友重点确认的问题

请重点确认以下问题：

1. `ComfyUI-Index-TTS` 的 IndexTTS2 模型对象实际是否只存在于 `IndexTTS2Loader._cache["tts"]`？

2. 如果 `loader.unload_tts()` 返回 `False`，是否能证明当前没有模型残留？还是可能存在其他引用？

3. 插件释放端点是否应该清理整个 `_cache`，而不只是 `_cache["tts"]`？

4. 是否需要在插件侧追踪更具体的对象状态，例如 `gpt`、`semantic_model`、`semantic_codec`、`s2mel`、`campplus_model`、`bigvgan`、`qwen_emo` 等？

5. Pixelle 是否应把“释放成功”的判断从“显存必须明显增加”改成“插件私有缓存无残留 + 下一阶段显存足够”？

6. 对于 PyTorch reserved memory 未下降但 allocated memory 很低的情况，是否可以视为安全进入下一阶段？

7. 是否有 ComfyUI 插件层面的更标准 hook，可以在 ComfyUI `/free` 或队列 flag 处理时同步释放 IndexTTS2 私有缓存？

## 9. 当前倾向方案

当前最适合 Pixelle 本机单 GPU 使用场景的方案：

```text
IndexTTS2 批量生成
  -> 调用增强版 /pixelle/indextts2/free
  -> 调用 ComfyUI 标准 /free
  -> 检查插件是否 safe_to_continue
  -> 检查下一阶段显存是否足够
      -> 足够：直接继续视频生成
      -> 不足：重试释放
      -> 仍不足：重启 ComfyUI 或提示用户处理
```

这个方案的目标是：

- 正常路径不增加 ComfyUI 冷启动时间。
- TTS 批次内继续保留热缓存提升性能。
- 阶段切换时有明确释放协议，避免显存混驻。
- 只有异常路径才重启 ComfyUI。

