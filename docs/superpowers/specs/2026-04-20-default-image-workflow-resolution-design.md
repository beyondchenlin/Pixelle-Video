# Default Image Workflow Resolution Design

## Goal

Make `selfhost/image_z_image_turbo.json` the product-wide default image workflow for illustration generation, using a single runtime source of truth that works consistently across:

- new installs
- existing local `config.yaml` files that still contain `null` or empty defaults
- the Web UI workflow selector
- service-level workflow resolution when callers omit `workflow`
- repository docs and example configuration

The design must preserve one important rule: a user-saved workflow preference still wins over the built-in default.

## Problem Summary

The current default behavior is fragmented:

- The Web UI in `web/components/style_config.py` falls back to index `0`, which effectively means "first item after sorting", not "product default".
- `config.example.yaml` and the config reference docs still describe `runninghub/image_flux.json` as the default image workflow.
- `pixelle_video/config/schema.py` leaves `comfyui.image.default_workflow` as `None`, so schema defaults do not express the intended product default.
- Existing local `config.yaml` files may explicitly store `default_workflow: null`, which means simply changing schema defaults is not enough.
- `ComfyBaseService._get_default_workflow()` treats missing config as an error instead of resolving through a product-level fallback.

Because these rules live in different layers, changing only one location creates drift and future regressions.

## Approved Approach

Introduce a centralized workflow-default resolution layer in the config/service boundary and make all callers use it.

## 1. Add a Built-In Default Catalog

Create a small, explicit mapping for product defaults, for example:

- image: `selfhost/image_z_image_turbo.json`
- video: `runninghub/video_wan2.1_fusionx.json`
- tts: `selfhost/tts_edge.json`

This catalog represents product defaults, not user preferences.

It should live in a reusable config-oriented module instead of inside Streamlit UI code.

## 2. Add an Effective Workflow Resolver

Add a pure resolver function or config-manager helper that computes the effective default workflow from:

- workflow domain: `image`, `video`, or `tts`
- available workflow keys
- persisted config value
- built-in product default

The resolver should operate on a normalized configured-workflow input rather than assuming every domain stores `default_workflow` at the same nesting level.

Important compatibility note:

- `image` and `video` currently store `default_workflow` directly under their domain config
- `tts` currently stores its ComfyUI workflow under `comfyui.tts.comfyui.default_workflow`

Either the caller must pass the normalized configured value into the resolver, or a dedicated config-access helper must normalize these shapes first.

Recommended precedence:

1. Explicit workflow argument provided by the caller
2. Persisted user config default, if non-empty and still available
3. Built-in product default, if available
4. Deterministic first available compatible workflow
5. No result only when there are no compatible workflows at all

Normalization rules:

- Treat `None`, empty string, and whitespace-only strings as "unset".
- Treat a configured workflow that no longer exists as invalid and fall through to the next level.
- Distinguish between "invalid configured default" and "invalid explicit runtime argument":
  - invalid configured default should gracefully fall back
  - invalid explicit runtime workflow should still raise an error

## 3. Make the Web UI Consume the Resolver

Replace the current `default_workflow_index = 0` behavior in `web/components/style_config.py`.

For image templates, the selector should compute the effective default through the shared resolver, then derive the selectbox index from that resolved key.

Result:

- fresh state shows `image_z_image_turbo.json - Selfhost`
- saved user preference still wins
- stale config values no longer force the UI into a broken or misleading default

## 4. Make Service-Level Resolution Consume the Same Logic

Update service-side default workflow resolution so runtime behavior matches the Web UI.

This is especially important because source-of-truth behavior should not depend on whether a workflow is chosen from the UI or omitted in a direct service call.

Implementation shape:

- keep `ComfyBaseService` responsible for explicit workflow validation
- move default selection into a shared resolver that `ComfyBaseService` calls
- add media-type-aware resolution for `MediaService`, so image and video defaults can resolve independently instead of both collapsing onto the `"image"` config branch

For `MediaService`, the effective default should be resolved from the requested `media_type`:

- `media_type="image"` -> image default
- `media_type="video"` -> video default

This avoids baking a new bug into the architecture while fixing the image default.

## 5. Align Config Schema and Example Config

Update the repository defaults to express the same intended default:

- `pixelle_video/config/schema.py`
- `config.example.yaml`

These values should describe the product default for new users, but they must not become a second runtime source of truth.

Runtime selection should still flow through the shared resolver and built-in default catalog described above.

Practical rule:

- the resolver catalog is authoritative for runtime fallback behavior
- schema defaults and `config.example.yaml` are alignment surfaces for new-user bootstrap and documentation
- if the codebase can avoid duplicating literals by importing shared constants safely, prefer that; otherwise, treat mirrored values as documentation that must stay in sync with the catalog

## 6. Align Documentation

Update docs that describe the default image workflow so the repo no longer documents an outdated default:

- `docs/en/reference/config-schema.md`
- `docs/zh/reference/config-schema.md`
- `README.md`
- any README or user-guide text that explicitly claims `image_flux.json` is the default image workflow

The documentation should reflect both:

- the new default value
- the precedence rule that saved user configuration overrides the built-in default

## 7. Do Not Silently Rewrite User Config on Read

The resolver should interpret missing or invalid config values without mutating `config.yaml` during reads.

Rationale:

- reading config should remain side-effect free
- local user environments may intentionally keep custom or partially filled configs
- the UI can display the effective default without silently changing persisted files

Persisted config should only change when the user explicitly saves settings.

## Precedence Table

| Scenario | Effective Result |
| --- | --- |
| User saved `selfhost/image_z_image.json` and it exists | Use saved value |
| User saved `runninghub/image_flux.json` and it exists | Use saved value |
| User config is `null` or empty | Use built-in image default |
| User config points to a missing workflow | Fall back to built-in image default if available |
| Built-in image default is missing from available workflows | Fall back to first compatible available workflow |
| No compatible workflows exist | UI shows no workflows; service raises clear error |

## Error Handling

The new resolver should be resilient for defaults and strict for explicit runtime choices.

Expected behavior:

- Missing or stale configured defaults should not break the UI.
- Missing built-in default should emit a warning and fall back deterministically.
- Explicitly requested nonexistent workflow keys should still fail fast with a clear error.
- If no compatible workflows exist, the error should say which domain was being resolved and list the available keys when possible.

## Testing Strategy

Add regression tests around the resolver instead of relying on Streamlit widget behavior alone.

Minimum coverage:

- built-in default for image resolves to `selfhost/image_z_image_turbo.json`
- persisted user default overrides built-in default
- `None` and empty persisted defaults fall back to built-in default
- missing persisted default falls back to built-in default
- missing built-in default falls back to first compatible workflow
- `MediaService` resolves image and video defaults separately based on `media_type`
- UI helper logic derives the correct selectbox default from the resolved key

Prefer extracting small pure helpers so tests can verify the logic without rendering the full Streamlit page.

## Out of Scope

- changing the actual prompt prefix default
- changing workflow files themselves
- auto-migrating or editing a user's local `config.yaml`
- changing unrelated TTS or template-selection UX beyond the shared default-resolution abstraction

## Rollout Notes

This design intentionally fixes the problem at the source instead of only patching the selector UI.

After implementation:

- new users get the intended default from repo defaults
- existing users with `null` config still land on the intended default
- saved user choices remain respected
- future workflow default changes only need to be updated in one resolution path and then documented once
