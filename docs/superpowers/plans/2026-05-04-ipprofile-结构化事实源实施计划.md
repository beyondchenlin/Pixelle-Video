# IPProfile 结构化事实源 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 IP 设计、AssetBible API、标准生成链路之间的数据合同断层，让启用 IP 的 Z-Image 文生图必须消费结构化身份锚点，且空锚点直接阻断生成。

**Architecture:** `IPProfile` 是唯一正式 IP 事实源。AssetBible 的创建与保存入口统一改为模型对齐的 `ip_profiles` 嵌套结构，IP 设计工作台与 Stage2 草稿创建入口都直接写入结构化字段；标准生成在解析 IP Profile 后进行完整性校验，最终 prompt 测试验证身份锚点进入 Z-Image 单段 prompt。本计划不做旧数据迁移，不做 `style_hint / forbidden_elements` 运行时兼容猜测，也不保留平铺轻量创建合同。

**Tech Stack:** Python dataclasses, Pydantic v2, FastAPI, Streamlit component helpers, pytest, local JSON repositories, Z-Image prompt assembly.

---

## Scope Guard

本计划只实现 `docs/superpowers/specs/2026-05-04-ipprofile-结构化事实源设计.md`。

包含：

- AssetBible API / schema 完整保存结构化 `IPProfile`
- AssetBible 正式创建/保存入口统一使用 `ip_profiles` 嵌套合同
- IP 设计工作台编辑和保存结构化 IP 字段
- Stage2 草稿创建入口改为直接创建结构化 `IPProfile`
- 启用 IP 时身份锚点缺失直接阻断生成
- 最终 Z-Image prompt 验证身份锚点进入输出

不包含：

- 旧 AssetBible 自动迁移
- 从 `style_hint / forbidden_elements` 推断身份锚点
- 生成页世界观提示 `generation_world_hint`
- 参考图、LoRA、IPAdapter、图生图

## File Structure

- Modify `api/schemas/asset_bible.py`
  - 新增 `IPProfileDraft` 请求模型，与 `pixelle_video.models.asset_bible.IPProfile` 字段对齐。
  - 扩展 `IPProfileResponse`，返回完整结构化字段。
  - 将 `AssetBibleDraftRequest` 改为正式只接收 `ip_profiles` 嵌套结构，并要求至少一个 `IPProfile`。

- Modify `api/routers/asset_bible.py`
  - `_request_to_model(...)` 通过新的嵌套合同构建完整 `AssetBible`。
  - 保持路由和 stale write 行为不变。

- Modify `web/utils/asset_bible_api.py`
  - `save_asset_bible(...)` 透传嵌套 `ip_profiles` payload。
  - `create_asset_bible(...)` 改为和正式合同一致的 payload 入口，不再保留平铺 `ip_name / world_hint / style_hint` helper 合同。

- Modify `web/ip_design/inprocess_client.py`
  - 使用新的 `AssetBibleDraftRequest` 保存完整结构化 IPProfile。

- Modify `web/components/asset_bible_draft_setup.py`
  - Stage2 草稿创建表单增加最小结构化 IP 字段输入。
  - 创建 payload 改为 `ip_profiles: [...]`，不再发送平铺 IP 字段。

- Modify `web/components/ip_design_workbench.py`
  - 增加结构化字段输入区。
  - 保存 payload 改为 `ip_profiles: [...]`。
  - 显示“可用于生成 / 缺少身份锚点”状态。

- Modify `web/i18n/locales/zh_CN.json`
  - 新增结构化字段 UI 文案。

- Modify `web/i18n/locales/en_US.json`
  - 新增英文文案。

- Modify `pixelle_video/pipelines/standard.py`
  - 在 `_resolve_ip_prompt_chain_inputs(...)` 解析到 `ip_profile` 后执行完整性校验。

- Modify `pixelle_video/utils/content_generators.py`
  - 如果还存在绕过标准管线直接调用 `generate_styled_image_prompt_batch(...)` 的测试入口，也要在 `ip_enabled=True` 时校验 `ip_profile` 身份锚点。

- Tests:
  - Modify `tests/test_asset_bible_api.py`
  - Modify `tests/test_ip_design_client.py`
  - Modify `tests/test_ip_design_workbench_ui.py`
  - Modify `tests/test_asset_prompt_plan_projection_ui.py`
  - Modify `tests/test_standard_pipeline_storyboard_generation.py`
  - Modify `tests/test_styled_image_prompt_batch.py`
  - Modify `tests/test_video_api.py` only if error propagation needs API-level assertion.

## Atomicity Rule

Task 1, Task 2, and Task 3 are one source-level contract batch. Do not commit after Task 1 or Task 2, because changing the API schema without updating every formal sender leaves a known broken intermediate state. Commit and push only after Task 3 passes the API, IP design, and Stage2 structured-entry tests.

---

## Task 1: AssetBible API Contract

**Files:**

- Modify: `api/schemas/asset_bible.py`
- Modify: `api/routers/asset_bible.py`
- Modify: `tests/test_asset_bible_api.py`

- [ ] **Step 1: Write failing API test for nested IPProfile fields**

Add this test near the existing AssetBible create/update tests in `tests/test_asset_bible_api.py`:

```python
def test_update_asset_bible_preserves_structured_ip_profile_fields():
    client = _client_with_repository()
    payload = _asset_bible_payload(
        ip_profiles=[
            {
                "ip_profile_id": "ip_main",
                "name": "正定向导兔",
                "logline": "一只白色兔子古城向导。",
                "world_hint": "正定古城、城墙、古寺、青砖、历史文化旅游。",
                "style_hint": "亲和、清爽、适合文旅短视频。",
                "identity_lock": ["白色卡通兔子", "长耳朵", "圆润脸型"],
                "identity_anchors": ["蓝色领结", "浅粉色耳朵内侧"],
                "identity_suppression_rules": ["远景时弱化耳朵内侧细节"],
                "variable_slots": ["动作", "表情", "站位"],
                "semantic_boundary": ["不能变成人类", "不能替代历史建筑"],
                "negative_constraints": ["避免画成普通人类讲述者", "避免多余文字"],
                "color_palette": {
                    "tie": {"hex": "#006BFF", "prompt": "鲜明宝蓝色领结"}
                },
                "image_text_palette": {
                    "title": {"hex": "#5A2A12", "prompt": "深棕色墨迹标题字"}
                },
                "visible_text_whitelist": ["长乐门", "正定古城"],
                "metadata": {"source": "unit-test"},
            }
        ],
    )

    response = client.put(
        "/api/projects/project_1/asset-bibles/bible_demo",
        json=payload,
    )

    assert response.status_code == 200
    profile = response.json()["asset_bible"]["ip_profiles"][0]
    assert profile["identity_lock"] == ["白色卡通兔子", "长耳朵", "圆润脸型"]
    assert profile["identity_anchors"] == ["蓝色领结", "浅粉色耳朵内侧"]
    assert profile["semantic_boundary"] == ["不能变成人类", "不能替代历史建筑"]
    assert profile["negative_constraints"] == ["避免画成普通人类讲述者", "避免多余文字"]
    assert profile["color_palette"]["tie"]["prompt"] == "鲜明宝蓝色领结"
    assert profile["visible_text_whitelist"] == ["长乐门", "正定古城"]
```

Update `_asset_bible_payload(...)` so nested `ip_profiles` is the only formal request shape used by tests:

```python
def _asset_bible_payload(**overrides) -> dict[str, Any]:
    payload = {
        "workspace_id": "workspace_1",
        "asset_bible_id": "bible_demo",
        "ip_profiles": [
            {
                "ip_profile_id": "ip_main",
                "name": "Pixelle Demo",
                "world_hint": "Soft futuristic city.",
                "style_hint": "clean comic panels",
            }
        ],
        ...
    }
    payload.update(overrides)
    return payload
```

- [ ] **Step 2: Run test to verify RED**

Run:

```powershell
pytest tests/test_asset_bible_api.py::test_update_asset_bible_preserves_structured_ip_profile_fields -v
```

Expected: FAIL because `AssetBibleDraftRequest` still expects flat top-level IP fields.

- [ ] **Step 3: Implement `IPProfileDraft` and response fields**

In `api/schemas/asset_bible.py`, add a draft model near `AssetBibleDraftRequest`:

```python
class IPProfileDraft(PublicMetadataModel):
    model_config = ConfigDict(extra="forbid")

    ip_profile_id: str
    name: str
    logline: str | None = None
    world_hint: str | None = None
    style_hint: str | None = None
    identity_lock: list[str] = Field(default_factory=list)
    identity_anchors: list[str] = Field(default_factory=list)
    identity_suppression_rules: list[str] = Field(default_factory=list)
    variable_slots: list[str] = Field(default_factory=list)
    semantic_boundary: list[str] = Field(default_factory=list)
    negative_constraints: list[str] = Field(default_factory=list)
    color_palette: dict[str, Any] = Field(default_factory=dict)
    image_text_palette: dict[str, Any] = Field(default_factory=dict)
    visible_text_whitelist: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("ip_profile_id")
    @classmethod
    def validate_id(cls, value: str, info) -> str:
        return validate_public_reference_id(info.field_name, value)

    @field_validator(
        "identity_lock",
        "identity_anchors",
        "identity_suppression_rules",
        "variable_slots",
        "semantic_boundary",
        "negative_constraints",
        "visible_text_whitelist",
    )
    @classmethod
    def validate_text_list(cls, value: list[str], info) -> list[str]:
        cleaned = [item.strip() for item in value if isinstance(item, str) and item.strip()]
        if len(cleaned) != len(value):
            raise ValueError(f"{info.field_name} must not include blank values")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError(f"{info.field_name} must not include duplicate values")
        return cleaned

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        reject_unsafe_public_metadata("metadata", value)
        return value

    def to_model(self, *, workspace_id: str, project_id: str) -> IPProfile:
        return IPProfile(
            ip_profile_id=self.ip_profile_id,
            workspace_id=workspace_id,
            project_id=project_id,
            name=self.name,
            logline=self.logline,
            world_hint=self.world_hint,
            style_hint=self.style_hint,
            identity_lock=tuple(self.identity_lock),
            identity_anchors=tuple(self.identity_anchors),
            identity_suppression_rules=tuple(self.identity_suppression_rules),
            variable_slots=tuple(self.variable_slots),
            semantic_boundary=tuple(self.semantic_boundary),
            negative_constraints=tuple(self.negative_constraints),
            color_palette=self.color_palette,
            image_text_palette=self.image_text_palette,
            visible_text_whitelist=tuple(self.visible_text_whitelist),
            metadata=self.metadata,
        )
```

Extend `IPProfileResponse` with the same structured fields:

```python
identity_lock: list[str] = Field(default_factory=list)
identity_anchors: list[str] = Field(default_factory=list)
identity_suppression_rules: list[str] = Field(default_factory=list)
variable_slots: list[str] = Field(default_factory=list)
semantic_boundary: list[str] = Field(default_factory=list)
negative_constraints: list[str] = Field(default_factory=list)
color_palette: dict[str, Any] = Field(default_factory=dict)
image_text_palette: dict[str, Any] = Field(default_factory=dict)
visible_text_whitelist: list[str] = Field(default_factory=list)
```

Update `AssetBibleDraftRequest`:

```python
ip_profiles: list[IPProfileDraft] = Field(min_length=1)
```

Delete the old flat request fields from `AssetBibleDraftRequest`:

```python
ip_profile_id
ip_name
logline
world_hint
style_hint
forbidden_elements
```

Add a validator so duplicated `ip_profile_id` values are rejected:

```python
@field_validator("ip_profiles")
@classmethod
def validate_ip_profiles(cls, value: list[IPProfileDraft]) -> list[IPProfileDraft]:
    ids = [item.ip_profile_id for item in value]
    if len(set(ids)) != len(ids):
        raise ValueError("ip_profiles must not include duplicate ip_profile_id")
    return value
```

In `to_model(...)`, build `ip_profiles` like this:

```python
ip_profiles = tuple(
    profile.to_model(workspace_id=self.workspace_id, project_id=project_id)
    for profile in self.ip_profiles
)

return AssetBible(
    asset_bible_id=self.asset_bible_id,
    workspace_id=self.workspace_id,
    project_id=project_id,
    ip_profiles=ip_profiles,
    ...
)
```

Any caller or test still sending flat top-level IP fields must be updated in this plan. Do not keep a compatibility branch in the request schema.

- [ ] **Step 4: Run focused API test**

Run:

```powershell
pytest tests/test_asset_bible_api.py::test_update_asset_bible_preserves_structured_ip_profile_fields -v
```

Expected: PASS.

- [ ] **Step 5: Run full AssetBible API tests**

Run:

```powershell
pytest tests/test_asset_bible_api.py tests/test_asset_bible_models.py -v
```

Expected: PASS.

- [ ] **Step 6: Contract checkpoint, do not commit yet**

Do not commit this task by itself. Continue to Task 2 and Task 3, then commit the whole contract batch once all formal senders have been moved to nested `ip_profiles`.

---

## Task 2: IP Design Workbench Structured Fields

**Files:**

- Modify: `web/components/ip_design_workbench.py`
- Modify: `web/i18n/locales/zh_CN.json`
- Modify: `web/i18n/locales/en_US.json`
- Modify: `tests/test_ip_design_workbench_ui.py`

- [ ] **Step 1: Write failing UI save test**

Update `tests/test_ip_design_workbench_ui.py::test_ip_design_workbench_saves_asset_bible_through_client`.

Add session state values:

```python
"ip_design_identity_lock": "白色卡通兔子, 长耳朵, 圆润脸型",
"ip_design_identity_anchors": "蓝色领结, 浅粉色耳朵内侧",
"ip_design_identity_suppression_rules": "远景弱化耳朵内侧",
"ip_design_variable_slots": "动作, 表情, 站位",
"ip_design_semantic_boundary": "不能变成人类, 不能替代历史建筑",
"ip_design_negative_constraints": "避免画成普通人类讲述者, 避免多余文字",
"ip_design_visible_text_whitelist": "长乐门, 正定古城",
```

Change expected payload to:

```python
"payload": {
    "ip_profiles": [
        {
            "ip_profile_id": "ip_main",
            "name": "New IP",
            "logline": "New logline",
            "world_hint": "New world",
            "style_hint": "New style",
            "identity_lock": ["白色卡通兔子", "长耳朵", "圆润脸型"],
            "identity_anchors": ["蓝色领结", "浅粉色耳朵内侧"],
            "identity_suppression_rules": ["远景弱化耳朵内侧"],
            "variable_slots": ["动作", "表情", "站位"],
            "semantic_boundary": ["不能变成人类", "不能替代历史建筑"],
            "negative_constraints": ["避免画成普通人类讲述者", "避免多余文字"],
            "visible_text_whitelist": ["长乐门", "正定古城"],
        }
    ],
    "character_profiles": [],
    "scene_assets": [],
    "prop_assets": [],
    "style_profiles": [],
}
```

- [ ] **Step 2: Write failing UI load/status test**

Add:

```python
def test_ip_design_workbench_marks_ip_without_identity_anchors_unavailable():
    from web.components.ip_design_workbench import render_ip_design_workbench

    fake_ui = _FakeUI()
    client = _FakeIPDesignClient(
        asset_bibles=[
            {
                "asset_bible_id": "bible_empty",
                "workspace_id": "workspace_1",
                "project_id": "project_1",
                "ip_profiles": [
                    {
                        "ip_profile_id": "ip_main",
                        "name": "Empty IP",
                        "identity_lock": [],
                        "identity_anchors": [],
                    }
                ],
                "character_profiles": [],
                "scene_assets": [],
                "prop_assets": [],
                "style_profiles": [],
            }
        ]
    )

    render_ip_design_workbench(
        ip_design_client=client,
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
    )

    assert "ip_design.asset_bible.generation_unavailable" in fake_ui.captions
```

If `_FakeIPDesignClient` does not currently accept constructor data, extend the fake in the test file only.

- [ ] **Step 3: Run tests to verify RED**

Run:

```powershell
pytest tests/test_ip_design_workbench_ui.py::test_ip_design_workbench_saves_asset_bible_through_client tests/test_ip_design_workbench_ui.py::test_ip_design_workbench_marks_ip_without_identity_anchors_unavailable -v
```

Expected: FAIL because fields and status do not exist.

- [ ] **Step 4: Implement structured field UI helpers**

In `web/components/ip_design_workbench.py`, remove the editable `forbidden_elements` field from the formal editing surface, then add structured text inputs or compact text areas after `style_hint`:

```python
identity_lock = _text_input(
    ui,
    translate("ip_design.asset_bible.identity_lock"),
    key="ip_design_identity_lock",
    value=", ".join(_text_list(ip_profile.get("identity_lock"))),
)
identity_anchors = _text_input(
    ui,
    translate("ip_design.asset_bible.identity_anchors"),
    key="ip_design_identity_anchors",
    value=", ".join(_text_list(ip_profile.get("identity_anchors"))),
)
identity_suppression_rules = _text_input(
    ui,
    translate("ip_design.asset_bible.identity_suppression_rules"),
    key="ip_design_identity_suppression_rules",
    value=", ".join(_text_list(ip_profile.get("identity_suppression_rules"))),
)
variable_slots = _text_input(
    ui,
    translate("ip_design.asset_bible.variable_slots"),
    key="ip_design_variable_slots",
    value=", ".join(_text_list(ip_profile.get("variable_slots"))),
)
semantic_boundary = _text_input(
    ui,
    translate("ip_design.asset_bible.semantic_boundary"),
    key="ip_design_semantic_boundary",
    value=", ".join(_text_list(ip_profile.get("semantic_boundary"))),
)
negative_constraints = _text_input(
    ui,
    translate("ip_design.asset_bible.negative_constraints"),
    key="ip_design_negative_constraints",
    value=", ".join(_text_list(ip_profile.get("negative_constraints"))),
)
visible_text_whitelist = _text_input(
    ui,
    translate("ip_design.asset_bible.visible_text_whitelist"),
    key="ip_design_visible_text_whitelist",
    value=", ".join(_text_list(ip_profile.get("visible_text_whitelist"))),
)
```

Add availability caption after summary:

```python
if _has_generation_identity(ip_profile):
    ui.caption(translate("ip_design.asset_bible.generation_ready"))
else:
    ui.caption(translate("ip_design.asset_bible.generation_unavailable"))
```

Add helper:

```python
def _has_generation_identity(ip_profile: Mapping[str, Any]) -> bool:
    return bool(_text_list(ip_profile.get("identity_lock")) or _text_list(ip_profile.get("identity_anchors")))
```

- [ ] **Step 5: Change save payload to nested `ip_profiles`**

Replace the flat IP payload fields with:

```python
payload = {
    "ip_profiles": [
        {
            "ip_profile_id": ip_profile_id,
            "name": ip_name,
            "logline": logline,
            "world_hint": world_hint,
            "style_hint": style_hint,
            "identity_lock": _split_csv(identity_lock),
            "identity_anchors": _split_csv(identity_anchors),
            "identity_suppression_rules": _split_csv(identity_suppression_rules),
            "variable_slots": _split_csv(variable_slots),
            "semantic_boundary": _split_csv(semantic_boundary),
            "negative_constraints": _split_csv(negative_constraints),
            "visible_text_whitelist": _split_csv(visible_text_whitelist),
        }
    ],
    "character_profiles": _list_of_dicts(source_asset_bible.get("character_profiles")),
    "scene_assets": _list_of_dicts(source_asset_bible.get("scene_assets")),
    "prop_assets": _list_of_dicts(source_asset_bible.get("prop_assets")),
    "style_profiles": _list_of_dicts(source_asset_bible.get("style_profiles")),
}
```

Do not include `forbidden_elements` in the formal save payload, and do not keep it as an editable formal field in this workbench.

- [ ] **Step 6: Add i18n keys**

In `web/i18n/locales/zh_CN.json`:

```json
"ip_design.asset_bible.identity_lock": "身份锁定锚点（逗号分隔）",
"ip_design.asset_bible.identity_anchors": "识别锚点（逗号分隔）",
"ip_design.asset_bible.identity_suppression_rules": "可弱化锚点规则（逗号分隔）",
"ip_design.asset_bible.variable_slots": "可变项（逗号分隔）",
"ip_design.asset_bible.semantic_boundary": "语义边界（逗号分隔）",
"ip_design.asset_bible.negative_constraints": "负向画面约束（逗号分隔）",
"ip_design.asset_bible.visible_text_whitelist": "画面文字白名单（逗号分隔）",
"ip_design.asset_bible.generation_ready": "状态：可用于正式生成。",
"ip_design.asset_bible.generation_unavailable": "状态：缺少身份锚点，暂不可用于正式生成。"
```

In `web/i18n/locales/en_US.json`:

```json
"ip_design.asset_bible.identity_lock": "Identity Lock Anchors (comma separated)",
"ip_design.asset_bible.identity_anchors": "Identity Anchors (comma separated)",
"ip_design.asset_bible.identity_suppression_rules": "Suppressible Anchor Rules (comma separated)",
"ip_design.asset_bible.variable_slots": "Variable Slots (comma separated)",
"ip_design.asset_bible.semantic_boundary": "Semantic Boundaries (comma separated)",
"ip_design.asset_bible.negative_constraints": "Negative Visual Constraints (comma separated)",
"ip_design.asset_bible.visible_text_whitelist": "Visible Text Whitelist (comma separated)",
"ip_design.asset_bible.generation_ready": "Status: ready for generation.",
"ip_design.asset_bible.generation_unavailable": "Status: missing identity anchors; not ready for generation."
```

- [ ] **Step 7: Run UI tests**

Run:

```powershell
pytest tests/test_ip_design_workbench_ui.py tests/test_ip_design_workbench_page.py -v
```

Expected: PASS.

- [ ] **Step 8: Contract checkpoint, do not commit yet**

Do not commit this task by itself. Continue to Task 3 so Stage2 and helper entry points are updated before the first contract commit.

---

## Task 3: Structured AssetBible Create Entry

**Files:**

- Modify: `web/utils/asset_bible_api.py`
- Modify: `web/components/asset_bible_draft_setup.py`
- Modify: `web/ip_design/inprocess_client.py`
- Modify: `tests/test_asset_prompt_plan_projection_ui.py`
- Modify: `tests/test_ip_design_client.py`

- [ ] **Step 1: Write failing helper payload test**

Update `tests/test_asset_prompt_plan_projection_ui.py::test_create_asset_bible_posts_minimal_draft_payload`.

Change the call site to pass a formal nested payload:

```python
result = asset_bible_api.create_asset_bible(
    api_base_url="http://localhost:8000/api/",
    project_id=" project_1 ",
    payload={
        "workspace_id": " ws_1 ",
        "asset_bible_id": " bible_1 ",
        "ip_profiles": [
            {
                "ip_profile_id": " ip_main ",
                "name": " Demo IP ",
                "world_hint": " sky city ",
                "style_hint": " clean comic ",
                "identity_lock": ["白色卡通兔子"],
                "identity_anchors": ["蓝色领结"],
            }
        ],
    },
)
```

Change the expected posted JSON to:

```python
{
    "workspace_id": "ws_1",
    "asset_bible_id": "bible_1",
    "ip_profiles": [
        {
            "ip_profile_id": "ip_main",
            "name": "Demo IP",
            "world_hint": "sky city",
            "style_hint": "clean comic",
            "identity_lock": ["白色卡通兔子"],
            "identity_anchors": ["蓝色领结"],
        }
    ],
}
```

- [ ] **Step 2: Write failing Stage2 create-form test**

Update `tests/test_asset_prompt_plan_projection_ui.py::test_render_asset_bible_draft_setup_creates_asset_bible`.

Add session state values:

```python
"stage2_ip_profile_id": "ip_main",
"stage2_identity_lock": "白色卡通兔子, 长耳朵",
"stage2_identity_anchors": "蓝色领结",
```

Change the expected `create_asset_bible(...)` call to:

```python
{
    "api_base_url": "http://localhost:8000/api",
    "project_id": "project_1",
    "payload": {
        "workspace_id": "ws_1",
        "asset_bible_id": "bible_1",
        "ip_profiles": [
            {
                "ip_profile_id": "ip_main",
                "name": "Demo IP",
                "world_hint": "sky city",
                "style_hint": "clean comic",
                "identity_lock": ["白色卡通兔子", "长耳朵"],
                "identity_anchors": ["蓝色领结"],
            }
        ],
    },
}
```

- [ ] **Step 3: Write failing client payload tests**

Update the AssetBible payloads in `tests/test_ip_design_client.py` to use nested `ip_profiles` instead of flat `ip_name`.

For `HttpIPDesignClient.save_asset_bible(...)`:

```python
payload={
    "ip_profiles": [
        {
            "ip_profile_id": "ip_main",
            "name": "Demo IP",
        }
    ]
}
```

For `InProcessIPDesignClient.save_asset_bible(...)`:

```python
payload={
    "ip_profiles": [
        {
            "ip_profile_id": "ip_main",
            "name": "Demo IP",
        }
    ],
    "character_profiles": [
        {
            "character_id": "char_luna",
            "display_name": "Luna",
        }
    ],
    ...
}
```

- [ ] **Step 4: Run tests to verify RED**

Run:

```powershell
pytest tests/test_asset_prompt_plan_projection_ui.py::test_create_asset_bible_posts_minimal_draft_payload tests/test_asset_prompt_plan_projection_ui.py::test_render_asset_bible_draft_setup_creates_asset_bible tests/test_ip_design_client.py -v
```

Expected: FAIL because helper, form, or client tests still rely on the flat create contract.

- [ ] **Step 5: Implement unified nested create payload**

In `web/utils/asset_bible_api.py`, change `create_asset_bible(...)` to accept a single formal `payload` argument and forward it without inventing a second contract:

```python
def create_asset_bible(
    *,
    api_base_url: str,
    project_id: str,
    payload: dict[str, Any],
    timeout: float = 30.0,
) -> dict[str, Any]:
    endpoint = build_asset_bible_list_endpoint(
        api_base_url=api_base_url,
        project_id=project_id,
    )

    response = httpx.post(
        endpoint,
        json=build_asset_bible_payload(payload),
        timeout=timeout,
    )
    ...
```

If no `build_asset_bible_payload(...)` helper exists yet, add one in this module that:

- validates `workspace_id` / `asset_bible_id`
- trims nested `ip_profiles[*].ip_profile_id / name / world_hint / style_hint`
- preserves structured lists such as `identity_lock` and `identity_anchors`
- does not accept or synthesize top-level `ip_name / world_hint / style_hint`

In `web/components/asset_bible_draft_setup.py`, build and submit:

```python
payload = {
    "workspace_id": workspace_id,
    "asset_bible_id": asset_bible_id,
    "ip_profiles": [
        {
            "ip_profile_id": ip_profile_id,
            "name": ip_name,
            "world_hint": world_hint,
            "style_hint": style_hint,
            "identity_lock": _split_csv(identity_lock),
            "identity_anchors": _split_csv(identity_anchors),
        }
    ],
}
```

Add the corresponding `stage2_ip_profile_id`, `stage2_identity_lock`, and `stage2_identity_anchors` inputs to the form.

In `web/ip_design/inprocess_client.py`, rely on the new nested request schema and do not preserve any flat AssetBible payload examples in tests.

- [ ] **Step 6: Run create-entry tests**

Run:

```powershell
pytest tests/test_asset_prompt_plan_projection_ui.py::test_create_asset_bible_posts_minimal_draft_payload tests/test_asset_prompt_plan_projection_ui.py::test_render_asset_bible_draft_setup_creates_asset_bible tests/test_ip_design_client.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit and push the complete contract batch**

```powershell
git add api/schemas/asset_bible.py api/routers/asset_bible.py web/utils/asset_bible_api.py web/ip_design/inprocess_client.py web/components/ip_design_workbench.py web/components/asset_bible_draft_setup.py web/i18n/locales/zh_CN.json web/i18n/locales/en_US.json tests/test_asset_bible_api.py tests/test_ip_design_client.py tests/test_ip_design_workbench_ui.py tests/test_asset_prompt_plan_projection_ui.py
git commit -m "refactor: 统一IPProfile结构化事实源合同"
git push
```

---

## Task 4: IP Generation Readiness Guard

**Files:**

- Modify: `pixelle_video/pipelines/standard.py`
- Modify: `pixelle_video/utils/content_generators.py`
- Modify: `tests/test_standard_pipeline_storyboard_generation.py`
- Modify: `tests/test_styled_image_prompt_batch.py`

- [ ] **Step 1: Write failing standard pipeline test**

In `tests/test_standard_pipeline_storyboard_generation.py`, add a repository variant with empty anchors:

```python
class _EmptyIPAssetBibleRepository(_RecordingAssetBibleRepository):
    async def load_asset_bible(self, workspace_id, asset_bible_id):
        payload = await super().load_asset_bible(workspace_id, asset_bible_id)
        payload["ip_profiles"][0]["identity_lock"] = []
        payload["ip_profiles"][0]["identity_anchors"] = []
        return payload
```

Add test:

```python
@pytest.mark.asyncio
async def test_standard_pipeline_rejects_enabled_ip_without_identity_anchors(monkeypatch):
    repository = _EmptyIPAssetBibleRepository()
    pipeline, ctx, captured = _pipeline_with_storyboard_dependencies(
        monkeypatch,
        asset_bible_repository=repository,
        params={
            "ip_enabled": True,
            "ip_asset_bible_id": "bible_demo",
            "ip_profile_id": "ip_main",
        },
    )

    with pytest.raises(ValueError, match="缺少身份锚点|identity anchors"):
        await pipeline.generate_storyboard(ctx)
```

If helper names differ in the file, use the existing helper used by the current IP tests around lines 290-340 and add only the assertion.

- [ ] **Step 2: Write failing direct prompt batch test**

In `tests/test_styled_image_prompt_batch.py`, add:

```python
def test_generate_styled_image_prompt_batch_rejects_enabled_ip_without_identity_anchors():
    profile = IPProfile(
        ip_profile_id="ip_main",
        workspace_id="workspace_1",
        project_id="project_1",
        name="Empty IP",
    )

    with pytest.raises(ValueError, match="identity anchors|身份锚点"):
        generate_styled_image_prompt_batch(
            narrations=["从长乐门出发。"],
            prompt_prefix="cinematic realism",
            media_type="image",
            storyboard_plan=_single_frame_storyboard_plan("从长乐门出发。"),
            ip_enabled=True,
            ip_profile=profile,
        )
```

Use existing local helpers from the test file for building storyboard plans instead of creating new broad utilities.

- [ ] **Step 3: Run tests to verify RED**

Run:

```powershell
pytest tests/test_standard_pipeline_storyboard_generation.py::test_standard_pipeline_rejects_enabled_ip_without_identity_anchors tests/test_styled_image_prompt_batch.py::test_generate_styled_image_prompt_batch_rejects_enabled_ip_without_identity_anchors -v
```

Expected: FAIL because no guard exists.

- [ ] **Step 4: Implement guard helper**

In `pixelle_video/utils/content_generators.py`, add a small helper near IP prompt chain logic:

```python
def _ensure_ip_profile_ready_for_generation(ip_profile: IPProfile | None) -> None:
    if ip_profile is None:
        raise ValueError("ip_profile is required when ip_enabled=True")
    if not tuple([*ip_profile.identity_lock, *ip_profile.identity_anchors]):
        raise ValueError(
            "当前 IP 形象缺少身份锚点，无法接入正式 Z-Image 生成。"
            "请先在 IP 设计工作台补全 identity_lock 或 identity_anchors。"
        )
```

Call it in `generate_styled_image_prompt_batch(...)` where `ip_prompt_chain_enabled` is true, before `IPUsagePlanner().plan_batch(...)`.

In `pixelle_video/pipelines/standard.py`, add an equivalent private method to avoid importing the util helper into pipeline if that creates coupling:

```python
@staticmethod
def _ensure_ip_profile_ready_for_generation(ip_profile: IPProfile) -> None:
    if not tuple([*ip_profile.identity_lock, *ip_profile.identity_anchors]):
        raise ValueError(
            "当前 IP 形象缺少身份锚点，无法接入正式 Z-Image 生成。"
            "请先在 IP 设计工作台补全 identity_lock 或 identity_anchors。"
        )
```

Call it after `ip_profile is None` check and before loading scene casts in `_resolve_ip_prompt_chain_inputs(...)`.

- [ ] **Step 5: Run focused guard tests**

Run:

```powershell
pytest tests/test_standard_pipeline_storyboard_generation.py::test_standard_pipeline_rejects_enabled_ip_without_identity_anchors tests/test_styled_image_prompt_batch.py::test_generate_styled_image_prompt_batch_rejects_enabled_ip_without_identity_anchors -v
```

Expected: PASS.

- [ ] **Step 6: Run existing IP prompt tests**

Run:

```powershell
pytest tests/test_standard_pipeline_storyboard_generation.py tests/test_styled_image_prompt_batch.py tests/test_ip_usage_planner.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit and push**

```powershell
git add pixelle_video/pipelines/standard.py pixelle_video/utils/content_generators.py tests/test_standard_pipeline_storyboard_generation.py tests/test_styled_image_prompt_batch.py
git commit -m "fix: 阻断缺少身份锚点的IP生成"
git push
```

---

## Task 5: Final Z-Image Prompt Identity Acceptance

**Files:**

- Modify: `tests/test_styled_image_prompt_batch.py`
- Modify: `pixelle_video/prompts/image_generation.py` only if the test exposes missing instruction strength.
- Modify: `pixelle_video/utils/content_generators.py` only if deterministic merge is missing.

- [ ] **Step 1: Write failing final prompt identity test**

Add a test in `tests/test_styled_image_prompt_batch.py` close to existing IP prompt chain tests:

```python
def test_z_image_final_prompt_contains_structured_ip_identity_anchors(monkeypatch):
    profile = IPProfile(
        ip_profile_id="ip_main",
        workspace_id="workspace_1",
        project_id="project_1",
        name="正定向导兔",
        identity_lock=("白色卡通兔子", "长耳朵"),
        identity_anchors=("蓝色领结",),
        semantic_boundary=("不能替代历史建筑",),
        negative_constraints=("避免画成普通人类讲述者",),
    )

    batch = generate_styled_image_prompt_batch(
        narrations=["从长乐门出发，这是正定古城的入口。"],
        prompt_prefix="cinematic realism",
        media_type="image",
        storyboard_plan=_single_frame_storyboard_plan("从长乐门出发，这是正定古城的入口。"),
        ip_enabled=True,
        ip_profile=profile,
        workflow_capabilities={"supports_negative_prompt": False},
    )

    final_prompt = batch.prompts[0]
    assert "白色卡通兔子" in final_prompt
    assert "蓝色领结" in final_prompt
    assert "避免画成普通人类讲述者" in final_prompt
```

Use existing signature names from current tests. If `workflow_capabilities` is not accepted directly, use the same helper/fake workflow capability setup already used in Z-Image text policy tests.

- [ ] **Step 2: Run test to verify RED or document existing GREEN**

Run:

```powershell
pytest tests/test_styled_image_prompt_batch.py::test_z_image_final_prompt_contains_structured_ip_identity_anchors -v
```

Expected:

- If FAIL: proceed to Step 3.
- If PASS: do not change implementation; keep the test as acceptance coverage and proceed to Step 5.

- [ ] **Step 3: Strengthen deterministic final prompt merge**

Only if Step 2 fails because anchors are present in `ip_adaptation` but not final prompt:

In `pixelle_video/utils/content_generators.py`, when `media_type == "image"` and capabilities do not support negative prompt, merge a compact identity clause into final prompt before `merge_z_image_constraints_into_prompt(...)`.

The clause must come from structured fields only:

```python
def _ip_identity_clause_from_context(frame_context: Mapping[str, Any]) -> tuple[str, ...]:
    adaptation = frame_context.get("ip_adaptation")
    if not isinstance(adaptation, Mapping):
        return ()
    anchors = _normalize_string_list(adaptation.get("identity_anchors_visible"))
    colors = _normalize_string_list(adaptation.get("identity_color_terms"))
    return tuple([*anchors, *colors])
```

Use this clause in the final prompt fragment list. Do not read `style_hint`, `logline`, or `forbidden_elements`.

- [ ] **Step 4: Re-run final prompt test**

Run:

```powershell
pytest tests/test_styled_image_prompt_batch.py::test_z_image_final_prompt_contains_structured_ip_identity_anchors -v
```

Expected: PASS.

- [ ] **Step 5: Run broader prompt tests**

Run:

```powershell
pytest tests/test_styled_image_prompt_batch.py tests/test_content_generators_text_policy.py tests/test_content_generators_structured_output.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit and push**

```powershell
git add tests/test_styled_image_prompt_batch.py pixelle_video/utils/content_generators.py pixelle_video/prompts/image_generation.py
git commit -m "test: 验证Z-Image提示词包含IP身份锚点"
git push
```

If no implementation files changed, only add the test file.

---

## Task 6: Full Verification and Review

**Files:**

- No planned source changes unless verification exposes issues.

- [ ] **Step 1: Run focused backend suite**

Run:

```powershell
pytest tests/test_asset_bible_api.py tests/test_asset_bible_models.py tests/test_styled_image_prompt_batch.py tests/test_ip_usage_planner.py tests/test_standard_pipeline_storyboard_generation.py -v
```

Expected: PASS.

- [ ] **Step 2: Run focused frontend/component suite**

Run:

```powershell
pytest tests/test_ip_design_workbench_ui.py tests/test_ip_design_workbench_page.py tests/test_style_config_ip_controls.py -v
```

Expected: PASS.

- [ ] **Step 3: Run structured create-entry suite**

Run:

```powershell
pytest tests/test_asset_prompt_plan_projection_ui.py tests/test_ip_design_client.py -v
```

Expected: PASS.

- [ ] **Step 4: Run contract/API smoke tests**

Run:

```powershell
pytest tests/test_video_api.py tests/test_output_preview.py -v
```

Expected: PASS.

- [ ] **Step 5: Search for forbidden compatibility patterns**

Run:

```powershell
rg -n "style_hint.*identity|forbidden_elements.*negative|fallback|兼容|迁移|identity_lock.*style_hint|identity_anchors.*style_hint" pixelle_video web api tests -S
```

Expected:

- No code that maps `style_hint` into identity anchors.
- No code that maps `forbidden_elements` into negative constraints for generation.
- No runtime fallback for missing identity anchors.
- No formal create/save helper that still requires top-level `ip_name`.

- [ ] **Step 6: Inspect generated AssetBible payload path**

Run:

```powershell
rg -n "ip_profiles|identity_lock|identity_anchors|semantic_boundary|negative_constraints|visible_text_whitelist" web/components/ip_design_workbench.py web/components/asset_bible_draft_setup.py web/utils/asset_bible_api.py api/schemas/asset_bible.py api/routers/asset_bible.py pixelle_video/pipelines/standard.py pixelle_video/utils/content_generators.py -S
```

Expected:

- UI saves nested `ip_profiles`.
- Stage2 create flow saves nested `ip_profiles`.
- API schema accepts and returns structured IP fields.
- Generation guard checks `identity_lock + identity_anchors`.
- Prompt tests assert final prompt content.

- [ ] **Step 7: Commit and push verification fixes if needed**

Only if Steps 1-5 required fixes:

```powershell
git add <changed-files>
git commit -m "fix: 修复IPProfile结构化事实源验证问题"
git push
```

---

## Acceptance Criteria

- IP 设计工作台能编辑并保存 `identity_lock / identity_anchors / semantic_boundary / negative_constraints / visible_text_whitelist`。
- Stage2 / 草稿创建入口与 `create_asset_bible(...)` helper 只发送嵌套 `ip_profiles`，不再发送平铺 IP 字段。
- AssetBible API 返回的 `ip_profiles` 不丢结构化字段。
- 标准生成启用 IP 且身份锚点为空时直接失败，错误指向 IP 设计工作台补全锚点。
- 启用 IP 且身份锚点完整时，最终 Z-Image prompt 包含结构化身份锚点。
- 未启用 IP 的标准生成不受影响。
- 没有 `style_hint` 到身份锚点的运行时兼容猜测。
- 没有 `forbidden_elements` 到生成负约束的运行时兼容猜测。
- 不实现旧数据迁移。

## Implementation Notes

- 现有测试和控制台在 Windows 上可能显示中文乱码，但文件内容本身按 UTF-8 保存；断言优先使用源文件中的中文字符串。
- 提交必须原子化，提交说明必须使用中文分类前缀。
- 每个任务完成一次提交并推送。
- 如果当前工作区出现非本任务改动，不要回滚；只暂存本任务文件。
- 生成页世界观提示计划必须等本计划完成后再执行。
