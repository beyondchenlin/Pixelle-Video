# V4.5.1 Series Visual Signature Source Replacement

This is a breaking cleanup patch. It is designed for source-level replacement, not suppressions.

## Verdict

The old IP / Visual Role runtime must leave the production source path. Recurring characters, mascot-like identities, dogs, Xiaohei-like figures, and brand characters must use one runtime contract only:

```text
SeriesVisualSignatureRequest
-> VisualSignatureProfileSnapshot
-> SeriesVisualSignatureContract
-> FinalVisualPromptContractV45
-> ArticleConcretizationPromptCompiler
-> ZImagePromptBundle
-> provider_z_image_adapter
```

## What must be physically removed

Run these commands in the real repository after applying the patch. These are source removals, not suppressions:

```powershell
git rm -- pixelle_video/models/visual_role_request.py
git rm -- pixelle_video/models/visual_role_strategy.py
git rm -- pixelle_video/services/visual_anchor_integration_planner.py
git rm -- pixelle_video/services/visual_role_prompt_projector.py
git rm -- pixelle_video/services/visual_role_scene_planner.py
git rm -- pixelle_video/services/visual_role_prompt_critic.py
git rm -- pixelle_video/services/visual_role_repair_loop.py
git rm -- web/components/ip_prompt_chain_controls.py
git rm -- web/components/content_ip_world_controls.py
git rm -- web/components/style_config_ip_controls.py
```

If a path does not exist in your branch, leave it absent. Do not recreate compatibility wrappers.

## What may remain

Structured identity assets may remain after migration, but only as `VisualSignatureProfileSnapshot` fields:

```text
series_visual_signature_profile_id
display_name
identity_traits
style_safe_traits
forbidden_traits
```

Profiles must not carry paragraph prompts, provider prompts, scene prompts, or old runtime fields.

## Required integration edits in your local tree

This patch adds the new infrastructure and failing architecture gates. Because this environment does not include your complete local source tree, the existing production call sites must be edited in your worktree as follows:

1. API schema accepts only `series_visual_signature_*` fields and rejects old keys with `extra="forbid"`.
2. Web UI removes old IP/Visual Role controls and emits only `series_visual_signature_*` fields.
3. Generation contract stores `SeriesVisualSignatureRequest`, not old role/IP fields.
4. Planning services build `SeriesVisualSignatureContract` through `SeriesVisualSignaturePlanningService` for article and non-article paths.
5. Final prompt contract serializes `series_visual_signature`, not old role metadata.
6. Provider code accepts only `ZImagePromptBundle` and never reads raw request params.
7. Trace manifests prove no old runtime files or fields participated.

## Verification

```powershell
python -m pytest tests/architecture/test_no_legacy_ip_runtime.py -q
python -m pytest tests/models/test_series_visual_signature.py -q
python -m pytest tests/services/test_series_visual_signature_contract_builder.py tests/services/test_series_visual_signature_planning_service.py -q
python -m pytest tests/services/test_visible_text_prompt_rewriter.py tests/services/test_article_concretization_prompt_compiler.py tests/services/test_provider_z_image_adapter.py -q
python -m ruff check pixelle_video/architecture pixelle_video/models/series_visual_signature.py pixelle_video/models/final_visual_prompt_contract_v45.py pixelle_video/models/z_image_prompt_bundle.py pixelle_video/services/series_visual_signature_contract_builder.py pixelle_video/services/series_visual_signature_planning_service.py pixelle_video/services/visible_text_prompt_rewriter.py pixelle_video/services/article_concretization_prompt_compiler.py pixelle_video/services/provider_z_image_adapter.py tests/architecture/test_no_legacy_ip_runtime.py tests/models/test_series_visual_signature.py tests/services/test_series_visual_signature_contract_builder.py tests/services/test_series_visual_signature_planning_service.py tests/services/test_visible_text_prompt_rewriter.py tests/services/test_article_concretization_prompt_compiler.py tests/services/test_provider_z_image_adapter.py
```

Do not use `git add .`. Stage explicit paths only.
