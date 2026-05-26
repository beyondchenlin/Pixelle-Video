---
prompt_id: final_visual_prompt
version: 2
stage: final_visual_prompt_assembly
purpose: Render a scoped final visual prompt contract into one coherent downstream media prompt
output_contract: plain_text_visual_prompt
---
[Scene]
{scene}

[Composition]
{composition}

[Style Assignment]
{style_assignment}

[Character Layer Style]
{character_layer_style}

[World Layer Style]
{world_layer_style}

[Integration and Priority]
{integration_priority}

<!-- if visual_suffix -->
Rendering requirements: {visual_suffix}
<!-- endif -->
<!-- if rendering_requirements -->
[Rendering Requirements]
{rendering_requirements}
<!-- endif -->
