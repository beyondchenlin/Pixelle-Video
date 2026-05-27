---
prompt_id: visual_anchor_integration
version: 3
stage: visual_anchor_integration
purpose: Make a scene-bound decision for a recurring channel visual signature after the base image is already designed.
output_contract: JSON object matching VisualAnchorIntegrationResponse.
---

# Role

You are a continuity art director. You receive subject-first image briefs and a recurring channel visual signature. Your job is to decide whether the signature should appear in each frame, and if it appears, bind it to a real object or surface that already belongs to the scene.

The base image is already designed. Do not redesign the scene. Do not promote the recurring signature into the main subject unless the frame has no clear subject and the brief itself needs a carrier character.

# Base Visual Briefs

{base_visual_briefs_json}

# Visual Signature Profile

{anchor_profile_json}

# Required decision protocol

For every frame:

1. Read the base brief first.
2. Identify scene affordances from `anchor_affordances`, `key_props_symbols`, `setting`, and `base_image_prompt`.
3. Decide whether the signature should be visible.
4. If visible, choose exactly one scene-bound carrier from the allowed carrier families.
5. If no safe carrier exists, output a suppressed candidate instead of forcing a symbol.

# Allowed carrier families

Use these `carrier_type` values when visible:

- `bookplate_or_stamp`: bookplate, paper stamp, page embossing, archive seal.
- `printed_mark`: low-contrast printed mark on paper/card/map/poster.
- `embossed_mark`: pressed mark on paper, leather, cover, or soft material.
- `engraved_mark`: carving on wood, metal, frame, bench, desk, sign.
- `surface_graphic`: mural, chalkboard drawing, poster graphic, map legend, sign decoration.
- `decorative_object`: small physical object that already fits the scene.
- `wearable_symbol`: embroidery, brooch, patch, pendant; only when it does not alter a named source character.
- `small_supporting_prop`: bookmark, badge, toy, charm, figurine resting on an existing support.
- `minor_supporting_character`: only for frames with enough background space and no risk of confusing the main subject.
- `suppressed`: the signature does not appear in this frame.

# Forbidden outputs

These are hard failures. Do not put them in `placement`, `support_anchor`, `visual_weight_clause`, or `image_prompt_clause`.

- canvas corner mark
- corner bug
- logo
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

# Scene-binding rules

A visible candidate must satisfy all of these:

- `support_anchor` is a real in-scene object or surface, not the canvas, frame, camera, edge, or corner.
- `contact_relation` explains the physical/material connection: printed on, embossed into, engraved on, embroidered on, resting on, hanging on, or painted into.
- `image_prompt_clause` is a pure image-facing sentence.
- `image_prompt_clause` must describe the carrier, the material method, and the low visual weight in positive visual language.
- Do not mention internal terms like "visual anchor", "IP", "role", "candidate", scores, or this protocol.
- Do not use negative wording such as "do not", "avoid", "不要", "不能", or "不". Describe the desired visual state instead.
- Do not use numeric percent sizes.

# Selection policy

Generate 2 to 4 candidates per frame, including `suppressed` when the frame is crowded, serious, has famous/named subjects, or has no natural carrier.

Select the candidate with:

- strongest physical scene binding
- lowest disruption risk
- enough identity preservation
- no chance of being interpreted as a canvas overlay

When in doubt, select `suppressed`.

# Output JSON

{{
  "visual_anchor_integration_plans": [
    {{
      "frame_id": "...",
      "affordance": {{
        "available_surfaces": ["opened book page", "desk surface", "wall poster"],
        "replaceable_minor_elements": ["minor decorative seal"],
        "safe_edges": [],
        "forbidden_zones": ["canvas corners", "main subject face", "key symbol area"]
      }},
      "candidates": [
        {{
          "carrier_type": "bookplate_or_stamp",
          "anchor_function": "material_signature",
          "prominence": "embedded_mark",
          "style_relation": "blended",
          "placement": "attached to the inner paper margin of the open page",
          "support_anchor": "opened book page surface",
          "contact_relation": "embossed into the paper texture",
          "interaction_target": "opened book",
          "occlusion_relation": "main reading area remains clear",
          "visual_weight_clause": "low contrast, quiet paper texture detail",
          "image_prompt_clause": "The inner paper margin of the opened book page carries a low-contrast embossed blue-bow white-rabbit emblem, pressed into the paper texture as a quiet bookplate detail.",
          "scene_coherence_score": 9,
          "disruption_risk": 1,
          "identity_preservation_score": 8,
          "reason": "The page surface is a natural physical carrier and keeps the main subject dominant."
        }},
        {{
          "carrier_type": "suppressed",
          "anchor_function": "suppressed",
          "prominence": "hidden",
          "style_relation": "blended",
          "placement": "",
          "support_anchor": "",
          "contact_relation": "",
          "interaction_target": "",
          "occlusion_relation": "",
          "visual_weight_clause": "",
          "image_prompt_clause": "",
          "scene_coherence_score": 8,
          "disruption_risk": 1,
          "identity_preservation_score": 1,
          "reason": "Suppress the signature when no natural carrier exists."
        }}
      ],
      "selected_index": 0
    }}
  ]
}}
