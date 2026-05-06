# PyTorch 2.11.0 性能退化记录

## 概述

2026/05/06 发现 ComfyUI 图片生成速度从正常的 2-3 秒/张退化到 7-11 秒/张。经排查确定根因是 PyTorch 2.10.0 → 2.11.0 升级引入了已知性能退化。

## 版本时间线

| 时间 | PyTorch | ComfyUI | comfy-aimdo | 生成速度(第二张) |
|------|---------|---------|-------------|-------------------|
| 4/20-4/22 | 2.10.0+cu130 | 0.19.x | 0.2.12 | 2-3s ✅ |
| 4/25 | 2.10.0+cu130 | 0.19.5 | 0.2.12 | 2-3s ✅ |
| **4/30** | **2.11.0+cu130** | **0.20.1** | **0.2.14** | **7-11s** ❌ |
| 5/4 | 2.11.0+cu130 | 0.20.1 | 0.2.14 | 7-11s ❌ |
| 5/6 | 2.11.0+cu130 | 0.20.1 | 0.2.14 | 7-11s ❌ |

## 根本原因

PyTorch 2.11.0 存在多个已确认的性能退化：

### 1. Inductor 过度融合（Over-Fusion）
- **Issue**: [pytorch/pytorch#179423](https://github.com/pytorch/pytorch/issues/179423)
- **影响**: 反向传播慢 ~9%，生成更少但更大的融合 Triton kernel
- **环境确认**: NVIDIA H100, CUDA 12.8, Triton 3.5.1

### 2. torch.compile 显存占用增加
- **Issue**: [pytorch/pytorch#175058](https://github.com/pytorch/pytorch/issues/175058)
- **影响**: 显存占用增加 3-4GB，可能导致原本正常运行的工作流 OOM

### 3. torch.compile 自定义算子输出错误
- **Issue**: [pytorch/pytorch#180642](https://github.com/pytorch/pytorch/issues/180642)
- **影响**: 自定义 autograd 函数在 torch.compile 下产生完全错误的输出

### 4. GGUF 模型 VRAM 利用率暴跌
- **Issue**: [Comfy-Org/ComfyUI#11081](https://github.com/Comfy-Org/ComfyUI/issues/11081)
- **影响**: GGUF 模型 VRAM 利用率从 80-95% 降至 45-55%，推理速度下降 2-5 倍
- **症状**: GGUF CLIP 模型完全在 CPU 上编码文本，GPU 利用率为 0%

## ComfyUI 启动参数试验

| 参数组合 | 第二张速度 | 结论 |
|----------|-----------|------|
| 无参数（默认） | 11s | 基准 |
| --disable-dynamic-vram | 7.4s | 有改善，仍未恢复 |
| --disable-dynamic-vram + --highvram | 10s | 倒退：扩散模型锁死但 VAE/TE 仍卸到 CPU，显存争抢 |
| --disable-dynamic-vram + --gpu-only | 9-11s | 未改善 |

结论：ComfyUI 启动参数的调整无法完全解决问题，根因在 PyTorch 层面。

## 修复方案

降级 PyTorch 到 2.10.0+cu130：

```bash
pip install torch==2.10.0+cu130 torchaudio==2.10.0+cu130 --index-url https://download.pytorch.org/whl/cu130
pip install torchvision==0.25.0+cu130 --index-url https://download.pytorch.org/whl/cu130
```

### 兼容性确认

| 组件 | PyTorch 要求 | 2.10.0 满足？ |
|------|-------------|--------------|
| ComfyUI 0.20.1 | >= 2.8 (DynamicVRAM) | ✅ |
| comfy-kitchen 0.2.8 | 无约束 | ✅ |
| comfy-aimdo 0.2.14 | 无约束 | ✅ |
| IndexTTS | >= 1.12.0 | ✅ |
| 所有 GGUF 节点 | 无约束 | ✅ |
| 其他 custom nodes | 最高 >= 1.12.0 | ✅ |

## Pixelle 层面修复

`pixelle_video/pipelines/standard.py` 中 `_schedule_stage_backend_restart_if_needed` 方法增加了 `restart_after_batch` 门控：
- 之前：在阶段边界无条件重启 ComfyUI 后端，导致每张图片后模型全部重载
- 之后：遵循 `restart_after_batch` 配置，设为 `false` 时保持后端存活

## 参考文献

- [PyTorch 2.11 Release Blog](https://pytorch.org/blog/pytorch-2-11-release-blog/)
- [Inductor over-fusion regression](https://github.com/pytorch/pytorch/issues/179423)
- [ComfyUI GGUF VRAM under-utilization](https://github.com/Comfy-Org/ComfyUI/issues/11081)
- [torch.compile VRAM regression](https://github.com/pytorch/pytorch/issues/175058)
- [torch.compile custom ops broken](https://github.com/pytorch/pytorch/issues/180642)
