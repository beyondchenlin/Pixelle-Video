# Storyboard No-Text Toggle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `禁止图中文字` toggle to the `Storyboard Planning` panel, default it to enabled, and thread the value through Web request building and API schemas so the existing backend no-text prompt policy becomes user-configurable.

**Architecture:** Keep the current backend no-text prompt logic as the source of truth and expose only one new boolean UI contract, `forbid_embedded_text_in_image`. Implement the feature in three layers: Streamlit storyboard UI, request/schema transport, and focused tests that prove the value defaults to `True` and reaches the shared styled-prompt generation path.

**Tech Stack:** Python 3.12, Streamlit, Pydantic v2, pytest, existing Pixelle storyboard UI helpers

---

Repository note: `AGENTS.md` in this repository forbids `git worktree`, so execute this plan on the current branch and stage only the files listed in each task before each atomic commit.

## File Structure

- Modify: `web/components/style_config.py`
  Add the storyboard no-text checkbox, include it in the storyboard guide copy, and thread the value into the returned style-config payload.
- Modify: `web/components/output_preview.py`
  Include `forbid_embedded_text_in_image` in single-generation and batch shared request builders.
- Modify: `api/schemas/content.py`
  Accept the optional boolean in image-prompt generation requests.
- Modify: `api/schemas/video.py`
  Accept the optional boolean in video-generation requests.
- Modify: `tests/test_style_config_storyboard_planning_ui.py`
  Lock UI default value, payload serialization, and request-building behavior.
- Modify: `tests/test_output_preview.py`
  Lock single and batch request builders so the field is copied through.
- Modify: `tests/test_content_image_prompt_api.py`
  Lock schema acceptance and endpoint threading for the new field.

Intentionally untouched in this patch:

- `pixelle_video/utils/content_generators.py`
  The backend no-text prompt behavior is already implemented and tested; this patch only exposes control of the existing parameter.
- `pixelle_video/pipelines/standard.py`
- `pixelle_video/pipelines/custom.py`
  They already accept and forward `forbid_embedded_text_in_image`; no code change is needed unless a failing integration test proves otherwise.

### Task 1: Add the storyboard UI toggle and payload field

**Files:**
- Modify: `web/components/style_config.py`
- Modify: `tests/test_style_config_storyboard_planning_ui.py`

- [ ] **Step 1: Write the failing UI tests**

```python
# tests/test_style_config_storyboard_planning_ui.py
def test_build_storyboard_control_payload_includes_no_text_toggle():
    payload = build_storyboard_control_payload(
        world_preset_id="neutral_knowledge_storyboard",
        forbid_embedded_text_in_image=False,
    )

    assert payload == {
        "world_preset_id": "neutral_knowledge_storyboard",
        "forbid_embedded_text_in_image": False,
    }


def test_render_style_config_defaults_no_text_toggle_to_true(monkeypatch):
    fake_st = _FakeStreamlit()
    fake_st.session_state["template_type_selector"] = "image"
    monkeypatch.setattr(style_config, "st", fake_st)
    monkeypatch.setattr(style_config, "tr", lambda key, **kwargs: key)
    monkeypatch.setattr(style_config, "get_language", lambda: "en_US")
    monkeypatch.setattr(
        style_config.config_manager,
        "get_comfyui_config",
        lambda: {
            "tts": {
                "inference_mode": "local",
                "local": {"voice": "zh-CN-YunjianNeural", "speed": 1.2},
                "comfyui": {},
            },
            "image": {},
            "video": {},
        },
    )
    monkeypatch.setattr(style_config, "render_render_backend_selector", lambda: "render_backend")
    monkeypatch.setattr(style_config, "render_tts_audio_strategy_selector", lambda: "auto")
    monkeypatch.setattr(style_config, "render_storyboard_planning_guide", lambda: None)
    monkeypatch.setattr(style_config, "render_storyboard_preview", lambda _snapshot: [])
    monkeypatch.setattr(style_config, "_render_image_prompt_prefix_library", lambda **_kwargs: "")
    monkeypatch.setattr(style_config, "check_and_warn_selfhost_workflow", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        style_config.config_manager,
        "get_storyboard_world_preset_library",
        lambda: {
            "default_world_preset_id": "neutral_knowledge_storyboard",
            "items": [{"preset_id": "neutral_knowledge_storyboard", "display_name": "Neutral"}],
        },
    )
    monkeypatch.setattr(
        style_config.config_manager,
        "get_storyboard_shot_preset_library",
        lambda: {
            "default_shot_preset_id": "balanced_explainer",
            "items": [{"preset_id": "balanced_explainer", "display_name": "Balanced"}],
        },
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.get_template_type",
        lambda _template_name: "image",
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.get_templates_grouped_by_size_and_type",
        lambda _template_type: {
            "1080x1920": [
                type(
                    "TemplateInfo",
                    (),
                    {
                        "template_path": "1080x1920/image_default.html",
                        "display_info": type(
                            "DisplayInfo",
                            (),
                            {"name": "image_default", "orientation": "portrait", "width": 1080, "height": 1920},
                        )(),
                    },
                )()
            ]
        },
    )

    result = style_config.render_style_config(type("Video", (), {"config": {"template": {}}})(), storyboard_default_enabled=True)

    assert result["forbid_embedded_text_in_image"] is True
    no_text_checkbox = next(
        call for call in fake_st.checkbox_calls if call["label"] == "storyboard.forbid_embedded_text"
    )
    assert no_text_checkbox["value"] is True
```

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run: `uv run pytest tests/test_style_config_storyboard_planning_ui.py -k "no_text_toggle" -v`

Expected: FAIL because the storyboard payload helper and `render_style_config()` do not yet expose `forbid_embedded_text_in_image`.

- [ ] **Step 3: Add the checkbox, payload wiring, and guide hook**

```python
# web/components/style_config.py
def build_storyboard_control_payload(
    *,
    world_preset_id: str | None = None,
    shot_preset_id: str | None = None,
    consistency_strength: str | None = None,
    content_mode: str | None = None,
    role_strategy: str | None = None,
    role_locking_strength: str | None = None,
    shot_strategy: str | None = None,
    frame_overrides: list[dict] | None = None,
    forbid_embedded_text_in_image: bool | None = None,
) -> dict:
    payload: dict = {}
    if world_preset_id is not None:
        payload["world_preset_id"] = world_preset_id
    if shot_preset_id not in (None, STORYBOARD_SHOT_PRESET_AUTO_VALUE):
        payload["shot_preset_id"] = shot_preset_id
    if consistency_strength not in (None, "standard"):
        payload["consistency_strength"] = consistency_strength
    if content_mode is not None:
        payload["content_mode"] = content_mode
    if role_strategy is not None:
        payload["role_strategy"] = role_strategy
    if role_locking_strength is not None:
        payload["role_locking_strength"] = role_locking_strength
    if shot_strategy is not None:
        payload["shot_strategy"] = shot_strategy
    if frame_overrides:
        payload["frame_overrides"] = frame_overrides
    if forbid_embedded_text_in_image is not None:
        payload["forbid_embedded_text_in_image"] = forbid_embedded_text_in_image
    return payload
```

```python
# web/components/style_config.py inside render_style_config(...)
    storyboard_forbid_embedded_text_in_image = True

    with render_middle_column_collapsible_section(
        tr("section.storyboard_planning"),
        expanded=False,
    ):
        storyboard_enabled = st.checkbox(
            tr("storyboard.enabled"),
            value=resolve_storyboard_toggle_default(
                st.session_state,
                storyboard_default_enabled=storyboard_default_enabled,
                preview_snapshot=st.session_state.get("storyboard_preview_snapshot"),
                template_type=selected_template_type_for_storyboard,
            ),
            key=storyboard_checkbox_key,
            help=tr("storyboard.enabled_help"),
            disabled=storyboard_controls_disabled,
        )

        if storyboard_controls_disabled:
            st.caption(tr("template.type.static_hint"))
        elif storyboard_enabled:
            render_storyboard_planning_guide()
            ...
            storyboard_forbid_embedded_text_in_image = st.checkbox(
                tr("storyboard.forbid_embedded_text"),
                value=st.session_state.get("storyboard_forbid_embedded_text_in_image", True),
                help=tr("storyboard.forbid_embedded_text_help"),
                key="storyboard_forbid_embedded_text_in_image",
            )
            storyboard_frame_overrides = render_storyboard_preview(
                st.session_state.get("storyboard_preview_snapshot")
            )
        else:
            st.caption(tr("storyboard.preview.empty"))

    return dict(
        ...,
        forbid_embedded_text_in_image=storyboard_forbid_embedded_text_in_image,
    )
```

```python
# web/components/style_config.py inside the storyboard guide content
{
    "title_key": "storyboard.forbid_embedded_text",
    "body_key": "storyboard.guide.forbid_embedded_text",
}
```

- [ ] **Step 4: Re-run the targeted tests**

Run: `uv run pytest tests/test_style_config_storyboard_planning_ui.py -k "no_text_toggle" -v`

Expected: PASS for the new payload and default-toggle tests.

- [ ] **Step 5: Commit the UI toggle change**

```bash
git add web/components/style_config.py tests/test_style_config_storyboard_planning_ui.py
git commit -m "feat: add storyboard no-text toggle"
```

### Task 2: Thread the toggle through Web request builders and API schemas

**Files:**
- Modify: `web/components/output_preview.py`
- Modify: `api/schemas/content.py`
- Modify: `api/schemas/video.py`
- Modify: `tests/test_output_preview.py`
- Modify: `tests/test_content_image_prompt_api.py`

- [ ] **Step 1: Write the failing transport tests**

```python
# tests/test_output_preview.py
def test_build_single_generation_request_includes_no_text_toggle():
    request = output_preview.build_single_generation_request(
        {
            "text": "demo",
            "mode": "generate",
            "frame_template": "1080x1920/image_default.html",
            "tts_inference_mode": "local",
            "forbid_embedded_text_in_image": False,
        },
        progress_callback=lambda _event: None,
        session_state={"template_media_width": 1080, "template_media_height": 1920},
    )

    assert request["forbid_embedded_text_in_image"] is False


def test_build_batch_shared_config_includes_no_text_toggle():
    shared_config = output_preview.build_batch_shared_config(
        {
            "frame_template": "1080x1920/image_default.html",
            "tts_inference_mode": "local",
            "forbid_embedded_text_in_image": False,
        }
    )

    assert shared_config["forbid_embedded_text_in_image"] is False
```

```python
# tests/test_content_image_prompt_api.py
def test_image_prompt_generate_request_accepts_no_text_toggle():
    request = ImagePromptGenerateRequest(
        narrations=["scene one"],
        forbid_embedded_text_in_image=False,
    )

    assert request.forbid_embedded_text_in_image is False


@pytest.mark.asyncio
async def test_generate_image_prompt_endpoint_threads_no_text_toggle(monkeypatch):
    async def fake_generate_styled_image_prompt_batch(**kwargs):
        assert kwargs["forbid_embedded_text_in_image"] is False
        return StyledImagePromptBatch(
            prompts=["styled prompt"],
            negative_prompt=None,
            resolved_style=None,
        )

    monkeypatch.setattr(
        "api.routers.content.generate_styled_image_prompt_batch",
        fake_generate_styled_image_prompt_batch,
    )

    response = await generate_image_prompt(
        ImagePromptGenerateRequest(
            narrations=["scene one"],
            forbid_embedded_text_in_image=False,
        ),
        _FakePixelleVideo(),
    )

    assert response.image_prompts == ["styled prompt"]
```

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run: `uv run pytest tests/test_output_preview.py tests/test_content_image_prompt_api.py -k "no_text_toggle" -v`

Expected: FAIL because request builders and API schemas do not yet expose `forbid_embedded_text_in_image`.

- [ ] **Step 3: Add the request and schema field**

```python
# web/components/output_preview.py
def build_single_generation_request(video_params, *, progress_callback, session_state):
    request = {
        "text": video_params.get("text", ""),
        "mode": video_params.get("mode", "generate"),
        "title": video_params.get("title") if video_params.get("title") else None,
        "n_scenes": video_params.get("n_scenes", 5),
        "split_mode": video_params.get("split_mode", "paragraph"),
        "media_workflow": video_params.get("media_workflow"),
        "frame_template": video_params.get("frame_template"),
        "prompt_prefix": video_params.get("prompt_prefix", ""),
        "bgm_path": video_params.get("bgm_path"),
        "bgm_volume": video_params.get("bgm_volume", 0.2) if video_params.get("bgm_path") else 0.2,
        "progress_callback": progress_callback,
        "media_width": session_state.get("template_media_width"),
        "media_height": session_state.get("template_media_height"),
        "tts_inference_mode": video_params.get("tts_inference_mode", "local"),
        "world_preset_id": video_params.get("world_preset_id"),
        "shot_preset_id": video_params.get("shot_preset_id"),
        "consistency_strength": video_params.get("consistency_strength") or "standard",
        "content_mode": video_params.get("content_mode"),
        "role_strategy": video_params.get("role_strategy"),
        "role_locking_strength": video_params.get("role_locking_strength"),
        "shot_strategy": video_params.get("shot_strategy"),
        "frame_overrides": video_params.get("frame_overrides"),
        "forbid_embedded_text_in_image": video_params.get("forbid_embedded_text_in_image", True),
    }
    ...


def build_batch_shared_config(video_params):
    shared_config = {
        "title_prefix": video_params.get("title_prefix"),
        "n_scenes": video_params.get("n_scenes") or 5,
        "media_workflow": video_params.get("media_workflow"),
        "frame_template": video_params.get("frame_template"),
        "prompt_prefix": video_params.get("prompt_prefix") or "",
        "bgm_path": video_params.get("bgm_path"),
        "bgm_volume": video_params.get("bgm_volume") or 0.2,
        "tts_inference_mode": video_params.get("tts_inference_mode") or "local",
        "media_width": video_params.get("media_width"),
        "media_height": video_params.get("media_height"),
        "world_preset_id": video_params.get("world_preset_id"),
        "shot_preset_id": video_params.get("shot_preset_id"),
        "consistency_strength": video_params.get("consistency_strength") or "standard",
        "content_mode": video_params.get("content_mode"),
        "role_strategy": video_params.get("role_strategy"),
        "role_locking_strength": video_params.get("role_locking_strength"),
        "shot_strategy": video_params.get("shot_strategy"),
        "frame_overrides": video_params.get("frame_overrides"),
        "forbid_embedded_text_in_image": video_params.get("forbid_embedded_text_in_image", True),
    }
    ...
```

```python
# api/schemas/content.py
class ImagePromptGenerateRequest(BaseModel):
    ...
    forbid_embedded_text_in_image: Optional[bool] = Field(
        None,
        description="Whether to suppress embedded text inside generated images",
    )
```

```python
# api/schemas/video.py
class VideoGenerateRequest(BaseModel):
    ...
    forbid_embedded_text_in_image: Optional[bool] = Field(
        None,
        description="Whether to suppress embedded text inside generated images",
    )
```

- [ ] **Step 4: Re-run the targeted tests**

Run: `uv run pytest tests/test_output_preview.py tests/test_content_image_prompt_api.py -k "no_text_toggle" -v`

Expected: PASS for the request builder and API schema coverage.

- [ ] **Step 5: Commit the transport change**

```bash
git add web/components/output_preview.py api/schemas/content.py api/schemas/video.py tests/test_output_preview.py tests/test_content_image_prompt_api.py
git commit -m "feat: thread storyboard no-text toggle through requests"
```

### Task 3: Verify integration and guide-copy consistency

**Files:**
- Modify: `web/components/style_config.py`
- Modify: `tests/test_style_config_storyboard_planning_ui.py`
- Modify: `tests/test_output_preview.py`
- Modify: `tests/test_content_image_prompt_api.py`

- [ ] **Step 1: Add an integration-focused test for explicit `False`**

```python
# tests/test_style_config_storyboard_planning_ui.py
def test_build_storyboard_control_payload_preserves_explicit_false_for_no_text_toggle():
    payload = build_storyboard_control_payload(
        world_preset_id="neutral_knowledge_storyboard",
        forbid_embedded_text_in_image=False,
    )

    assert payload["forbid_embedded_text_in_image"] is False
```

```python
# tests/test_output_preview.py
def test_build_single_generation_request_defaults_no_text_toggle_to_true():
    request = output_preview.build_single_generation_request(
        {
            "text": "demo",
            "mode": "generate",
            "frame_template": "1080x1920/image_default.html",
            "tts_inference_mode": "local",
        },
        progress_callback=lambda _event: None,
        session_state={"template_media_width": 1080, "template_media_height": 1920},
    )

    assert request["forbid_embedded_text_in_image"] is True
```

- [ ] **Step 2: Run the focused integration tests to verify behavior**

Run: `uv run pytest tests/test_style_config_storyboard_planning_ui.py tests/test_output_preview.py tests/test_content_image_prompt_api.py -k "no_text_toggle or defaults_no_text_toggle or preserves_explicit_false" -v`

Expected: PASS, proving both explicit `False` and implicit default `True` behaviors.

- [ ] **Step 3: Run the full focused regression suite**

Run: `uv run pytest tests/test_style_config_storyboard_planning_ui.py tests/test_output_preview.py tests/test_content_image_prompt_api.py tests/test_prompt_helper_no_text_policy.py tests/test_styled_image_prompt_batch.py -q`

Expected: PASS with all relevant UI, request, API, and downstream no-text prompt tests green.

- [ ] **Step 4: Run lint on touched files**

Run: `uv run ruff check web/components/style_config.py web/components/output_preview.py api/schemas/content.py api/schemas/video.py tests/test_style_config_storyboard_planning_ui.py tests/test_output_preview.py tests/test_content_image_prompt_api.py`

Expected: `All checks passed!`

- [ ] **Step 5: Commit the verification and final polish**

```bash
git add web/components/style_config.py web/components/output_preview.py api/schemas/content.py api/schemas/video.py tests/test_style_config_storyboard_planning_ui.py tests/test_output_preview.py tests/test_content_image_prompt_api.py
git commit -m "test: cover storyboard no-text toggle flow"
```

## Self-Review

Spec coverage check:

- UI placement in storyboard panel: covered by Task 1
- default-on behavior: covered by Task 1 and Task 3
- request-builder threading: covered by Task 2
- API schema contract: covered by Task 2
- explicit `False` reaching the shared prompt path: covered by Task 2 endpoint threading test and Task 3 focused verification

Placeholder scan:

- no `TODO`, `TBD`, or indirect “handle later” placeholders remain
- all tasks list exact file paths, commands, and concrete assertions

Type consistency:

- the field name is consistently `forbid_embedded_text_in_image`
- request builders, UI payload, and API schema all use the same boolean name

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-23-storyboard-no-text-toggle-implementation.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
