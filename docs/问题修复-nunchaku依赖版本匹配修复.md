# 问题修复：nunchaku 依赖版本匹配修复

## 概述

2026/05/06 通过 `start_image_backend.bat` 启动 ComfyUI 时，发现 `ComfyUI-nunchaku` 插件的所有节点导入失败（`ImportError: DLL load failed while importing _C: 找不到指定的程序`）。根因是 nunchaku 安装版本与 PyTorch 版本不匹配。

## 现象

```
Node `NunchakuFluxDiTLoader` import failed:
ImportError: DLL load failed while importing _C: 找不到指定的程序。
...
共 8 类节点全部导入失败
```

ComfyUI 其他节点正常，服务正常监听 `127.0.0.1:8001`。

## 根因分析

| 组件 | 版本 | 来源 |
|------|------|------|
| nunchaku（已安装） | `1.2.1+cu13.0torch2.11` | GitHub Release |
| PyTorch（实际） | `2.10.0+cu130` | pytorch.org whl |

nunchaku 的 `_C.cp311-win_amd64.pyd`（260 MB C/CUDA 编译产物）是针对 PyTorch 2.11 编译的，链接了 torch 2.11 的 C++ 运行时 DLL。环境中 PyTorch 为 2.10.0，缺少对应 DLL，`ctypes.CDLL` 加载失败。

> **注意**：PyTorch 2.10.0 是刻意降级的版本，原因参见 [性能优化-PyTorch降级实现Z-Image出图性能提升](./性能优化-PyTorch降级实现Z-Image出图性能提升.md)。因此不能通过升级 PyTorch 解决此问题。

## 修复方案

1. 从 GitHub Release 下载匹配 PyTorch 2.10 的 nunchaku wheel
2. 使用 `--no-deps` 安装，避免 pip 自动升级 PyTorch

```bash
# 安装 nunchaku 1.2.1+cu13.0torch2.10（匹配 PyTorch 2.10.0+cu130）
pip install "https://github.com/nunchaku-tech/nunchaku/releases/download/v1.2.1/nunchaku-1.2.1+cu13.0torch2.10-cp311-cp311-win_amd64.whl" --no-deps --force-reinstall
```

## 连带修复

nunchaku 依赖链中的 `transformers>=4.54` 会引入 `protobuf>=7.0`，与 `descript-audiotools 0.7.4` 要求的 `protobuf<5.0.0` 冲突。修复：

```bash
pip install "protobuf>=3.19.6,<5.0.0,!=4.24.0" --no-deps --force-reinstall
```

## 验证

```bash
python -c "
import torch; print('PyTorch:', torch.__version__); print('CUDA:', torch.cuda.is_available())
import nunchaku; print('nunchaku OK')
from nunchaku._C.ops import gemm_awq, gemv_awq; print('_C.ops OK')
"
# 输出: PyTorch: 2.10.0+cu130 / CUDA: True / nunchaku OK / _C.ops OK

pip check
# 输出: No broken requirements found.
```

## 经验教训

- 安装编译类 Python 包（含 `.pyd`/`.so` 的 C/CUDA 扩展）时，必须确保其构建版本与当前 PyTorch/CUDA 版本精确匹配
- 使用 `pip install --force-reinstall` 时务必带 `--no-deps` 或显式 pin 住 torch 版本，否则 pip 解析器会将 torch 升级到最新版
- ComfyUI 的 `--base-directory` 共享数据根模式下，所有后端共享同一个 `.venv`，依赖变更的影响范围更大
