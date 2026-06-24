# Pixelle-Video V3.2 Visual Signature Best Practice

> Superseded for default generation by
> `visual_signature_policy.v1_0_mandatory_ip_participation`.
> This document now describes the sparse compatibility path only. New default
> work should follow `visual_signature_v1_0_mandatory_ip_participation.md`.

## Goal

This version replaces the old "IP character in every frame" mental model with a
sparse, scene-bound "visual signature" system.

The recurring identity detail can still be derived from an IP profile, but after
that conversion it is treated as a material signature, prop detail, surface graphic,
or suppressed candidate. It is not a default protagonist, supporting character,
canvas badge, sticker, watermark, or corner logo.

## Architecture

1. Base image prompt remains subject-first and anchor-free.
2. `VisualSignaturePolicy` is loaded from `pixelle_video/config/visual_signature_policy.md`.
3. `VisualSignatureCadencePlanner` decides a sparse batch-level visibility cadence.
4. `VisualAnchorIntegrationPlanner` asks the LLM for scene-bound candidates only when
   the cadence allows visibility.
5. Candidate projection is deterministic. The provider prompt does not directly trust
   LLM-written `image_prompt_clause` text.
6. Python hard gates reject any candidate or final clause that smells like a canvas
   corner, watermark, floating sticker, UI badge, or logo.
7. LLM errors and rejected candidates fail closed to `suppressed`.

## Markdown policy

The Markdown policy is for runtime data, not executable behavior. It can tune:

- visibility cadence
- high-risk subject terms
- high-risk scene terms
- extra forbidden terms
- allowed carrier families, narrowed from the built-in safe list
- positive prompt guard sentences

It cannot disable Python hard gates or introduce unsupported carrier families.

## Operational note

If the application process is long-running, restart it after editing
`visual_signature_policy.md` so every worker reads the updated data consistently.
