# Pixelle-Video V1.0 Mandatory IP Participation

## Goal

Default visual signature generation is no longer sparse decoration. When visual
anchor generation is enabled with an `IPProfile`, every frame must carry a
scene-bound IP participation plan into the provider prompt.

Disabled or profile-less requests are the compatibility path: they are projected
with an anchor-free policy so normal source-only image prompts continue to work.

## Source Of Truth

The mandatory pipeline is:

1. `IPDutyPlan`
2. carrier selection or carrier injection
3. `MandatoryIPPromptCompiler`
4. `VisualAnchorPlacementPlan`
5. `ProviderPromptProjector`
6. `FinalPromptIPGate`

`IPDutyPlan` is the structured source of truth for why the IP is present in a
frame. It carries the duty preset, goal, action, interaction target, scene
binding, presentation form, fallback presentation, and removal tests.

When upstream context does not provide a duty plan, the deterministic default is
conservative:

- known visual-story routes map to richer duties such as curator, operator, or
  relationship mediator;
- high-risk or existing-IP subject scenes use `background_signature`;
- unknown routes also use `background_signature` rather than inventing an
  explanatory actor.

## Mandatory Projection

In `coverage_mode=every_frame` with `projection_failure=repair_or_fail`:

- a missing, filtered, hidden, or non-scene-bound anchor clause raises before
  provider projection;
- the final prompt is checked again by `FinalPromptIPGate`;
- concrete identity must survive into the anchor clause;
- forbidden final prompt terms such as logo, sticker, watermark, overlay, and
  canvas-corner language remain blocked.

`projection_failure=allow_anchor_free` is reserved for explicit compatibility
requests. It must not be used to make enabled mandatory IP silently disappear.

## Fallback Behavior

LLM integration is allowed to fail or return unusable candidates. The repair path
does not return suppressed output by default. It deterministically injects a
content-compatible real carrier such as a paper analysis card, book margin,
timeline card, folder label, board legend, task card, or judgment card.

`fallback_strategy=suppress` is a compatibility switch. It produces an explicit
suppressed plan and still requires the projection policy to decide whether an
anchor-free provider prompt is allowed.

## Maintenance Rules

- Do not add free-text-only duties that bypass `IPDutyPlan`.
- Do not make the cadence planner hide frames in mandatory mode.
- Do not put internal policy names into provider-facing prompts.
- Do not repair forbidden overlay language by passing it through; repair means
  replacing it with a scene-bound carrier.
- Add tests at the boundary where behavior can silently become anchor-free.
