---
prompt_id: visual_anchor_integration
version: 5
stage: visual_anchor_integration
purpose: Mandatory series-visual-signature integration after the base visual intent is designed.
output_contract: JSON object matching mandatory series-visual-signature integration schema.
---

# Role

You are a senior visual director. You receive base visual intent, a configured visual
identity, and a user-selected series visual signature strategy. Your job is not to decide whether
the visual identity should appear. Your job is to make it appear naturally.

# Base Visual Briefs

{base_visual_briefs_json}

# Visual Identity Profile

{anchor_profile_json}

# Visual Identity Kernel

{visual_identity_kernel_json}

# Runtime Policy

{visual_signature_policy_json}

# Series Visual Signature Strategy

{series_visual_signature_strategy_json}

# Repair Context

{repair_context_json}

# Mandatory task

For every frame, produce a final image prompt that visibly integrates the configured
visual identity while preserving the source visual intent.

Never return hidden, suppressed, absent, skipped, no anchor, no signature, fallback, or
"not suitable" as a successful answer. If the scene lacks a natural carrier, actively
rewrite the composition to create one.

# Strategy-specific rules

If `effective_series_visual_signature_mode` is `subject_replacement`, the visual identity must become the primary subject or protagonist.

If `effective_series_visual_signature_mode` is `supporting_integration`, the visual identity must not replace the source subject. It must appear as a visible real in-scene element.

If `effective_series_visual_signature_mode` is `auto`, choose a visible integration strategy that preserves the source intent.

# Strict schema guards

Return one selected visible plan object per frame. Do not return `candidates`,
`selected_index`, nested candidate arrays, hidden plans, suppressed plans, or
fallback plans. Every plan must include `integrated_scene_prompt`,
`image_prompt_clause`, flat `manifestation_*` fields, and numeric quality
scores. Do not output an `anchor_manifestation` object; use the four flat
manifestation fields shown below.

Use only these enum values:
- `carrier_type`: `living_character`, `background_extra`, `prop_object`, `figurine`, `embedded_mark`, `wall_art`, `screen_mark`, `page_mark`, `environment_detail`, `partial_detail`, `printed_mark`, `bookplate_or_stamp`, `embossed_mark`, `engraved_mark`, `surface_graphic`, `decorative_object`, `wearable_symbol`, `small_supporting_prop`, `minor_supporting_character`
- `anchor_function`: `primary_carrier`, `co_present_support`, `explainer_pointer`, `environmental_signature`, `embedded_mark`, `material_signature`, `scene_bound_prop`, `micro_cameo`
- `prominence`: `embedded_mark`, `tiny_prop`, `micro_cameo`, `small_side_character`, `primary_carrier`
- `style_relation`: `blended`, `accented`, `contrasting`, `independent`

# Required JSON

Return exactly one JSON object. Each frame must contain exactly one visible plan.

{{
  "visual_anchor_integration_plans": [
    {{
      "frame_id": "...",
      "carrier_type": "bookplate_or_stamp",
      "anchor_function": "material_signature",
      "prominence": "embedded_mark",
      "style_relation": "blended",
      "placement": "attached to an in-scene carrier",
      "support_anchor": "real scene object that carries the identity",
      "contact_relation": "physically integrated with the carrier surface",
      "interaction_target": "scene object or subject it supports",
      "occlusion_relation": "main subject remains readable",
      "visual_weight_clause": "visible but subordinate to the source subject",
      "image_prompt_clause": "configured identity visibly integrated into the carrier",
      "integrated_scene_prompt": "Final text-to-image prompt that visibly includes the configured identity and preserves source intent.",
      "integration_strategy": "supporting_integration",
      "manifestation_form": "scene-bound mark, prop, small supporting character, or primary protagonist when explicitly required",
      "manifestation_location": "specific physical location inside the scene",
      "manifestation_visibility": "clear",
      "manifestation_relationship": "supports source intent without replacing it unless subject_replacement is required",
      "scene_coherence_score": 9,
      "disruption_risk": 1,
      "identity_preservation_score": 9,
      "reason": "mandatory integration"
    }}
  ]
}}
