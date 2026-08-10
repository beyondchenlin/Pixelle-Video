# V4.5.1 Series Visual Signature Source Replacement

This migration ends with one production runtime contract, but the replacement is staged. The current production executor must not be physically removed before the V4.5 candidate path is complete, shadow-observed, and explicitly cut over.

## Target architecture

The final production source path is:

```text
SeriesVisualSignatureRequest
-> VisualSignatureProfileSnapshot
-> SeriesVisualSignatureContract
-> FinalVisualPromptContractV45
-> ArticleConcretizationPromptCompiler
-> final prompt gate
-> ZImagePromptBundle
-> provider_z_image_adapter
```

`provider_z_image_adapter` is a mechanical projection boundary. It must not reinterpret business constraints or repair prompts.

## Migration stages

### Stage 1: remove duplicate request facts without removing the production executor

- `SeriesVisualSignatureRequest` has one canonical runtime definition.
- Legacy/product controls may remain only as compatibility adapters that produce the canonical request.
- Pipeline-version facts also have one source of truth. `v4_expression` remains a supported compatibility value and `v4_2_identity_contract` remains the canonical default, but both are defined and validated by the canonical request model.
- `pipeline_version` remains a real dataclass field so existing legacy routing based on `dataclasses.replace(...)` continues to work during migration.
- Serialization must keep canonical normalized values authoritative; compatibility fields must not overwrite them.
- Profile resolution must fail explicitly. A profile ID must never be fabricated into a display name or identity trait.

### Stage 2: make the V4.5 candidate path safe to switch

The candidate path must satisfy all of these invariants before shadow observation:

- contract object -> dict -> compiler round trips keep the visual signature enabled and intact;
- required source subjects are present in the model-visible positive prompt;
- required subjects and identity traits are protected prompt sections and are never silently truncated;
- if protected semantics exceed the provider prompt budget, compilation fails explicitly;
- automatic role selection uses one context-aware resolver rather than a hard-coded role;
- final prompt validation checks required subjects, identity name, identity traits, negative protections, and visible-text policy before provider projection;
- protected-term matching uses boundary-safe matching for ASCII terms so a subject such as `AI` cannot be falsely matched inside an unrelated word such as `chair`;
- provider projection remains mechanical.

### Stage 3: same-frame shadow comparison

The production prompt remains authoritative while the V4.5 candidate path runs beside it at prompt/contract level.

The shadow path is observational only:

- it must never replace or mutate the production prompt;
- unexpected shadow exceptions are converted into failed shadow observations and must not interrupt production generation;
- it does not issue a second image-generation request by default, so observation does not double provider cost;
- production and candidate prompts are recorded per frame;
- required-subject and identity presence are recorded separately for production and candidate prompts using the same protected-term matcher as the final gate;
- candidate final-gate and provider-projection results are recorded;
- missing same-frame candidate coverage is a cutover blocker;
- optional production/candidate render-result fields are reserved for an explicit later A/B media experiment.

Shadow frame input has two supported sources:

1. If an `ArticleConcretizationPlan` exists for the frame, the candidate consumes the real article anchor, required subjects, diagram grammar, render contract, visible-text policy, and role context.
2. Otherwise the candidate consumes the same-frame storyboard/prompt context. It reuses the current production base scene text so the shadow experiment isolates visual-signature source replacement from unrelated base-scene generation changes. Required subjects come from storyboard subjects plus `BaseVisualBrief.main_subjects` when available. The candidate uses `plain_scene` / `preserve_base` semantics so it preserves the existing action, subject hierarchy, camera, lighting, and visual style instead of forcing an explanatory-diagram grammar.

A non-article frame with no structured subject facts is `blocked`. An empty subject list must never be interpreted as proof that subject preservation passed.

The strict cutover qualification is:

```text
shadow coverage rate == 100%
candidate pass rate == 100%
failed candidate frames == 0
global shadow errors == 0
```

This qualification means "eligible for an explicit cutover decision". It does not automatically switch production traffic.

The runtime snapshot key is:

```text
series_visual_signature_shadow_comparison
```

Each frame record includes `candidate_source_kind` so deployed observations can distinguish article-concretization candidates from ordinary storyboard-frame candidates.

### Stage 4: explicit production cutover

After representative deployed traffic demonstrates stable shadow qualification, submit a separate cutover change that routes the default production path through the canonical V4.5 chain.

The cutover change must preserve rollback ability and must not delete the old executor in the same step.

### Stage 5: physical source deletion

Only after the new production path is stable may old execution services, duplicate article-level role/contract types, compatibility imports, and obsolete UI controls be physically removed.

Do not recreate deleted runtime types as compatibility wrappers after this stage.

## What may remain during staged migration

The current `VisualPromptPlanningService` and visual-anchor execution path may remain while they still carry production traffic.

Article concretization may also retain frame-level intermediate role/contract objects until the canonical V4.5 contract owns the production provider boundary. Those intermediate types must not become a second provider-facing fact source.

Structured identity assets may remain, but `VisualSignatureProfileSnapshot` itself contains identity facts only:

```text
series_visual_signature_profile_id
display_name
identity_traits
style_safe_traits
forbidden_traits
source_asset_ids
```

Profiles must not carry paragraph prompts, provider prompts, scene prompts, or deprecated runtime fields.

## Architecture and CI gates

The repository must enforce:

- exactly one production definition of `SeriesVisualSignatureRequest`;
- one canonical definition of supported series-visual-signature pipeline versions;
- legacy `pipeline_version` dataclass replacement compatibility until the legacy route is physically removed;
- no deprecated IP/Visual Role runtime imports after their deletion stage;
- object/dict prompt-contract round-trip coverage;
- unresolved or mismatched profile failure coverage;
- full required-subject preservation coverage;
- boundary-safe protected-term matching coverage;
- context-aware automatic role coverage;
- final prompt gate coverage;
- provider adapter mechanical-projection coverage;
- shadow comparison coverage for article frames and ordinary storyboard frames;
- shadow coverage for missing frame context, missing subject facts, profile failure, over-budget protected semantics, and candidate failure;
- prompt composer coverage proving shadow observation cannot replace production prompts and proving base-visual subject facts reach the non-article shadow path.

Run the dedicated workflow or equivalent commands:

```powershell
python -m pytest -q tests/architecture/test_no_legacy_ip_runtime.py tests/models/test_series_visual_signature.py tests/models/test_series_visual_signature_request.py tests/services/test_series_visual_signature_*.py tests/services/test_article_concretization_prompt_compiler.py tests/services/test_provider_z_image_adapter.py
python -m ruff check pixelle_video/models/series_visual_signature.py pixelle_video/models/series_visual_signature_request.py pixelle_video/services/series_visual_signature_*.py pixelle_video/services/article_concretization_prompt_compiler.py pixelle_video/services/provider_z_image_adapter.py pixelle_video/services/image_prompt_composer.py tests/architecture/test_no_legacy_ip_runtime.py tests/models/test_series_visual_signature.py tests/models/test_series_visual_signature_request.py tests/services/test_series_visual_signature_*.py tests/services/test_article_concretization_prompt_compiler.py tests/services/test_provider_z_image_adapter.py
```

The dedicated Visual Signature CI workflow includes this migration document in its path trigger so documentation-only changes to the cutover contract are revalidated against the executable tests.

The dedicated Visual Signature CI workflow should be configured as a required check on `dev` in repository branch-protection settings once repository policy allows it.
