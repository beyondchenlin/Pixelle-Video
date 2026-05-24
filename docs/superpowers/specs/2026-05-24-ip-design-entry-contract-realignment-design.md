# IP Design Entry Contract Realignment Design

Date: 2026-05-24

## 1. Conclusion

This document realigns the current IP design work with the earlier requirements and the code that exists today.

The immediate problem is not that the whole downstream IP pipeline is missing. The downstream `generation_world_hint` path already exists in API schema, generation contract, standard pipeline, `ContentWorldPlanner`, `IPFrameAppearancePlanner`, and image prompt composition. The broken part is the left-side generation-page entry: `web/components/content_ip_world_controls.py` has drifted away from the previous design and from its own tests.

The next implementation should first restore the left-side IP/world entry contract:

1. The left-side content module is the authoritative generation-page entry for IP selection and request-level world hint.
2. The formal generation request should carry `ip_enabled`, `ip_asset_bible_id`, `ip_profile_id`, and `generation_world_hint`.
3. Helper fields such as `ip_profile_world_hint`, `generation_world_hint_source`, and draft state may exist only in frontend session state or draft API payloads.
4. UI-only fields that do not enter the formal generation contract must either be removed or converted to the formal `generation_world_hint` workflow.

This is a smaller and safer first step than changing planner architecture again.

## 2. Terminal Evidence

The app terminal was checked through Codex Desktop, but no app terminal session was attached to this thread:

```text
No app terminal session is attached to this thread yet.
```

Shell verification was run in the repository virtual environment:

```powershell
./.venv/Scripts/python.exe -c "import streamlit, comfykit, loguru; print('deps ok')"
```

Result:

```text
deps ok
```

The focused content IP/world tests currently fail:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_content_ip_world_controls.py tests/test_content_input_storyboard_ui.py::test_left_content_ip_payload_render_content_input tests/test_output_preview.py::test_build_single_generation_request_includes_generation_world_hint -q
```

Result:

```text
11 failed, 4 passed
```

The failures are concentrated in `tests/test_content_ip_world_controls.py`:

- `generation_world_hint` is not returned from the left-side payload.
- `content_ip_profile_world_hint` is not synced or cleared.
- `safe_rerun` is no longer imported for the world-hint helper actions.
- Missing i18n keys for `generation_world_hint`, `generate_from_content`, `use_ip_default`, and warnings.
- The fake UI lacks `container()` because current rendering now calls capability preview.

The downstream `generation_world_hint` path still passes targeted tests:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_content_input_storyboard_ui.py::test_left_content_ip_payload_render_content_input tests/test_output_preview.py::test_build_single_generation_request_includes_generation_world_hint tests/test_video_api.py::test_build_video_generation_params_copies_generation_world_hint tests/test_image_prompt_composer.py::test_composer_passes_generation_world_hint_to_styled_batch -q
```

Result:

```text
4 passed
```

Two small mismatches were also verified directly:

- `IPProfile.color_palette={"prompt": "纯白色身体"}` yields no planner color terms because `_identity_color_terms()` expects each palette entry to be a mapping with its own `prompt`.
- Frontend readiness currently returns `False` for `{"identity_lock": [], "identity_anchors": ["蓝色领带"]}`, while backend readiness accepts `identity_anchors`.

## 3. Historical Requirements Baseline

The old requirements are real and are present in repository docs and recovered conversation logs.

### 3.1 User Requirement From `docs/IP设计对话记录.md`

The user requirement was:

- The IP must serve the user-provided script, not force every scene to become an IP scene.
- The IP should blend into generated images naturally instead of appearing as a separate sticker-like object.
- The IP may be the main subject, a supporting role, a passerby, full body, half body, partial appearance, far background, or absent.
- The IP should not occupy a large share of every image by default.
- The final image prompt should let the model freely dress, equip, pose, emote, and interact with the IP within the IP's stable visual style.

This led to the three-layer model:

1. Visual identity: what the IP looks like and must not lose.
2. Role and behavior: what the IP does in this script or frame.
3. Frame presence: how large, close, visible, or absent the IP is.

### 3.2 Existing Specs That Define The Rules

`docs/superpowers/specs/2026-05-04-ipprofile-结构化事实源设计.md` says:

- `IPProfile` is the single structured source of truth for the IP.
- Formal generation identity comes from `identity_lock`, `identity_anchors`, `semantic_boundary`, `negative_constraints`, `color_palette[*].prompt`, and `visible_text_whitelist`.
- `logline`, `world_hint`, and `style_hint` are explanatory or creative context, not hard identity facts.
- If IP is enabled and both `identity_lock` and `identity_anchors` are empty, generation must fail clearly.

`docs/superpowers/specs/2026-05-04-生成页世界观提示设计.md` says:

- `IPProfile.world_hint` is asset-level, long-term, and reusable.
- `generation_world_hint` is request-level and describes the current script world and how the IP should fit this generation.
- `generation_world_hint` must not replace `identity_lock` or `identity_anchors`.
- `generation_world_hint` must not be written back to AssetBible.

`docs/superpowers/specs/2026-05-04-左侧IP与世界观入口提升设计.md` says:

- The left content input area should contain a first-class "IP and world" module.
- That module is the authoritative standard-generation entry for IP selection, IP default world hint fill, script-based world hint draft, and manual request-level world hint editing.
- The formal request still uses only `ip_enabled`, `ip_asset_bible_id`, `ip_profile_id`, and `generation_world_hint`.
- `ip_profile_world_hint` is helper context only and must not enter the formal generation request.

`docs/superpowers/specs/2026-05-06-ip-通用演员化设计.md` says:

- IP is a universal actor, not a fixed-job mascot.
- `identity_lock` should contain pure visual identity, not fixed role duties.
- `role_presets`, `presence_spectrum`, and adaptable slots should guide per-frame role and presence decisions.
- `IPFrameAppearancePlanner` should drive frame-level natural-language appearance descriptions.

`docs/superpowers/specs/2026-05-01-stage2-prompt-plan-projection-design.md` says:

- SceneCast projection was originally a preview loop, not a main generation integration.
- Later integration can happen deliberately, but it should not be confused with the left-side generation request contract.

## 4. Current Code Facts

### 4.1 Downstream `generation_world_hint` Is Present

These files already support the formal request-level world hint:

- `api/schemas/video.py`
- `api/routers/video.py`
- `pixelle_video/models/video_generation_contract.py`
- `pixelle_video/pipelines/standard.py`
- `pixelle_video/services/content_world_planner.py`
- `pixelle_video/services/image_prompt_composer.py`
- `pixelle_video/utils/content_generators.py`

The targeted downstream tests pass, so this path should not be rewritten first.

### 4.2 Left-Side Entry Is Regressed

`web/components/content_ip_world_controls.py` currently builds this payload:

```python
{
    "ip_enabled": ...,
    "ip_asset_bible_id": ...,
    "ip_profile_id": ...,
    "generation_notes": ...,
    "slot_preference_override": ...,
    "presence_strength": ...,
}
```

The formal generation contract ignores `generation_notes`, `slot_preference_override`, and `presence_strength`.

The tests expect this module to return `generation_world_hint`, support "use IP default", support "generate from script", and keep helper world-hint fields out of the formal payload.

### 4.3 Content Input Already Gives Left-Side Payload Priority

`web/components/content_input.py` deliberately removes `generation_world_hint` from storyboard controls before merging:

```python
storyboard_generation = dict(storyboard_generation)
storyboard_generation.pop("generation_world_hint", None)
...
**content_ip_world
```

This matches the old requirement: the left-side content IP/world module should own request-level world hint.

### 4.4 `output_preview.py` Copies The Correct Contract

`web/components/output_preview.py` uses `copy_generation_world_hint()` and `copy_ip_prompt_chain_options()` to keep the formal generation request narrow.

This is correct and should stay narrow. The left-side helper fields should be fixed before reaching `output_preview.py`.

### 4.5 IP Planner Is Partly Integrated, Not The First Blocker

`pixelle_video/utils/content_generators.py` already calls `IPFrameAppearancePlanner(llm_client=llm_service).plan_batch(...)`.

There are still deeper improvement opportunities:

- LLM role selection input does not yet include all fields such as `presence_spectrum`, `adaptable_slots`, `minimal_traits`, and `semantic_boundary`.
- SceneCast currently influences presence mostly through `ip_presence_type` / `presence_type`.
- Full `ip_adaptation` is stored in planning snapshot, while prompt contexts receive selected flattened fields.

These are real enhancement areas, but they are not the current first blocker because the left-side request entry is failing before the planner can receive the right request-level world hint.

### 4.6 Small Data Shape Mismatches

`web/components/ip_design_workbench.py` saves color rules as:

```python
color_palette = {**ip_profile.get("color_palette", {}), "prompt": color_rules}
```

`pixelle_video/services/ip_usage_planner.py` reads:

```python
for palette_entry in ip_profile.color_palette.values():
    if isinstance(palette_entry, Mapping):
        prompt = palette_entry.get("prompt")
```

The UI root-level `"prompt"` string is not a mapping, so it is ignored by the planner.

`web/components/ip_design_workbench.py` readiness currently checks only `identity_lock`, while backend readiness checks `identity_lock + identity_anchors`.

## 5. Prioritization

### P0: Restore Left-Side Request Contract

Fix `web/components/content_ip_world_controls.py` so it matches the old left-side entry design:

- Render and return `generation_world_hint`.
- Support "generate from script" and "use IP default".
- Keep `ip_profile_world_hint` in frontend helper state only.
- Remove or stop forwarding `generation_notes`, `slot_preference_override`, and `presence_strength`.
- Make `tests/test_content_ip_world_controls.py` pass.

This is the first task because it is directly failing and because downstream already expects the correct formal field.

### P1: Align Small Data Shape Contracts

Fix:

- `color_palette` saved shape so planner can read `color_palette[*].prompt`.
- frontend readiness to match backend readiness.

These are narrow and verifiable.

### P2: Planner/SceneCast Enrichment

After P0 and P1 are stable, enrich `IPFrameAppearancePlanner` inputs and SceneCast consumption:

- Pass `presence_spectrum`, `adaptable_slots`, `minimal_traits`, `semantic_boundary`, and `negative_constraints` into LLM role selection.
- Let LLM output or override a usable `ip_presence_type` only when it passes validation.
- Decide whether SceneCast is preview-only, hard main-chain constraint, or optional per-frame override.

This is intentionally not first because it has a larger behavioral surface.

## 6. Non-Goals For This Iteration

This iteration does not:

- Move Streamlit homepage generation to FastAPI async tasks.
- Move I2V, digital human, or action transfer pipelines into backend tasks.
- Split `StandardPipeline`.
- Redesign the entire IP workbench UI.
- Change Z-Image provider behavior.
- Add new image-reference, LoRA, IPAdapter, or image-to-image flows.
- Rework SceneCast persistence.

Those are valuable platform steps, but they should not be mixed with the request-contract repair.

## 7. Acceptance Criteria

The iteration is complete when:

1. `tests/test_content_ip_world_controls.py` passes.
2. `tests/test_content_input_storyboard_ui.py::test_left_content_ip_payload_render_content_input` passes.
3. `tests/test_output_preview.py::test_build_single_generation_request_includes_generation_world_hint` passes.
4. `tests/test_video_api.py::test_build_video_generation_params_copies_generation_world_hint` passes.
5. `tests/test_image_prompt_composer.py::test_composer_passes_generation_world_hint_to_styled_batch` passes.
6. The formal generation request does not include `ip_profile_world_hint`, `generation_world_hint_source`, `generation_notes`, `slot_preference_override`, or `presence_strength`.
7. Frontend and backend readiness both consider `identity_lock` and `identity_anchors`.
8. Color rules saved from the workbench can be read by `_identity_color_terms()`.
9. The implementation does not write `generation_world_hint` back into AssetBible.

## 8. Recommended Execution Strategy

Use the execution plan in:

`docs/superpowers/plans/2026-05-24-ip-design-entry-contract-realignment-implementation.md`

Execute in small commits:

1. Restore `generation_world_hint` entry and tests.
2. Align i18n and helper-state behavior.
3. Fix readiness and color palette shape.
4. Run focused regression tests.

