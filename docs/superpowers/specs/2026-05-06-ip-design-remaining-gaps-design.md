# IP 设计剩余缺口 — 现状评估

## 背景

基于 `docs/IP设计整体链路与提示词融合方案.md` 的蓝图，对代码库进行全量审计后，IP 系统核心基础设施完成度超出预期。本文聚焦**剩余缺口**，为后续执行计划提供依据。

## 已完成的基础设施（摘要）

| 层级 | 已完成 |
|------|--------|
| 数据模型 | IPProfile（40字段）、AssetBible、SceneCast、IPFrameAdaptationPackage、IPImageTextPlan、IPPresenceType 枚举 |
| 规划引擎 | IPUsagePlanner（确定性） + IPFrameAppearancePlanner（LLM+回退）含 6 领域服装/姿势/动作映射 |
| 管线集成 | 标准管线 `_resolve_ip_prompt_chain_inputs()` → `_enrich_prompt_contexts_with_ip()` → `_ip_identity_prompt_terms_from_context()` |
| API | AssetBible CRUD + SceneCast CRUD + PromptPlan 投影/应用 + 预设导入 |
| UI | IP 设计工作台（7 大编辑区块）、IP 工作台面板、IP 提示词链控件、内容 IP 世界控件 |
| 安全 | `_HEX_COLOR_RE` 色号拒绝、`_NO_JSON_NO_PARAMS_RE` JSON/参数拒绝、`_RESERVED_PROMPT_PROJECTION_METADATA_KEYS` 元数据防护 |

## 剩余缺口

### 缺口 1: 测试覆盖（P0）

当前零自动化测试覆盖 IP 管线：
- 6 种 IPPresenceType 模式无回归
- 色号泄漏无回归
- 文字白名单无回归
- IP 适配包生成无验证
- 提示词权重控制无测试

### 缺口 2: ip_presence_type 不可手动选择（P1）

- `ip_presence_type` 由 IPUsagePlanner 自动裁决
- `FramePlan` 无此字段
- Storyboard Workbench 无下拉选择器

### 缺口 3: PromptPlan 缺少 IP 分段（P1）

- `prompt_sections` 中无 `ip_appearance`、`ip_negative`、`ip_text_whitelist`
- IP 适配贡献不可追溯

### 缺口 4: ComfyKit 管线不支持 IP（P1）

- action_transfer / digital_human / i2v 不经过 ImagePromptComposer
- 三条管线对 IP 完全无感知

### 缺口 5: IP 创建体验（P2）

- 仅支持手动表单编辑
- 缺少自然语言生成、图片反推、AI Chat 修改

### 缺口 6: IP 版本管理（P2）

- 无标准化版本字段
- 无版本历史 UI

## 关联文件

| 组件 | 关键路径 |
|------|---------|
| IPFrameAdaptationPackage | `pixelle_video/models/ip_prompt_planning.py` |
| IPUsagePlanner | `pixelle_video/services/ip_usage_planner.py` |
| IPFrameAppearancePlanner | 同上 |
| 标准管线 IP 注入 | `pixelle_video/utils/content_generators.py` |
| PromptPlan | `pixelle_video/models/prompt_plan.py` |
| FramePlan | `pixelle_video/models/storyboard_planning.py` |
| IP 设计工作台 UI | `web/components/ip_design_workbench.py` |
| IP 工作台面板 | `web/components/ip_workbench_panel.py` |
| IP 提示词链控件 | `web/components/ip_prompt_chain_controls.py` |
| 内容 IP 世界控件 | `web/components/content_ip_world_controls.py` |
| Storyboard 预览 | `web/components/storyboard_preview.py` |
| ComfyKit 管线 | `web/pipelines/action_transfer.py`, `digital_human.py`, `i2v.py` |
