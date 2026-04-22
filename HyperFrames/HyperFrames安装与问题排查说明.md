# HyperFrames安装与问题排查说明

## 适用范围

本文档基于当前项目目录 `D:\demo1\Pixelle\Pixelle\HyperFrames` 的实际安装过程整理，适用于在 Windows 电脑上部署、运行和扩展 HyperFrames。

本文重点记录两类内容：

1. 正常安装步骤
2. 本次实际遇到的问题、原因和可行替代方案

## 本次验证环境

- 操作系统：Windows
- Node.js：`v24.12.0`
- npm：`11.6.2`
- FFmpeg：已安装并可在命令行使用
- HyperFrames 项目目录：`D:\demo1\Pixelle\Pixelle\HyperFrames`

README 中要求：

- Node.js `>= 22`
- FFmpeg

## 推荐安装方式

如果网络正常，优先按 HyperFrames README 的手动初始化方式安装。

```powershell
npx hyperframes init my-video
cd my-video
npx hyperframes preview
npx hyperframes render
```

如果你已经在一个固定目录里准备好项目，也可以直接在目标目录执行初始化。

## 本次实际采用的安装方式

由于 GitHub 克隆在当前网络环境下多次失败，本次最终采用的是 README 的手动初始化方案，而不是先 `git clone` 再安装。

实际执行示例：

```powershell
cd D:\demo1\Pixelle\Pixelle
npx --yes hyperframes init HyperFrames
cd D:\demo1\Pixelle\Pixelle\HyperFrames
npx hyperframes preview
```

## 安装前检查

建议先确认以下命令都可用：

```powershell
node -v
npm -v
ffmpeg -version
```

如果 `ffmpeg` 无法识别，先安装 FFmpeg 再继续。

## 项目预览

在项目目录中运行：

```powershell
cd D:\demo1\Pixelle\Pixelle\HyperFrames
npx hyperframes preview
```

如果预览服务启动成功，可以在浏览器中打开本地地址，例如：

```text
http://127.0.0.1:3002
```

## 项目渲染

在项目目录中运行：

```powershell
cd D:\demo1\Pixelle\Pixelle\HyperFrames
npx hyperframes render . --workers 1
```

建议先使用 `--workers 1`，这样在 Windows 上更稳定，也更便于排查问题。

## 本次遇到的问题与解决方案

### 1. GitHub `git clone` 失败

现象：

- 克隆 `https://github.com/heygen-com/hyperframes` 时多次失败
- 报错包含 `Recv failure: Connection was reset`

原因：

- 当前网络环境下对 GitHub 连接不稳定

解决方案：

- 不依赖 `git clone`
- 改用 `npx hyperframes init` 直接初始化项目

推荐命令：

```powershell
npx --yes hyperframes init HyperFrames
```

### 2. `chrome-headless-shell` 自动下载失败

现象：

- `npx hyperframes render` 过程中尝试下载浏览器
- 报错包含 `ECONNRESET`、下载中断或找不到缓存文件

原因：

- HyperFrames 在渲染时需要可用的浏览器内核
- 自动下载浏览器依赖外网，网络不稳定时容易失败

解决方案：

- 手动下载 `chrome-headless-shell`
- 显式指定浏览器路径给 HyperFrames

本次已验证可用的浏览器路径：

```text
C:\Users\ai\Downloads\chrome-headless-shell-win64\chrome-headless-shell.exe
```

### 3. 永久浏览器环境变量未配置时，每次渲染都要手动指定

现象：

- 如果不设置环境变量，每次都要先执行：

```powershell
$env:HYPERFRAMES_BROWSER_PATH='C:\Users\ai\Downloads\chrome-headless-shell-win64\chrome-headless-shell.exe'
```

解决方案：

- 将 `HYPERFRAMES_BROWSER_PATH` 写成当前用户永久环境变量

推荐 PowerShell 命令：

```powershell
[Environment]::SetEnvironmentVariable(
  'HYPERFRAMES_BROWSER_PATH',
  'C:\Users\ai\Downloads\chrome-headless-shell-win64\chrome-headless-shell.exe',
  'User'
)
```

验证命令：

```powershell
[Environment]::GetEnvironmentVariable('HYPERFRAMES_BROWSER_PATH', 'User')
Get-ItemProperty -Path HKCU:\Environment -Name HYPERFRAMES_BROWSER_PATH
```

说明：

- 设置完成后，新开的 PowerShell 或终端会自动生效
- 已打开的旧终端需要关闭后重开

### 4. README 中的 Codex 插件命令在当前机器不可用

README 中的命令：

```powershell
codex plugin marketplace add heygen-com/hyperframes --sparse .codex-plugin --sparse skills --sparse assets
```

现象：

- 当前机器上的 `codex` CLI 不支持 `plugin marketplace`
- 会报类似 `unexpected argument 'marketplace' found`

原因：

- 当前安装的 Codex CLI 版本或分发方式不包含该子命令

解决方案：

- 不使用这条命令
- 改为手动安装 skill 到 Codex skills 目录

### 5. `npx skills add heygen-com/hyperframes` 也可能失败

现象：

- 执行 `npx skills add heygen-com/hyperframes` 时仍然访问 GitHub
- 网络不稳定时同样可能失败

原因：

- 该命令底层仍然需要从 GitHub 拉取内容

解决方案：

- 手动把 skill 安装到 `C:\Users\ai\.codex\skills\`

本次最终确认已安装好的 skill：

- `C:\Users\ai\.codex\skills\hyperframes`
- `C:\Users\ai\.codex\skills\hyperframes-cli`
- `C:\Users\ai\.codex\skills\gsap`

注意：

- 安装完 skill 后，通常需要重启一次 Codex 才能正式加载

### 6. 字体映射警告

现象：

- 渲染时可能出现类似 `No deterministic font mapping for ...`

原因：

- HyperFrames 会尽量把字体映射到确定可复现的字体
- 某些 Windows 字体不在它的默认映射表里

处理建议：

- 优先使用 HyperFrames 已知可映射字体
- 或者在项目里自行提供字体文件
- 如果只是警告而不是中断，通常仍可完成渲染

## 推荐的稳定渲染命令

在已经设置好永久环境变量后，推荐直接使用：

```powershell
cd D:\demo1\Pixelle\Pixelle\HyperFrames
npx hyperframes render . --workers 1
```

如果临时机器还没有永久环境变量，可以用：

```powershell
$env:HYPERFRAMES_BROWSER_PATH='C:\Users\ai\Downloads\chrome-headless-shell-win64\chrome-headless-shell.exe'
npx hyperframes render . --workers 1
```

## `chrome-headless-shell` 手动下载建议

如果自动下载失败，可以先手动下载并解压，再配置环境变量。

下载后目录中应至少包含：

- `chrome-headless-shell.exe`
- `locales`
- `resources`
- `icudtl.dat`

本次实际验证通过的目录示例：

```text
C:\Users\ai\Downloads\chrome-headless-shell-win64
```

可执行文件：

```text
C:\Users\ai\Downloads\chrome-headless-shell-win64\chrome-headless-shell.exe
```

## 建议的安装顺序

建议其他电脑按以下顺序执行：

1. 安装 Node.js 22 或更高版本
2. 安装 FFmpeg，并确认命令行可用
3. 使用 `npx hyperframes init` 初始化项目
4. 启动 `npx hyperframes preview` 验证预览
5. 如果渲染时报浏览器下载失败，手动下载 `chrome-headless-shell`
6. 配置永久环境变量 `HYPERFRAMES_BROWSER_PATH`
7. 再执行 `npx hyperframes render . --workers 1`
8. 如需在 Codex 中使用 skill，手动安装 skill 并重启 Codex

## 安装完成后的验证命令

### 验证浏览器环境变量

```powershell
[Environment]::GetEnvironmentVariable('HYPERFRAMES_BROWSER_PATH', 'User')
```

### 验证渲染

```powershell
cd D:\demo1\Pixelle\Pixelle\HyperFrames
npx hyperframes render . --workers 1
```

### 验证 skill 是否已落盘

```powershell
Get-ChildItem C:\Users\ai\.codex\skills
```

## 常见问题速查

### 问题：`git clone` 失败怎么办？

答：直接改用 `npx hyperframes init`。

### 问题：`render` 时自动下载浏览器失败怎么办？

答：手动下载 `chrome-headless-shell`，并设置 `HYPERFRAMES_BROWSER_PATH`。

### 问题：README 里的 `codex plugin marketplace add` 不能用怎么办？

答：当前机器上的 Codex CLI 不支持时，改为手动安装 skill 到 `C:\Users\ai\.codex\skills\`。

### 问题：设置了环境变量但当前终端还是不生效怎么办？

答：关闭当前终端，重新打开一个新的 PowerShell 窗口。

### 问题：渲染时出现字体映射警告怎么办？

答：优先换成 HyperFrames 可映射字体；如果只是警告且视频已正常输出，可以先继续使用。

## 本文档维护建议

如果后续在其他电脑上又遇到新的安装问题，建议继续补充：

- 具体报错原文
- 出现条件
- 最终可用的解决命令
- 是否已验证成功

这样这份文档就可以逐步变成团队内的标准安装说明。
