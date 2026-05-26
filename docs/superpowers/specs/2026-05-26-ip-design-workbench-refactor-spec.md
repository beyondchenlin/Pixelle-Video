# IP Design Workbench 重构设计文档

> 基于四次根源级 Review 输出的系统性重构方案
> 审查日期：2026-05-26 | 审查轮次：2 次（架构完整性 + 状态管理/实现可行性）+ 2 次最佳实践修复

## 1. 问题陈述

IP Design Workbench（`3_IP_Design_Workbench.py`）当前存在架构与 UX 两个层面的根源问题：

### 架构层
- **无 UI 层领域模型**：763 行代码全部操作 `dict[str, Any]`，字段名是 magic string，无类型检查，无 IDE 补全
- **辅助函数跨 8 个文件重复**：`_text_input`、`_first_text`、`_list_of_dicts` 等至少在 ip_design_workbench.py、ip_workbench_panel.py、ip_prompt_chain_controls.py、asset_bible_draft_setup.py、content_ip_world_controls.py、storyboard_workbench_panel.py、asset_prompt_plan_projection.py、stale_panel.py 中各有一份
- **Session Key 无集中管理**：20+ `"ip_design_xxx"` 硬编码在组件内，`_clear_ip_form_session_state` 依赖手工维护的 preserve 集合
- **只编辑 IP Profile 一种资产**：AssetBible 实际含 5 种资产（ip_profiles、character_profiles、scene_assets、prop_assets、style_profiles），其余 4 种 UI 不可见
- **无删除/复制 API**：Protocol 只有 save/load，用户无法纠错
- **手工逐字段映射**：每个字段需在 model 定义、session key、populate、build、test 五处同步维护。这是最根本的债务——新增一个字段要改 5 个点。

### UX 层
- **无渐进式呈现**：20+ 字段平铺 9 个 container，没有核心/推荐/高级分层
- **无字段级验证反馈**：只显 "可用于生成/暂不可生成"，不告诉用户缺哪个字段
- **预设导入打断表单流**：内置 AssetBible 导入嵌在选择器和表单之间
- **SceneCast 无上下文关联**：storyboard_plan_id / frame_id 需手动输入
- **保存不刷新列表**：save 成功后页面不 rerun

## 2. 设计目标

1. **消除 `dict[str, Any]`** — 用 Pydantic model 定义 UI 层领域对象，所有新版代码返回 typed response
2. **DRY 辅助函数** — 统一到 `streamlit_helpers.py`
3. **Session Key 集中管理** — 一个 dataclass 定义所有 key
4. **补齐 5 种资产编辑** — 用 Tab 拆分
5. **渐进式呈现** — 三层（核心/推荐/高级）折叠结构
6. **字段级验证** — 实时显示每个字段缺失/就绪状态
7. **独立预设导入** — 移到 sidebar 或折叠区
8. **SceneCast 上下文关联** — 支持从 Storyboard 选取
9. **保存后自动刷新** — `st.rerun()` + toast
10. **删除/复制功能** — 带确认弹窗的完整 CRUD
11. **元编程自动映射** — populate/build 由字段定义驱动，无手工逐字段代码。新增字段只需改 model + session key 两处
12. **错误处理闭环** — 所有 client 调用有 typed 返回 + UI 级错误展示，无未捕获异常路径
13. **可回滚部署** — feature flag 控制新旧版本切换，灰度放量

## 3. 架构设计

### 3.1 分层架构

> **关键决策：** Client 层 `list_asset_bibles()` 和 `load_asset_bible()` 返回不同的响应类型（list 返回摘要列表，load 返回完整模型）。因此需要用两个不同的 Response model，而非统一使用 `AssetBibleDraft`。

```
┌─────────────────────────────────────────────┐
│               UI Layer (Streamlit)           │
│  pages/3_IP_Design_Workbench.py              │
│  components/ip_design_workbench.py (重构)     │
│  components/ip_workbench_panel.py (重构)      │
├─────────────────────────────────────────────┤
│         Domain Model Layer — NEW             │
│  ip_design/models.py                        │
│  ip_design/session_keys.py                  │
├─────────────────────────────────────────────┤
│         Client Abstraction Layer             │
│  ip_design/client.py (Protocol)             │
│  ip_design/http_client.py                    │
│  ip_design/inprocess_client.py               │
├─────────────────────────────────────────────┤
│            Utility Layer                     │
│  utils/streamlit_helpers.py (已有, 扩充)      │
│  utils/asset_bible_payloads.py               │
└─────────────────────────────────────────────┘
```

### 3.2 关键模型（Pydantic）

**约束：**
- 所有 model 继承 `BaseModel` 而非 `_DictCompatMixin`（无 `.get()` / `__getitem__` 兼容包装）
- 调用方必须使用属性访问（`model.field`），不允许 `model["field"]` 或 `model.get("field")`
- 存量 dict 消费者的迁移见 Step 0

```python
# web/ip_design/models.py
from typing import Any, Literal, Protocol
from pydantic import BaseModel, Field
from enum import Enum

# ── 字段标识符 Enum（替代 magic string） ──

class FieldId(str, Enum):
    """与 ReadinessReport.missing 匹配的字段标识符，支持 IDE 补全和 rename-safe。"""
    NAME = "name"
    IP_TYPE = "ip_type"
    LOGLINE = "logline"
    VISUAL_SUMMARY = "visual_summary"
    IDENTITY_LOCK = "identity_lock"
    MINIMAL_TRAITS = "minimal_traits"
    ADAPTABLE_SLOTS = "adaptable_slots"
    DEFAULT_SLOT_PREF = "default_slot_preference"
    PRESENCE_SPECTRUM = "presence_spectrum"
    ROLE_PRESETS = "role_presets"
    NEGATIVE_CONSTRAINTS = "negative_constraints"
    SEMANTIC_BOUNDARY = "semantic_boundary"
    ID_SUPPRESSION = "identity_suppression_rules"
    FORBIDDEN = "forbidden_elements"
    VISIBLE_TEXT = "visible_text_whitelist"

# ── 通用响应类型 ──

class TypedResponse(BaseModel):
    """所有 Client 方法的通用响应基类。"""
    success: bool
    message: str = ""
    errors: list[str] = []

class SaveResponse(TypedResponse):
    """save_asset_bible / save_scene_cast 的标准响应。"""
    pass

class DeleteResponse(TypedResponse):
    """delete_asset_bible / delete_scene_cast 的标准响应。"""
    pass

# ── 响应模型（Client 层返回值） ──

class AssetBibleSummary(BaseModel):
    """list_asset_bibles() 返回的摘要项，非完整加载。
    各资产列表仍为 list[dict] 因为这是 API 响应原始形状，
    但 AssetBibleSummary 本身是 typed 容器。"""
    asset_bible_id: str
    character_profiles: list[dict[str, Any]] = []
    scene_assets: list[dict[str, Any]] = []
    prop_assets: list[dict[str, Any]] = []
    style_profiles: list[dict[str, Any]] = []
    ip_profiles: list[dict[str, Any]] = []
    metadata: dict[str, Any] = {}

class ListAssetBiblesResponse(BaseModel):
    """list_asset_bibles() 的标准响应。"""
    success: bool = True
    asset_bibles: list[AssetBibleSummary] = []
    errors: list[str] = []

class ListSceneCastsResponse(BaseModel):
    """list_scene_casts() 的标准响应。"""
    success: bool = True
    scene_casts: list[dict[str, Any]] = []
    errors: list[str] = []

class PresetSummary(BaseModel):
    """list_asset_bible_presets() 的摘要项。"""
    preset_id: str
    display_name: str = ""
    description: str = ""

class ListPresetsResponse(BaseModel):
    success: bool = True
    presets: list[PresetSummary] = []
    errors: list[str] = []

class ImportPresetResponse(TypedResponse):
    asset_bible_id: str = ""

# ── 颜色调色板 ──
# ColorPalette 不定义为独立 model。它在 UI 层是纯透传的 dict，
# 直接由 build_color_palette_prompt_entries()（pixelle_video 核心库）管理。
# IPProfileDraft.color_palette 使用 dict[str, Any] 以保持与核心库兼容。

# ── 领域模型 ──

class IPProfileDraft(BaseModel):
    ip_profile_id: str
    name: str
    ip_type: Literal["cartoon_animal", "anime_human", "hybrid_real_anime",
                      "line_drawing", "3d_cartoon"] = "cartoon_animal"
    logline: str = ""
    visual_summary: str = ""
    identity_lock: list[str] = []
    color_palette: dict[str, Any] = Field(default_factory=dict)
    minimal_traits: list[str] = []
    adaptable_slots: list[str] = []
    default_slot_preference: Literal["prefer_supporting", "prefer_main",
                                      "auto", "minimal"] = "prefer_supporting"
    presence_spectrum: list[str] = []
    role_presets: list[str] = []
    negative_constraints: list[str] = []
    semantic_boundary: list[str] = []
    identity_suppression_rules: list[str] = []
    forbidden_elements: list[str] = []
    visible_text_whitelist: list[str] = []

class CharacterProfileDraft(BaseModel):
    character_id: str
    display_name: str = ""
    role: str = ""
    visual_description: str = ""
    personality: str = ""
    continuity_notes: list[str] = []

class SceneAssetDraft(BaseModel):
    scene_id: str
    display_name: str = ""
    visual_description: str = ""
    environment_notes: str = ""

class PropAssetDraft(BaseModel):
    prop_id: str
    display_name: str = ""
    visual_description: str = ""
    usage_notes: str = ""

class StyleProfileDraft(BaseModel):
    style_id: str
    display_name: str = ""
    visual_style: str = ""
    world_style: str = ""
    provider_prompt: str = ""
    negative_prompt: str = ""

class AssetBibleDraft(BaseModel):
    asset_bible_id: str
    ip_profiles: list[IPProfileDraft] = []
    character_profiles: list[CharacterProfileDraft] = []
    scene_assets: list[SceneAssetDraft] = []
    prop_assets: list[PropAssetDraft] = []
    style_profiles: list[StyleProfileDraft] = []

class SceneCastDraft(BaseModel):
    scene_cast_id: str
    storyboard_plan_id: str = ""
    frame_id: str = ""
    character_ids: list[str] = []
    scene_id: str = ""
    prop_ids: list[str] = []
    style_id: str = ""
    continuity_notes: list[str] = []

class ReadinessReport(BaseModel):
    """字段级验证报告。missing 使用 FieldId Enum，杜绝 magic string。"""
    ready: bool
    missing: list[FieldId] = []
    warnings: list[FieldId] = []
```

### 3.3 管理模式——IPSessionKeys 按类别拆分

> **决策：** 为避免 `form_keys()` 随字段新增而手工维护 `preserved` 集合，将 Keys 分为三个独立 dataclass，按用途自动归类。

```python
# web/ip_design/session_keys.py
from dataclasses import dataclass, fields

PREFIX = "ip_design"

@dataclass(frozen=True)
class _AssetBibleKeys:
    select: str = f"{PREFIX}_asset_bible_select"
    id: str = f"{PREFIX}_asset_bible_id"

@dataclass(frozen=True)
class _IPFormKeys:
    ip_profile_select: str = f"{PREFIX}_ip_profile_select"
    ip_profile_id: str = f"{PREFIX}_ip_profile_id"
    name: str = f"{PREFIX}_ip_name"
    ip_type: str = f"{PREFIX}_ip_type"
    logline: str = f"{PREFIX}_logline"
    visual_summary: str = f"{PREFIX}_visual_summary"
    identity_lock: str = f"{PREFIX}_identity_lock"
    color_rules: str = f"{PREFIX}_color_rules"
    minimal_traits: str = f"{PREFIX}_minimal_traits"
    adaptable_slots: str = f"{PREFIX}_adaptable_slots"
    default_slot_pref: str = f"{PREFIX}_default_slot_preference"
    presence_spectrum: str = f"{PREFIX}_presence_spectrum"
    role_presets: str = f"{PREFIX}_role_presets"
    negative_constraints: str = f"{PREFIX}_negative_constraints"
    semantic_boundary: str = f"{PREFIX}_semantic_boundary"
    id_suppression: str = f"{PREFIX}_identity_suppression_rules"
    forbidden: str = f"{PREFIX}_forbidden_elements"
    visible_text: str = f"{PREFIX}_visible_text_whitelist"
    # Tab + dirty 状态
    active_asset_tab: str = f"{PREFIX}_active_asset_tab"
    _dirty: str = f"{PREFIX}_form_dirty"  # 存储 dict[str, bool]（per-tab 脏状态）

    @classmethod
    def all_keys(cls) -> set[str]:
        return {getattr(cls, f.name) for f in fields(cls)}

    @classmethod
    def widget_keys(cls) -> set[str]:
        """仅返回 widget 绑定的 key（排除 _dirty 等纯状态标记）。"""
        return {k for k in cls.all_keys() if not k.startswith("_")}

@dataclass(frozen=True)
class _SceneCastKeys:
    select: str = f"{PREFIX}_scene_cast_select"
    id: str = f"{PREFIX}_scene_cast_id"
    storyboard_plan_id: str = f"{PREFIX}_storyboard_plan_id"
    frame_id: str = f"{PREFIX}_frame_id"
    character_ids: str = f"{PREFIX}_character_ids"
    scene_id: str = f"{PREFIX}_scene_id"
    prop_ids: str = f"{PREFIX}_prop_ids"
    style_id: str = f"{PREFIX}_style_id"
    continuity_notes: str = f"{PREFIX}_continuity_notes"
    _dirty: str = f"{PREFIX}_scene_cast_dirty"

    @classmethod
    def all_keys(cls) -> set[str]:
        return {getattr(cls, f.name) for f in fields(cls)}

    @classmethod
    def widget_keys(cls) -> set[str]:
        return {k for k in cls.all_keys() if not k.startswith("_")}

@dataclass(frozen=True)
class _PresetKeys:
    select: str = f"{PREFIX}_builtin_asset_bible_preset_select"
    import_id: str = f"{PREFIX}_import_asset_bible_id"

class IPSessionKeys:
    ASSET_BIBLE = _AssetBibleKeys()
    FORM = _IPFormKeys()
    SCENE_CAST = _SceneCastKeys()
    PRESET = _PresetKeys()
```

### 3.4 状态管理模式——"元编程自动映射"

> **关键决策**：Streamlit 的 widget 通过 `key` 直接绑定 session_state，不能同时用 model 对象管理状态。但 populate/build 的逐字段手工映射必须消除——采用字段名+dataclass 命名契约驱动通用映射器。

**命名契约：** `IPSessionKeys.FORM` 的 dataclass 字段名与 `IPProfileDraft` 的 model 字段名一一对应。
- 例如 `IPProfileDraft.name` ↔ `IPSessionKeys.FORM.name`
- 特例字段（key 名与 model 字段名不同）用单独映射注册。

```python
# web/utils/streamlit_helpers.py （扩充）

def populate_form_from_model(model: BaseModel, key_group) -> None:
    """通用回填：model 字段名 → session_state[key_group.同名字段]。

    命名契约：key_group 的 dataclass 字段名与 model_fields 一一对应。
    特例字段通过 _FIELD_KEY_OVERRIDES 字典处理。
    """
    ss = st.session_state
    for field_name in model.model_fields:
        key = getattr(key_group, field_name, None)
        if key:
            value = getattr(model, field_name)
            # list/dict 等非标量类型序列化为适合 widget 的格式
            if isinstance(value, list):
                value = ", ".join(value) if value else ""
            elif isinstance(value, dict):
                value = str(value) if value else ""
            ss[key] = value

def build_model_from_form(model_cls: type[BaseModel], key_group) -> BaseModel:
    """通用构建：session_state[key_group.xxx] → model。

    支持 list 字段（从 CSV 反序列化）、Literal 字段（直接取值）、
    dict 字段（JSON 解析）。
    """
    ss = st.session_state
    data: dict[str, Any] = {}
    for field_name, field_info in model_cls.model_fields.items():
        key = getattr(key_group, field_name, None)
        if key is None:
            continue
        raw = ss.get(key, "")
        data[field_name] = _deserialize_field(raw, field_info)
    return model_cls(**data)

def _deserialize_field(raw: Any, field_info) -> Any:
    """根据字段类型反序列化 session_state 中的原始值。

    使用 typing.get_origin() 统一处理 list、dict、Literal、Union 等泛型类型。
    """
    import typing
    origin = typing.get_origin(field_info.annotation)
    if origin is list:
        return _split_csv(str(raw)) if raw else []
    if origin is dict:
        return _parse_json_dict(str(raw)) if raw else {}
    # Literal、str、int 等直接取值
    return str(raw) if raw else ""

def _split_csv(value: str) -> list[str]:
    """逗号分隔字符串 → list[str]（替代所有 _split_csv 拷贝）。"""
    return [s.strip() for s in value.split(",") if s.strip()]

def _parse_json_dict(value: str) -> dict[str, Any]:
    """JSON 字符串 → dict（用于 color_palette 等字段）。"""
    import json
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return {"raw": value}
```

**策略：**
- **加载时**：从已有 AssetBible 读取数据 → `populate_form_from_model(profile, IPSessionKeys.FORM)` 自动回填
- **编辑时**：每个 widget 独立绑定自己的 key，Streamlit 自动管理
- **保存时**：`build_model_from_form(IPProfileDraft, IPSessionKeys.FORM)` 自动构建 → 序列化发送
- **切换时**：`IPSessionKeys.FORM.widget_keys()` 返回需要清除的 widget key

切换 IP Profile 时只清除 widget key，保留选择器和 AssetBible ID：

```python
def clear_ip_form_session_state():
    for key in IPSessionKeys.FORM.widget_keys():
        st.session_state.pop(key, None)
```

### 3.5 渐进式呈现——层级字段分配

```
核心层（默认可见，contract() + border）：
├── IP 类型*      │ 名称*        │ 一句话设定*   │ 视觉摘要*
└── 固定锚点*     │ 颜色约束      │ 最小可识别特征*
    * 标 = 生成就绪必需的字段

推荐层（st.expander("角色预设与约束", expanded=False)）：
├── 角色预设（每行一条）
├── 通用负向约束（逗号分隔）
└── 语义边界（逗号分隔）

高级层（st.expander("高级设置", expanded=False)）：
├── 可变项（LLM 自由发挥）
├── 默认替换偏好 + 出场规格范围
├── 身份抑制规则 + 禁用元素
└── 可见文本白名单
```

### 3.6 字段级验证设计

**采用方案 B（与 Streamlit 组件体系兼容）：**
每个字段用 `st.columns` 两列布局，验证标识符使用 `FieldId` Enum（§3.2），杜绝 magic string。

```python
# 样式常量（消除 magic number 0.92/0.08）
_VALIDATION_LAYOUT_RATIO = [0.92, 0.08]

def _render_validated_field(
    label: str,
    *,
    field_id: FieldId,      # ← Enum 类型，非 magic string
    key: str,
    report: ReadinessReport,
    required: bool = False,
) -> str:
    col1, col2 = st.columns(_VALIDATION_LAYOUT_RATIO)
    with col1:
        value = st.text_input(label, key=key)
    with col2:
        if required and field_id in report.missing:
            st.markdown("❌", help=f"缺少必填字段：{label}")
        elif required and value.strip():
            st.markdown("✅")
    return value
```

### 3.7 UI 布局

```
┌─ st.sidebar ──────────────────────────────┐
│  ▼ 快速操作                                 │
│  内置 AssetBible 预设导入                    │
│  [预设下拉]  [导入ID]  [导入]               │
│                                            │
│  [新建 AssetBible]  [删除]  [复制]          │
│  ────────────────────────────────────────  │
│  🚩 调试: V2 组件 [启用/禁用]               │
└───────────────────────────────────────────┘

┌─ 主区域 ───────────────────────────────────┐
│  ████████░░ 就绪度 70%                      │
│                                            │
│  ❌ 错误提示区域（仅异常时显示）               │
│  ⚠️ 当前 Tab 有未保存修改（仅 dirty 时显示）   │
│                                            │
│  选择 AssetBible: [下拉]                     │
│  AssetBible ID: [_________]                 │
│                                            │
│  ┌─ [IP Profile] [配角] [场景] [道具] [风格] │
│  │                                         │
│  │  核心信息 (default open)                 │
│  │  IP类型* │ 名称* │ 一句话设定* │ 视觉摘要* │
│  │  ✅ IP类型 ✅ 名称 ✅ 一句话设定 ❌ 视觉摘要 │
│  │                                         │
│  │  ▼ 视觉锚点                             │
│  │  固定锚点* │ 颜色约束  │ 最小可识别特征*   │
│  │                                         │
│  │  ▶ 角色预设与约束                       │
│  │  ▶ 高级设置                             │
│  │                                         │
│  │  [保存 AssetBible]                      │
│  └─────────────────────────────────────────┘
│                                            │
│  ┌─ SceneCast ──────────────────────────┐  │
│  │  选择 SceneCast: [下拉]               │  │
│  │  SceneCast ID │ Storyboard Plan ID   │  │
│  │  [__________] [___________________]   │  │
│  │  Frame ID │ Character IDs │ Scene ID │  │
│  │  [________] [_____________] [_______] │  │
│  │  [保存 SceneCast]                    │  │
│  └──────────────────────────────────────┘  │
└───────────────────────────────────────────┘
```

### 3.8 Tab 切换状态策略

- 5 个 Tab（IP Profile / 配角 / 场景 / 道具 / 风格）使用 `st.tabs()`
- `IPSessionKeys.FORM.active_asset_tab` 记录当前 Tab
- 每个 Tab 有独立的保存按钮
- 切换 Tab 时数据不丢失（widget key 保持不变）

**脏状态检测（Dirty State Detection）：**
采用 per-tab `dict[str, bool]` 策略：
- `st.session_state[IPSessionKeys.FORM._dirty]` 存储 `{"ip_profile": True, "character": False, ...}`
- 所有 input widget 的 `on_change` 回调记录当前 tab 的脏标记：
  ```python
  def _mark_dirty(tab_name: str):
      dirty = st.session_state.get(IPSessionKeys.FORM._dirty, {})
      dirty[tab_name] = True
      st.session_state[IPSessionKeys.FORM._dirty] = dirty
  ```
- 保存成功后设置当前 tab 的 `_dirty[tab_name] = False`
- Tab 切换时读取 `_dirty[tab_name]` 决定是否显示"⚠️ 当前 Tab 有未保存修改"
- 跨 Tab 之间的脏标记互不影响

**防御性校验：** `st.tabs()` 按位置记忆而非 label 记忆。每次 rerun 时从 `IPSessionKeys.FORM.active_asset_tab` 读取并显式设置 `st.tabs()` 的 `default` 参数，确保 tab 选择状态与 session state 一致。

### 3.9 删除/复制语义

**删除 AssetBible：**
- 使用 `st.popover` + 确认按钮，"确认删除 [id]？此操作不可撤销，关联的 SceneCast 也将被删除。"
- 调用 `IPDesignClient.delete_asset_bible()` → 返回 `DeleteResponse`
- 成功后 `st.toast(DeleteResponse.message)` + `st.rerun()` 刷新页面
- 失败后显示 `DeleteResponse.errors` 在错误提示区域

**复制 AssetBible：**
- 弹出输入框："请输入新 AssetBible ID（留空自动生成）"
- 只复制 5 种资产（不复制 SceneCast）
- 调用 `IPDesignClient.save_asset_bible()` 用新 ID 保存 → 返回 `SaveResponse`
- 成功后选中新副本

**需要扩展 Protocol：**
```python
class IPDesignClient(Protocol):
    def delete_asset_bible(self, *, workspace_id: str, project_id: str, asset_bible_id: str) -> DeleteResponse: ...
    def delete_scene_cast(self, *, workspace_id: str, project_id: str, asset_bible_id: str, scene_cast_id: str) -> DeleteResponse: ...
```

### 3.10 SceneCast 上下文关联

- 在 SceneCast 区域加"从 Storyboard 选取"按钮
- 点击弹出 `st.popover`，显示可选的分镜计划列表和帧缩略图（复用 `storyboard_preview` 组件）
- 选取后自动填充 `storyboard_plan_id` 和 `frame_id`

### 3.11 错误处理设计

**分层错误处理策略：**

| 层级 | 错误类型 | 处理方式 |
|------|----------|----------|
| Client | 网络错误、HTTP 非 200、超时 | 抛出 `IPDesignClientError`，UI 层 catch |
| Client | API 返回 `success: false` | 不抛异常，将 `errors` 列表原样传递 |
| Model | Pydantic `ValidationError` | 在 `build_model_from_form` 中 try-except，转换为结构化错误列表 |
| UI | 权限不足、资源不存在 | 在错误提示区域展示，不打断表单输入 |

**UI 展示规则：**
- 错误提示区域在页面顶部、AssetBible 选择器上方（见 §3.7 布局）
- 错误 `st.error()` 显示，3 秒后自动消失（`st.toast`）
- 非阻塞错误（如验证警告）以 `st.warning` 形式悬挂在字段旁
- 所有 `delete` / `save` / `import` 调用的返回必须先检查 `success` 再继续

### 3.12 部署与回滚策略

**Feature Flag：**
```python
# web/config.py 或 st.secrets
IP_DESIGN_V2_ENABLED = os.getenv("IP_DESIGN_V2_ENABLED", "false").lower() == "true"
```

- 新组件由 `if IP_DESIGN_V2_ENABLED: render_new_workbench() else: render_old_workbench()` 切换
- 默认关闭，staging 环境先验证，production 灰度放量
- 旧版组件代码保留至少一个发布周期，确认无 regression 后删除

**回滚路径：**
- 关闭 feature flag 即可恢复旧版，无需 revert commit
- 旧版 session_state widget key 与新版的 `IPSessionKeys` 完全隔离（旧版用 `"ip_design_xxx"` 字面量，新版全部通过 dataclass 引用）
- 新旧版本切换时使用 `safe_rerun()` 清理 widget 残留

## 4. 数据流

```
状态机（每个操作共享 LOADING → READY → SAVING 模式）：

                    ┌──────────┐
               ┌───→│  ERROR   │←──────────────┐
               │    └──────────┘                │
               │         ↑                      │
    ┌──────────┴──┐  ┌──┴──────────┐  ┌────────┴────────┐
    │  LOADING    │──→│   READY     │──→│    SAVING      │
    │ (骨架屏)     │   │ (表单可编辑)  │   │ (保存中)       │
    └─────────────┘   └──┬──────────┘   └────────┬────────┘
                         │                       │
                         │ 切换 AssetBible       │ 完成
                         └───────────────────────┘

加载流程：
  selectbox → 选中 AssetBible ID
    → IPDesignClient.load_asset_bible()
    → AssetBibleDraft.model_validate(response)
    → populate_form_from_model(profile, IPSessionKeys.FORM) 自动回填
    → 设置 _state = "ready"

保存流程（IP Profile Tab）：
  点击保存
    → 验证：build_model_from_form(IPProfileDraft, IPSessionKeys.FORM)
    → 失败：返回验证错误 → 展示到错误区域
    → 成功：color_palette 处理：
        build_color_palette_prompt_entries(profile.color_palette, color_rules_str)
      profile.color_palette 是 dict（IPProfileDraft 中声明为 dict[str, Any]），
      直接传入 build_color_palette_prompt_entries（兼容核心库签名）
    → AssetBibleDraft(asset_bible_id=..., ip_profiles=[...])
    → IPDesignClient.save_asset_bible(payload=model.model_dump())
    → 检查 SaveResponse.success
    → 成功：st.toast("已保存") + _dirty[tab] = False + st.rerun()
    → 失败：展示 SaveResponse.errors → 状态回到 "ready"

预设导入流程：
  sidebar 选中预设 → 输入导入 ID → 点击导入
    → IPDesignClient.import_asset_bible_preset()
    → 检查 ImportPresetResponse.success
    → 成功：st.toast() + st.rerun()
    → 失败：展示 errors

删除流程：
  点击删除 → popover 确认
    → IPDesignClient.delete_asset_bible()
    → 检查 DeleteResponse.success
    → 成功：st.toast(message) + st.rerun()
    → 失败：展示 errors
```

## 5. streamlit_helpers.py 扩充方案

已有工具（保留不改）：
- `session_state_has_key()`
- `keyed_widget_default_kwargs()` — 替代当前 `if key in session_state` 模式
- `normalize_keyed_option()`
- `RefreshableSlot`
- `safe_rerun()`

新增工具（统一 8 个文件的重复函数）：

```python
def first_text(*values: Any) -> str:
    """替代所有 _first_text 拷贝"""

def list_of_dicts(value: Any) -> list[dict[str, Any]]:
    """替代所有 _list_of_dicts 拷贝"""

def text_list(value: Any) -> list[str]:
    """替代所有 _text_list 拷贝"""

def split_csv(value: str) -> list[str]:
    """替代所有 _split_csv 拷贝"""

def find_item(items: list[dict[str, Any]], field_name: str, value: str) -> dict[str, Any] | None:
    """替代所有 _find_item 拷贝"""

def keyed_text_input(ui, label: str, *, key: str, value: str = "") -> str:
    """替代所有 _text_input 拷贝。内部使用 keyed_widget_default_kwargs。"""

def keyed_text_area(ui, label: str, *, key: str, value: str = "", height: int) -> str:
    """替代所有 _text_area 拷贝。"""

def populate_form_from_model(model: BaseModel, key_group) -> None:
    """元编程自动回填（§3.4）。"""

def build_model_from_form(model_cls: type[BaseModel], key_group) -> BaseModel:
    """元编程自动构建（§3.4）。"""
```

## 6. 执行顺序与文件变更清单

> **注意：** 以下按执行顺序排列，前序步骤完成后，后续步骤间可并行。

### Step 0 — 存量消费者 Audit 与迁移（前置，阻断后续所有步骤）

**目标：** 消除所有 `result.get("xxx")` 的 dict 访问模式，确保 Pydantic model 上线后不存在双重访问路径。

| 动作 | 文件 | 内容 |
|------|------|------|
| Audit | `web/components/*.py`、`web/utils/*.py` | grep 所有 `.get("asset_bible"` / `.get("ip_profiles"` 等 dict 访问，列出精确位置 |
| 迁移 | 审计出的所有文件 | 替换 `result.get("asset_bibles")` → `result.asset_bibles`，修改签名以接收 typed 响应 |
| 验证 | `tests/` | 更新 mock 响应类型，确保编译/类型检查通过 |

共从 audit 结果中识别出 **24 处** `.get("asset_bible"` 调用（分布在 8 个文件中），需要逐个迁移。

### Step 1 — 新建文件（无依赖）
| 文件 | 职责 |
|------|------|
| `web/ip_design/models.py` | 所有 Pydantic 领域模型（§3.2） |
| `web/ip_design/session_keys.py` | `IPSessionKeys` 常量类（§3.3） |

### Step 2 — 工具层扩充（依赖 Step 1）
| 文件 | 变更内容 |
|------|----------|
| `web/utils/streamlit_helpers.py` | 新增 `first_text`, `list_of_dicts`, `text_list`, `split_csv`, `find_item`, `keyed_text_input`, `keyed_text_area`, `populate_form_from_model`, `build_model_from_form` 共 9 个函数 |

### Step 3 — Payload 层适配（依赖 Step 1）
| 文件 | 变更内容 |
|------|----------|
| `web/utils/asset_bible_payloads.py` | 适配 Pydantic model（`AssetBibleDraft.model_dump()` 替代 `dict()` 构造）；标记 `build_asset_bible_payload` 为 `@deprecated("use AssetBibleDraft.model_dump()")` |

### Step 4 — Client 层全面 Typed（依赖 Step 1, Step 3；阻断 Step 5）
> **串行约束：** `save_asset_bible(payload)` 参数类型从 `dict[str, Any]` 改为 `AssetBibleDraft`。签名变更后 Step 5 之前任何未迁移的调用方会编译失败。因此 **Step 4 必须先完成并提交，再开始 Step 5**，不可并行。

| 文件 | 变更内容 |
|------|----------|
| `web/ip_design/client.py` | Protocol 所有方法返回类型改为 typed response（`ListAssetBiblesResponse`、`AssetBibleDraft`、`SaveResponse`、`DeleteResponse` 等）；`save` 的 `payload` 参数改为 `AssetBibleDraft` |
| `web/ip_design/http_client.py` | 所有方法适配新签名；`load_asset_bible()` 用 `AssetBibleDraft.model_validate()`；新增 delete 实现 |
| `web/ip_design/inprocess_client.py` | 同上 |

### Step 5 — UI 组件重构（依赖 Step 1-4，文件间可并行）

**核心组件（重构整个页面逻辑）：**
| 文件 | 变更内容 |
|------|----------|
| `web/components/ip_design_workbench.py` | 整体重构：Pydantic model、元编程自动映射、渐进式呈现、字段级验证（FieldId Enum）、5 Tab、删除/复制（popover）、sidebar 预设导入、保存刷新、per-tab dirty 检测、错误提示区域、feature flag |
| `web/components/ip_workbench_panel.py` | 删除局部 `_first_text`, `_text_list`, `_list_of_dicts`, `_find_item`；改用 `streamlit_helpers` |

**辅助组件（仅替换 helper 引用，不改变逻辑）：**
| 文件 | 变更内容 |
|------|----------|
| `web/components/asset_bible_draft_setup.py` | 删除局部 `_text_input`, `_split_csv`, `_list_of_dicts`；改用 `streamlit_helpers` |
| `web/components/ip_prompt_chain_controls.py` | 删除局部 `_text_list`, `_list_of_dicts`, `_first_text`；改用 `streamlit_helpers` |
| `web/components/asset_prompt_plan_projection.py` | 删除局部 `_text_input`, `_list_of_dicts`, `_find_item`；改用 `streamlit_helpers` |
| `web/components/storyboard_workbench_panel.py` | 删除局部 `_list_of_dicts`, `_first_text`；改用 `streamlit_helpers` |

**此前排除的组件（本次纳入 scope，DRY 彻底化）：**
| 文件 | 变更内容 |
|------|----------|
| `web/components/content_ip_world_controls.py` | 删除局部 `_first_text`（1 处定义 + 10 处调用）；改用 `streamlit_helpers.first_text` |
| `web/components/stale_panel.py` | 删除局部 `_list_of_dicts`（1 处定义 + 1 处调用）；改用 `streamlit_helpers.list_of_dicts` |

### Step 6 — i18n（可全程并行）
| 文件 | 变更内容 |
|------|----------|
| `web/i18n/locales/zh_CN.json` | 新增：Tab 标签、字段验证文本、删除/复制按钮、dirty 状态提示 |
| `web/i18n/locales/en_US.json` | 对应英文翻译 |

### Step 7 — 测试补全（并行于 Step 5-6）
| 文件 | 变更内容 |
|------|----------|
| `tests/test_ip_design_workbench_ui.py` | 适配新 model 签名；增加 dirty state、delete、error handling 测试 |

### 已知遗留债务追踪（本次明确不改，附 ticket）

| 债务 | 位置 | 原因 | 追责 |
|------|------|------|------|
| `_first_text` 在核心层重复 | `pixelle_video/services/ip_usage_planner.py` | 核心库不在本重构 scope | 需核心库维护者单独处理 |
| `build_asset_bible_payload` 过时 | `web/utils/asset_bible_payloads.py` | 被 API 层直接 import | 已标记 `@deprecated`，跟随 API 层重构移除 |
| `AssetBibleSummary` 含 `list[dict]` 字段 | `web/ip_design/models.py:125-129` | API 响应形状暂未 typify，属有意边界 | 待 API 层引入结构化响应后对齐 |

## 7. 测试策略

> **已有测试文件：** `tests/test_ip_design_workbench_ui.py`（703 行），使用 `_FakeUI` mock 框架测试 `render_ip_design_workbench`。

### 测试分类（精确映射）

| 测试类型 | 覆盖范围 | 新增/修改 | 具体用例 |
|----------|----------|-----------|----------|
| 单元测试 | `IPProfileDraft` / `AssetBibleDraft` 模型验证逻辑 | **新增** | 构造、字段类型校验、`model_dump()` 序列化 |
| 单元测试 | `FieldId` Enum 值与字段名一致性 | **新增** | `FieldId.NAME.value == "name"` |
| 单元测试 | `streamlit_helpers.py` 新增的 9 个函数 | **新增** | `first_text`、`split_csv`、`list_of_dicts` 边界值 |
| 单元测试 | `IPSessionKeys` 各子类 `all_keys()` / `widget_keys()` | **新增** | 排除 `_dirty` 前缀 key |
| 单元测试 | `populate_form_from_model` / `build_model_from_form` 双向映射 | **新增** | 构建 → 回填 → 再构建，数据不丢失；list/dict/Literal 字段 |
| 集成测试 | client 实现的 CRUD（含 `delete_asset_bible` / `delete_scene_cast`） | **新增** | mock HTTP 返回 `DeleteResponse` |
| 集成测试 | 错误路径：`IPDesignClientError` 抛异常 → UI 展示 error | **新增** | 网络断开、400、500 |
| 回归测试 | 已有 `test_ip_design_workbench_ui.py` 中不依赖内部实现的测试 | **修改签名** | 约 30% 的测试仅需更新 mock 响应类型 |
| 回归测试 | 已有测试中依赖 widget key 常量字符串的 | **修改引用** | 约 20% 的测试需改为引用 `IPSessionKeys` |
| UI 测试 | dirty state per-tab 正确性 | **新增** | 修改 Tab A → 切到 Tab B → 切回 → 警告存在 |

### 新增测试文件优先级

| 优先级 | 文件 | 原因 |
|--------|------|------|
| P0 | `tests/test_ip_design_models.py` | model 是重构核心，无测试不可上线 |
| P0 | `tests/test_streamlit_helpers_ext.py` | 元编程自动映射函数是状态管理核心 |
| P1 | `tests/test_ip_design_client_typed.py` | typed response 是新 Protocol 的契约验证 |

## 8. 向后兼容策略

1. **Client Protocol 方法签名语义不变**（参数名不变；`payload` 参数类型从 `dict[str, Any]` 改为 `AssetBibleDraft`；返回类型从 `dict[str, Any]` 改为 typed response）
2. **HTTP API 端点 URL 不变**，请求/响应体结构不变
3. **已有 session_state widget key 前缀不变**（`"ip_design_xxx"`），只改为通过 `IPSessionKeys` 集中引用
4. **存在存量 AssetBible 数据**：`AssetBibleDraft.model_validate(existing_dict)` 可直接从已有 dict 构建
5. **feature flag `IP_DESIGN_V2_ENABLED`** 提供完整回滚路径（§3.12）
6. **Step 0 确保所有消费者在重构前已迁移**，不存在 `.get("xxx")` → 属性访问的冲突窗口

## 9. 未纳入范围的边界

- **不会**删除 `asset_bible_draft_setup.py`（Stage2 功能仍然使用）
- **不会**改动 `pixelle_video/` 核心库（`ip_usage_planner.py` 和 `ip_generation_request.py` 中的 `_first_text` 属于核心层，不在本重构范围）
- `build_asset_bible_payload` 已标记 `@deprecated`，在 API 层后续重构中移除
