# IP Design Workbench Refactor 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标:** 消除 `dict[str, Any]` 魔术字符串架构债务，引入 Pydantic 领域模型、集中式 Session Key、元编程自动映射、渐进式 UI、字段级验证、5 种资产 Tab 编辑、CRUD 完整操作，同时保留 feature flag 回滚路径。

**架构:** 四层架构——Domain Model Layer（Pydantic models + SessionKeys）→ Client Abstraction Layer（typed Protocol + 实现）→ Utility Layer（扩充 streamlit_helpers + payload 适配）→ UI Layer（重构 ip_design_workbench.py）。Step 0 预先审计迁移所有 `.get("xxx")` dict 消费者，确保无双重访问路径。

**Tech Stack:** Python 3.11+, Streamlit, Pydantic v2, pytest, `ip_design/client.py` (Protocol)

---

## 工作目录

全部工作在 `D:\demo1\Pixelle\Pixelle` 下执行。假设当前在 `dev` 分支。

---

## File Structure

### 新建文件
- `web/ip_design/models.py` — Pydantic 领域模型 + FieldId Enum + 响应类型
- `web/ip_design/session_keys.py` — IPSessionKeys 集中常量类
- `tests/test_ip_design_models.py` — model 构造/序列化测试
- `tests/test_streamlit_helpers_ext.py` — 新增 9 个函数 + 元编程映射测试
- `tests/test_ip_design_client_typed.py` — typed response 契约测试

### 修改文件
- `web/utils/streamlit_helpers.py` — 新增 9 个工具函数
- `web/utils/asset_bible_payloads.py` — 适配 Pydantic model，标记 `@deprecated`
- `web/ip_design/client.py` — Protocol 返回 typed response，`save` 参数改为 `AssetBibleDraft`
- `web/ip_design/http_client.py` — 适配新签名，新增 delete 方法
- `web/ip_design/inprocess_client.py` — 适配新签名，新增 delete 方法
- `web/components/ip_design_workbench.py` — 整体重构（核心变更）
- `web/components/ip_workbench_panel.py` — 替换局部 helper 为 streamlit_helpers
- `web/components/asset_bible_draft_setup.py` — 替换局部 helper
- `web/components/ip_prompt_chain_controls.py` — 替换局部 helper
- `web/components/asset_prompt_plan_projection.py` — 替换局部 helper
- `web/components/storyboard_workbench_panel.py` — 替换局部 helper
- `web/components/content_ip_world_controls.py` — 替换局部 helper
- `web/components/stale_panel.py` — 替换局部 helper
- `tests/test_ip_design_workbench_ui.py` — 适配新签名
- `web/i18n/locales/zh_CN.json` — 新增 Tab/验证/CRUD 文本
- `web/i18n/locales/en_US.json` — 对应英文
- `web/pages/3_IP_Design_Workbench.py` — 加入 feature flag 切换

---

## Task 0 — 存量消费者审计（阻断后续所有步骤）

> **目标:** 识别所有 `result.get("asset_bible"` / `.get("ip_profiles"` 等 dict 访问，列出精确位置。

**Files:**
- Audit: `web/components/*.py`, `web/utils/*.py`
- Test: 手动验证 audit 清单

- [ ] **Step 1: 运行 grep 审计所有 `.get()` 调用**

Run:
```powershell
Set-Location 'D:\demo1\Pixelle\Pixelle'; rg '\.get\("(asset_bible|ip_profiles|character_profiles|scene_assets|prop_assets|style_profiles|scene_casts)"\)' web/components/ web/utils/ --line-number
```

Expected: 列出所有位置。已有的 14 处分布在 6 个文件中：
- `ip_design_workbench.py`: 7 处
- `ip_workbench_panel.py`: 2 处
- `ip_prompt_chain_controls.py`: 3 处
- `asset_bible_draft_setup.py`: 1 处
- `asset_prompt_plan_projection.py`: 1 处

- [ ] **Step 2: 保存审计结果到临时文件**

Run:
```powershell
rg '\.get\("(asset_bible|ip_profiles|character_profiles|scene_assets|prop_assets|style_profiles|scene_casts)"\)' web/components/ web/utils/ --line-number | Set-Content -LiteralPath '_runtime/audit_dict_access.log'
```

- [ ] **Step 3: 确认审计清单完整**

检查 `web/utils/asset_bible_payloads.py` 和 `web/utils/asset_bible_api.py` 中是否还有其他 `.get("xxx")` 的 dict 消费者。手动验证后记入 `_runtime/audit_dict_access.log`。

---

## Task 1 — 新建 Domain Model 文件

> **目标:** 创建 `models.py` 和 `session_keys.py`。这是所有后续步骤的基础。

**Files:**
- Create: `web/ip_design/models.py`
- Create: `web/ip_design/session_keys.py`

- [ ] **Step 1: 创建 `web/ip_design/models.py`**

```python
from __future__ import annotations

from typing import Any, Literal, Protocol
from pydantic import BaseModel, Field
from enum import Enum


class FieldId(str, Enum):
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


class TypedResponse(BaseModel):
    success: bool
    message: str = ""
    errors: list[str] = []


class SaveResponse(TypedResponse):
    pass


class DeleteResponse(TypedResponse):
    pass


class AssetBibleSummary(BaseModel):
    asset_bible_id: str
    character_profiles: list[dict[str, Any]] = []
    scene_assets: list[dict[str, Any]] = []
    prop_assets: list[dict[str, Any]] = []
    style_profiles: list[dict[str, Any]] = []
    ip_profiles: list[dict[str, Any]] = []
    metadata: dict[str, Any] = {}


class ListAssetBiblesResponse(BaseModel):
    success: bool = True
    asset_bibles: list[AssetBibleSummary] = []
    errors: list[str] = []


class ListSceneCastsResponse(BaseModel):
    success: bool = True
    scene_casts: list[dict[str, Any]] = []
    errors: list[str] = []


class PresetSummary(BaseModel):
    preset_id: str
    display_name: str = ""
    description: str = ""


class ListPresetsResponse(BaseModel):
    success: bool = True
    presets: list[PresetSummary] = []
    errors: list[str] = []


class ImportPresetResponse(TypedResponse):
    asset_bible_id: str = ""


class IPDesignClientError(RuntimeError):
    """Raised when the IP design client cannot satisfy a requested operation."""


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
    ready: bool
    missing: list[FieldId] = []
    warnings: list[FieldId] = []


__all__ = [
    "FieldId", "TypedResponse", "SaveResponse", "DeleteResponse",
    "AssetBibleSummary", "ListAssetBiblesResponse", "ListSceneCastsResponse",
    "PresetSummary", "ListPresetsResponse", "ImportPresetResponse",
    "IPProfileDraft", "CharacterProfileDraft", "SceneAssetDraft",
    "PropAssetDraft", "StyleProfileDraft", "AssetBibleDraft",
    "SceneCastDraft", "ReadinessReport", "IPDesignClientError",
]
```

- [ ] **Step 2: 创建 `web/ip_design/session_keys.py`**

```python
from __future__ import annotations

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
    active_asset_tab: str = f"{PREFIX}_active_asset_tab"
    _dirty: str = f"{PREFIX}_form_dirty"

    @classmethod
    def all_keys(cls) -> set[str]:
        return {getattr(cls, f.name) for f in fields(cls)}

    @classmethod
    def widget_keys(cls) -> set[str]:
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


__all__ = ["IPSessionKeys"]
```

- [ ] **Step 3: 运行导入验证**

Run:
```powershell
python -c "from web.ip_design.models import *; from web.ip_design.session_keys import IPSessionKeys; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add web/ip_design/models.py web/ip_design/session_keys.py
git commit -m "feat: 新增 Pydantic 领域模型和集中式 Session Key 管理"
```

---

## Task 2 — 扩充 streamlit_helpers.py

> **目标:** 新增 9 个工具函数，统一 8 个文件的重复辅助函数。

**Files:**
- Modify: `web/utils/streamlit_helpers.py`

- [ ] **Step 1: 在 `web/utils/streamlit_helpers.py` 末尾新增函数**

在 `safe_rerun()` 之后添加。如果文件有 `from collections.abc import Callable` 则无需改动；否则在文件顶部 import 区域添加：

```python
from collections.abc import Callable
```

新增函数代码：

```python
# ── 新增通用辅助函数（替代 8 个文件中的重复拷贝） ──

def first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [first_text(item) for item in value if first_text(item)]


def split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def find_item(items: list[dict[str, Any]], field_name: str, value: str) -> dict[str, Any] | None:
    for item in items:
        if first_text(item.get(field_name)) == value:
            return item
    return None


def keyed_text_input(ui, label: str, *, key: str, value: str = "", on_change: Callable[[], None] | None = None) -> str:
    kwargs = keyed_widget_default_kwargs(getattr(ui, "session_state", {}), key, value=value)
    if on_change:
        kwargs["on_change"] = on_change
    return ui.text_input(label, key=key, **kwargs)


def keyed_text_area(ui, label: str, *, key: str, value: str = "", height: int = 68, on_change: Callable[[], None] | None = None) -> str:
    kwargs = keyed_widget_default_kwargs(getattr(ui, "session_state", {}), key, value=value)
    if on_change:
        kwargs["on_change"] = on_change
    return ui.text_area(label, key=key, height=height, **kwargs)


def populate_form_from_model(model: BaseModel, key_group) -> None:
    ss = st.session_state
    for field_name in model.model_fields:
        key = getattr(key_group, field_name, None)
        if key:
            value = getattr(model, field_name)
            if isinstance(value, list):
                value = ", ".join(value) if value else ""
            elif isinstance(value, dict):
                value = str(value) if value else ""
            ss[key] = value


def build_model_from_form(model_cls: type[BaseModel], key_group) -> BaseModel:
    import typing
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
    import typing
    origin = typing.get_origin(field_info.annotation)
    if origin is list:
        return split_csv(str(raw)) if raw else []
    if origin is dict:
        return _parse_json_dict(str(raw)) if raw else {}
    return str(raw) if raw else ""


def _parse_json_dict(value: str) -> dict[str, Any]:
    import json
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return {"raw": value}
```

同时更新 `__all__`（如果存在）。如果不存在 `__all__`，则在文件末尾添加：

```python
__all__ = [
    "session_state_has_key", "keyed_widget_default_kwargs",
    "normalize_keyed_option", "RefreshableSlot", "safe_rerun",
    "first_text", "list_of_dicts", "text_list", "split_csv",
    "find_item", "keyed_text_input", "keyed_text_area",
    "populate_form_from_model", "build_model_from_form",
]
```

- [ ] **Step 2: 运行导入验证**

Run:
```powershell
python -c "from web.utils.streamlit_helpers import first_text, split_csv, list_of_dicts, find_item, keyed_text_input, populate_form_from_model, build_model_from_form; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add web/utils/streamlit_helpers.py
git commit -m "feat: 扩充 streamlit_helpers.py 新增 9 个通用辅助函数"
```

---

## Task 3 — 适配 asset_bible_payloads.py

> **目标:** 适配 Pydantic model，标记 `build_asset_bible_payload` 为 `@deprecated`。

**Files:**
- Modify: `web/utils/asset_bible_payloads.py`

- [ ] **Step 1: 在文件顶部新增 deprecation 标记**

在 `from __future__` 之后添加：

```python
import warnings
```

- [ ] **Step 2: 在 `build_asset_bible_payload` 函数体内添加 deprecation 警告**

在函数体第一行添加：

```python
    warnings.warn(
        "build_asset_bible_payload is deprecated; use AssetBibleDraft.model_dump() instead",
        DeprecationWarning,
        stacklevel=2,
    )
```

- [ ] **Step 3: 验证导入无报错**

Run:
```powershell
python -c "from web.utils.asset_bible_payloads import build_asset_bible_payload, build_asset_bible_draft_payload_from_response; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add web/utils/asset_bible_payloads.py
git commit -m "chore: 标记 build_asset_bible_payload 为 @deprecated"
```

---

### Task 3.5 — 旧版组件快照（在 Protocol 变更前执行）

> **目标:** 在修改 Client Protocol 签名之前，保留旧版 `ip_design_workbench.py` 的完整副本用于 feature flag 回滚。必须在 Task 4 之前执行，确保旧版代码引用旧 Protocol 签名。

**Files:**
- Copy: `web/components/ip_design_workbench.py` → `web/components/ip_design_workbench_legacy.py`

- [ ] **Step 1: 复制旧版组件并重命名导出函数**

```powershell
Copy-Item -LiteralPath 'web/components/ip_design_workbench.py' -Destination 'web/components/ip_design_workbench_legacy.py'
```

- [ ] **Step 2: 在 `ip_design_workbench_legacy.py` 中将导出函数改名为 `render_ip_design_workbench_legacy`**

在文件末尾将 `__all__ = ["render_ip_design_workbench"]` 改为 `__all__ = ["render_ip_design_workbench_legacy"]`，并将函数定义从 `def render_ip_design_workbench` 改为 `def render_ip_design_workbench_legacy`。

- [ ] **Step 3: 提交快照**

```bash
git add web/components/ip_design_workbench_legacy.py
git commit -m "chore: 备份旧版 IP Design Workbench 用于回滚（Protocol 变更前）"
```

---

## Task 4 — Client 层全面 Typed（阻断 UI 重构）

> **目标:** Protocol 和两个实现都改为 typed response，`save` 参数改为 `AssetBibleDraft`，新增 delete 方法。

> **串行约束:** signature 变更后 UI 层编译失败，因此本 Task 必须完成并提交后再开始 Task 5。

**Files:**
- Modify: `web/ip_design/client.py`
- Modify: `web/ip_design/http_client.py`
- Modify: `web/ip_design/inprocess_client.py`

- [ ] **Step 1: 重写 `web/ip_design/client.py`**

```python
from __future__ import annotations

from typing import Any, Protocol

from web.ip_design.models import (
    AssetBibleDraft,
    DeleteResponse,
    ImportPresetResponse,
    IPDesignClientError,
    ListAssetBiblesResponse,
    ListSceneCastsResponse,
    SaveResponse,
    SceneCastDraft,
)


class IPDesignClient(Protocol):
    def list_asset_bible_presets(self) -> list[dict[str, Any]]: ...

    def import_asset_bible_preset(
        self,
        *,
        workspace_id: str,
        project_id: str,
        preset_id: str,
        asset_bible_id: str | None = None,
    ) -> ImportPresetResponse: ...

    def list_asset_bibles(
        self,
        *,
        workspace_id: str,
        project_id: str,
    ) -> ListAssetBiblesResponse: ...

    def load_asset_bible(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
    ) -> AssetBibleDraft: ...

    def save_asset_bible(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
        payload: AssetBibleDraft,
    ) -> SaveResponse: ...

    def delete_asset_bible(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
    ) -> DeleteResponse: ...

    def list_scene_casts(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
    ) -> ListSceneCastsResponse: ...

    def load_scene_cast(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
        scene_cast_id: str,
    ) -> SceneCastDraft: ...

    def save_scene_cast(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
        scene_cast_id: str,
        payload: SceneCastDraft,
    ) -> SaveResponse: ...

    def delete_scene_cast(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
        scene_cast_id: str,
    ) -> DeleteResponse: ...


__all__ = ["IPDesignClient", "IPDesignClientError"]
```

- [ ] **Step 2: 重写 `web/ip_design/http_client.py`**

```python
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from web.ip_design.models import (
    AssetBibleDraft,
    DeleteResponse,
    ImportPresetResponse,
    IPDesignClientError,
    ListAssetBiblesResponse,
    ListPresetsResponse,
    ListSceneCastsResponse,
    SaveResponse,
    SceneCastDraft,
)
from web.ip_design.session_keys import IPSessionKeys
from web.utils.asset_bible_api import (
    import_asset_bible_preset,
    list_asset_bible_presets,
    list_asset_bibles,
    list_scene_casts,
    load_asset_bible,
    load_scene_cast,
    save_asset_bible,
    save_scene_cast,
)


class HttpIPDesignClient:
    def __init__(
        self,
        *,
        api_base_url: str,
        asset_bible_loader: Callable[..., list[dict[str, Any]]] = list_asset_bibles,
        asset_bible_getter: Callable[..., dict[str, Any]] = load_asset_bible,
        asset_bible_saver: Callable[..., dict[str, Any]] = save_asset_bible,
        asset_bible_preset_loader: Callable[..., list[dict[str, Any]]] = (
            list_asset_bible_presets
        ),
        asset_bible_preset_importer: Callable[..., dict[str, Any]] = (
            import_asset_bible_preset
        ),
        scene_cast_loader: Callable[..., list[dict[str, Any]]] = list_scene_casts,
        scene_cast_getter: Callable[..., dict[str, Any]] = load_scene_cast,
        scene_cast_saver: Callable[..., dict[str, Any]] = save_scene_cast,
    ) -> None:
        self.api_base_url = api_base_url.rstrip("/")
        self._asset_bible_loader = asset_bible_loader
        self._asset_bible_getter = asset_bible_getter
        self._asset_bible_saver = asset_bible_saver
        self._asset_bible_preset_loader = asset_bible_preset_loader
        self._asset_bible_preset_importer = asset_bible_preset_importer
        self._scene_cast_loader = scene_cast_loader
        self._scene_cast_getter = scene_cast_getter
        self._scene_cast_saver = scene_cast_saver

    def list_asset_bible_presets(self) -> list[dict[str, Any]]:
        return self._asset_bible_preset_loader(api_base_url=self.api_base_url)

    def import_asset_bible_preset(
        self,
        *,
        workspace_id: str,
        project_id: str,
        preset_id: str,
        asset_bible_id: str | None = None,
    ) -> ImportPresetResponse:
        result = self._asset_bible_preset_importer(
            api_base_url=self.api_base_url,
            workspace_id=workspace_id,
            project_id=project_id,
            preset_id=preset_id,
            asset_bible_id=asset_bible_id,
        )
        return ImportPresetResponse(
            success=result.get("success", True),
            asset_bible_id=str(result.get("asset_bible_id", "")),
        )

    def list_asset_bibles(
        self,
        *,
        workspace_id: str,
        project_id: str,
    ) -> ListAssetBiblesResponse:
        raw = self._asset_bible_loader(
            api_base_url=self.api_base_url,
            workspace_id=workspace_id,
            project_id=project_id,
        )
        return ListAssetBiblesResponse(asset_bibles=[AssetBibleSummary(**item) for item in raw])

    def load_asset_bible(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
    ) -> AssetBibleDraft:
        raw = self._asset_bible_getter(
            api_base_url=self.api_base_url,
            workspace_id=workspace_id,
            project_id=project_id,
            asset_bible_id=asset_bible_id,
        )
        return AssetBibleDraft.model_validate(raw)

    def save_asset_bible(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
        payload: AssetBibleDraft,
    ) -> SaveResponse:
        self._asset_bible_saver(
            api_base_url=self.api_base_url,
            workspace_id=workspace_id,
            project_id=project_id,
            asset_bible_id=asset_bible_id,
            payload=payload.model_dump(),
        )
        return SaveResponse(success=True, message="已保存")

    def delete_asset_bible(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
    ) -> DeleteResponse:
        raise IPDesignClientError("HTTP client does not support delete_asset_bible")

    def list_scene_casts(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
    ) -> ListSceneCastsResponse:
        raw = self._scene_cast_loader(
            api_base_url=self.api_base_url,
            workspace_id=workspace_id,
            project_id=project_id,
            asset_bible_id=asset_bible_id,
        )
        return ListSceneCastsResponse(scene_casts=list(raw))

    def load_scene_cast(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
        scene_cast_id: str,
    ) -> SceneCastDraft:
        raw = self._scene_cast_getter(
            api_base_url=self.api_base_url,
            workspace_id=workspace_id,
            project_id=project_id,
            asset_bible_id=asset_bible_id,
            scene_cast_id=scene_cast_id,
        )
        return SceneCastDraft.model_validate(raw)

    def save_scene_cast(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
        scene_cast_id: str,
        payload: SceneCastDraft,
    ) -> SaveResponse:
        self._scene_cast_saver(
            api_base_url=self.api_base_url,
            workspace_id=workspace_id,
            project_id=project_id,
            asset_bible_id=asset_bible_id,
            scene_cast_id=scene_cast_id,
            payload=payload.model_dump(),
        )
        return SaveResponse(success=True, message="已保存")

    def delete_scene_cast(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
        scene_cast_id: str,
    ) -> DeleteResponse:
        raise IPDesignClientError("HTTP client does not support delete_scene_cast")


__all__ = ["HttpIPDesignClient"]
```

- [ ] **Step 3: 重写 `web/ip_design/inprocess_client.py`**

```python
from __future__ import annotations

from typing import Any

from api.asset_bible_responses import asset_bible_response_payload
from api.schemas.asset_bible import AssetBibleDraftRequest, SceneCastDraftRequest
from api.schemas.storyboard_workbench import validate_public_reference_id
from pixelle_video.models.asset_bible import AssetBible
from pixelle_video.services.asset_bible_import_metadata import (
    mark_imported_asset_bible_customized,
)
from pixelle_video.services.scene_casting import validate_scene_cast
from web.ip_design.models import (
    AssetBibleDraft,
    AssetBibleSummary,
    DeleteResponse,
    ImportPresetResponse,
    ListAssetBiblesResponse,
    ListPresetsResponse,
    ListSceneCastsResponse,
    PresetSummary,
    SaveResponse,
    SceneCastDraft,
)
from web.state.async_runtime import get_async_runtime


class InProcessIPDesignClient:
    def __init__(self, *, pixelle_video: Any, async_runner=None) -> None:
        self.pixelle_video = pixelle_video
        self._async_runner = async_runner

    def list_asset_bible_presets(self) -> list[dict[str, Any]]:
        registry = self._require_attr("asset_bible_preset_registry")
        return list(registry.list_summaries())

    def import_asset_bible_preset(
        self,
        *,
        workspace_id: str,
        project_id: str,
        preset_id: str,
        asset_bible_id: str | None = None,
        conflict_policy: str = "overwrite",
    ) -> ImportPresetResponse:
        workspace_id = validate_public_reference_id("workspace_id", workspace_id)
        project_id = validate_public_reference_id("project_id", project_id)
        preset_id = validate_public_reference_id("preset_id", preset_id)
        if asset_bible_id is not None and asset_bible_id.strip():
            asset_bible_id = validate_public_reference_id("asset_bible_id", asset_bible_id)
        else:
            asset_bible_id = None
        repository = self._require_attr("asset_bible_repository")
        registry = self._require_attr("asset_bible_preset_registry")
        asset_bible = registry.build_project_asset_bible(
            preset_id=preset_id,
            workspace_id=workspace_id,
            project_id=project_id,
            asset_bible_id=asset_bible_id,
        )
        asset_bible_payload = asset_bible.to_dict()
        imported_asset_bible_id = str(asset_bible_payload.get("asset_bible_id", "")).strip()
        existing = self._run_async(
            repository.load_asset_bible(workspace_id, imported_asset_bible_id)
        )
        if existing is not None and conflict_policy != "overwrite":
            raise ValueError("asset bible already exists; choose a different asset_bible_id")
        saved = self._run_async(repository.save_asset_bible(workspace_id, asset_bible_payload))
        return ImportPresetResponse(
            success=True,
            asset_bible_id=imported_asset_bible_id,
        )

    def list_asset_bibles(
        self,
        *,
        workspace_id: str,
        project_id: str,
    ) -> ListAssetBiblesResponse:
        repository = self._require_attr("asset_bible_repository")
        asset_bibles = self._run_async(repository.list_asset_bibles(workspace_id, project_id))
        return ListAssetBiblesResponse(
            asset_bibles=[
                AssetBibleSummary(
                    asset_bible_id=str(item.get("asset_bible_id", "")),
                    ip_profiles=list(item.get("ip_profiles", [])),
                    character_profiles=list(item.get("character_profiles", [])),
                    scene_assets=list(item.get("scene_assets", [])),
                    prop_assets=list(item.get("prop_assets", [])),
                    style_profiles=list(item.get("style_profiles", [])),
                    metadata=dict(item.get("metadata", {})),
                )
                for item in asset_bibles
            ]
        )

    def load_asset_bible(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
    ) -> AssetBibleDraft:
        repository = self._require_attr("asset_bible_repository")
        asset_bible = self._run_async(repository.load_asset_bible(workspace_id, asset_bible_id))
        if asset_bible is None:
            raise ValueError("asset bible draft was not found")
        return AssetBibleDraft.model_validate(
            asset_bible_response_payload(
                asset_bible,
                project_id=project_id,
                asset_bible_id=asset_bible_id,
            )
        )

    def save_asset_bible(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
        payload: AssetBibleDraft,
    ) -> SaveResponse:
        repository = self._require_attr("asset_bible_repository")
        request = AssetBibleDraftRequest(
            **{
                **payload.model_dump(),
                "workspace_id": workspace_id,
                "asset_bible_id": asset_bible_id,
            }
        )
        existing = self._run_async(repository.load_asset_bible(workspace_id, asset_bible_id))
        asset_bible_payload = mark_imported_asset_bible_customized(
            request.to_model(project_id=project_id).to_dict(),
            existing,
        )
        saved = self._run_async(
            repository.save_asset_bible(
                workspace_id,
                AssetBible.from_dict(asset_bible_payload).to_dict(),
            )
        )
        return SaveResponse(success=True, message="已保存")

    def delete_asset_bible(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
    ) -> DeleteResponse:
        repository = self._require_attr("asset_bible_repository")
        existing = self._run_async(repository.load_asset_bible(workspace_id, asset_bible_id))
        if existing is None:
            return DeleteResponse(success=False, errors=["AssetBible not found"])
        self._run_async(repository.delete_asset_bible(workspace_id, asset_bible_id))
        return DeleteResponse(success=True, message=f"已删除 {asset_bible_id}")

    def list_scene_casts(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
    ) -> ListSceneCastsResponse:
        repository = self._require_attr("asset_bible_repository")
        scene_casts = self._run_async(
            repository.list_scene_casts(workspace_id, project_id, asset_bible_id)
        )
        return ListSceneCastsResponse(scene_casts=list(scene_casts))

    def load_scene_cast(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
        scene_cast_id: str,
    ) -> SceneCastDraft:
        repository = self._require_attr("asset_bible_repository")
        scene_cast = self._run_async(repository.load_scene_cast(workspace_id, scene_cast_id))
        if scene_cast is None:
            raise ValueError("scene cast draft was not found")
        if scene_cast.get("project_id") != project_id:
            raise ValueError("scene cast project does not match request")
        if scene_cast.get("asset_bible_id") != asset_bible_id:
            raise ValueError("scene cast asset bible does not match request")
        return SceneCastDraft.model_validate(scene_cast)

    def save_scene_cast(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
        scene_cast_id: str,
        payload: SceneCastDraft,
    ) -> SaveResponse:
        repository = self._require_attr("asset_bible_repository")
        loaded_asset_bible = self._run_async(
            repository.load_asset_bible(workspace_id, asset_bible_id)
        )
        if loaded_asset_bible is None:
            raise ValueError("asset bible draft was not found")
        asset_bible = AssetBible.from_dict(loaded_asset_bible)
        if asset_bible.project_id != project_id:
            raise ValueError("asset bible project does not match request")
        request = SceneCastDraftRequest(
            **{
                **payload.model_dump(),
                "workspace_id": workspace_id,
                "scene_cast_id": scene_cast_id,
            }
        )
        scene_cast = request.to_model(
            project_id=project_id,
            asset_bible_id=asset_bible_id,
        )
        validate_scene_cast(scene_cast, asset_bible)
        saved = self._run_async(
            repository.save_scene_cast(
                workspace_id,
                scene_cast.to_dict(),
            )
        )
        return SaveResponse(success=True, message="已保存")

    def delete_scene_cast(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
        scene_cast_id: str,
    ) -> DeleteResponse:
        repository = self._require_attr("asset_bible_repository")
        existing = self._run_async(repository.load_scene_cast(workspace_id, scene_cast_id))
        if existing is None:
            return DeleteResponse(success=False, errors=["SceneCast not found"])
        self._run_async(repository.delete_scene_cast(workspace_id, scene_cast_id))
        return DeleteResponse(success=True, message=f"已删除 {scene_cast_id}")

    def _require_attr(self, name: str) -> Any:
        value = getattr(self.pixelle_video, name, None)
        if value is None:
            raise ValueError(f"{name} is not configured")
        return value

    def _run_async(self, coro):
        if self._async_runner is not None:
            return self._async_runner(coro)
        return get_async_runtime().run(coro)


__all__ = ["InProcessIPDesignClient"]
```

- [ ] **Step 4: 验证导入无报错**

Run:
```powershell
python -c "from web.ip_design.client import IPDesignClient; from web.ip_design.http_client import HttpIPDesignClient; from web.ip_design.inprocess_client import InProcessIPDesignClient; from web.ip_design.models import AssetBibleDraft, SaveResponse, DeleteResponse; print('OK')"
```
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add web/ip_design/client.py web/ip_design/http_client.py web/ip_design/inprocess_client.py web/ip_design/__init__.py
git commit -m "refactor: Client 层全面 Typed Protocol，新增 delete_asset_bible/delete_scene_cast"
```

---

## Task 5 — UI 组件重构（核心变更）

> **目标:** 整体重构 `ip_design_workbench.py`：Pydantic model、元编程自动映射、渐进式呈现、字段级验证、5 Tab、删除/复制、sidebar 预设导入、per-tab dirty 检测、feature flag。

**Files:**
- Modify: `web/components/ip_design_workbench.py`
- Modify: `web/pages/3_IP_Design_Workbench.py`（加 feature flag 切换）

- [ ] **Step 1: 完整重写 `web/components/ip_design_workbench.py`**

```python
from __future__ import annotations

from collections.abc import Callable
from typing import Any

import streamlit as st

from pixelle_video.platform_context import (
    DEFAULT_PROJECT_ID,
    DEFAULT_WORKSPACE_ID,
    first_explicit_text,
)
from pixelle_video.services.ip_color_palette import build_color_palette_prompt_entries
from pixelle_video.services.ip_profile_readiness import ip_generation_identity_terms
from web.i18n import tr
from web.ip_design.models import (
    AssetBibleDraft,
    CharacterProfileDraft,
    FieldId,
    IPProfileDraft,
    PropAssetDraft,
    ReadinessReport,
    SceneAssetDraft,
    SceneCastDraft,
    StyleProfileDraft,
)
from web.ip_design.session_keys import IPSessionKeys
from web.utils.streamlit_helpers import (
    build_model_from_form,
    find_item,
    first_text,
    keyed_text_area,
    keyed_text_input,
    list_of_dicts,
    populate_form_from_model,
    safe_rerun,
    split_csv,
    text_list,
)

Translate = Callable[..., str]

_VALIDATION_LAYOUT_RATIO = [0.92, 0.08]

_TAB_LABELS = ["ip_profile", "character", "scene", "prop", "style"]
_TAB_NAMES = ["ip_profile", "character", "scene", "prop", "style"]

_REQUIRED_FIELDS: dict[str, set[FieldId]] = {
    "ip_profile": {FieldId.NAME, FieldId.IP_TYPE, FieldId.LOGLINE},
    "character": set(),
    "scene": set(),
    "prop": set(),
    "style": set(),
}


def render_ip_design_workbench(
    *,
    ip_design_client,
    ui=st,
    translate: Translate = tr,
) -> None:
    workspace_id = first_explicit_text(st.session_state.get("workspace_id"), DEFAULT_WORKSPACE_ID)
    project_id = first_explicit_text(st.session_state.get("project_id"), DEFAULT_PROJECT_ID)

    if ip_design_client is None:
        ui.info(translate("ip_design.unavailable"))
        return

    ui.markdown(f"### {translate('ip_design.surface.title')}")
    ui.caption(translate("ip_design.surface.caption"))

    # 错误提示区域（使用 st.session_state 而非 ui.session_state，确保 .get() 兼容）
    if st.session_state.get("_ip_design_error"):
        ui.error(st.session_state["_ip_design_error"])

    # 就绪度条
    readiness = st.session_state.get("_ip_design_readiness")
    if readiness:
        total = len(FieldId)
        pct = int((total - len(readiness.missing)) / total * 100) if total else 0
        ui.progress(pct / 100, text=f"{translate('ip_design.readiness')} {pct}%")

    try:
        asset_response = ip_design_client.list_asset_bibles(
            workspace_id=workspace_id,
            project_id=project_id,
        )
    except Exception:
        ui.error(translate("ip_design.asset_bible.load_failed"))
        return

    # 预设导入（sidebar）
    _render_sidebar_actions(
        ip_design_client=ip_design_client,
        workspace_id=workspace_id,
        project_id=project_id,
        ui=ui,
        translate=translate,
    )

    # AssetBible 选择
    asset_bibles = asset_response.asset_bibles
    asset_bible_id = _render_asset_bible_selector(
        asset_bibles=asset_bibles,
        ui=ui,
        translate=translate,
    )
    if not asset_bible_id:
        return

    # 加载完整数据
    try:
        draft = ip_design_client.load_asset_bible(
            workspace_id=workspace_id,
            project_id=project_id,
            asset_bible_id=asset_bible_id,
        )
    except Exception:
        ui.error(translate("ip_design.asset_bible.load_failed"))
        return

    # 计算就绪度
    _compute_and_store_readiness(draft, state)

    # 5 Tab 编辑区
    tabs = ui.tabs(
        [translate(f"ip_design.tab.{label}") for label in _TAB_LABELS],
    )
    for tab_name, tab in zip(_TAB_NAMES, tabs):
        with tab:
            if st.session_state.get(IPSessionKeys.FORM._dirty, {}).get(tab_name):
                ui.warning(translate("ip_design.dirty_warning"))
            if tab_name == "ip_profile":
                _render_ip_profile_tab(
                    draft=draft,
                    ip_design_client=ip_design_client,
                    workspace_id=workspace_id,
                    project_id=project_id,
                    asset_bible_id=asset_bible_id,
                    ui=ui,
                    translate=translate,
                )
            elif tab_name == "character":
                _render_character_tab(
                    draft=draft,
                    ui=ui,
                    translate=translate,
                )
            elif tab_name == "scene":
                _render_scene_tab(
                    draft=draft,
                    ui=ui,
                    translate=translate,
                )
            elif tab_name == "prop":
                _render_prop_tab(
                    draft=draft,
                    ui=ui,
                    translate=translate,
                )
            elif tab_name == "style":
                _render_style_tab(
                    draft=draft,
                    ui=ui,
                    translate=translate,
                )

    # SceneCast 区
    try:
        scene_response = ip_design_client.list_scene_casts(
            workspace_id=workspace_id,
            project_id=project_id,
            asset_bible_id=asset_bible_id,
        )
    except Exception:
        ui.error(translate("ip_design.scene_cast.load_failed"))
        return

    _render_scene_cast_section(
        ip_design_client=ip_design_client,
        workspace_id=workspace_id,
        project_id=project_id,
        asset_bible_id=asset_bible_id,
        scene_casts=scene_response.scene_casts if scene_response.success else [],
        ui=ui,
        translate=translate,
    )


def _render_ip_profile_tab(
    *,
    draft: AssetBibleDraft,
    ip_design_client,
    workspace_id: str,
    project_id: str,
    asset_bible_id: str,
    ui,
    translate: Translate,
) -> None:
    profile_options = [p.ip_profile_id for p in draft.ip_profiles] + ["__new__"]
    selected_id = ui.selectbox(
        translate("ip_design.asset_bible.ip_profile"),
        profile_options,
        key=IPSessionKeys.FORM.ip_profile_select,
        format_func=lambda x: translate("ip_design.asset_bible.new_ip_profile") if x == "__new__" else x,
    )

    if selected_id == "__new__":
        profile = IPProfileDraft(ip_profile_id="", name="")
    else:
        matched = [p for p in draft.ip_profiles if p.ip_profile_id == selected_id]
        profile = matched[0] if matched else IPProfileDraft(ip_profile_id="", name="")

    # 回填到表单
    if IPSessionKeys.FORM.ip_profile_select not in ui.session_state:
        populate_form_from_model(profile, IPSessionKeys.FORM)

    # 核心信息（默认展开）
    with ui.container(border=True):
        ui.caption(translate("ip_design.section.core"))
        col1, col2 = ui.columns(2)
        with col1:
            ip_profile_id = keyed_text_input(
                ui,
                translate("ip_design.asset_bible.ip_profile_id"),
                key=IPSessionKeys.FORM.ip_profile_id,
                value=profile.ip_profile_id,
            )
        with col2:
            ip_type = ui.selectbox(
                translate("ip_design.asset_bible.ip_type"),
                ["cartoon_animal", "anime_human", "hybrid_real_anime", "line_drawing", "3d_cartoon"],
                key=IPSessionKeys.FORM.ip_type,
                on_change=lambda: _mark_dirty("ip_profile"),
            )
        # 每个 widget 添加 on_change 回调以标记脏状态
        name = keyed_text_input(
            ui,
            translate("ip_design.asset_bible.ip_name"),
            key=IPSessionKeys.FORM.name,
            value=profile.name,
            on_change=lambda: _mark_dirty("ip_profile"),
        )
        logline = keyed_text_area(
            ui,
            translate("ip_design.asset_bible.logline"),
            key=IPSessionKeys.FORM.logline,
            value=profile.logline,
            height=68,
            on_change=lambda: _mark_dirty("ip_profile"),
        )
        visual_summary = keyed_text_area(
            ui,
            translate("ip_design.asset_bible.visual_summary"),
            key=IPSessionKeys.FORM.visual_summary,
            value=profile.visual_summary,
            height=88,
        )

    # 视觉锚点
    with ui.container(border=True):
        ui.caption(translate("ip_design.section.visual_anchors"))
        identity_lock = keyed_text_input(
            ui,
            translate("ip_design.asset_bible.identity_lock"),
            key=IPSessionKeys.FORM.identity_lock,
            value=", ".join(profile.identity_lock),
        )
        color_rules = keyed_text_input(
            ui,
            translate("ip_design.asset_bible.color_palette"),
            key=IPSessionKeys.FORM.color_rules,
            value=_read_color_palette_prompt(profile.color_palette),
        )
        minimal_traits = keyed_text_input(
            ui,
            translate("ip_design.asset_bible.minimal_traits"),
            key=IPSessionKeys.FORM.minimal_traits,
            value=", ".join(profile.minimal_traits),
        )

    # 角色预设与约束（折叠）
    with ui.expander(translate("ip_design.section.role_presets"), expanded=False):
        role_presets = keyed_text_area(
            ui,
            translate("ip_design.asset_bible.role_presets"),
            key=IPSessionKeys.FORM.role_presets,
            value="\n".join(profile.role_presets),
            height=136,
        )
        negative_constraints = keyed_text_input(
            ui,
            translate("ip_design.asset_bible.negative_constraints"),
            key=IPSessionKeys.FORM.negative_constraints,
            value=", ".join(profile.negative_constraints),
        )

    # 高级设置（折叠）
    with ui.expander(translate("ip_design.section.advanced"), expanded=False):
        adaptable_slots = keyed_text_input(
            ui,
            translate("ip_design.asset_bible.adaptable_slots"),
            key=IPSessionKeys.FORM.adaptable_slots,
            value=", ".join(profile.adaptable_slots),
        )
        default_slot_pref = ui.selectbox(
            translate("ip_design.asset_bible.default_slot_preference"),
            ["prefer_supporting", "prefer_main", "auto", "minimal"],
            key=IPSessionKeys.FORM.default_slot_pref,
        )
        presence_spectrum = keyed_text_input(
            ui,
            translate("ip_design.asset_bible.presence_spectrum"),
            key=IPSessionKeys.FORM.presence_spectrum,
            value=", ".join(profile.presence_spectrum),
        )
        semantic_boundary = keyed_text_input(
            ui,
            translate("ip_design.asset_bible.semantic_boundary"),
            key=IPSessionKeys.FORM.semantic_boundary,
            value=", ".join(profile.semantic_boundary),
        )
        id_suppression = keyed_text_input(
            ui,
            translate("ip_design.asset_bible.identity_suppression_rules"),
            key=IPSessionKeys.FORM.id_suppression,
            value=", ".join(profile.identity_suppression_rules),
        )
        forbidden = keyed_text_input(
            ui,
            translate("ip_design.asset_bible.forbidden_elements"),
            key=IPSessionKeys.FORM.forbidden,
            value=", ".join(profile.forbidden_elements),
        )
        visible_text = keyed_text_input(
            ui,
            translate("ip_design.asset_bible.visible_text_whitelist"),
            key=IPSessionKeys.FORM.visible_text,
            value=", ".join(profile.visible_text_whitelist),
        )

    # 保存按钮
    _render_ip_save_button(
        ip_design_client=ip_design_client,
        workspace_id=workspace_id,
        project_id=project_id,
        asset_bible_id=asset_bible_id,
        draft=draft,
        profile=profile,
        color_rules=color_rules,
        ui=ui,
        translate=translate,
    )

    # 删除/复制
    _render_asset_bible_crud_actions(
        ip_design_client=ip_design_client,
        workspace_id=workspace_id,
        project_id=project_id,
        asset_bible_id=asset_bible_id,
        ui=ui,
        translate=translate,
    )


def _render_ip_save_button(
    *,
    ip_design_client,
    workspace_id: str,
    project_id: str,
    asset_bible_id: str,
    draft: AssetBibleDraft,
    profile: IPProfileDraft,
    color_rules: str,
    ui,
    translate: Translate,
) -> None:
    if not ui.button(
        translate("ip_design.asset_bible.save"),
        key="ip_design_save_asset_bible_v2",
    ):
        return

    try:
        built = build_model_from_form(IPProfileDraft, IPSessionKeys.FORM)
    except Exception as e:
        ui.error(f"{translate('ip_design.save_validation_error')}: {e}")
        return

    # 合并 color_palette
    built.color_palette = build_color_palette_prompt_entries(
        profile.color_palette,
        color_rules,
    )

    # 替换或追加到 draft
    new_ip_profiles = [p for p in draft.ip_profiles if p.ip_profile_id != built.ip_profile_id]
    new_ip_profiles.append(built)
    updated_draft = AssetBibleDraft(
        asset_bible_id=asset_bible_id,
        ip_profiles=new_ip_profiles,
        character_profiles=draft.character_profiles,
        scene_assets=draft.scene_assets,
        prop_assets=draft.prop_assets,
        style_profiles=draft.style_profiles,
    )

    try:
        result = ip_design_client.save_asset_bible(
            workspace_id=workspace_id,
            project_id=project_id,
            asset_bible_id=asset_bible_id,
            payload=updated_draft,
        )
    except Exception as e:
        ui.error(str(e))
        return

    if result.success:
        st.session_state[IPSessionKeys.FORM._dirty] = {}
        ui.toast(result.message)
        safe_rerun()
    else:
        ui.error("\n".join(result.errors))


def _render_asset_bible_crud_actions(
    *,
    ip_design_client,
    workspace_id: str,
    project_id: str,
    asset_bible_id: str,
    ui,
    translate: Translate,
) -> None:
    col1, col2 = ui.columns(2)
    with col1:
        if hasattr(ip_design_client, "delete_asset_bible"):
            with ui.popover(translate("ip_design.delete")):
                ui.caption(translate("ip_design.delete_confirm", id=asset_bible_id))
                if ui.button(translate("ip_design.delete_confirm_button"), type="primary"):
                    try:
                        result = ip_design_client.delete_asset_bible(
                            workspace_id=workspace_id,
                            project_id=project_id,
                            asset_bible_id=asset_bible_id,
                        )
                    except Exception as e:
                        ui.error(str(e))
                        return
                    if result.success:
                        ui.toast(result.message)
                        safe_rerun()
                    else:
                        ui.error("\n".join(result.errors))
    with col2:
        copy_popover_key = "_ip_design_copy_popover"
        with ui.popover(translate("ip_design.copy")):
            ui.caption(translate("ip_design.copy_instruction"))
            new_id = keyed_text_input(
                ui,
                translate("ip_design.asset_bible.ip_profile_id"),
                key=IPSessionKeys.FORM.ip_profile_id + "_copy",
                value=asset_bible_id + "_copy",
            )
            if ui.button(translate("ip_design.copy_confirm"), key=copy_popover_key):
                try:
                    # 复用当前 draft，只换 ID
                    copied_draft = draft.model_copy(update={"asset_bible_id": new_id})
                    result = ip_design_client.save_asset_bible(
                        workspace_id=workspace_id,
                        project_id=project_id,
                        asset_bible_id=new_id,
                        payload=copied_draft,
                    )
                except Exception as e:
                    ui.error(str(e))
                    return
                if result.success:
                    st.session_state[IPSessionKeys.ASSET_BIBLE.select] = new_id
                    ui.toast(result.message)
                    safe_rerun()
                else:
                    ui.error("\n".join(result.errors))


def _render_character_tab(
    *,
    draft: AssetBibleDraft,
    ui,
    translate: Translate,
) -> None:
    for i, char in enumerate(draft.character_profiles):
        with ui.container(border=True):
            ui.caption(f"{translate('ip_design.tab.character')} #{i + 1}")
            keyed_text_input(
                ui, translate("ip_design.character.character_id"),
                key=f"_char_{i}_id", value=char.character_id,
            )
            keyed_text_input(
                ui, translate("ip_design.character.display_name"),
                key=f"_char_{i}_name", value=char.display_name,
            )
            keyed_text_input(
                ui, translate("ip_design.character.role"),
                key=f"_char_{i}_role", value=char.role,
            )
            keyed_text_area(
                ui, translate("ip_design.character.visual_description"),
                key=f"_char_{i}_visual", value=char.visual_description, height=68,
            )
    if not draft.character_profiles:
        ui.caption(translate("ip_design.empty_tab"))


def _render_scene_tab(
    *,
    draft: AssetBibleDraft,
    ui,
    translate: Translate,
) -> None:
    for i, scene in enumerate(draft.scene_assets):
        with ui.container(border=True):
            ui.caption(f"{translate('ip_design.tab.scene')} #{i + 1}")
            keyed_text_input(
                ui, translate("ip_design.scene.scene_id"),
                key=f"_scene_{i}_id", value=scene.scene_id,
            )
            keyed_text_input(
                ui, translate("ip_design.scene.display_name"),
                key=f"_scene_{i}_name", value=scene.display_name,
            )
            keyed_text_area(
                ui, translate("ip_design.scene.visual_description"),
                key=f"_scene_{i}_visual", value=scene.visual_description, height=68,
            )
    if not draft.scene_assets:
        ui.caption(translate("ip_design.empty_tab"))


def _render_prop_tab(
    *,
    draft: AssetBibleDraft,
    ui,
    translate: Translate,
) -> None:
    for i, prop in enumerate(draft.prop_assets):
        with ui.container(border=True):
            ui.caption(f"{translate('ip_design.tab.prop')} #{i + 1}")
            keyed_text_input(
                ui, translate("ip_design.prop.prop_id"),
                key=f"_prop_{i}_id", value=prop.prop_id,
            )
            keyed_text_input(
                ui, translate("ip_design.prop.display_name"),
                key=f"_prop_{i}_name", value=prop.display_name,
            )
            keyed_text_area(
                ui, translate("ip_design.prop.visual_description"),
                key=f"_prop_{i}_visual", value=prop.visual_description, height=68,
            )
    if not draft.prop_assets:
        ui.caption(translate("ip_design.empty_tab"))


def _render_style_tab(
    *,
    draft: AssetBibleDraft,
    ui,
    translate: Translate,
) -> None:
    for i, style in enumerate(draft.style_profiles):
        with ui.container(border=True):
            ui.caption(f"{translate('ip_design.tab.style')} #{i + 1}")
            keyed_text_input(
                ui, translate("ip_design.style.style_id"),
                key=f"_style_{i}_id", value=style.style_id,
            )
            keyed_text_input(
                ui, translate("ip_design.style.display_name"),
                key=f"_style_{i}_name", value=style.display_name,
            )
            keyed_text_area(
                ui, translate("ip_design.style.visual_style"),
                key=f"_style_{i}_visual", value=style.visual_style, height=68,
            )
    if not draft.style_profiles:
        ui.caption(translate("ip_design.empty_tab"))


def _render_sidebar_actions(
    *,
    ip_design_client,
    workspace_id: str,
    project_id: str,
    ui,
    translate: Translate,
) -> None:
    with ui.sidebar:
        ui.markdown(f"### {translate('ip_design.sidebar.quick_actions')}")
        if hasattr(ip_design_client, "list_asset_bible_presets"):
            try:
                presets = ip_design_client.list_asset_bible_presets()
            except Exception:
                presets = []
            if presets:
                preset_options = [p.get("preset_id", "") for p in presets if p.get("preset_id")]
                selected = ui.selectbox(
                    translate("ip_design.asset_bible.builtin_presets"),
                    preset_options,
                    key=IPSessionKeys.PRESET.select,
                )
                import_id = keyed_text_input(
                    ui,
                    translate("ip_design.asset_bible.import_id"),
                    key=IPSessionKeys.PRESET.import_id,
                )
                if ui.button(translate("ip_design.asset_bible.import")):
                    try:
                        result = ip_design_client.import_asset_bible_preset(
                            workspace_id=workspace_id,
                            project_id=project_id,
                            preset_id=selected,
                            asset_bible_id=import_id,
                        )
                    except Exception as e:
                        ui.error(str(e))
                        return
                    if result.success:
                        ui.toast(translate("ip_design.asset_bible.imported"))
                        safe_rerun()
                    else:
                        ui.error("\n".join(result.errors))


def _render_asset_bible_selector(
    asset_bibles: list,
    *,
    ui,
    translate: Translate,
) -> str:
    ids = [b.asset_bible_id for b in asset_bibles]
    if not ids:
        ui.caption(translate("ip_design.asset_bible.empty"))
        return ""
    selected_id = ui.selectbox(
        translate("ip_design.asset_bible.select"),
        ids,
        key=IPSessionKeys.ASSET_BIBLE.select,
    )
    return selected_id


def _render_scene_cast_section(
    *,
    ip_design_client,
    workspace_id: str,
    project_id: str,
    asset_bible_id: str,
    scene_casts: list[dict[str, Any]],
    ui,
    translate: Translate,
) -> None:
    with ui.container(border=True):
        ui.markdown(f"#### {translate('ip_design.scene_cast.title')}")
        cast_ids = [first_text(c.get("scene_cast_id")) for c in scene_casts if first_text(c.get("scene_cast_id"))]
        if cast_ids:
            selected_id = ui.selectbox(
                translate("ip_design.scene_cast.select"),
                cast_ids,
                key=IPSessionKeys.SCENE_CAST.select,
            )
            selected = find_item(scene_casts, "scene_cast_id", selected_id) or {}
        else:
            selected_id = ""
            selected = {}
            ui.caption(translate("ip_design.scene_cast.empty"))

        scene_cast_id = keyed_text_input(
            ui, translate("ip_design.scene_cast.id"),
            key=IPSessionKeys.SCENE_CAST.id, value=selected_id,
        )
        storyboard_plan_id = keyed_text_input(
            ui, translate("ip_design.scene_cast.storyboard_plan_id"),
            key=IPSessionKeys.SCENE_CAST.storyboard_plan_id,
            value=first_text(selected.get("storyboard_plan_id")),
        )
        frame_id = keyed_text_input(
            ui, translate("ip_design.scene_cast.frame_id"),
            key=IPSessionKeys.SCENE_CAST.frame_id,
            value=first_text(selected.get("frame_id")),
        )
        character_ids = keyed_text_input(
            ui, translate("ip_design.scene_cast.character_ids"),
            key=IPSessionKeys.SCENE_CAST.character_ids,
            value=", ".join(text_list(selected.get("character_ids"))),
        )
        scene_id = keyed_text_input(
            ui, translate("ip_design.scene_cast.scene_id"),
            key=IPSessionKeys.SCENE_CAST.scene_id,
            value=first_text(selected.get("scene_id")),
        )
        prop_ids = keyed_text_input(
            ui, translate("ip_design.scene_cast.prop_ids"),
            key=IPSessionKeys.SCENE_CAST.prop_ids,
            value=", ".join(text_list(selected.get("prop_ids"))),
        )
        style_id = keyed_text_input(
            ui, translate("ip_design.scene_cast.style_id"),
            key=IPSessionKeys.SCENE_CAST.style_id,
            value=first_text(selected.get("style_id")),
        )

        if ui.button(
            translate("ip_design.scene_cast.save"),
            key="ip_design_save_scene_cast_v2",
        ):
            cast = SceneCastDraft(
                scene_cast_id=scene_cast_id,
                storyboard_plan_id=storyboard_plan_id,
                frame_id=frame_id,
                character_ids=split_csv(character_ids),
                scene_id=scene_id,
                prop_ids=split_csv(prop_ids),
                style_id=style_id,
            )
            try:
                result = ip_design_client.save_scene_cast(
                    workspace_id=workspace_id,
                    project_id=project_id,
                    asset_bible_id=asset_bible_id,
                    scene_cast_id=scene_cast_id,
                    payload=cast,
                )
            except Exception as e:
                ui.error(str(e))
                return
            if result.success:
                ui.toast(result.message)
                safe_rerun()
            else:
                ui.error("\n".join(result.errors))


def _read_color_palette_prompt(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    prompts: list[str] = []
    for key, item in value.items():
        if not str(key).startswith("rule_"):
            continue
        if isinstance(item, dict):
            prompt = first_text(item.get("prompt"))
            if prompt:
                prompts.append(prompt)
    return ", ".join(prompts)


def _mark_dirty(tab_name: str) -> None:
    dirty = dict(st.session_state.get(IPSessionKeys.FORM._dirty, {}))
    dirty[tab_name] = True
    st.session_state[IPSessionKeys.FORM._dirty] = dirty


def _compute_and_store_readiness(draft: AssetBibleDraft, state) -> None:
    """计算 IP Profile 的字段级就绪度并写入 session state。

    遍历 draft 中第一个 IP Profile 的必填字段，生成 ReadinessReport。
    """
    required_names = {field_id.value for field_id in _REQUIRED_FIELDS["ip_profile"]}
    if not draft.ip_profiles:
        st.session_state["_ip_design_readiness"] = ReadinessReport(ready=False)
        return
    profile = draft.ip_profiles[0]
    missing: list[FieldId] = []
    for field_id in _REQUIRED_FIELDS["ip_profile"]:
        value = getattr(profile, field_id.value, "")
        if not value or (isinstance(value, list) and not value):
            missing.append(field_id)
    st.session_state["_ip_design_readiness"] = ReadinessReport(
        ready=len(missing) == 0,
        missing=missing,
    )


__all__ = ["render_ip_design_workbench"]
```

- [ ] **Step 2: 修改 `web/pages/3_IP_Design_Workbench.py` 加入 feature flag**

在文件顶部 import 之后添加：

```python
import os

IP_DESIGN_V2_ENABLED = os.getenv("IP_DESIGN_V2_ENABLED", "false").lower() == "true"
```

修改 `render_ip_design_workbench_page` 函数：

```python
def render_ip_design_workbench_page(
    *,
    ui=st,
    translate=tr,
    workbench_renderer: WorkbenchRenderer = None,
) -> None:
    if workbench_renderer is None:
        if IP_DESIGN_V2_ENABLED:
            from web.components.ip_design_workbench import render_ip_design_workbench
            workbench_renderer = render_ip_design_workbench
        else:
            # 回退到旧版组件
            from web.components.ip_design_workbench_legacy import render_ip_design_workbench_legacy  # type: ignore
            workbench_renderer = render_ip_design_workbench_legacy

    ui.markdown(f"## {translate('ip_design.page.title')}")
    ui.caption(translate("ip_design.page.caption"))

    client_mode = resolve_workbench_client_mode(getattr(ui, "session_state", {}))
    pixelle_video = get_pixelle_video() if client_mode == "inprocess" else None
    ip_design_client = resolve_ip_design_client(
        getattr(ui, "session_state", {}),
        pixelle_video=pixelle_video,
    )
    workbench_renderer(
        ip_design_client=ip_design_client,
        ui=ui,
        translate=translate,
    )
```

- [ ] **Step 3: 验证导入无报错**

Run:
```powershell
python -c "from web.components.ip_design_workbench import render_ip_design_workbench; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add web/components/ip_design_workbench.py web/components/ip_design_workbench_legacy.py web/pages/3_IP_Design_Workbench.py
git commit -m "feat: 重构 IP Design Workbench — Pydantic model、5 Tab、渐进式 UI、CRUD、feature flag"
```

---

## Task 6 — 辅助组件替换 Helper 引用

> **目标:** 7 个辅助组件中的局部 helper 函数统一替换为 `streamlit_helpers`。

**Files:**
- Modify: `web/components/ip_workbench_panel.py`
- Modify: `web/components/asset_bible_draft_setup.py`
- Modify: `web/components/ip_prompt_chain_controls.py`
- Modify: `web/components/asset_prompt_plan_projection.py`
- Modify: `web/components/storyboard_workbench_panel.py`
- Modify: `web/components/content_ip_world_controls.py`
- Modify: `web/components/stale_panel.py`

每个文件的改动模式一致——删除局部定义，改为 import 自 `web.utils.streamlit_helpers`。

- [ ] **Step 1: 修改 `ip_workbench_panel.py`**

删除局部函数 `_first_text`, `_text_list`, `_list_of_dicts`, `_find_item` 的定义。在文件顶部添加：

```python
from web.utils.streamlit_helpers import (
    find_item,
    first_text,
    list_of_dicts,
    text_list,
)
```

将所有 `_first_text(` 调用改为 `first_text(`, `_list_of_dicts(` 改为 `list_of_dicts(`, `_text_list(` 改为 `text_list(`, `_find_item(` 改为 `find_item(`。

- [ ] **Step 1.5: 验证 `ip_workbench_panel.py` 导入无报错**

```powershell
python -c "from web.components.ip_workbench_panel import render_ip_workbench_panel; print('OK')"
```
Expected: `OK`

- [ ] **Step 2: 修改 `asset_bible_draft_setup.py`**

删除局部 `_text_input`, `_split_csv`, `_list_of_dicts` 定义。添加：

```python
from web.utils.streamlit_helpers import (
    keyed_text_input,
    list_of_dicts,
    split_csv,
)
```

将所有 `_text_input(` 改为 `keyed_text_input(`, `_split_csv(` 改为 `split_csv(`, `_list_of_dicts(` 改为 `list_of_dicts(`。

- [ ] **Step 2.5: 验证 `asset_bible_draft_setup.py` 导入无报错**

```powershell
python -c "from web.components.asset_bible_draft_setup import render_asset_bible_draft_setup; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: 修改 `ip_prompt_chain_controls.py`**

删除局部 `_text_list`, `_list_of_dicts`, `_first_text` 定义。添加：

```python
from web.utils.streamlit_helpers import (
    first_text,
    list_of_dicts,
    text_list,
)
```

将所有 `_first_text(` → `first_text(`, `_list_of_dicts(` → `list_of_dicts(`, `_text_list(` → `text_list(`。

- [ ] **Step 3.5: 验证 `ip_prompt_chain_controls.py` 导入无报错**

```powershell
python -c "from web.components.ip_prompt_chain_controls import render_ip_prompt_chain_controls; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: 修改 `asset_prompt_plan_projection.py`**

删除局部 `_text_input`, `_list_of_dicts`, `_find_item` 定义。添加：

```python
from web.utils.streamlit_helpers import (
    find_item,
    keyed_text_input,
    list_of_dicts,
)
```

将所有 `_text_input(` → `keyed_text_input(`, `_list_of_dicts(` → `list_of_dicts(`, `_find_item(` → `find_item(`。

- [ ] **Step 4.5: 验证 `asset_prompt_plan_projection.py` 导入无报错**

```powershell
python -c "from web.components.asset_prompt_plan_projection import render_asset_prompt_plan_projection_preview; print('OK')"
```
Expected: `OK`

- [ ] **Step 5: 修改 `storyboard_workbench_panel.py`**

删除局部 `_list_of_dicts`, `_first_text` 定义。添加：

```python
from web.utils.streamlit_helpers import first_text, list_of_dicts
```

将所有 `_list_of_dicts(` → `list_of_dicts(`, `_first_text(` → `first_text(`。

- [ ] **Step 5.5: 验证 `storyboard_workbench_panel.py` 导入无报错**

```powershell
python -c "from web.components.storyboard_workbench_panel import render_storyboard_workbench_panel; print('OK')"
```
Expected: `OK`

- [ ] **Step 6: 修改 `content_ip_world_controls.py`**

找到局部 `_first_text` 定义并删除。添加：

```python
from web.utils.streamlit_helpers import first_text
```

将所有 `_first_text(` → `first_text(`。

- [ ] **Step 6.5: 验证 `content_ip_world_controls.py` 导入无报错**

```powershell
python -c "from web.components.content_ip_world_controls import render_content_ip_world_controls; print('OK')"
```
Expected: `OK`

- [ ] **Step 7: 修改 `stale_panel.py`**

找到局部 `_list_of_dicts` 定义并删除。添加：

```python
from web.utils.streamlit_helpers import list_of_dicts
```

将所有 `_list_of_dicts(` → `list_of_dicts(`。

- [ ] **Step 7.5: 验证 `stale_panel.py` 导入无报错**

```powershell
python -c "from web.components.stale_panel import render_stale_target_panel; print('OK')"
```
Expected: `OK`

- [ ] **Step 8: 验证所有模板都导入正常**

Run:
```powershell
python -c "
from web.components.ip_workbench_panel import render_ip_workbench_panel
from web.components.asset_bible_draft_setup import render_asset_bible_draft_setup
from web.components.ip_prompt_chain_controls import render_ip_prompt_chain_controls
from web.components.storyboard_workbench_panel import render_storyboard_workbench_panel
from web.components.content_ip_world_controls import render_content_ip_world_controls
from web.components.stale_panel import render_stale_target_panel
from web.components.asset_prompt_plan_projection import render_asset_prompt_plan_projection_preview
print('ALL OK')
"
```
Expected: `ALL OK`

- [ ] **Step 9: 批量确认没有遗留的局部 `_first_text` 等定义**

Run:
```powershell
rg '^def _first_text|^def _list_of_dicts|^def _text_list|^def _find_item|^def _text_input|^def _text_area|^def _split_csv' web/components/
```
Expected: 0 matches（全部被替换）

- [ ] **Step 10: Commit**

```bash
git add web/components/ip_workbench_panel.py web/components/asset_bible_draft_setup.py web/components/ip_prompt_chain_controls.py web/components/asset_prompt_plan_projection.py web/components/storyboard_workbench_panel.py web/components/content_ip_world_controls.py web/components/stale_panel.py
git commit -m "refactor: 7 个组件替换局部 helper 为 streamlit_helpers 统一引用"
```

---

## Task 7 — i18n 文本补充

> **目标:** 新增 Tab 标签、CRUD 按钮、dirty 状态、字段验证等翻译键。

**Files:**
- Modify: `web/i18n/locales/zh_CN.json`
- Modify: `web/i18n/locales/en_US.json`

- [ ] **Step 1: 在 `zh_CN.json` 中添加新 key**

在 `ip_design` 区块内添加：

```json
{
  "ip_design": {
    "readiness": "就绪度",
    "save_validation_error": "表单验证失败",
    "dirty_warning": "当前 Tab 有未保存修改",
    "delete": "删除",
    "delete_confirm": "确认删除 {id}？此操作不可撤销",
    "delete_confirm_button": "确认删除",
    "copy": "复制此 AssetBible",
    "copy_instruction": "请输入新 AssetBible ID（留空自动生成）",
    "copy_confirm": "确认复制",
    "empty_tab": "暂无数据",
    "sidebar.quick_actions": "快速操作",
    "section.core": "核心信息",
    "section.visual_anchors": "视觉锚点",
    "section.role_presets": "角色预设与约束",
    "section.advanced": "高级设置",
    "tab.ip_profile": "IP Profile",
    "tab.character": "配角",
    "tab.scene": "场景",
    "tab.prop": "道具",
    "tab.style": "风格",
    "character.character_id": "角色 ID",
    "character.display_name": "显示名称",
    "character.role": "角色类型",
    "character.visual_description": "视觉描述",
    "scene.scene_id": "场景 ID",
    "scene.display_name": "显示名称",
    "scene.visual_description": "视觉描述",
    "prop.prop_id": "道具 ID",
    "prop.display_name": "显示名称",
    "prop.visual_description": "视觉描述",
    "style.style_id": "风格 ID",
    "style.display_name": "显示名称",
    "style.visual_style": "视觉风格",
    "scene_cast.prop_ids": "道具 ID 列表",
    "scene_cast.style_id": "风格 ID"
  }
}
```

- [ ] **Step 2: 在 `en_US.json` 中对应添加**

```json
{
  "ip_design": {
    "readiness": "Readiness",
    "save_validation_error": "Form validation failed",
    "dirty_warning": "Current tab has unsaved changes",
    "delete": "Delete",
    "delete_confirm": "Confirm delete {id}? This action cannot be undone",
    "delete_confirm_button": "Confirm Delete",
    "copy": "Copy this AssetBible",
    "copy_instruction": "Enter a new AssetBible ID (leave blank for auto-generate)",
    "copy_confirm": "Confirm Copy",
    "empty_tab": "No data",
    "sidebar.quick_actions": "Quick Actions",
    "section.core": "Core Information",
    "section.visual_anchors": "Visual Anchors",
    "section.role_presets": "Role Presets & Constraints",
    "section.advanced": "Advanced Settings",
    "tab.ip_profile": "IP Profile",
    "tab.character": "Characters",
    "tab.scene": "Scenes",
    "tab.prop": "Props",
    "tab.style": "Styles",
    "character.character_id": "Character ID",
    "character.display_name": "Display Name",
    "character.role": "Role",
    "character.visual_description": "Visual Description",
    "scene.scene_id": "Scene ID",
    "scene.display_name": "Display Name",
    "scene.visual_description": "Visual Description",
    "prop.prop_id": "Prop ID",
    "prop.display_name": "Display Name",
    "prop.visual_description": "Visual Description",
    "style.style_id": "Style ID",
    "style.display_name": "Display Name",
    "style.visual_style": "Visual Style",
    "scene_cast.prop_ids": "Prop IDs",
    "scene_cast.style_id": "Style ID"
  }
}
```

- [ ] **Step 3: 验证 JSON 文件格式**

Run:
```powershell
python -c "import json; json.load(open('web/i18n/locales/zh_CN.json', 'r', encoding='utf-8')); json.load(open('web/i18n/locales/en_US.json', 'r', encoding='utf-8')); print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add web/i18n/locales/zh_CN.json web/i18n/locales/en_US.json
git commit -m "feat: i18n 新增 Tab/CRUD/验证文本"
```

---

## Task 8 — 测试

> **目标:** 新增 3 个测试文件 + 适配已有测试。

**Files:**
- Create: `tests/test_ip_design_models.py`
- Create: `tests/test_streamlit_helpers_ext.py`
- Create: `tests/test_ip_design_client_typed.py`
- Modify: `tests/test_ip_design_workbench_ui.py`

- [ ] **Step 1: 创建 `tests/test_ip_design_models.py`**

```python
from __future__ import annotations

from web.ip_design.models import (
    AssetBibleDraft,
    CharacterProfileDraft,
    FieldId,
    IPProfileDraft,
    SceneCastDraft,
)


def test_field_id_enum_values():
    assert FieldId.NAME.value == "name"
    assert FieldId.IP_TYPE.value == "ip_type"
    assert FieldId.LOGLINE.value == "logline"


def test_ip_profile_draft_construction():
    profile = IPProfileDraft(ip_profile_id="ip_1", name="Test IP")
    assert profile.ip_profile_id == "ip_1"
    assert profile.name == "Test IP"
    assert profile.ip_type == "cartoon_animal"
    assert profile.logline == ""
    assert profile.identity_lock == []


def test_ip_profile_draft_serialization():
    profile = IPProfileDraft(
        ip_profile_id="ip_1",
        name="Test",
        logline="A test",
        identity_lock=["feature_a", "feature_b"],
    )
    data = profile.model_dump()
    assert data["ip_profile_id"] == "ip_1"
    assert data["identity_lock"] == ["feature_a", "feature_b"]


def test_asset_bible_draft_round_trip():
    original = AssetBibleDraft(
        asset_bible_id="bible_1",
        ip_profiles=[
            IPProfileDraft(ip_profile_id="ip_1", name="IP One"),
        ],
        character_profiles=[
            CharacterProfileDraft(character_id="char_1", display_name="Char One"),
        ],
    )
    data = original.model_dump()
    restored = AssetBibleDraft.model_validate(data)
    assert restored.asset_bible_id == "bible_1"
    assert len(restored.ip_profiles) == 1
    assert restored.ip_profiles[0].name == "IP One"
    assert len(restored.character_profiles) == 1
    assert restored.character_profiles[0].display_name == "Char One"


def test_scene_cast_draft_construction():
    cast = SceneCastDraft(
        scene_cast_id="cast_1",
        storyboard_plan_id="plan_1",
        frame_id="frame_001",
        character_ids=["char_1", "char_2"],
    )
    assert cast.scene_cast_id == "cast_1"
    assert cast.character_ids == ["char_1", "char_2"]
```

- [ ] **Step 2: 运行 model 测试**

Run:
```powershell
python -m pytest tests/test_ip_design_models.py -v
```
Expected: 5 passed

- [ ] **Step 3: 创建 `tests/test_streamlit_helpers_ext.py`**

```python
from __future__ import annotations

from web.utils.streamlit_helpers import (
    find_item,
    first_text,
    list_of_dicts,
    split_csv,
    text_list,
)


def test_first_text():
    assert first_text("hello") == "hello"
    assert first_text(None, "") == ""
    assert first_text(None, "fallback") == "fallback"
    assert first_text("  spaced  ") == "spaced"


def test_list_of_dicts():
    assert list_of_dicts([{"a": 1}, {"b": 2}]) == [{"a": 1}, {"b": 2}]
    assert list_of_dicts(None) == []
    assert list_of_dicts("not a list") == []
    assert list_of_dicts([{"a": 1}, "string"]) == [{"a": 1}]


def test_text_list():
    assert text_list(["a", "b", None, ""]) == ["a", "b"]
    assert text_list(None) == []
    assert text_list(["  spaced  "]) == ["spaced"]


def test_split_csv():
    assert split_csv("a, b, c") == ["a", "b", "c"]
    assert split_csv("") == []
    assert split_csv("single") == ["single"]
    assert split_csv("a,,b") == ["a", "b"]


def test_find_item():
    items = [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}]
    result = find_item(items, "id", "a")
    assert result is not None
    assert result["name"] == "A"
    assert find_item(items, "id", "z") is None
```

- [ ] **Step 4: 运行 helper 测试**

Run:
```powershell
python -m pytest tests/test_streamlit_helpers_ext.py -v
```
Expected: 5 passed

- [ ] **Step 5: 创建 `tests/test_ip_design_client_typed.py`**

```python
from __future__ import annotations

from web.ip_design.models import (
    AssetBibleDraft,
    DeleteResponse,
    ListAssetBiblesResponse,
    SaveResponse,
    SceneCastDraft,
)


def test_list_asset_bibles_response_from_dict():
    raw = {
        "success": True,
        "asset_bibles": [
            {
                "asset_bible_id": "bible_1",
                "ip_profiles": [],
                "character_profiles": [],
                "scene_assets": [],
                "prop_assets": [],
                "style_profiles": [],
            }
        ],
    }
    resp = ListAssetBiblesResponse.model_validate(raw)
    assert resp.success is True
    assert len(resp.asset_bibles) == 1
    assert resp.asset_bibles[0].asset_bible_id == "bible_1"


def test_save_response():
    resp = SaveResponse(success=True, message="已保存")
    assert resp.success is True
    assert resp.message == "已保存"


def test_delete_response():
    resp = DeleteResponse(success=True, message="已删除 bible_1")
    assert resp.success is True


def test_asset_bible_draft_model_validate():
    raw = {
        "asset_bible_id": "bible_1",
        "ip_profiles": [
            {"ip_profile_id": "ip_1", "name": "Test"}
        ],
    }
    draft = AssetBibleDraft.model_validate(raw)
    assert draft.asset_bible_id == "bible_1"
    assert len(draft.ip_profiles) == 1


def test_scene_cast_draft_model_validate():
    raw = {
        "scene_cast_id": "cast_1",
        "storyboard_plan_id": "plan_1",
        "frame_id": "frame_001",
    }
    cast = SceneCastDraft.model_validate(raw)
    assert cast.scene_cast_id == "cast_1"
    assert cast.storyboard_plan_id == "plan_1"
```

- [ ] **Step 6: 运行 client typed 测试**

Run:
```powershell
python -m pytest tests/test_ip_design_client_typed.py -v
```
Expected: 5 passed

- [ ] **Step 7: 适配 `tests/test_ip_design_workbench_ui.py`**

更新 `_FakeIPDesignClient` 以返回 typed response。关键修改点：

- `list_asset_bibles` 返回 `ListAssetBiblesResponse`
- `load_asset_bible` 返回 `AssetBibleDraft`
- `save_asset_bible` 接收 `AssetBibleDraft` 作为 `payload`
- `list_scene_casts` 返回 `ListSceneCastsResponse`

先更新 `list_asset_bibles`:

```python
def list_asset_bibles(self, **kwargs):
    self.calls.append({"method": "list_asset_bibles", **kwargs})
    from web.ip_design.models import ListAssetBiblesResponse, AssetBibleSummary
    return ListAssetBiblesResponse(
        asset_bibles=[AssetBibleSummary(**b) for b in self.asset_bibles]
    )
```

更新 `save_asset_bible`:

```python
def save_asset_bible(self, **kwargs):
    self.calls.append({"method": "save_asset_bible", **kwargs})
    from web.ip_design.models import SaveResponse
    payload = kwargs["payload"]
    # payload 现在是 AssetBibleDraft，用 model_dump()
    new_bible = _asset_bible(asset_bible_id=kwargs["asset_bible_id"])
    new_bible["ip_profiles"] = [p.model_dump() for p in payload.ip_profiles]
    self.asset_bibles = [new_bible]
    return SaveResponse(success=True, message="已保存")
```

- [ ] **Step 8: 运行全量测试**

Run:
```powershell
python -m pytest tests/test_ip_design_models.py tests/test_streamlit_helpers_ext.py tests/test_ip_design_client_typed.py tests/test_ip_design_workbench_ui.py -v
```
Expected: 全部通过

- [ ] **Step 9: Commit**

```bash
git add tests/test_ip_design_models.py tests/test_streamlit_helpers_ext.py tests/test_ip_design_client_typed.py tests/test_ip_design_workbench_ui.py
git commit -m "test: 新增 model/helper/client typed 测试，适配已有 UI 测试"
```

---

## 未纳入范围

- `pixelle_video/services/ip_usage_planner.py` 中的 `_first_text`—核心库不在 scope
- `web/utils/asset_bible_payloads.py` 中的 `build_asset_bible_payload`—已标记 `@deprecated`，在 API 层后续重构中移除
- 删除 `asset_bible_draft_setup.py`—Stage2 仍然使用
