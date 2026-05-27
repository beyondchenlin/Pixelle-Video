# Visual Anchor V3.1 Scene-Bound Protocol

This document defines the source-level rules for recurring visual signatures in image prompt generation.

## Problem statement

The recurring visual signature is not a default protagonist. It is a channel continuity motif. In previous versions, the system asked the image model to keep the motif small and non-disruptive, which made text-to-image models solve the task by placing a small logo, watermark, sticker, or corner badge in the canvas. That behavior is now treated as a policy failure.

## Architectural rule

Visual anchor integration is a three-step process:

1. Build an anchor-free base visual brief from the narration and storyboard context.
2. Extract scene affordances: real objects, surfaces, props, documents, walls, furniture, clothing, maps, screens-within-the-scene, or other carriers that can physically host a small recurring motif.
3. Project only a validated scene-bound anchor clause into the final provider prompt.

The provider prompt must never receive internal planning vocabulary such as `visual anchor`, `IP`, `support_anchor`, `placement_zone`, `carrier_type`, scores, or role labels.

## Allowed visible carrier families

A visible recurring motif must use one of these carrier families:

- `bookplate_or_stamp`: bookplate, paper stamp, page embossing, archive seal.
- `printed_mark`: low-contrast printed mark on paper, card, map, or poster.
- `embossed_mark`: pressed mark on paper, leather, cover, or soft material.
- `engraved_mark`: carving on wood, metal, frame, bench, desk, or sign.
- `surface_graphic`: mural, chalkboard drawing, poster graphic, map legend, sign decoration.
- `decorative_object`: small physical object that already fits the scene.
- `wearable_symbol`: embroidery, brooch, patch, or pendant, only when it does not alter a named source character.
- `small_supporting_prop`: bookmark, badge, toy, charm, or figurine resting on an existing support.
- `minor_supporting_character`: only when there is enough background space and no risk of confusing the main subject.
- `suppressed`: the motif does not appear in this frame.

## Forbidden outputs

The following outputs are hard failures:

- canvas corner mark
- corner bug
- logo overlay
- watermark
- floating sticker
- UI badge
- standalone overlay icon
- 画面角落
- 画面边角
- 右上角 / 左上角 / 右下角 / 左下角
- 角标
- 水印
- 贴纸
- 悬浮 / 漂浮

## Hard gate for visible candidates

A visible candidate must satisfy all of these conditions:

1. It has a non-empty image-facing prompt clause.
2. Its support anchor is a real in-scene object or surface, not the canvas, frame, camera, edge, or corner.
3. The combined candidate text contains an in-world carrier term.
4. The combined candidate text contains a material or physical binding term such as printed, embossed, engraved, embroidered, resting, mounted, painted, attached, or physically contacting a surface.
5. It contains no forbidden overlay language.

Candidates that fail the hard gate must be filtered out. If no valid visible candidate remains, the frame must use a deterministic safe fallback or a suppressed plan. The system must fail closed rather than forcing a corner mark.

## LLM response handling

The LLM may propose multiple candidates. Invalid candidates are not allowed to poison the whole response. The planner accepts the response, filters candidates through the same scene-bound policy, and chooses the best valid candidate. If the selected candidate is invalid but another valid scene-bound candidate exists, the valid candidate wins. If only suppressed is usable, the frame is hidden. If no usable candidate exists, deterministic fallback is used.

## Deterministic fallback

Fallback must never emit canvas-edge language. It must choose from scene affordances such as:

- open book page surface
- book cover bookplate
- bookmark
- map legend
- paper margin emblem
- desk surface object
- wood engraving
- wall mural detail
- poster paper emblem
- road sign decoration
- TV cabinet prop
- clothing embroidery, when safe

If no natural carrier exists, fallback returns `suppressed` instead of inventing a logo overlay.

## Provider projection

Provider projection performs the final safety gate. Even if an upstream plan is visible, the provider prompt receives the anchor clause only when it passes the scene-bound policy. Otherwise the final prompt is rendered as an anchor-free image prompt and metadata records `scene_bound_anchor_gate = absent_or_rejected`.

Provider-facing text should be concrete visual language, for example:

- `The inner paper margin of the opened book page carries a low-contrast embossed blue-bow white-rabbit emblem, pressed into the paper texture as a quiet bookplate detail.`
- `A low-contrast rabbit-shaped engraving is worked into the wooden frame, matching the material and remaining below the main subject's visual priority.`
- `A small rabbit-shaped bookmark rests on the desk surface as a low-presence physical prop.`

Provider-facing text should not say:

- `put the visual anchor in the corner`
- `small logo`
- `watermark`
- `floating sticker`
- `IP role`
- `support_anchor`
- `corner badge`

## Success criteria

A generated image prompt is successful when the recurring motif, if visible, is physically bound to an in-scene object or surface and reads as part of the scene. A generated image prompt is a failure when the motif reads as a canvas overlay, corner badge, sticker, logo, watermark, or detached floating icon.
