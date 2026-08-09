# 项目参考

本文件承载不需要每次会话常驻的项目地图、长链接和高风险路径说明。仓库级硬规则仍以根目录 `AGENTS.md` 为准。

## 主要路径

```text
pixelle_video/       核心领域模型、配置与服务
api/                 接口路由与服务入口
web/                 Streamlit 页面、组件与交互逻辑
tests/               Python 自动化测试
workflows/           ComfyUI 工作流事实文件
workflows/down/      工作流依赖、下载、安装与验证说明
tools/comfyui/       本地 ComfyUI 节点和配套工具
scripts/             项目运行、迁移与代理校验脚本
docs/                用户文档、设计说明和实施记录
```

## 项目入口

- 项目说明：`README.md`
- 中文文档入口：`docs/zh/index.md`
- 贡献指南：`docs/zh/development/contributing.md`
- 配置说明：`docs/zh/getting-started/configuration.md`
- 分支工作流：`docs/agent/branch-workflow.md`
- 任务写法：`docs/agent/prompting-workflow.md`

## 代理工作流来源

- 入口仓库：`https://github.com/oceans777/skills`
- 代理操作系统来源：`repos/oceans-skills/skills/agent-operating-system/`
- 本次搭建锁定入口提交：`05d640f4badb31a84abadf2e4420120e20c3228b`
- 本次搭建锁定技能子仓库提交：`9958fb786f3121b3da7b4062fd6929071c13c4d8`
- 配置契约见 `.oceans/agent-standards.conf`；升级时只创建缺失文件，不自动覆盖项目已经修改的文件。

## 生成目录与高风险路径

- `_runtime/`、`output/`、`temp/`、`logs/`、缓存和测试输出属于本地运行产物，默认不提交。
- `.env`、`config.yaml`、`extra_models_config.yaml`、密钥、令牌和真实账号信息属于敏感配置，禁止提交。
- `workflows/` 中由转换器生成的工作流必须修改事实源后重新生成，不直接修补生成结果。
- `.safetensors`、`.ckpt`、`.gguf`、`.pt`、`.pth`、`.onnx`、`.bin`、`.engine` 等模型文件属于大体积制品，禁止提交；下载前检查磁盘与目标加载目录，完成后验证文件大小、格式和工作流引用。
