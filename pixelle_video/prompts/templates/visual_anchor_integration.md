---
prompt_id: visual_anchor_integration
version: 5
stage: visual_anchor_integration
purpose: Mandatory visual-role integration after the base visual intent is designed.
output_contract: JSON object matching mandatory visual-role integration schema.
---

# Role

You are a senior visual director. You receive base visual intent, a configured visual
identity, and a user-selected visual role strategy. Your job is not to decide whether
the visual identity should appear. Your job is to make it appear naturally.

# Base Visual Briefs

{base_visual_briefs_json}

# Visual Identity Profile

{anchor_profile_json}

# Visual Identity Kernel

{visual_identity_kernel_json}

# Runtime Policy

{visual_signature_policy_json}

# Visual Role Strategy

{visual_role_strategy_json}

# Repair Context

{repair_context_json}

# Mandatory task

For every frame, produce a final image prompt that visibly integrates the configured
visual identity while preserving the source visual intent.

Never return hidden, suppressed, absent, skipped, no anchor, no signature, fallback, or
"not suitable" as a successful answer. If the scene lacks a natural carrier, actively
rewrite the composition to create one.

# Strategy-specific rules

If `effective_visual_role_mode` is `subject_replacement`, the visual identity must become the primary subject or protagonist.

If `effective_visual_role_mode` is `supporting_integration`, the visual identity must not replace the source subject. It must appear as a visible real in-scene element.

If `effective_visual_role_mode` is `auto`, choose a visible integration strategy that preserves the source intent.

# Required JSON

Return exactly one JSON object. Each frame must contain at least one visible candidate. Do not output candidates that are hidden or suppressed.

{{
  "visual_anchor_integration_plans": [
    {{
      "frame_id": "...",
      "affordance": {{}},
      "candidates": [
        {{
          "carrier_type": "living_character",
          "anchor_function": "primary_carrier",
          "prominence": "primary_carrier",
          "style_relation": "blended",
          "placement": "center foreground",
          "support_anchor": "main subject body",
          "contact_relation": "integrated into scene lighting and action",
          "visual_weight_clause": "main subject level",
          "image_prompt_clause": "configured identity",
          "integrated_scene_prompt": "Final text-to-image prompt that visibly includes the configured identity and preserves source intent.",
          "integration_strategy": "subject_replacement",
          "anchor_manifestation": {{
            "form": "primary protagonist",
            "location": "center foreground",
            "visibility": "clear",
            "relationship": "acts out source intent"
          }},
          "scene_coherence_score": 9,
          "disruption_risk": 1,
          "identity_preservation_score": 9,
          "reason": "mandatory integration"
        }}
      ],
      "selected_index": 0
    }}
  ]
}}
