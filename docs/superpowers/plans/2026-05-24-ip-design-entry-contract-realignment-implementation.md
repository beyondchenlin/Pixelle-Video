# IP Design Entry Contract Realignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the left-side IP/world generation entry so request-level `generation_world_hint` and IP controls reach the existing downstream pipeline, then align two small IP design data-shape mismatches.

**Architecture:** Keep the formal generation contract narrow. The left content module owns request-level world hint and selected IP IDs; helper fields stay in Streamlit session state or draft API payloads. Downstream API, contract, pipeline, and prompt composition remain unchanged except for focused tests proving the contract is still connected.

**Tech Stack:** Python 3.11, Streamlit, Pydantic v2, pytest, Pixelle `IPProfile` / `AssetBible` / `ContentWorldPlanner` / `IPFrameAppearancePlanner`.

---

## File Structure

- Modify: `web/components/content_ip_world_controls.py`
  - Owns left-side IP selection and request-level world hint UI.
  - Must return only formal generation fields plus IP controls.
- Modify: `web/i18n/locales/zh_CN.json`
  - Adds Chinese labels for request-level world hint and helper buttons.
- Modify: `web/i18n/locales/en_US.json`
  - Adds English labels for request-level world hint and helper buttons.
- Modify: `tests/test_content_ip_world_controls.py`
  - Update fake UI only where current UI rendering requires `container()`.
  - Keep existing behavior expectations for `generation_world_hint`.
- Modify: `web/components/ip_design_workbench.py`
  - Align readiness and color-palette save shape.
- Modify: `tests/test_ip_design_workbench_ui.py`
  - Add regression coverage for anchor-only readiness and color-palette prompt entry shape.
- Optional modify: `tests/test_style_config_text_rendering_ui.py`
  - Only if a stale style-side IP payload test expects old helper fields.

## Task 1: Reproduce Baseline And Confirm Scope

**Files:**
- Read: `docs/superpowers/specs/2026-05-24-ip-design-entry-contract-realignment-design.md`
- Test: `tests/test_content_ip_world_controls.py`
- Test: `tests/test_content_input_storyboard_ui.py`
- Test: `tests/test_output_preview.py`
- Test: `tests/test_video_api.py`
- Test: `tests/test_image_prompt_composer.py`

- [ ] **Step 1: Run the failing left-entry test group**

Run:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_content_ip_world_controls.py -q
```

Expected now:

```text
11 failed, 4 passed
```

The failure list should include missing `generation_world_hint`, missing `safe_rerun`, missing i18n keys, stale helper world hint not cleared, and fake UI missing `container()`.

- [ ] **Step 2: Run the downstream proof tests**

Run:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_content_input_storyboard_ui.py::test_left_content_ip_payload_render_content_input tests/test_output_preview.py::test_build_single_generation_request_includes_generation_world_hint tests/test_video_api.py::test_build_video_generation_params_copies_generation_world_hint tests/test_image_prompt_composer.py::test_composer_passes_generation_world_hint_to_styled_batch -q
```

Expected now:

```text
4 passed
```

This proves the first fix belongs in the left-side control module, not in API schema or standard pipeline.

- [ ] **Step 3: Commit nothing**

No code has changed in this task.

## Task 2: Restore `generation_world_hint` Payload Contract

**Files:**
- Modify: `web/components/content_ip_world_controls.py`
- Test: `tests/test_content_ip_world_controls.py`

- [ ] **Step 1: Write or keep the failing payload tests**

Keep these existing tests as the contract:

```python
def test_render_content_ip_world_controls_keeps_world_hint_without_ip():
    fake_ui = _FakeContentIPWorldUI()
    fake_ui.session_state["content_generation_world_hint"] = "Manual request world."
    loader_calls = []

    payload = content_ip_world_controls.render_content_ip_world_controls(
        ui=fake_ui,
        translate=_tr,
        pixelle_video=None,
        content_context={"title": "Demo", "text": "Script text"},
        asset_bible_loader=lambda: loader_calls.append("called"),
    )

    assert payload == {
        "ip_enabled": False,
        "generation_world_hint": "Manual request world.",
    }
    assert loader_calls == []
```

Keep this existing IP-enabled payload assertion:

```python
assert payload == {
    "ip_enabled": True,
    "ip_asset_bible_id": "bible_demo",
    "ip_profile_id": "ip_main",
    "generation_world_hint": "Manual request world.",
}
assert fake_ui.session_state["content_ip_profile_world_hint"] == "Friendly guide world."
assert "ip_profile_world_hint" not in payload
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_content_ip_world_controls.py::test_render_content_ip_world_controls_keeps_world_hint_without_ip tests/test_content_ip_world_controls.py::test_render_content_ip_world_controls_returns_selected_ip_payload_without_helper_field -q
```

Expected now:

```text
FAILED
```

The first failure should show that `generation_world_hint` is missing.

- [ ] **Step 3: Replace dead payload fields with request world hint**

In `web/components/content_ip_world_controls.py`, change the constants and payload builder to this shape:

```python
from web.utils.content_api import generate_world_hint_draft
from web.utils.streamlit_helpers import safe_rerun

CONTENT_IP_STATE_PREFIX = "content_ip"
CONTENT_GENERATION_WORLD_HINT_KEY = "content_generation_world_hint"
CONTENT_GENERATION_WORLD_HINT_SOURCE_KEY = "content_generation_world_hint_source"
CONTENT_GENERATION_WORLD_HINT_LAST_VALUE_KEY = "content_generation_world_hint_last_value"
CONTENT_IP_PROFILE_WORLD_HINT_KEY = "content_ip_profile_world_hint"


def build_content_ip_world_payload(
    *,
    ip_payload: Mapping[str, Any] | None = None,
    generation_world_hint: str | None = None,
) -> dict[str, Any]:
    """Build the formal content IP/world payload for request submission."""
    source = dict(ip_payload or {})
    payload: dict[str, Any] = {"ip_enabled": bool(source.get("ip_enabled", False))}
    if payload["ip_enabled"]:
        ip_asset_bible_id = _first_text(source.get("ip_asset_bible_id"))
        ip_profile_id = _first_text(source.get("ip_profile_id"))
        if ip_asset_bible_id:
            payload["ip_asset_bible_id"] = ip_asset_bible_id
        if ip_profile_id:
            payload["ip_profile_id"] = ip_profile_id

    hint = _first_text(generation_world_hint)
    if hint:
        payload["generation_world_hint"] = hint
    return payload
```

Remove the formal forwarding of:

```python
"generation_notes"
"slot_preference_override"
"presence_strength"
```

These fields are currently UI-only dead parameters because the formal generation contract does not consume them.

- [ ] **Step 4: Sync IP default world hint into helper session state**

Add this helper in `web/components/content_ip_world_controls.py`:

```python
def _sync_ip_profile_world_hint(session_state, ip_profile_world_hint: str) -> None:
    hint = _first_text(ip_profile_world_hint)
    if hint:
        session_state[CONTENT_IP_PROFILE_WORLD_HINT_KEY] = hint
        return
    session_state.pop(CONTENT_IP_PROFILE_WORLD_HINT_KEY, None)
```

In `render_content_ip_world_controls()`, after `render_ip_prompt_chain_controls(...)`, add:

```python
ip_default_world_hint = (
    _first_text(ip_payload.get("ip_profile_world_hint"))
    if ip_payload.get("ip_enabled")
    else ""
)
_sync_ip_profile_world_hint(session_state, ip_default_world_hint)
```

- [ ] **Step 5: Render the request-level world hint text area**

Inside the expander, after IP controls, render:

```python
generation_world_hint = ui.text_area(
    translate("content.ip_world.generation_world_hint"),
    key=CONTENT_GENERATION_WORLD_HINT_KEY,
    value=session_state.get(CONTENT_GENERATION_WORLD_HINT_KEY, ""),
    height=92,
    help=translate("content.ip_world.generation_world_hint_help"),
)
_mark_world_hint_manual_if_user_edited(session_state, generation_world_hint)
```

Add:

```python
def _mark_world_hint_manual_if_user_edited(session_state, current_hint: str) -> None:
    current = _first_text(current_hint)
    source = _first_text(session_state.get(CONTENT_GENERATION_WORLD_HINT_SOURCE_KEY))
    last = _first_text(session_state.get(CONTENT_GENERATION_WORLD_HINT_LAST_VALUE_KEY))
    if source in {"generated_from_script", "ip_default"} and current != last:
        session_state[CONTENT_GENERATION_WORLD_HINT_SOURCE_KEY] = "manual"
    if current:
        session_state[CONTENT_GENERATION_WORLD_HINT_LAST_VALUE_KEY] = current
```

- [ ] **Step 6: Return the formal payload**

At the end of `render_content_ip_world_controls()`, return:

```python
return build_content_ip_world_payload(
    ip_payload=ip_payload,
    generation_world_hint=session_state.get(
        CONTENT_GENERATION_WORLD_HINT_KEY,
        generation_world_hint,
    ),
)
```

- [ ] **Step 7: Run focused tests**

Run:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_content_ip_world_controls.py::test_render_content_ip_world_controls_keeps_world_hint_without_ip tests/test_content_ip_world_controls.py::test_render_content_ip_world_controls_returns_selected_ip_payload_without_helper_field tests/test_content_ip_world_controls.py::test_render_content_ip_world_controls_clears_stale_ip_world_hint_when_ip_disabled -q
```

Expected after this task:

```text
3 passed
```

- [ ] **Step 8: Commit**

```powershell
git add web/components/content_ip_world_controls.py tests/test_content_ip_world_controls.py
git commit -m "fix: 恢复左侧IP世界观请求合同"
```

## Task 3: Restore World Hint Helper Actions And I18n

**Files:**
- Modify: `web/components/content_ip_world_controls.py`
- Modify: `web/i18n/locales/zh_CN.json`
- Modify: `web/i18n/locales/en_US.json`
- Modify: `tests/test_content_ip_world_controls.py`

- [ ] **Step 1: Keep failing helper tests**

Keep these existing tests:

```python
def test_render_content_ip_world_controls_can_use_ip_default(monkeypatch):
    ...

def test_render_content_ip_world_controls_generates_world_hint_from_script(monkeypatch):
    ...

def test_render_content_ip_world_controls_warns_when_generating_without_script():
    ...
```

- [ ] **Step 2: Update fake UI to support current preview rendering**

In `tests/test_content_ip_world_controls.py`, add:

```python
def container(self, **kwargs):
    return _FakeContext()
```

to `_FakeContentIPWorldUI`.

- [ ] **Step 3: Add helper action buttons**

In `render_content_ip_world_controls()`, after the text area, add:

```python
action_col, default_col = ui.columns((1, 1))
with action_col:
    if ui.button(
        translate("content.ip_world.generate_from_content"),
        key="content_world_hint_generate_from_content",
    ):
        _handle_generate_world_hint_from_content(
            session_state=session_state,
            ui=ui,
            translate=translate,
            content_context=content_context,
            storyboard_prompt_language=storyboard_prompt_language,
            world_preset_id=world_preset_id,
            ip_default_world_hint=ip_default_world_hint,
            world_hint_draft_generator=world_hint_draft_generator or generate_world_hint_draft,
        )
with default_col:
    if ui.button(
        translate("content.ip_world.use_ip_default"),
        key="content_world_hint_use_ip_default",
    ):
        _handle_use_ip_default_world_hint(
            session_state=session_state,
            ui=ui,
            translate=translate,
            ip_default_world_hint=ip_default_world_hint,
        )
```

Add the two handlers:

```python
def _handle_use_ip_default_world_hint(
    *,
    session_state,
    ui,
    translate: Translate,
    ip_default_world_hint: str,
) -> None:
    hint = _first_text(ip_default_world_hint)
    if not hint:
        ui.warning(translate("content.ip_world.missing_ip_default"))
        return
    session_state[CONTENT_GENERATION_WORLD_HINT_KEY] = hint
    session_state[CONTENT_GENERATION_WORLD_HINT_SOURCE_KEY] = "ip_default"
    session_state[CONTENT_GENERATION_WORLD_HINT_LAST_VALUE_KEY] = hint
    safe_rerun()


def _handle_generate_world_hint_from_content(
    *,
    session_state,
    ui,
    translate: Translate,
    content_context: Mapping[str, Any] | None,
    storyboard_prompt_language: str,
    world_preset_id: str | None,
    ip_default_world_hint: str,
    world_hint_draft_generator: Callable[..., Mapping[str, Any]],
) -> None:
    context = dict(content_context or {})
    source_text = _first_text(context.get("text"))
    if not source_text:
        ui.warning(translate("content.ip_world.missing_content"))
        return
    try:
        response = world_hint_draft_generator(
            source_text=source_text,
            title=_first_text(context.get("title")) or None,
            world_preset_id=world_preset_id,
            storyboard_prompt_language=storyboard_prompt_language,
            ip_default_world_hint=_first_text(ip_default_world_hint) or None,
        )
    except Exception:
        logger.exception("failed to generate content world hint draft")
        ui.warning(translate("content.ip_world.generate_failed"))
        return
    if not isinstance(response, Mapping):
        ui.warning(translate("content.ip_world.generate_failed"))
        return
    hint = _first_text(response.get("world_hint_draft"))
    if not hint:
        ui.warning(translate("content.ip_world.generate_failed"))
        return
    session_state[CONTENT_GENERATION_WORLD_HINT_KEY] = hint
    session_state[CONTENT_GENERATION_WORLD_HINT_SOURCE_KEY] = "generated_from_script"
    session_state[CONTENT_GENERATION_WORLD_HINT_LAST_VALUE_KEY] = hint
    safe_rerun()
```

- [ ] **Step 4: Add i18n keys**

In `web/i18n/locales/zh_CN.json`, replace the old generation-notes-only labels with:

```json
"content.ip_world.generation_world_hint": "世界观提示",
"content.ip_world.generation_world_hint_help": "描述本次文案发生的世界、叙事边界，以及 IP 在本次内容里如何自然融入；不会覆盖 IP 设计页的长期世界观。",
"content.ip_world.generate_from_content": "根据文案生成",
"content.ip_world.use_ip_default": "使用 IP 默认",
"content.ip_world.missing_content": "请先填写文案，再生成世界观提示草稿。",
"content.ip_world.missing_ip_default": "当前 IP 没有可用的默认世界观提示。",
"content.ip_world.generate_failed": "世界观提示草稿生成失败，请稍后重试。"
```

In `web/i18n/locales/en_US.json`, add:

```json
"content.ip_world.generation_world_hint": "World Hint",
"content.ip_world.generation_world_hint_help": "Describe the current script world, narrative boundaries, and how the IP should naturally fit this generation. This does not overwrite the IP design world hint.",
"content.ip_world.generate_from_content": "Generate from Script",
"content.ip_world.use_ip_default": "Use IP Default",
"content.ip_world.missing_content": "Fill in the script before generating a world hint draft.",
"content.ip_world.missing_ip_default": "The selected IP has no default world hint.",
"content.ip_world.generate_failed": "World hint draft generation failed. Please try again."
```

Keep the existing capability-preview i18n keys.

- [ ] **Step 5: Run helper and i18n tests**

Run:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_content_ip_world_controls.py -q
```

Expected after this task:

```text
15 passed
```

- [ ] **Step 6: Commit**

```powershell
git add web/components/content_ip_world_controls.py web/i18n/locales/zh_CN.json web/i18n/locales/en_US.json tests/test_content_ip_world_controls.py
git commit -m "fix: 恢复世界观提示辅助回填"
```

## Task 4: Verify Formal Request Path Stays Narrow

**Files:**
- Test: `tests/test_content_input_storyboard_ui.py`
- Test: `tests/test_output_preview.py`
- Test: `tests/test_video_api.py`
- Test: `tests/test_image_prompt_composer.py`
- Optional modify: tests only if expectations reference removed UI-only fields.

- [ ] **Step 1: Run existing contract tests**

Run:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_content_input_storyboard_ui.py::test_left_content_ip_payload_render_content_input tests/test_output_preview.py::test_build_single_generation_request_includes_generation_world_hint tests/test_output_preview.py::test_build_single_generation_request_does_not_forward_ip_profile_world_hint tests/test_video_api.py::test_build_video_generation_params_copies_generation_world_hint tests/test_image_prompt_composer.py::test_composer_passes_generation_world_hint_to_styled_batch -q
```

Expected:

```text
5 passed
```

- [ ] **Step 2: Add a regression assertion that dead UI fields are not forwarded**

In `tests/test_output_preview.py`, add:

```python
def test_build_single_generation_request_does_not_forward_content_ip_ui_only_fields():
    def _progress(_event):
        return None

    request = output_preview.build_single_generation_request(
        {
            "mode": "generate",
            "text": "demo",
            "ip_enabled": True,
            "ip_asset_bible_id": "bible_demo",
            "ip_profile_id": "ip_main",
            "generation_world_hint": "古城清晨漫游，IP 是陪伴式向导。",
            "generation_notes": "ui-only old field",
            "slot_preference_override": "prefer_main",
            "presence_strength": "more",
            "ip_profile_world_hint": "helper only",
        },
        progress_callback=_progress,
        session_state={},
    )

    assert request["generation_world_hint"] == "古城清晨漫游，IP 是陪伴式向导。"
    assert "generation_notes" not in request
    assert "slot_preference_override" not in request
    assert "presence_strength" not in request
    assert "ip_profile_world_hint" not in request
```

- [ ] **Step 3: Run the new test**

Run:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_output_preview.py -k "generation_world_hint or ui_only_fields or ip_profile_world_hint" -q
```

Expected:

```text
passed
```

- [ ] **Step 4: Commit**

```powershell
git add tests/test_output_preview.py
git commit -m "test: 锁定生成请求世界观合同"
```

## Task 5: Align IP Workbench Readiness With Backend

**Files:**
- Modify: `web/components/ip_design_workbench.py`
- Modify: `tests/test_ip_design_workbench_ui.py`

- [ ] **Step 1: Add failing frontend readiness test**

In `tests/test_ip_design_workbench_ui.py`, add:

```python
def test_ip_profile_ready_for_generation_accepts_identity_anchors():
    from web.components.ip_design_workbench import _ip_profile_ready_for_generation

    assert _ip_profile_ready_for_generation(
        {"identity_lock": [], "identity_anchors": ["蓝色领结"]}
    )
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_ip_design_workbench_ui.py::test_ip_profile_ready_for_generation_accepts_identity_anchors -q
```

Expected now:

```text
FAILED
```

- [ ] **Step 3: Implement frontend readiness using both identity fields**

In `web/components/ip_design_workbench.py`, change:

```python
def _ip_profile_ready_for_generation(ip_profile: Mapping[str, Any]) -> bool:
    return bool(_text_list(ip_profile.get("identity_lock")))
```

to:

```python
def _ip_profile_ready_for_generation(ip_profile: Mapping[str, Any]) -> bool:
    return bool(
        [
            *_text_list(ip_profile.get("identity_lock")),
            *_text_list(ip_profile.get("identity_anchors")),
        ]
    )
```

- [ ] **Step 4: Run readiness tests**

Run:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_ip_design_workbench_ui.py -k "ready_for_generation or generation_unavailable" -q
```

Expected:

```text
passed
```

- [ ] **Step 5: Commit**

```powershell
git add web/components/ip_design_workbench.py tests/test_ip_design_workbench_ui.py
git commit -m "fix: 统一IP生成可用性判断"
```

## Task 6: Align `color_palette` Save Shape With Planner Consumption

**Files:**
- Modify: `web/components/ip_design_workbench.py`
- Modify: `tests/test_ip_design_workbench_ui.py`
- Optional test: `tests/test_ip_usage_planner.py`

- [ ] **Step 1: Add failing save-shape test**

In `tests/test_ip_design_workbench_ui.py`, extend `test_ip_design_workbench_saves_asset_bible_through_client()` with a prompt-safe color rule:

```python
fake_ui.session_state["ip_design_color_rules"] = "纯白色身体, 鲜明宝蓝色领结"
```

Add assertions after `profile = saved_profiles[0]`:

```python
assert profile["color_palette"] == {
    "rule_1": {"prompt": "纯白色身体"},
    "rule_2": {"prompt": "鲜明宝蓝色领结"},
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_ip_design_workbench_ui.py::test_ip_design_workbench_saves_asset_bible_through_client -q
```

Expected now:

```text
FAILED
```

The failure should show the current root-level `"prompt"` shape.

- [ ] **Step 3: Add a color palette builder**

In `web/components/ip_design_workbench.py`, add:

```python
def _build_color_palette_prompt_entries(
    existing_palette: Mapping[str, Any],
    color_rules: str,
) -> dict[str, Any]:
    palette = {
        str(key): dict(value)
        for key, value in dict(existing_palette or {}).items()
        if isinstance(value, Mapping)
    }
    rules = _split_csv(color_rules)
    if not rules:
        return palette
    for index, rule in enumerate(rules, start=1):
        palette[f"rule_{index}"] = {"prompt": rule}
    return palette
```

Then replace:

```python
"color_palette": (
    {**ip_profile.get("color_palette", {}), "prompt": color_rules}
    if color_rules.strip()
    else ip_profile.get("color_palette", {})
),
```

with:

```python
"color_palette": _build_color_palette_prompt_entries(
    ip_profile.get("color_palette", {}),
    color_rules,
),
```

- [ ] **Step 4: Add planner consumption test**

In `tests/test_ip_usage_planner.py`, add:

```python
def test_identity_color_terms_reads_workbench_palette_entries():
    from pixelle_video.models.asset_bible import IPProfile
    from pixelle_video.services.ip_usage_planner import _identity_color_terms

    profile = IPProfile(
        ip_profile_id="ip_main",
        workspace_id="workspace_1",
        project_id="project_1",
        name="正定向导兔",
        identity_lock=("白色卡通兔子",),
        color_palette={
            "rule_1": {"prompt": "纯白色身体"},
            "rule_2": {"prompt": "鲜明宝蓝色领结"},
        },
    )

    assert _identity_color_terms(profile) == ("纯白色身体", "鲜明宝蓝色领结")
```

- [ ] **Step 5: Run color tests**

Run:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_ip_design_workbench_ui.py::test_ip_design_workbench_saves_asset_bible_through_client tests/test_ip_usage_planner.py::test_identity_color_terms_reads_workbench_palette_entries -q
```

Expected:

```text
2 passed
```

- [ ] **Step 6: Commit**

```powershell
git add web/components/ip_design_workbench.py tests/test_ip_design_workbench_ui.py tests/test_ip_usage_planner.py
git commit -m "fix: 对齐IP颜色规则存储结构"
```

## Task 7: Final Verification

**Files:**
- Verify: all files touched in Tasks 2-6.

- [ ] **Step 1: Run focused IP/world contract tests**

Run:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_content_ip_world_controls.py tests/test_content_input_storyboard_ui.py::test_left_content_ip_payload_render_content_input tests/test_output_preview.py::test_build_single_generation_request_includes_generation_world_hint tests/test_output_preview.py::test_build_single_generation_request_does_not_forward_ip_profile_world_hint tests/test_video_api.py::test_build_video_generation_params_copies_generation_world_hint tests/test_image_prompt_composer.py::test_composer_passes_generation_world_hint_to_styled_batch -q
```

Expected:

```text
passed
```

- [ ] **Step 2: Run focused IP workbench tests**

Run:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_ip_design_workbench_ui.py tests/test_ip_usage_planner.py -q
```

Expected:

```text
passed
```

- [ ] **Step 3: Run a wider regression group**

Run:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_output_preview.py tests/test_video_api.py tests/test_image_prompt_composer.py tests/test_styled_image_prompt_batch.py -q
```

Expected:

```text
passed
```

If unrelated pre-existing failures appear, capture the failing test names and error messages before deciding whether they belong to this change.

- [ ] **Step 4: Check formal request fields with ripgrep**

Run:

```powershell
rg -n "generation_notes|slot_preference_override|presence_strength" web/components/content_ip_world_controls.py web/components/output_preview.py pixelle_video/models/video_generation_contract.py api/schemas/video.py
```

Expected after Task 2:

```text
```

No matches should appear in the formal request builder or contract. If `ip_usage_planner.py` still has internal `generation_notes` derived from `ContentWorldProfile`, that is allowed because it is not the old frontend dead parameter.

- [ ] **Step 5: Confirm git diff**

Run:

```powershell
git status --short
git diff --stat
```

Expected:

```text
Only files from this plan are modified.
```

- [ ] **Step 6: Final commit if needed**

If Task 7 required any test-only or documentation updates:

```powershell
git add docs/superpowers/specs/2026-05-24-ip-design-entry-contract-realignment-design.md docs/superpowers/plans/2026-05-24-ip-design-entry-contract-realignment-implementation.md
git commit -m "docs: 补充IP入口合同回归执行计划"
```

## Self-Review

Spec coverage:

- Historical requirement that IP should blend into user scripts is covered by the development document and by preserving `generation_world_hint`.
- Historical requirement that the left content module is the authoritative entry is covered by Tasks 2-4.
- Historical requirement that `IPProfile` remains the structured identity source is preserved by keeping identity fields separate from `generation_world_hint`.
- Current failed tests are covered by Tasks 2-3.
- Color and readiness mismatches are covered by Tasks 5-6.

Placeholder scan:

- The plan contains concrete commands and code snippets for each code-changing step.

Type consistency:

- `generation_world_hint` remains request-level.
- `IPProfile.world_hint` remains asset-level.
- `ip_profile_world_hint` remains helper-only.
- `color_palette` stores per-entry mappings with `prompt`, matching `_identity_color_terms()`.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-24-ip-design-entry-contract-realignment-implementation.md`. Two execution options:

**1. Subagent-Driven (recommended)** - Dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints.
