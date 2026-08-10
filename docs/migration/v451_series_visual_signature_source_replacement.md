# V4.5.1 Series Visual Signature Source Replacement

## Verdict

This migration is a source replacement, not a shadow rollout.

The former same-frame shadow design was removed because its candidate path reused a production prompt that had already passed through the legacy signature path. That design could compare two prompt representations, but it could not prove that V4.5 independently owned recurring visual identity. Keeping it would preserve two execution semantics and create a false cutover signal.

The production architecture in this PR therefore follows one rule:

> Content planning is signature-free. Recurring visual identity may enter only at the canonical V4.5 final projection boundary.

## Canonical production path

```text
Article / Storyboard
-> VisualStoryEngine                     # content-only route selection
-> FrameVisualPlanBatchService           # content-only frame planning
-> VisualPromptComposer
     -> signature-free base prompt
     -> VisualSignatureProfileSnapshot   # explicit identity facts only
     -> canonical role resolver
     -> SeriesVisualSignatureContract
     -> FinalVisualPromptContractV45
     -> FinalVisualPromptCompiler
     -> final prompt gate
     -> provider/media adapter
```

`provider_z_image_adapter` and other provider/media adapters are mechanical boundaries. They must not repair prompts, reinterpret business constraints, select roles, or invent identity facts.

## Ownership rules

### Request ownership

`SeriesVisualSignatureRequest` has exactly one runtime definition in `pixelle_video.models.series_visual_signature`.

The historical `series_visual_signature_request.py` module may re-export or adapt the canonical type for protocol compatibility, but it must not define a second request class or version registry.

Canonical request state always wins over compatibility fields during serialization and projection.

### Profile ownership

`VisualSignatureProfileSnapshot` is the only runtime identity snapshot used by final projection.

A profile snapshot may contain only explicit identity facts:

```text
profile_id
display_name
identity_traits
style_safe_traits
forbidden_traits
source_asset_ids
```

Identity may never be fabricated from profile id, display name, world hint, free-form prose, or missing asset data.

Identity traits are treated as untrusted data:

- length is bounded;
- instruction-like text is rejected;
- multiline/instruction-shaped traits are rejected;
- validation errors never echo the raw rejected trait;
- all required identity traits must survive into the final prompt and pass the final gate.

### Role ownership

Only the canonical V4.5 role resolver may decide the recurring visual-signature role.

Article Concretization no longer owns a second role decision center. Historical article role/profile/strategy inputs are compatibility diagnostics only and must resolve to `NONE` at the article boundary.

`models/article_concretization.py` re-exports the canonical role/contract types and does not define article-local duplicates.

### Content-route ownership

Visual Story is content-only.

`VisualRouteScores.computed_final()` is the single route-ranking authority. Its score is derived only from:

```text
content_fit
memorability
channel_consistency
production_reliability
risk
```

Historical `ip_compatibility` and model-supplied `final` values may still deserialize for protocol compatibility, but neither may influence route ranking. The service must not define a second route-score formula.

## Compatibility boundary

`VisualPromptComposer` is the canonical media-neutral core service. It accepts:

- canonical `SeriesVisualSignatureRequest`;
- optional canonical `VisualSignatureProfileSnapshot`;
- the resolved `IPProfile` asset source used to build a snapshot when required.

It does **not** accept historical expression/structure/participation/mode/fallback controls.

`ImagePromptComposer` is a bounded compatibility adapter. Historical callers may still pass the old fields to that adapter; it normalizes them once into the canonical request/profile snapshot and delegates to `VisualPromptComposer`.

If a canonical request and historical controls are both supplied, the canonical request is authoritative. Historical controls cannot overwrite it.

The adapter contains no prompt-generation or projection implementation.

## Signature-free base generation

Before canonical projection, `VisualPromptComposer` hard-disables all legacy recurring-IP / visual-signature inputs sent to the lower base generator.

Visual Story context is whitelist-projected. Only content route facts, content frame facts, and reference-image facts may reach the base prompt. Compatibility-only IP fields and active IP fusion plans are excluded.

This prevents a hidden double application in which recurring identity appears in the base scene and is injected again by V4.5.

## Article Concretization contract

Article Concretization owns:

- cognitive anchor;
- explanation grammar;
- diagram layout;
- visible-text policy;
- render style;
- article required subjects and evidence.

It does not own recurring identity.

`ArticleConcretizationPlanner` may retain historical identity parameters in its call signature only while old callers exist, but those parameters are non-operative. Every article plan carries the canonical disabled `SeriesVisualSignatureContract` until the final projection stage creates the active contract.

## Required-subject invariants

Every projected frame must have structured required subjects.

Sources are merged from:

1. Article Concretization required subjects when present;
2. base visual brief subjects;
3. storyboard primary/secondary subjects;
4. explicit frame required subjects.

An empty subject set is an error. It must never be interpreted as proof that subject preservation passed.

Protected-term matching is boundary-safe for short ASCII tokens so a subject such as `AI` cannot be falsely matched inside an unrelated word such as `chair`.

Required subjects and required identity traits are protected final-prompt semantics. They are never silently truncated. If the protected semantics themselves exceed the provider budget, compilation fails closed.

## Projection observability contract

The old shadow snapshot is deleted. There is no `series_visual_signature_shadow_comparison` runtime fact source.

The canonical projection emits a bounded audit record under:

```text
series_visual_signature_projection_audit
```

The audit schema is `series_visual_signature_projection_audit.v3`. Version 3 makes observation coverage and successful projection separate metrics so a failed-but-observed frame cannot be confused with an unattempted frame.

### Success denominator

Every successful or failed batch audit records:

```text
expected_frame_count
attempted_frame_count
projected_frame_count
unique_frame_count
duplicate_frame_count
failed_frame_count
not_attempted_frame_count
coverage_rate
projection_success_rate
all_frames_passed
```

The rates have distinct meanings:

```text
coverage_rate            = attempted_frame_count / expected_frame_count
projection_success_rate  = projected_frame_count / expected_frame_count
```

`coverage_rate` answers whether expected production frames reached the canonical projection attempt. `projection_success_rate` answers whether expected frames completed projection successfully. A frame that was attempted and failed therefore contributes to coverage but not projection success.

A successful production batch is publishable only when:

```text
attempted == expected
projected == expected
unique == expected
duplicate == 0
failed == 0
not_attempted == 0
coverage_rate == 1.0
projection_success_rate == 1.0
```

Duplicate frame ids are rejected before projection.

### Failure denominator

A frame projection failure raises `SeriesVisualSignatureProjectionError` with a bounded audit payload containing:

- expected/attempted/projected/failed/not-attempted counts;
- observation coverage and projection success rates;
- failed frame id/index;
- stable reason code;
- exception type.

The failure audit does not contain the raw exception message or protected prompt data. Remaining frames are explicitly counted as not attempted.

The production method remains fail closed: a partial batch is never returned as a successful projection.

## Privacy and retention policy

Projection observability is not a second prompt store and does not own a second storage lifecycle.

The audit policy is:

```text
payload_class                  = bounded_hash_count_only
retention_owner                = parent_planning_snapshot
retention_mode                 = inherit_parent_planning_snapshot_atomically
independent_retention_allowed  = false
independent_cleanup_allowed    = false
raw_prompt_retention           = forbidden
raw_subject_retention          = forbidden
raw_identity_trait_retention   = forbidden
raw_request_hint_retention     = forbidden
```

Projection audit may store:

- prompt character counts;
- SHA-256 fingerprints;
- role;
- subject/trait counts;
- gate state;
- operational frame/contract ids;
- bounded failure reason codes.

It must not store raw positive/negative prompts, raw subjects, raw identity traits, user hints, or world hints.

`VisualPromptComposer` therefore stores only a canonical request audit summary and a profile reference/count summary. It does not copy the full canonical request or full profile snapshot into planning observability.

The projection audit is embedded planning metadata. Its retention is inherited atomically from the parent planning snapshot: it cannot outlive the parent artifact, cannot receive an independent TTL, and cannot be independently renewed or cleaned up. This avoids creating a visual-signature-specific retention database, cleanup scheduler, or orphaned audit lifecycle.

Because no additional raw prompt/identity corpus is created, retention risk is bounded by the existing parent planning artifact lifecycle.

## Deterministic runtime budget

Projection correctness must not depend on wall-clock latency because host load is nondeterministic.

The canonical projection instead enforces deterministic complexity limits:

```text
max frames per batch             = 512
max base prompt chars/frame      = 20,000
max negative prompt chars/frame  = 12,000
max required subjects/frame      = 64
max required subject chars       = 256
max identity traits              = 32
max projection audit bytes       = 512 KiB
```

The limits are validated before or during projection. Over-budget inputs fail explicitly; the service never silently drops protected semantics to remain inside the budget.

These defaults may be revised only together with tests and the migration contract.

## Migration state

Current source state after this PR:

```text
production identity owner        = canonical V4.5 projection
legacy prompt runtime allowed    = no
article signature runtime        = disabled/non-operative compatibility only
visual-story signature runtime   = disabled/non-operative compatibility only
legacy input adapter             = allowed at ImagePromptComposer boundary only
raw projection observability     = forbidden
shadow runtime                   = removed
```

The compatibility adapter is a protocol boundary, not a second runtime. It may be physically removed only after supported external/first-party callers no longer send historical controls. Until then architecture tests must prove it cannot execute prompt generation or projection itself.

## Physically removed runtime

The source-replacement work deletes or prevents revival of:

- legacy shadow comparison runtime and tests;
- old IP route-compatibility prompt template;
- old style-harmonization prompt template;
- old frame-IP-fusion prompt templates;
- Visual Story IP model prompt renderers;
- Article Concretization automatic visual-signature role resolver;
- article-local duplicate visual-signature role/contract classes;
- active recurring-IP planning in Visual Story content routes/frame plans.

## Architecture gates

Executable architecture tests enforce:

- one canonical request/version source;
- Article Concretization cannot define a second visual-signature role/contract;
- Article Concretization cannot resolve active visual-signature roles;
- shared route scoring cannot read external `final` or `ip_compatibility`;
- Visual Story cannot define a second content-score formula;
- `VisualPromptComposer.compose()` cannot regain historical signature controls;
- `ImagePromptComposer` remains an adapter with no base-prompt or projection implementation;
- deleted legacy templates remain absent;
- projection observability declares raw prompt/subject/identity/request-hint retention forbidden;
- projection observability inherits the parent planning-snapshot lifecycle and cannot own independent retention or cleanup;
- final prompt gate, protected terms, provider projection, profile security, route/frame content-only behavior and article no-role behavior remain covered by tests.

## CI contract

`.github/workflows/visual-signature-ci.yml` must compile, test and lint the canonical models/services, compatibility adapter, architecture gates and source-replacement tests.

The workflow is intentionally not gated by a manually maintained `paths` list for changes entering `dev` or `main`; repository-wide runtime architecture scanners must always have an opportunity to run when those branches are affected.

Repository policy should make Visual Signature CI a required `dev` branch check when branch-protection settings permit it.

## Done definition

This source replacement is complete only when the final PR head satisfies all of the following:

- shared route score ignores external `final` and IP compatibility;
- old Article Concretization role tests are migrated to the new ownership boundary;
- article-local duplicate role/contract definitions are gone;
- canonical core composer has no historical signature controls;
- compatibility adapter is the only historical input normalization boundary;
- projection audit has explicit success/failure denominators;
- projection audit separates observation coverage from successful projection rate;
- projection observability retains no raw prompt/subject/identity/request-hint text;
- projection observability inherits the parent planning-snapshot lifecycle atomically and cannot create independent retention/cleanup;
- deterministic projection budgets are enforced;
- architecture gates pass;
- Visual Signature CI passes on the final head;
- Reference Image CI passes on the final head;
- PR is mergeable and has no unresolved blocking review thread.

Do not call the migration complete before the final-head checks satisfy this list.
