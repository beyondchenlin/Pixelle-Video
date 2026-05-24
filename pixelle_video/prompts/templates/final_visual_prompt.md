---
prompt_id: final_visual_prompt
version: 1
stage: final_visual_prompt_assembly
purpose: Render structured semantic visual prompt clauses into one coherent downstream media prompt
output_contract: plain_text_visual_prompt
---
{base_prompt}
<!-- if world_clause -->
 World context: {world_clause}
<!-- endif -->
<!-- if style_clause -->
 Visual style: {style_clause}
<!-- endif -->
<!-- if camera_clause -->
 Composition: {camera_clause}
<!-- endif -->
<!-- if environment_clause -->
 Environment: {environment_clause}
<!-- endif -->
<!-- if visual_suffix -->
 Rendering requirements: {visual_suffix}
<!-- endif -->
