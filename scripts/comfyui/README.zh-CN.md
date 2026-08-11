# Pixelle ComfyUI 后端脚本

这些脚本用于运行一个由 Pixelle 托管的单实例 ComfyUI 后端，供本地 `selfhost` 工作流使用。
后端启动后仍然可以通过浏览器访问 GUI：

```text
http://127.0.0.1:8000
```

Pixelle 生成任务不需要打开 ComfyUI Desktop。建议把 ComfyUI Desktop 留给节点安装、模型管理和手工调试；Pixelle 生产生成使用这里的托管后端。

## Windows 双击入口

Windows 默认双击 `.ps1` 文件通常会打开编辑器或记事本，这是系统安全策略，不建议修改文件关联。

需要双击运行时，请使用同目录下的 `.bat` 文件：

```text
check_backend.bat
start_backend.bat
stop_backend.bat
```

双击 `.bat` 文件会真正执行对应命令，而不是打开脚本源码。

无参数运行 `.bat` 文件时，它会从项目根目录的 `config.yaml` 读取 `comfyui.backends.default`，再调用统一的生命周期管理器。等价命令为：

```powershell
uv run python -m scripts.comfyui.backend_cli start
uv run python -m scripts.comfyui.backend_cli check
uv run python -m scripts.comfyui.backend_cli stop
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

`start_backend.ps1` 会刻意避免传入 `--log-stdout` 和 `--enable-manager`，并将 stdout / stderr 重定向到：

```text
logs\comfyui\
```

## 默认配置

- ComfyUI Python：`E:\ComfyUIData\.venv\Scripts\python.exe`
- ComfyUI 根目录：`E:\comfyui\resources\ComfyUI`
- ComfyUI 数据目录：`E:\ComfyUIData\pixelle`
- 共享模型与插件目录：`E:\ComfyUIData`
- 前端资源目录：默认不覆盖，使用 ComfyUI 自带前端；仅在明确配置时传入
- 数据库 URL：`sqlite:///E:/ComfyUIData/pixelle/user/comfyui.db`
- 监听地址：`127.0.0.1:8000`
- 后端 PID 文件：`_runtime\comfyui\comfyui-backend.pid`
- 启动器 PID 文件：`_runtime\comfyui\comfyui-backend.launcher.pid`
- 所有权凭证：`_runtime\comfyui\comfyui-backend.owner.json`

## 配置覆盖

可以通过脚本参数或环境变量覆盖默认值：

```powershell
$env:PIXELLE_COMFYUI_PYTHON = 'E:\ComfyUIData\.venv\Scripts\python.exe'
$env:PIXELLE_COMFYUI_ROOT = 'E:\comfyui\resources\ComfyUI'
$env:PIXELLE_COMFYUI_DATA_ROOT = 'E:\ComfyUIData\pixelle'
$env:PIXELLE_COMFYUI_SHARED_BASE_PATH = 'E:\ComfyUIData'
$env:PIXELLE_COMFYUI_FRONTEND_ROOT = 'E:\comfyui\resources\ComfyUI\web_custom_versions\desktop_app'
$env:PIXELLE_COMFYUI_DATABASE_URL = 'sqlite:///E:/ComfyUIData/pixelle/user/comfyui.db'
$env:PIXELLE_COMFYUI_PORT = '8000'
```

默认不传入 `--enable-cors-header *`。Pixelle 通过服务端访问 ComfyUI，不需要向任意网页来源开放本机接口。

旧的 `start_image_backend.bat`、`start_tts_backend.bat` 及对应检查、停止文件只用于升级兼容，全部转发到同一个 `default` 后端，不会再创建第二个实例。

如果 `8000` 已被非托管进程占用，`start_backend.ps1` 会拒绝启动新的 ComfyUI 后端，而不是自动漂移到其他端口。

`stop_backend.ps1` 只会停止同时满足进程号、进程创建时间和当前配置三重校验的后端。PID 文件缺失、非法、陈旧、缺少所有权凭证或指向其他进程时只清理无效记录，绝不根据命令行相似性终止监听进程。这样既能防止 Windows 复用进程号造成误杀，也能安全复用由 ComfyUI Desktop 或其他管理器启动的同一后端。

从不含所有权凭证的旧版本升级时，现有进程按外部进程处理。`auto` 模式会继续复用，`required` 模式需要先手动关闭旧进程，再由当前版本启动一次以生成新凭证。
