# HyperFrames Render 依赖与下载说明

## 对应工作流路径

- 标准管线入口：`pixelle_video/pipelines/standard.py`
- HyperFrames Node Bridge：`tools/hyperframes_bridge/src/render.mjs`
- HyperFrames 参考模板：`resources/hyperframes/templates/image_life_insights_light/`
- 对齐服务：`pixelle_video/services/alignment_service.py`
- 可选静音裁剪服务：`pixelle_video/services/audio_edit_service.py`

## 本次核对范围与结论

- 核对日期：`2026-04-22`
- 已核对本地存在：
  - `resources/hyperframes/templates/image_life_insights_light/index.html`
  - `tools/hyperframes_bridge/src/render.mjs`
  - `tools/hyperframes_bridge/package.json`
- 已核对本机命令可执行：
  - `node --version` -> `v24.12.0`
  - `npm --version` -> `11.6.2`
  - `ffmpeg -version` -> 可执行
  - `.venv\Scripts\python.exe -m ensurepip --version` -> `pip 25.0.1`
- 已核对远端地址可访问：
  - ModelScope：`https://www.modelscope.cn/models/Qwen/Qwen3-ForcedAligner-0.6B` -> HTTP `200`
  - PyPI：`https://pypi.org/project/qwen-asr/` -> HTTP `200`
  - PyPI：`https://pypi.org/project/auto-editor/` -> HTTP `200`
  - auto-editor 安装页：`https://auto-editor.com/installing` -> HTTP `200`
  - npm registry：`https://registry.npmjs.org/@hyperframes%2Fproducer/0.4.11` -> 已返回包元数据
- 说明：
  - 本次任务未执行大模型下载。
  - 本次任务未执行 `npm install` 拉包。
  - 本文中的下载地址与安装命令已经做过“页面或元数据可访问 / 命令可执行”级别核对，但不应表述为“已完成下载”。

## 节点与依赖清单

### 1. 最终渲染

- 节点/模块：`HyperFramesRenderer`
- 作用：调用 Node bridge，把 `render_manifest.json + captions.json + 模板 shell` 渲染成最终 MP4
- 关键依赖：
  - Node.js `>=22`
  - npm
  - `@hyperframes/producer@0.4.11`
  - FFmpeg

### 2. 模板层

- 节点/模块：`image_life_insights_light`
- 作用：承载 HyperFrames 参考 shell、标题区、布局、字幕 composition
- 关键依赖：
  - `resources/hyperframes/templates/image_life_insights_light/index.html`
  - `resources/hyperframes/templates/image_life_insights_light/compositions/captions.html`

### 3. 文本对齐

- 节点/模块：`AlignmentService`
- 作用：把已知句子文本对回 block TTS 音频，恢复句级时间戳
- 关键依赖：
  - Python 包：`qwen-asr`
  - 模型：`Qwen/Qwen3-ForcedAligner-0.6B`

### 4. 可选静音裁剪

- 节点/模块：`AudioEditService`
- 作用：当 `silence_trim_tool == "auto_editor"` 时导出 edit timeline，并把句级时间映射到裁剪时间线
- 关键依赖：
  - Python 包 / CLI：`auto-editor`

## 依赖分类

| 分类 | 名称 | 是否必需 | 说明 |
| --- | --- | --- | --- |
| Node 运行时 | Node.js `>=22` | 必需 | `tools/hyperframes_bridge/package.json` 明确要求 |
| Node 包 | `@hyperframes/producer@0.4.11` | 必需 | HyperFrames 渲染核心依赖 |
| 系统工具 | FFmpeg | 必需 | 现有视频/音频处理与渲染链都会用到 |
| Python 包 | `qwen-asr` | 必需 | 默认对齐客户端依赖 |
| 模型文件 | `Qwen/Qwen3-ForcedAligner-0.6B` | 必需 | forced alignment 模型，按仓库规则优先 ModelScope |
| Python 包 / CLI | `auto-editor` | 可选 | 仅在启用静音裁剪 remap 时需要 |
| 仓库内模板 | `image_life_insights_light` | 必需 | 当前 HyperFrames V1 参考模板 |

## 目标目录

| 依赖 | 目标目录 | 备注 |
| --- | --- | --- |
| HyperFrames bridge npm 包 | `tools/hyperframes_bridge/node_modules/` | 不要提交到 Git |
| HyperFrames 参考模板 | `resources/hyperframes/templates/image_life_insights_light/` | 已在仓库内 |
| qwen forced aligner 模型（默认缓存） | `%USERPROFILE%\\.cache\\modelscope\\hub\\Qwen\\Qwen3-ForcedAligner-0.6B\\` | 使用 ModelScope 默认缓存时 |
| qwen forced aligner 模型（离线固定路径，可选） | `models/qwen/Qwen3-ForcedAligner-0.6B/` | 需要自行在服务初始化时传入路径 |
| auto-editor 可执行文件 | 当前 Python 环境的 `Scripts/` 或系统 PATH | 不要求放到仓库内 |

## 下载优先级

1. 模型文件优先使用 `ModelScope`
2. `ModelScope` 缺失或不可用时，回退到 `Hugging Face`
3. Python 包优先官方 PyPI
4. Node 包优先官方 npm registry

## ModelScope 检索或主地址

### Qwen3 Forced Aligner

- ModelScope 主地址：
  - `https://www.modelscope.cn/models/Qwen/Qwen3-ForcedAligner-0.6B`
- 检索关键词：
  - `Qwen3-ForcedAligner-0.6B`
  - `Qwen/Qwen3-ForcedAligner-0.6B`
- 备用地址：
  - `https://huggingface.co/Qwen/Qwen3-ForcedAligner-0.6B`
- 备注：
  - 当前代码默认模型 ID 就是 `Qwen/Qwen3-ForcedAligner-0.6B`
  - 如果使用离线路径，需要在服务初始化时覆盖 `model_path`

## 安装命令

### 1. HyperFrames Node 依赖

```powershell
cd tools/hyperframes_bridge
npm install
```

### 2. qwen-asr

说明：
- 当前仓库默认配置使用 `render_backend = legacy` 与 `subtitle_alignment_engine = qwen_forced_aligner`
- 如果要切换到新的 compiled HyperFrames 链路，必须显式设置 `render_backend = hyperframes_compiled`
- 因此 `qwen-asr` 已提升为项目基础依赖，常规 `uv sync` 应直接安装到当前环境
- 如果当前环境缺失，可按下面命令补装

优先使用仓库环境同步：

```powershell
uv sync
```

如果当前虚拟环境有 `pip`：

```powershell
.venv\Scripts\python.exe -m pip install -U qwen-asr
```

如果当前虚拟环境没有 `pip`，先补齐：

```powershell
.venv\Scripts\python.exe -m ensurepip --upgrade
.venv\Scripts\python.exe -m pip install -U qwen-asr
```

### 3. auto-editor（可选）

```powershell
.venv\Scripts\python.exe -m pip install -U auto-editor
```

### 4. ModelScope 客户端（仅在需要命令行下载模型时）

```powershell
.venv\Scripts\python.exe -m pip install -U modelscope
```

### 5. 使用 ModelScope 下载 `Qwen/Qwen3-ForcedAligner-0.6B`

说明：
- 以下命令是推荐下载方式。
- 本次任务未实际执行下载，因此这里只标注为“已核对地址与命令形态”，不是“已完成下载”。

```powershell
.venv\Scripts\python.exe -m modelscope.cli.cli download --model Qwen/Qwen3-ForcedAligner-0.6B --local_dir models/qwen/Qwen3-ForcedAligner-0.6B
```

### 6. Hugging Face 回退下载命令

仅在 `ModelScope` 缺失对应资源或不可用时使用：

```powershell
.venv\Scripts\python.exe -m pip install -U "huggingface_hub[cli]"
huggingface-cli download Qwen/Qwen3-ForcedAligner-0.6B --local-dir models/qwen/Qwen3-ForcedAligner-0.6B
```

## 验证命令

### 1. 磁盘空间预检查

```powershell
Get-PSDrive -Name C | Select-Object Used,Free
```

本次核对结果：

- `Free = 89123835904`，约 `83.00 GiB`

### 2. Node / npm / FFmpeg

```powershell
node --version
npm --version
ffmpeg -version
```

### 3. 仓库内 HyperFrames 关键文件

```powershell
Test-Path resources\hyperframes\templates\image_life_insights_light\index.html
Test-Path tools\hyperframes_bridge\src\render.mjs
```

### 4. HyperFrames bridge 自测

```powershell
cd tools/hyperframes_bridge
node --test tests/render.test.mjs
```

### 5. 标准管线 HyperFrames 分支测试

```powershell
cd D:\demo1\Pixelle\Pixelle
.venv\Scripts\python.exe -m pytest tests/test_standard_pipeline_hyperframes_mode.py -q
```

### 6. 服务初始化联通性测试

```powershell
cd D:\demo1\Pixelle\Pixelle
.venv\Scripts\python.exe -m pytest tests/test_hyperframes_renderer.py::test_initialize_wires_hyperframes_services -q
```

### 7. 模型下载后的存在性与大小检查

下载完成后再执行：

```powershell
Test-Path models\qwen\Qwen3-ForcedAligner-0.6B
Get-ChildItem models\qwen\Qwen3-ForcedAligner-0.6B -Recurse | Select-Object FullName,Length
```

校验要求：

- 目录必须存在
- 至少应包含模型权重、配置文件、tokenizer 或 processor 相关文件
- 文件大小应明显大于“只有配置无权重”的异常情况

## 常见问题

### 1. 为什么 HyperFrames 分支还要保留 shell-only 合成图？

- 这是为了保留迁移产物与模板壳层调试入口。
- 但 `visual_clips` 默认应指向原始媒体资源（`frame.image_path / frame.video_path`），不要把整张 shell PNG 再塞回 HyperFrames visual track。

### 2. 为什么没有要求下载 ComfyUI 的 `diffusion_models` / `vae`？

- 本文只覆盖 HyperFrames render path 的新增依赖。
- 现有 ComfyUI 图像/视频生成依赖仍按各自工作流文档处理。

### 3. 如果 `.venv` 里没有 `pip` 怎么办？

- 本机已验证 `.venv\Scripts\python.exe -m ensurepip --version` 可执行。
- 先运行：

```powershell
.venv\Scripts\python.exe -m ensurepip --upgrade
```

### 4. 如果 `ModelScope` 可访问但下载速度慢怎么办？

- 仍然应该先走 `ModelScope`，不要直接跳到 Hugging Face。
- 只有在 `ModelScope` 缺失该模型或当前不可用时，才切换到 Hugging Face。

### 5. `tools/hyperframes_bridge/node_modules/` 需要提交吗？

- 不需要。
- 本仓库任务也明确要求不要把 `tools/hyperframes_bridge/node_modules/` 纳入提交范围。

## 2026-04-22 编译式 HyperFrames 新规则

- `hyperframes_compiled` 现在走 compiled-project 路径，Pixelle 会先在任务目录下编译出可直接渲染的 `index.html` 与 `compositions/captions.html`，再交给 Node bridge 渲染。
- runtime-critical 文件禁止依赖运行时 `fetch("./data/render_manifest.json")`、Google Fonts、CDN 脚本或其他公网资源。
- phase-1 模板的本地字体入口统一为 `resources/hyperframes/runtime/fonts/phase1_fonts.css`。
- phase-1 模板如需运行时库，只能放在 `resources/hyperframes/runtime/vendor/`，不得临时改回公网脚本地址。
- `@hyperframes/producer` 是运行时真源；`vendor` 目录只承担模板依赖与升级对照责任，不替代 producer 包本身。
- `data/render_manifest.json` 与 `data/captions.json` 仍然保留，但它们属于诊断输出，不再是运行时是否可渲染的前提条件。
