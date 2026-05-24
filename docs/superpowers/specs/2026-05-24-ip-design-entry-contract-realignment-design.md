# Final Visual Prompt Source-Root Realignment Design

Date: 2026-05-24

## 1. Decision

This design supersedes the narrower entry-repair framing. The primary product is the final visual prompt sent to the image/video generation model through the media service and ComfyUI-compatible workflows.

The final prompt must be a complete, semantically coherent visual instruction. It must not be a mechanical sequence of blocks such as style prefix + scene block + IP block + world block. IP design, scene design, style prefix, world hint, storyboard planning, text policy, and negative constraints are upstream inputs that exist only to help produce that final prompt.

The implementation must solve the drift at its source, across the full generation path:

1. The generation-page IP/world entry exposes only the formal request contract.
2. `IPProfile` remains the single structured source of truth for durable IP facts.
3. Request-level `generation_world_hint` remains separate from asset-level `IPProfile.world_hint`.
4. The actorization planner receives the full IP fact surface it needs to place the IP naturally in each frame.
5. SceneCast influence has an explicit main-chain policy instead of an accidental preview-only ambiguity.
6. Style, scene, world, IP, text, and workflow constraints are fused into one natural final prompt per frame.
7. Final prompts receive useful scene language, while internal field names and control keys stay out of final user-facing prompt text.
8. Every prompt template that is sent to an LLM is stored as a Markdown document, with source metadata that can be audited.
9. Every LLM interaction records the exact rendered prompt, the exact returned response, the model/provider metadata, and the generation-stage chain that produced it.

The goal is not to repair only the currently failing tests. The goal is to remove the conditions that allowed prompt quality drift: duplicated field definitions, UI-only fields that reached request builders, frontend/backend readiness divergence, color fact shape divergence, incomplete planner inputs, unclear SceneCast authority, and final prompt assembly that can fall back to block concatenation.

### 1.1 Final Prompt Product Contract

For every generated frame that needs media, the chain must end with:

```python
media_params["prompt"] == storyboard_frame.image_prompt == prompt_plan.final_prompt
```

That prompt must:

- describe one coherent image, not multiple appended instructions.
- integrate style as visual language, not as a detached prefix.
- integrate IP as a subject/role inside the scene, not as an extra sticker or trailing sentence.
- integrate world and storyboard constraints as scene semantics.
- keep negative rules and text policies out of the positive prompt unless the workflow requires positive-only handling.
- avoid JSON keys, parameter names, hex color codes, section labels, and internal control words.

### 1.2 Reverse Design Logic

The design works backward from the final prompt:

1. ComfyUI or the media model receives one final positive prompt plus a separate negative prompt when the workflow supports one.
2. The final prompt is assembled from an LLM-produced base prompt plus structured style, storyboard, IP, world, text, and workflow constraints.
3. The LLM receives structured prompt contexts so it can write the base prompt as integrated scene language.
4. The upstream UI and workbench store structured facts that the LLM and assembly layer can understand.

This is the controlling architecture. IP/world contract repair is one necessary part of it, not the whole product goal.

### 1.3 Prompt Provenance Contract

Prompt quality is the core product surface. Therefore prompt source ownership must be explicit:

- Python code may load, validate, and render prompt templates, but it must not contain long-form prompt bodies.
- Each LLM prompt template must live in a Markdown file under the prompt-template registry.
- Each Markdown prompt file must declare `prompt_id`, `version`, `stage`, `purpose`, and `output_contract` in front matter.
- Builder functions may assemble structured variables and render the Markdown template. They must not recreate the template as a Python triple-quoted string.
- Prompt fragments such as style-prefix interpretation, IP role selection, world planning, storyboard planning, image prompt generation, video prompt generation, narration, title, and script generation are all governed by the same rule.
- A final visual prompt can be generated only from traceable upstream prompt-template sources and structured runtime inputs.

This means the implementation must migrate existing prompt bodies out of Python files and into Markdown templates. Keeping prompt bodies in code is not an acceptable intermediate endpoint because it prevents product-level prompt review.

### 1.4 LLM Interaction Trace Contract

Every interaction with an LLM must be inspectable after the run. A generated result without its prompt-and-response chain is incomplete.

For every LLM call, the system must persist:

- a run/task identifier and parent generation chain identifier.
- operation, stage, optional frame id, attempt number, and retry relationship.
- provider, model, temperature, max tokens, response mode, and output schema.
- Markdown template id, template version, and template file path when a template was used.
- the exact rendered prompt sent to the LLM.
- the exact response payload returned by the LLM, including parse errors or provider errors.
- parse/validation status, token usage, elapsed time, and error message when applicable.

The final media-generation prompt also needs a saved artifact per frame. The artifact must link `PromptPlan.final_prompt`, `StoryboardFrame.image_prompt`, and the media service `prompt` parameter so prompt review can work backward from the image/video result to every upstream LLM interaction.

## 2. Terminal Evidence

The app terminal was checked through Codex Desktop. No app terminal session was attached to this thread:

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

- `generation_world_hint` is missing from the left-side formal payload.
- `content_ip_profile_world_hint` is no longer synced or cleared.
- world-hint helper actions no longer import `safe_rerun`.
- i18n keys for `generation_world_hint`, helper actions, and warnings are missing.
- the fake UI lacks `container()` because current rendering now calls capability preview.

The downstream `generation_world_hint` path still passes targeted tests:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_content_input_storyboard_ui.py::test_left_content_ip_payload_render_content_input tests/test_output_preview.py::test_build_single_generation_request_includes_generation_world_hint tests/test_video_api.py::test_build_video_generation_params_copies_generation_world_hint tests/test_image_prompt_composer.py::test_composer_passes_generation_world_hint_to_styled_batch -q
```

Result:

```text
4 passed
```

Direct probes also confirmed two fact-source mismatches:

- `IPProfile(color_palette={"prompt": "white body"})` yields no planner color terms because `_identity_color_terms()` expects each palette value to be a mapping with its own `prompt`.
- frontend `_ip_profile_ready_for_generation({"identity_lock": [], "identity_anchors": ["blue tie"]})` returns `False`, while backend readiness accepts `identity_anchors`.

## 3. Historical Requirements Baseline

The old IP design requirement was not "make the IP appear everywhere." It was:

- The IP must serve the user-provided script.
- The IP should blend naturally into images instead of appearing as a sticker or unrelated inserted object.
- The IP may be a main subject, supporting role, passerby, partial presence, far-background presence, or absent.
- The IP should not dominate every image by default.
- The model should freely dress, equip, pose, emote, and interact with the IP within stable visual identity boundaries.

That led to the three-layer model:

1. Visual identity: stable facts the IP must not lose.
2. Role and behavior: what the IP does for this script or frame.
3. Frame presence: whether the IP is prominent, subtle, partial, background, symbolic, or absent.

Existing repository specs define these rules:

- `IPProfile` is the durable structured fact source.
- formal identity comes from `identity_lock`, `identity_anchors`, `semantic_boundary`, `negative_constraints`, `color_palette[*].prompt`, and `visible_text_whitelist`.
- `IPProfile.world_hint` is durable asset context.
- `generation_world_hint` is request-level context for the current script.
- `generation_world_hint` must not replace identity facts and must not write back into AssetBible.
- the left content IP/world module is the authoritative standard-generation entry for selected IP and request world hint.
- formal generation requests use `ip_enabled`, `ip_asset_bible_id`, `ip_profile_id`, and `generation_world_hint`.
- helper fields such as `ip_profile_world_hint` and `generation_world_hint_source` are UI/session or draft metadata.
- `IPFrameAppearancePlanner` should drive frame-level natural-language appearance descriptions.

## 4. Current Code Facts

### 4.0 Current Final Prompt Chain

The current generation path already has the right high-level shape:

1. `StandardPipeline` calls `ImagePromptComposer().compose()` with storyboard, style, IP, world, and text-rendering inputs.
2. `ImagePromptComposer` builds structured frame `prompt_contexts` from the storyboard plan.
3. `generate_styled_image_prompt_batch()` enriches those contexts with generation world profile, style profile, IP adaptation, text policy, and workflow capability data.
4. `generate_image_prompts()` asks the LLM to produce base visual prompts from the structured contexts.
5. `assemble_storyboard_prompt()` or `assemble_image_prompt()` produces `final_prompts`.
6. `StandardPipeline` writes each final prompt to `StoryboardFrame.image_prompt`.
7. `FrameProcessor._step_generate_media()` sends `frame.image_prompt` as `media_params["prompt"]` to the media service, which routes to ComfyUI-compatible workflows or other image/video providers.

So the target architecture is not a new parallel pipeline. The issue is that the existing path needs a stronger product contract: all upstream inputs must be semantically fused into the final prompt, and tests must fail when the chain degrades into plain block concatenation.

### 4.1 Entry Contract Drift

`web/components/content_ip_world_controls.py` currently emits:

```python
{
    "ip_enabled": True,
    "ip_asset_bible_id": "selected_asset_bible",
    "ip_profile_id": "selected_ip_profile",
    "generation_notes": "old UI notes",
    "slot_preference_override": "old slot preference",
    "presence_strength": "old presence strength",
}
```

The old `generation_notes`, `slot_preference_override`, and `presence_strength` fields are not formal generation fields. Keeping them in the entry module creates a false contract and lets execution appear successful while the downstream pipeline ignores the user's intent.

### 4.2 Downstream Request Path Exists

These files already support `generation_world_hint`:

- `api/schemas/video.py`
- `api/routers/video.py`
- `pixelle_video/models/video_generation_contract.py`
- `pixelle_video/pipelines/standard.py`
- `pixelle_video/services/content_world_planner.py`
- `pixelle_video/services/image_prompt_composer.py`
- `pixelle_video/utils/content_generators.py`

The downstream path is present, but it needs guard tests so future UI changes cannot reintroduce dead request fields.

### 4.3 Content Input Gives Left Entry Priority

`web/components/content_input.py` removes storyboard-level `generation_world_hint` before merging:

```python
storyboard_generation = dict(storyboard_generation)
storyboard_generation.pop("generation_world_hint", None)
payload = {**storyboard_generation, **content_ip_world}
```

That matches the old design: the left content IP/world module owns the request-level world hint.

### 4.4 Workbench Fact Shape Drift

`web/components/ip_design_workbench.py` saves color rules as a root-level `"prompt"` string:

```python
color_palette = {**ip_profile.get("color_palette", {}), "prompt": color_rules}
```

`pixelle_video/services/ip_usage_planner.py` reads palette values only when each entry is a mapping:

```python
for palette_entry in ip_profile.color_palette.values():
    if isinstance(palette_entry, Mapping):
        prompt = palette_entry.get("prompt")
```

The persisted workbench shape therefore bypasses planner identity terms.

The workbench readiness check also considers only `identity_lock`, while backend generation readiness uses `identity_lock + identity_anchors`.

### 4.5 Planner Actorization Input Drift

`pixelle_video/utils/content_generators.py` already calls:

```python
IPFrameAppearancePlanner(llm_client=llm_service).plan_batch(
    storyboard_plan=storyboard_plan,
    ip_profile=ip_profile,
    generation_world_profile=generation_world_profile,
)
```

But `IPFrameAppearancePlanner._llm_role_selection()` currently passes only:

```python
{
    "name": ip_profile.name,
    "identity_lock": list(ip_profile.identity_lock),
    "identity_anchors": list(ip_profile.identity_anchors),
    "visual_summary": ip_profile.visual_summary,
    "role_presets": list(ip_profile.role_presets),
}
```

That omits actorization facts such as `presence_spectrum`, `adaptable_slots`, `minimal_traits`, `semantic_boundary`, `negative_constraints`, `default_slot_preference`, `style_hint`, `world_hint`, and request-level generation world guidance.

### 4.6 SceneCast Authority Is Too Implicit

`IPUsagePlanner` already accepts `scene_casts_by_frame` and uses `ip_presence_type` or `presence_type`. Tests show SceneCast metadata can drive per-frame presence.

The missing design rule is not code reachability. The missing rule is authority: when SceneCast is present, it should be treated as a validated per-frame main-chain directive for IP presence, while invalid values are ignored and the deterministic planner continues.

### 4.7 Prompt Context Carries Flattened IP Signals

`_enrich_prompt_contexts_with_ip()` currently injects:

- `ip_scene_description`
- `ip_negative_constraints`
- `ip_image_text_plan`
- `style_context`

The full `ip_adaptation` is stored in the planning snapshot. For auditability and prompt planning continuity, frame contexts should also carry a structured `ip_adaptation` package for generation services that consume `prompt_contexts`. Prompt instructions already forbid leaking internal keys into final prompt text.

### 4.8 Prompt Template And Trace Risks

The repository already contains several long-form prompt bodies in Python:

- `pixelle_video/prompts/image_generation.py`
- `pixelle_video/prompts/video_generation.py`
- `pixelle_video/prompts/ip_role_selection.py`
- `pixelle_video/prompts/topic_narration.py`
- `pixelle_video/prompts/content_narration.py`
- `pixelle_video/prompts/title_generation.py`
- `pixelle_video/prompts/style_conversion.py`

Other prompt builders also assemble LLM instructions in code, including storyboard, style-resolution, prompt-prefix, content-world, and asset/script generation paths. `pixelle_video/prompts/script_templates/default.md` proves Markdown prompt storage already fits this codebase, but the pattern has not been generalized.

The repository also has useful LLM tracing primitives:

- `pixelle_video/models/llm_interaction_trace.py`
- `pixelle_video/services/llm_interaction_recorder.py`
- `pixelle_video/services/llm_service.py`
- `tests/test_llm_service_trace_capture.py`

The risk is that tracing is optional at the call boundary. `_record_llm_trace()` returns without recording when `trace_context` or `trace_recorder` is missing, and several business call sites call `llm_service(...)` without mandatory trace metadata. This means the system can still produce a final image/video while losing the exact LLM prompt/response chain that created it.

## 5. Source-Root Design

### 5.1 Formal Request Contract

Create a shared pure-Python contract module for content IP/world request fields:

- formal fields: `ip_enabled`, `ip_asset_bible_id`, `ip_profile_id`, `generation_world_hint`
- helper-only fields: `ip_profile_world_hint`, `generation_world_hint_source`, draft status keys
- removed legacy fields: `generation_notes`, `slot_preference_override`, `presence_strength`

The web entry module and final request builder should use the same field constants or helper function. No local ad hoc copies of the old legacy field list should remain in request-building code.

### 5.2 Left Entry UI Contract

`web/components/content_ip_world_controls.py` should:

- render IP selection through existing `render_ip_prompt_chain_controls()`.
- sync `ip_profile_world_hint` only into session helper state.
- render request-level `generation_world_hint`.
- support "use IP default" by copying asset world hint into the request-level field.
- support "generate from script" through `web.utils.content_api.generate_world_hint_draft`.
- return only the formal request payload.
- delete the old notes, slot preference, and strength controls from this module.

### 5.3 Asset Fact Contract

`web/components/ip_design_workbench.py` should persist color rules as planner-readable entries:

```python
{
    "rule_1": {"prompt": "white body"},
    "rule_2": {"prompt": "bright blue tie"},
}
```

When the UI accepts hex-like user input, hex values must be separated from prompt values:

```python
{
    "rule_1": {"hex": "#FFFFFF", "prompt": "white body"}
}
```

`IPProfile` already rejects hex colors inside prompt keys. That rule should remain. The workbench parser should clean prompt text before saving.

### 5.4 Shared Readiness Contract

Backend and frontend should share the same generation-readiness logic. `ip_generation_identity_terms()` should support both `IPProfile` objects and mapping payloads, then the workbench should call that helper instead of duplicating readiness rules.

### 5.5 Planner Actorization Contract

`IPFrameAppearancePlanner._llm_role_selection()` should receive the complete IP actorization source:

- `name`
- `identity_lock`
- `identity_anchors`
- `visual_summary`
- `minimal_traits`
- `semantic_boundary`
- `negative_constraints`
- `role_presets`
- `presence_spectrum`
- `adaptable_slots`
- `default_slot_preference`
- `style_hint`
- `world_hint`
- normalized `generation_world_profile`

Frame payloads should include:

- deterministic `presence_type`
- `presence_mode`
- `semantic_reason`
- `must_not_replace`
- `identity_anchors_visible`
- `identity_anchors_suppressed`
- SceneCast presence source when present

The LLM prompt should explicitly separate stable identity facts, adaptable styling/clothing/pose decisions, and frame presence decisions.

### 5.6 SceneCast Main-Chain Policy

SceneCast is a validated per-frame directive when it provides a valid `ip_presence_type` or `presence_type`.

Policy:

1. valid SceneCast presence wins for that frame.
2. invalid SceneCast presence is ignored with deterministic fallback.
3. SceneCast never overrides stable identity facts.
4. SceneCast may reduce, elevate, or suppress presence for a frame through the validated enum only.
5. planning snapshot records the resulting `ip_presence_type` per frame.

### 5.7 Prompt Context Audit Contract

Generation prompt contexts should include structured `ip_adaptation` for auditability:

```python
frame_context["ip_adaptation"] = package.to_dict()
```

Final prompt strings must not include internal keys such as:

- `generation_world_profile`
- `story_constraints`
- `ip_integration_guidance`
- `ip_adaptation`
- `ip_presence_type`
- `identity_anchors_visible`

The context may contain structured keys; final generated prompt text must not copy those key names.

### 5.8 Final Visual Prompt Assembly Contract

The assembly layer must treat upstream inputs as meaning, not as raw text chunks.

Allowed assembly:

- use a resolved style template that contains `{prompt}` exactly once.
- translate shot type, shot purpose, world elements, style core, and visual suffix into natural visual clauses.
- merge IP scene description into the scene sentence or paragraph.
- add text whitelist and workflow-specific positive-only constraints only after final prompt semantics are formed.
- sanitize the final string before it becomes `StoryboardFrame.image_prompt`.

Disallowed assembly:

- prefixing a raw style paragraph before every prompt when a structured style profile exists.
- appending `ip_scene_description` as a separate trailing sentence.
- emitting raw enum values such as `medium_shot`, `scene_integrated`, or `balanced_narrative`.
- copying JSON keys such as `generation_world_profile`, `identity_anchors_visible`, or `ip_adaptation`.
- treating `generation_world_hint` as permanent IP identity.

The implementation should add tests around `assemble_image_prompt()`, `assemble_storyboard_prompt()`, `generate_styled_image_prompt_batch()`, `build_prompt_plan_bundle()`, and `FrameProcessor._step_generate_media()` so the final prompt is proven to be the same artifact from assembly through ComfyUI handoff.

### 5.9 Markdown Prompt Template Contract

Create one prompt-template registry for all LLM prompt bodies.

Required template shape:

```markdown
---
prompt_id: image_generation
version: 2026-05-24-v1
stage: image_prompt_generation
purpose: Generate integrated per-frame visual prompts from structured storyboard context.
output_contract: ImagePromptBatchResponse
---
```

The body below the front matter contains the full prompt prose, starting with its role/instruction section and ending with the output contract rules.

The loader must:

- load templates only from the registered Markdown directory.
- parse and validate front matter before rendering.
- return both the rendered text and template metadata.
- reject unknown `prompt_id` values.
- reject unresolved template variables.
- keep all prompt-body prose in Markdown files.

Python files under `pixelle_video/prompts/` should become adapters: they prepare variables, call the Markdown renderer, and return either a `RenderedPrompt` object or a compatibility `.text` value. They should not own prompt language.

Static verification must fail when a Python prompt module reintroduces a long-form triple-quoted prompt constant.

### 5.10 Runtime LLM Trace Contract

The LLM gateway must stop treating tracing as optional for generation work.

Required behavior:

1. every production LLM call receives `LLMTraceContext` and `LLMInteractionRecorder`, or explicitly opts out in a test-only path.
2. missing trace metadata raises a clear error before the provider request is sent.
3. the raw request payload stores the exact rendered prompt and request parameters.
4. the raw response payload stores the exact provider response or error response.
5. trace metadata includes the Markdown template id/version/path when available.
6. retries create separate trace entries with attempt numbers and a shared parent chain id.
7. final visual prompts are persisted as per-frame artifacts after assembly and before media generation.
8. media generation logs reference the same final prompt artifact that was sent through `media_params["prompt"]`.

The trace is not just a debugging convenience. It is the product feedback loop for prompt optimization.

## 6. Required Implementation Scope

The implementation ships as one source-root cleanup:

1. add shared request contract constants and payload builder.
2. remove legacy content IP/world request controls and i18n keys.
3. restore request-level `generation_world_hint` UI and helper actions.
4. add request-builder tests plus ripgrep gates for removed legacy fields.
5. update workbench readiness to use shared backend logic.
6. update color-rule persistence to planner-readable prompt entries with hex separation.
7. enrich `IPFrameAppearancePlanner` LLM input with full actorization and world profile data.
8. lock SceneCast presence authority with tests.
9. carry structured `ip_adaptation` into prompt contexts.
10. add final visual prompt assembly tests so style, scene, world, and IP are semantically fused.
11. verify final prompts do not leak internal field names and are the exact prompts handed to media generation.
12. migrate every LLM prompt body from Python into Markdown prompt-template files.
13. add a prompt-template loader/registry with front-matter validation and unresolved-variable checks.
14. make LLM tracing mandatory for generation call sites and persist request/response payloads for each interaction.
15. persist per-frame final prompt artifacts that connect prompt planning to media generation.

## 7. Out Of Scope

This design keeps unrelated platform work outside the change:

- moving Streamlit homepage generation to FastAPI background tasks.
- moving I2V, digital human, or action-transfer pipelines into backend tasks.
- splitting `StandardPipeline`.
- changing Z-Image provider behavior.
- adding new LoRA, IPAdapter, image-reference, or image-to-image flows.

These items are separate platform projects. Planner actorization and SceneCast policy are inside this design because they are part of the IP source chain.

## 8. Acceptance Criteria

The work is complete when all of the following are true:

1. `tests/test_content_ip_world_controls.py` passes.
2. `tests/test_content_input_storyboard_ui.py::test_left_content_ip_payload_render_content_input` passes.
3. `tests/test_output_preview.py::test_build_single_generation_request_includes_generation_world_hint` passes.
4. `tests/test_video_api.py::test_build_video_generation_params_copies_generation_world_hint` passes.
5. `tests/test_image_prompt_composer.py::test_composer_passes_generation_world_hint_to_styled_batch` passes.
6. a contract test proves `generation_notes`, `slot_preference_override`, and `presence_strength` are dropped before formal request submission.
7. `rg -n "generation_notes|slot_preference_override|presence_strength" web/components/content_ip_world_controls.py web/i18n/locales/en_US.json web/i18n/locales/zh_CN.json` returns no matches.
8. frontend and backend readiness both accept `identity_anchors` when `identity_lock` is empty.
9. workbench color rules save to `color_palette[*].prompt`, and hex values are excluded from prompt fields.
10. `_identity_color_terms()` reads color rules saved by the workbench.
11. `IPFrameAppearancePlanner._llm_role_selection()` prompt input includes actorization fields and generation world profile data.
12. SceneCast metadata with valid `ip_presence_type` controls per-frame presence in the main generation path.
13. invalid SceneCast presence values fall back without breaking generation.
14. prompt contexts include structured `ip_adaptation` when IP prompt chain is enabled.
15. final prompt assembly tests prove resolved style, storyboard meaning, world constraints, and IP appearance are fused into one natural visual instruction.
16. `PromptPlan.final_prompt`, `StoryboardFrame.image_prompt`, and the media service `prompt` parameter are the same final prompt artifact.
17. final generated prompt strings contain scene language but no internal key names or hex color codes.
18. every LLM prompt template used by generation code exists as a Markdown document with valid front matter.
19. `rg -n "PROMPT\\s*=\\s*\"\"\"|_PROMPT\\s*=\\s*\"\"\"" pixelle_video/prompts` returns no prompt-body constants.
20. tests prove prompt rendering records template id, version, file path, rendered text, and output contract.
21. tests prove each production `llm_service(...)` generation call records request payload, response payload, status, operation, stage, and attempt metadata.
22. every completed generation has inspectable prompt-trace artifacts showing the LLM interaction count and the exact final prompt sent to media generation.

## 9. Review Passes Applied

### Review 1: Architecture And Source Ownership

Finding: the earlier document framed planner and SceneCast work as a deferred enhancement. It also did not make the final prompt the top-level product contract. That left the root cause open because the IP can still fail to blend naturally after the entry tests pass.

Correction: final visual prompt assembly, planner actorization input, SceneCast authority, and prompt-context auditability are now required scope.

### Review 2: Execution And Verification

Finding: the earlier plan contained non-required tests and weak wording for dead fields. It also tested final prompt cleanup but not final prompt semantic fusion or media handoff. That permits leftover UI, i18n, and prompt-quality debt.

Correction: the execution plan now requires deletion of legacy controls and i18n keys, shared contract tests, ripgrep gates, planner input tests, SceneCast tests, final prompt assembly tests, media handoff tests, and final prompt leak tests.

### Current Review 1: Prompt Source Ownership

Finding: the document described the final prompt as the product, but it did not yet make Markdown prompt templates the required source of truth. That left room for future work to keep hardcoding prompt prose inside Python.

Correction: this document now requires Markdown prompt templates, front-matter metadata, a renderer/registry, and a static gate that forbids long-form prompt constants in prompt modules.

### Current Review 2: Prompt Process Traceability

Finding: the document relied on existing tracing primitives but did not require every generation LLM call to record its exact prompt and exact response. Optional tracing still leaves the team unable to diagnose which prompt stage caused a bad image.

Correction: this document now requires mandatory trace metadata, raw request/response persistence, attempt counts, prompt-template provenance, final-prompt artifacts, and verification that the media handoff uses the same saved final prompt.

## 10. Execution Document

Use:

`docs/superpowers/plans/2026-05-24-ip-design-entry-contract-realignment-implementation.md`
