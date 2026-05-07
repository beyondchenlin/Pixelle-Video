# IP 设计剩余缺口 — 分阶段执行计划

## Phase 0: 测试补全（P0，3-5 天）

> 建立 IP 管线回归测试安全网

```
tests/
├── test_ip_presence_modes.py          # 6 种 presence 模式判定逻辑
├── test_ip_color_safety.py            # 色号不入提示词回归
├── test_ip_text_whitelist.py          # 文字白名单回归
├── test_ip_adaptation_package.py      # IPFrameAdaptationPackage 生成
├── test_ip_prompt_integration.py      # 提示词组装中 IP 术语注入
└── test_ip_pipeline_e2e.py            # 端到端：AssetBible → PromptPlan
```

### 测试场景清单

1. **出场模式测试（test_ip_presence_modes.py）**
   - 受保护主体（佛祖/历史建筑/真实人物） → `absent` 或 `low_intrusion`
   - 风景空镜 → `symbolic_only`
   - 主角帧 → `strong_identity`
   - 叙述/讲解帧 → `balanced_narrative`
   - 开场建立场景 → `scene_integrated`
   - 6 种模式全部覆盖

2. **色号安全测试（test_ip_color_safety.py）**
   - `#FFFFFF` 不出现在 `final_prompt` 中
   - `#5A2A12` 不出现在 `body_prompt` / `tie_prompt` 中
   - 自然语言颜色描述（"纯白色身体"）正确出现在提示词中
   - `color_palette.*_hex` 可包含色号（仅内部使用）

3. **文字白名单测试（test_ip_text_whitelist.py）**
   - `visible_text_whitelist` 内文字可出现在提示词中
   - 白名单外文字被拦截
   - `text_safety_rules` 被编译为负向约束

4. **适配包测试（test_ip_adaptation_package.py）**
   - `IPFrameAdaptationPackage` 包含所有必需字段
   - `appearance_description` 非空（当 IP 出场时）
   - `identity_anchors_visible` 包含核心锚点
   - `negative_constraints` 非空

5. **提示词注入测试（test_ip_prompt_integration.py）**
   - `_enrich_prompt_contexts_with_ip()` 正确注入 `ip_adaptation` 到 context
   - `_ip_identity_prompt_terms_from_context()` 正确追加到最终提示词
   - `PromptPlan.metadata` 包含 `ip_presence_type`、`image_text_plan`

6. **端到端测试（test_ip_pipeline_e2e.py）**
   - 创建 AssetBible → SceneCast → 调用 IPUsagePlanner → 检查 IPFrameAdaptationPackage
   - 验证 `appearance_description` 流向 `final_prompt`

### 验证

```bash
pytest tests/test_ip_presence_modes.py tests/test_ip_color_safety.py \
       tests/test_ip_text_whitelist.py tests/test_ip_adaptation_package.py \
       tests/test_ip_prompt_integration.py tests/test_ip_pipeline_e2e.py -v
```

---

## Phase 1: IP 出场类型 UI 可选（P1，3-5 天）

### 1.1 FramePlan 扩展

**文件**: `pixelle_video/models/storyboard_planning.py`

```python
@dataclass(frozen=True)
class FramePlan:
    # ... 现有字段 ...
    ip_presence_type: str | None = None  # 新增
```

- 更新 `to_dict()` / `from_dict()`
- 默认 `None` 表示自动裁决

### 1.2 IPUsagePlanner 适配

**文件**: `pixelle_video/services/ip_usage_planner.py`

- `plan_frame()` 方法开头检查 `frame_context.ip_presence_type`
- 如果非空，跳过 `_presence_type_for_frame()` 裁决，直接映射为 `IPPresenceType`

### 1.3 UI 控件

**文件**: `web/components/storyboard_preview.py`

- `build_storyboard_preview_rows()` 提取 `ip_presence_type` 作为可编辑值
- 每帧行添加 `st.selectbox`，6 个选项：
  - `strong_identity` — 强身份锁定
  - `balanced_narrative` — 平衡叙事
  - `scene_integrated` — 场景融入
  - `low_intrusion` — 低侵入陪伴
  - `symbolic_only` — 符号化
  - `absent` — 不出场
- 锁定时纳入 `locked_fields`

### 1.4 Storyboard Workbench 集成

**文件**: `web/pages/4_🧭_Storyboard_Workbench.py`

- `build_storyboard_override_snapshot_identity()` 将 `ip_presence_type` 纳入快照
- 重生成时传递手动选择的 `ip_presence_type`

### 验证

- 手动测试：Home 生成 → Workbench 手动选择出场类型 → 锁定 → 重新生成 → 锁定未变
- 检查 FramePlan 持久化 `ip_presence_type`

---

## Phase 2: PromptPlan 可追溯性增强（P1，2-3 天）

### 2.1 prompt_sections 扩展

**文件**: `pixelle_video/utils/content_generators.py`

组装提示词后将 IP 分段写入 prompt_sections：

```python
prompt_sections["ip_appearance"] = ip_appearance_description
prompt_sections["ip_negative"] = ip_negative_constraints
prompt_sections["ip_text_whitelist"] = json.dumps(visible_text_whitelist)
```

### 2.2 build_prompt_plan_bundle 适配

**文件**: `pixelle_video/services/prompt_plan_service.py`

- 从 `planning_snapshot.ip_adaptations_by_frame` 提取 IP 数据
- 将 IP 分段写入每个 `PromptPlan.prompt_sections`

### 2.3 Storyboard Workbench 预览增强

**文件**: `web/components/storyboard_preview.py`

- PromptPlan 详情展开时显示 IP 分段
- `ip_appearance` / `ip_negative` / `ip_text_whitelist` 三段独立展示

### 验证

- 生成后调用 API 检查 `PromptPlan.prompt_sections` 包含新字段
- Workbench 中展开查看 IP 分段

---

## Phase 3: ComfyKit 管线 IP 支持（P1，2-3 天）

### 3.1 IP 配置控件

**文件**: `web/pipelines/action_transfer.py`, `digital_human.py`, `i2v.py`

- 复用 `web/components/ip_prompt_chain_controls.py` 添加 IP 选择 UI
- 添加 `ip_enabled` / `ip_asset_bible_id` / `ip_profile_id` 参数到 `video_params`

### 3.2 IP 适配生成与注入

在管线 UI 层（`render_pipeline_ui()` 或生成函数内）：
- 如果 `ip_enabled`：
  1. 加载 AssetBible 和 IPProfile（复用 `_resolve_ip_prompt_chain_inputs` 逻辑）
  2. 实例化 `IPFrameAppearancePlanner` 生成适配包
  3. 将 `appearance_description` 注入到 ComfyUI workflow 的 prompt 参数
  4. 将 `negative_constraints` 合并到 workflow 的 negative_prompt

### 3.3 分镜捕获增强

- 生成 IP 适配后，将 `planning_snapshot` 写入 `task_dir/storyboard.json`
- `capture_snapshot_from_task_dir()` 可正常捕获

### 验证

- 从 action_transfer / digital_human / i2v 生成 → 检查 workflow 参数包含 IP 描述
- 生成后导航到 Storyboard Workbench → 验证有 IP 数据

---

## Phase 4: IP 创建体验增强（P2，5-7 天）

### 4.1 自然语言创建 IP

**新建**: `pixelle_video/services/ip_profile_generator.py`

- LLM 提示词模板：从自然语言描述提取结构化 IPProfile
- 输出：`identity_lock`、`identity_anchors`、`variable_slots`、`negative_constraints`、`color_palette`

**UI**: `web/components/ip_design_workbench.py`
- 新增"从描述生成"按钮和文本输入区
- 生成的草稿可手动调整后保存

### 4.2 图片反推 IP

**新建**: `pixelle_video/services/ip_profile_reverse.py`

- 调用视觉模型分析上传图片
- 提取角色身份锚点、主色配色、轮廓特征
- 生成 IPProfile 草稿

**UI**: `web/components/ip_design_workbench.py`
- 上传图片 → 反推生成 IPProfile → 手动调整 → 保存

### 4.3 IP 版本管理

**文件**: `pixelle_video/models/asset_bible.py`

- `IPProfile` 增加：
  - `version: int = 1`
  - `parent_version_id: str | None = None`
  - `version_note: str = ""`

**UI**: IP 设计工作台
- 版本历史时间线
- 版本对比（diff）
- 版本回退

### 验证

- 自然语言生成 IP → 检查字段完整性
- 图片上传反推 → 检查色彩/锚点准确性
- 保存多次 → 版本号递增 → 可查看历史
