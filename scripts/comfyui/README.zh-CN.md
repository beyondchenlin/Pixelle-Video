# Pixelle ComfyUI 后端脚本

Pixelle 默认管理完整的本地 ComfyUI 服务：图片或音频工作流需要时启动，完整批次
结束且队列为空后停止，下一批本地工作流再按需启动。进程退出是释放显存和系统内存
的边界，不依赖插件私有的释放接口。

本目录脚本负责完整服务的启动、检查和停止。服务使用已配置的 ComfyUI 核心、前端、
模型目录和数据目录；它不会创建 ComfyUI Desktop 窗口，但运行期间仍可通过浏览器
查看队列、历史和生成内容。推荐配置使用两个按需端口：

```text
图片：http://127.0.0.1:8001
语音：http://127.0.0.1:8002
```

## 生命周期模式

- 推荐按需启停：`backend_management_mode: required`、`managed: true`、
  `stop_after_batch: true`。Pixelle 只停止经过进程身份验证、由自己启动的完整服务。
- 推荐保留 `resource_policy: auto`，并省略 `minimum_free_commit_gb`。Windows 托管服务
  只关闭锁页内存，保留批次内必需的异步模型卸载和执行缓存；启动门槛会根据系统提交上限
  自动计算为 2 至 6 GiB 的操作系统安全余量。该门槛不冒充未知工作流的内存需求估算。
- 外部连接：`backend_management_mode: disabled`。用户先手动启动实例，Pixelle 只检测
  连接和提交任务，绝不停止外部服务。
- 自动复用：`backend_management_mode: auto`。此模式可复用外部服务，因此无法保证批次
  结束后彻底释放内存。

桌面外壳和 ComfyUI 核心服务是两个生命周期层。按需启停管理的是提供生成能力的完整
核心服务；服务运行时通过浏览器地址查看界面，停止后该地址随服务一起退出。

## Windows 双击入口

Windows 默认双击 `.ps1` 文件通常会打开编辑器或记事本，这是系统安全策略，不建议修改文件关联。

需要双击运行时，请使用同目录下的 `.bat` 文件：

```text
check_backend.bat
start_backend.bat
stop_backend.bat
```

双击 `.bat` 文件会真正执行对应命令，而不是打开脚本源码。

通用 `.bat` 文件默认读取 `workflow_routing.default` 指向的配置；图片和语音入口分别读取 `image` 与 `tts` 配置。等价命令为：

```powershell
uv run python -m scripts.comfyui.backend_cli start --profile image
uv run python -m scripts.comfyui.backend_cli check --profile tts
uv run python -m scripts.comfyui.backend_cli stop --profile tts
```

命令结束后窗口会停留，方便查看输出。

## PowerShell 命令

`.ps1` 是底层维护入口，不会读取 `config.yaml`。只有需要显式覆盖全部路径时才直接调用，例如：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\comfyui\start_backend.ps1 `
  -PythonExe 'E:\ComfyUIData\.venv\Scripts\python.exe' `
  -ComfyUIRoot 'E:\comfyui\resources\ComfyUI' `
  -DataRoot 'E:\ComfyUIData\pixelle' `
  -SharedBasePath 'E:\ComfyUIData'
```

`start_backend.ps1` 会以无界面后台方式运行，刻意避免传入 `--log-stdout` 和
`--enable-manager`，并将 stdout / stderr 重定向到：

```text
logs\comfyui\
```

相对的运行目录和日志目录始终按项目根目录解析。每次启动会归档上一次后端日志和监督进程
错误日志，每类最多保留 20 份；监督进程提前退出时，启动命令会立即返回退出码和受限长度的
日志尾部，不再无意义地等待完整超时时间。

## 默认配置

- ComfyUI Python：`E:\ComfyUIData\.venv\Scripts\python.exe`
- ComfyUI 根目录：`E:\comfyui\resources\ComfyUI`
- 图片数据目录：`E:\ComfyUIData\pixelle-image`
- 语音数据目录：`E:\ComfyUIData\pixelle-tts`
- 共享模型与插件目录：`E:\ComfyUIData`
- 前端资源目录：默认不覆盖，使用 ComfyUI 自带前端；仅在明确配置时传入
- 图片监听地址：`127.0.0.1:8001`
- 语音监听地址：`127.0.0.1:8002`
- 运行状态、日志和数据库均按 `image`、`tts` 配置隔离

## 配置覆盖

可以通过脚本参数或环境变量覆盖默认值：

```powershell
$env:PIXELLE_COMFYUI_PYTHON = 'E:\ComfyUIData\.venv\Scripts\python.exe'
$env:PIXELLE_COMFYUI_ROOT = 'E:\comfyui\resources\ComfyUI'
$env:PIXELLE_COMFYUI_DATA_ROOT = 'E:\ComfyUIData\pixelle'
$env:PIXELLE_COMFYUI_SHARED_BASE_PATH = 'E:\ComfyUIData'
$env:PIXELLE_COMFYUI_FRONTEND_ROOT = 'E:\comfyui\resources\ComfyUI\web_custom_versions\desktop_app'
$env:PIXELLE_COMFYUI_DATABASE_URL = 'sqlite:///E:/ComfyUIData/pixelle/user/comfyui.db'
$env:PIXELLE_COMFYUI_PORT = '8001'
```

默认不传入 `--enable-cors-header *`。Pixelle 通过服务端访问 ComfyUI，不需要向任意网页来源开放本机接口。

`start_image_backend.bat`、`start_tts_backend.bat` 及对应检查、停止文件分别操作 `image` 与 `tts` 配置。每个配置可用 `custom_node_loading: allowlist` 限制插件；启动器会先禁用全部自定义节点，再只加载 `allowed_custom_node_folders` 中列出的目录。瞬时启动超时在首次失败后默认再重试三次，配置、路径、端口和内存错误不会盲目重试。本机所有登录会话共用一个系统互斥锁，因此图片与语音后端不能同时占用显卡。

白名单模式按照 ComfyUI 自身的路径规则计算实际生效的 `custom_nodes` 根目录，包括 `--base-directory`、程序自带的 `extra_model_paths.yaml` 和显式传入的额外模型路径配置。最终必须只有一个实际生效的插件根目录：没有被注册的程序目录副本不会造成误报；真正注册第二个插件根目录时，启动器会在执行插件代码前拒绝启动。白名单只是插件选择机制，不是安全沙箱；获准加载的插件仍会在 ComfyUI 进程中执行代码。

如果配置端口已被非托管进程占用，`start_backend.ps1` 会拒绝启动新的 ComfyUI 后端，而不是自动漂移到其他端口。

`stop_backend.ps1` 只会停止同时满足进程号、进程创建时间和当前配置三重校验的后端。配置校验覆盖完整启动参数以及程序自带、显式传入的额外路径配置内容；启动期间配置发生变化时，新进程会被停止并要求重试，已经运行的进程也不会被误认成新配置。PID 文件缺失、非法、陈旧、缺少所有权凭证或指向其他进程时只清理无效记录，绝不根据命令行相似性终止监听进程。这样既能防止 Windows 复用进程号造成误杀，也能安全隔离不同的数据目录、数据库和插件路径配置。

从不含所有权凭证的旧版本升级时，现有进程按外部进程处理。`auto` 模式会继续复用，`required` 模式需要先手动关闭旧进程，再由当前版本启动一次以生成新凭证。
