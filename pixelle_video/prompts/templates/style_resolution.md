---
prompt_id: style_resolution
version: 1
stage: style_resolution
purpose: Resolve a raw style prefix into structured backend-ready style metadata.
output_contract: JSON object matching StyleResolutionResponse.
---

<!-- template-loader:strip # style_resolution -->
{{
  "task": "resolve_style_prefix",
  "raw_prefix": {raw_prefix_json},
  "required_output": {required_output_json},
  "instructions": [
    "Return JSON only.",
    "Resolve the prefix into backend-ready style metadata.",
    "Return style_profile.style_kind identical to the top-level style_kind.",
    "If prompt_template is non-empty it must contain {{prompt}} exactly once.",
    "Use concise but specific strings for every style_profile field.",
    "Do not leave any style_profile field empty.",
    "For ip_world, subject_policy, world_elements, and consistency_anchor must describe the persistent world rules.",
    "For visual_only, preserve the subject semantics instead of replacing it with a named IP character.",
    "When the style describes scoped object rendering, include visual_style_contract.layers with explicit targets, rendering_style, positive_rules, boundary_rules, priority, and exclusive.",
    "Use visual_style_contract for object-level style separation, such as photorealistic human character versus flat illustrated non-human world.",
    "If no scoped layers are needed, visual_style_contract may be null; the runtime will normalize style_profile into a visual style contract.",
    "Validate the final payload against required_output before returning it.",
    "Do not wrap the JSON in markdown fences."
  ]
}}
