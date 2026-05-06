# 性能优化：PyTorch 降级 + ComfyUI 启动参数调优实现 Z-Image 出图性能恢复

## 概述

2026/04/30 发现 ComfyUI Z-Image Turbo GGUF 工作流出图速度从正常的 2-3 秒/张退化到 7-11 秒/张。经过两阶段排查：第一阶段定位 PyTorch 2.11 为主因，降级恢复至 5 秒；第二阶段定位 ComfyUI 0.20 内存管理变化为次因，通过启动参数调优逐步恢复（当前 3.8s，目标 2-3s）。

## 版本时间线

| 时间 | PyTorch | ComfyUI | comfy-aimdo | 启动方式 | 生成速度(第二张) |
|------|---------|---------|-------------|----------|-------------------|
| 4/20-4/22 | 2.10.0+cu130 | 0.19.x | 0.2.12 | 桌面客户端 | 2-3s ✅ |
| 4/25 | 2.10.0+cu130 | 0.19.5 | 0.2.12 | 桌面客户端 | 2-3s ✅ |
| **4/30** | **2.11.0+cu130** | **0.20.1** | **0.2.14** | PowerShell 脚本 | **7-11s** ❌ |
| 5/4 | 2.11.0+cu130 | 0.20.1 | 0.2.14 | PowerShell 脚本 | 7-11s ❌ |

> **关键变化**：4/30 同时发生了三个变更——PyTorch 升级（2.10→2.11）、ComfyUI 升级（0.19→0.20）、启动方式切换（桌面客户端→PowerShell 脚本）。这导致问题排查需要逐层分离。

---

## 第一阶段：PyTorch 降级（7-11s → 5s）

### 根本原因

PyTorch 2.11.0 存在多个已确认的性能退化：

#### 1. Inductor 过度融合（Over-Fusion）
- **Issue**: [pytorch/pytorch#179423](https://github.com/pytorch/pytorch/issues/179423)
- **影响**: 反向传播慢 ~9%，生成更少但更大的融合 Triton kernel
- **环境确认**: NVIDIA H100, CUDA 12.8, Triton 3.5.1

#### 2. torch.compile 显存占用增加
- **Issue**: [pytorch/pytorch#175058](https://github.com/pytorch/pytorch/issues/175058)
- **影响**: 显存占用增加 3-4GB，可能导致原本正常运行的工作流 OOM

#### 3. torch.compile 自定义算子输出错误
- **Issue**: [pytorch/pytorch#180642](https://github.com/pytorch/pytorch/issues/180642)
- **影响**: 自定义 autograd 函数在 torch.compile 下产生完全错误的输出

#### 4. GGUF 模型 VRAM 利用率暴跌
- **Issue**: [Comfy-Org/ComfyUI#11081](https://github.com/Comfy-Org/ComfyUI/issues/11081)
- **影响**: GGUF 模型 VRAM 利用率从 80-95% 降至 45-55%，推理速度下降 2-5 倍
- **症状**: GGUF CLIP 模型完全在 CPU 上编码文本，GPU 利用率为 0%

### ComfyUI 启动参数试验（PyTorch 2.11 环境）

| 参数组合 | 第二张速度 | 结论 |
|----------|-----------|------|
| 无参数（默认） | 11s | 基准 |
| --disable-dynamic-vram | 7.4s | 有改善，仍未恢复 |
| --disable-dynamic-vram + --highvram | 10s | 倒退：扩散模型锁死但 VAE/TE 仍卸到 CPU，显存争抢 |
| --disable-dynamic-vram + --gpu-only | 9-11s | 未改善 |

结论：ComfyUI 启动参数的调整在 PyTorch 2.11 下**无法完全解决问题**，根因在 PyTorch 层面。

### 修复方案

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

### 降级后效果

PyTorch 降级后，生成速度从 7-11s 恢复到 **~5s**。但未回到 4 月的 2-3s。说明 PyTorch 降级解决了主要退化（约 3-6s），但还有约 2s 的额外开销未被定位。

---

## 第二阶段：ComfyUI 启动参数调优（5s → 3.8s → 目标 2-3s）

### 问题定位

PyTorch 降级后暖机跑耗时结构分析（768×768, 5 steps, Z-Image Turbo Q8_0）：

```
got prompt
        ← 约 1.5s 静默开销（CLIP 编码 + pipeline 准备）
5/5 [00:01<00:00, ~3.0it/s]
        ← 采样 ~1.7s
        ← 约 1.5s 静默开销（VAE 解码 + 保存）
Prompt executed in ~5.0 seconds
```

采样仅占 1.7s，剩余 **~3.3s 全是静默开销**。对比 4 月 ComfyUI 0.19.x 下这部分仅约 0.5-1s，说明问题在 ComfyUI 0.20 的模型管理逻辑。

### 剩余变量排查

| 变量 | 4月（快） | 5月（慢） | 状态 |
|------|----------|----------|------|
| PyTorch | 2.10.0 | 2.10.0 | ✅ 已恢复 |
| ComfyUI | 0.19.x | 0.20.1 | ❓ 待验证 |
| comfy-aimdo | 0.2.12 | 0.2.14 | ❓ 待验证 |
| 启动方式 | 桌面客户端 | PowerShell 脚本 | ❓ 待验证 |
| 工作流参数 | 960×1280, 8步 | 768×768, 5步 | ✅ 理论上更快 |

### 逐参数试验（PyTorch 2.10 环境）

每次重启 ComfyUI 图片后端后跑 3 张图取第二、三张暖机数据。

#### 基准：--disable-dynamic-vram（降级后默认）

```
采样速度: ~2.97 it/s | 暖机耗时: 5.05s
日志: Using async weight offloading with 2 streams
     Set vram state to: NORMAL_VRAM
     VAE load device: cuda:0, offload device: cpu, dtype: torch.bfloat16
```

#### 试验 1：关闭异步权重卸载（+ --disable-async-offload）

```
采样速度: ~3.09 it/s | 暖机耗时: 4.70s
日志: 无 "async weight offloading" 行
     Set vram state to: NORMAL_VRAM
     VAE load device: cuda:0, offload device: cpu, dtype: torch.bfloat16
```

**改善 0.35s**。async offload 的 CUDA stream 管理有少量开销，但非主因。

#### 试验 2：锁定模型在 GPU（--disable-dynamic-vram → --highvram）

```
采样速度: ~6.94 it/s | 暖机耗时: 3.79-3.87s
日志: Set vram state to: HIGH_VRAM
     VAE load device: cuda:0, offload device: cpu, dtype: torch.bfloat16
```

**改善 0.9s，采样速度翻倍**。关键发现：

- `--disable-dynamic-vram` 关掉了 DynamicVRAM 管理器，但仍使用 NORMAL_VRAM 模式，VAE 和 text encoder 在不用时仍可能被卸到 CPU
- `--highvram` 将所有模型锁死在 GPU，完全避免 CPU-GPU 数据搬运
- 采样从 3 it/s → 6.9 it/s 说明 GGUF 模型在 HIGH_VRAM 下避免了运行时 dequantize 的额外数据搬运
- VAE 仍标记 `offload device: cpu`（安全兜底），但实际未被卸载

#### 试验 3：关闭智能内存管理 + VAE 精度优化（+ --disable-smart-memory + --fp16-vae）

| 参数 | 作用 |
|------|------|
| `--disable-smart-memory` | 关闭 ComfyUI 0.20 新增的智能内存管理，防止不必要的逐层卸载 |
| `--fp16-vae` | VAE 解码使用 FP16 替代 bfloat16，RTX 4090 上 FP16 更快 |

待重启测试。

### 关键 GitHub Issue 引用

| Issue | 描述 | 关联度 |
|-------|------|--------|
| [ComfyUI#9082](https://github.com/Comfy-Org/ComfyUI/issues/9082) | 大量时间浪费在逐层卸载模型 | 🔴 直接相关 |
| [ComfyUI#10723](https://github.com/Comfy-Org/ComfyUI/issues/10723) | 内存管理变更导致模型被强制卸载到 CPU RAM，提交 `5ebcab3` 为嫌疑 | 🔴 直接相关 |
| [ComfyUI#11081](https://github.com/Comfy-Org/ComfyUI/issues/11081) | GGUF 模型 VRAM 利用率降至 45-55% | 🟡 部分相关 |
| [ComfyUI#11072](https://github.com/Comfy-Org/ComfyUI/issues/11072) | VAE 智能卸载不释放足够显存导致 GPU 显存换页到系统内存 | 🟡 部分相关 |

### 最终参数组合

```powershell
# scripts/comfyui/backend_common.ps1 Get-BackendArguments 函数
--highvram                  # 所有模型锁死在 GPU
--disable-async-offload     # 关闭异步权重卸载（减少 CUDA stream 开销）
--disable-smart-memory      # 关闭 ComfyUI 0.20 智能内存管理
--fp16-vae                  # VAE 使用 FP16（RTX 4090 更快）
```

对应 Git 提交：

| 提交 | 变更 |
|------|------|
| `789d939` | 新增 --disable-async-offload |
| `0a8cb60` | --disable-dynamic-vram → --highvram |
| （当前） | 新增 --disable-smart-memory + --fp16-vae |

### 日志验证要点

启动后检查以下日志行确认参数生效：

```
Set vram state to: HIGH_VRAM                    # --highvram 生效
# 无 "Using async weight offloading" 行         # --disable-async-offload 生效
VAE load device: cuda:0, offload device: cpu, dtype: torch.float16  # --fp16-vae 生效（bfloat16→float16）
```

暖机跑期望：

```
100%|██████████| 5/5 [00:00<00:00, 6.5+ it/s]   # 采样速度 > 6 it/s
Prompt executed in 2-3 seconds                    # 目标耗时
```

---

## Pixelle 层面修复

`pixelle_video/pipelines/standard.py` 中 `_schedule_stage_backend_restart_if_needed` 方法增加了 `restart_after_batch` 门控：
- 之前：在阶段边界无条件重启 ComfyUI 后端，导致每张图片后模型全部重载
- 之后：遵循 `restart_after_batch` 配置，设为 `false` 时保持后端存活

---

## 经验教训

1. **性能退化排查必须逐层分离变量**。本次同时发生 PyTorch 升级、ComfyUI 升级、启动方式切换三个变更，如果混在一起排查会误判根因。
2. **PyTorch 大版本升级前应先在非生产环境验证**。2.11 的多个已知退化在发布说明和 GitHub Issues 中已有报告。
3. **ComfyUI 启动参数在不同 PyTorch 版本下行为不同**。`--highvram` 在 PyTorch 2.11 下倒退到 10s，在 2.10 下却带来近 2x 加速。不能凭一次测试就标记"无效"。
4. **ComfyUI 桌面客户端和脚本启动的默认参数不同**。桌面客户端可能使用不同的 VRAM 管理策略。对齐全量启动参数是迁移启动方式时的必要步骤。
5. **RTX 4090 24GB 显存充足时，`--highvram` 是最优选择**。模型总占用约 11.5 GB（CLIP 4.4G + UNet 7G + VAE 0.16G），完全可常驻 GPU，无需任何卸载。

## 参考文献

- [PyTorch 2.11 Release Blog](https://pytorch.org/blog/pytorch-2-11-release-blog/)
- [Inductor over-fusion regression](https://github.com/pytorch/pytorch/issues/179423)
- [ComfyUI GGUF VRAM under-utilization](https://github.com/Comfy-Org/ComfyUI/issues/11081)
- [torch.compile VRAM regression](https://github.com/pytorch/pytorch/issues/175058)
- [torch.compile custom ops broken](https://github.com/pytorch/pytorch/issues/180642)
- [ComfyUI layers offloading waste](https://github.com/Comfy-Org/ComfyUI/issues/9082)
- [ComfyUI memory changes cause offload to CPU](https://github.com/Comfy-Org/ComfyUI/issues/10723)
- [ComfyUI VAE smart offload VRAM insufficient](https://github.com/Comfy-Org/ComfyUI/issues/11072)
