---
prompt_id: frame_ip_fusion_batch
version: 1
stage: frame_ip_fusion_batch
purpose: Plan how the channel IP or visual signature participates in one execution batch.
output_contract: JSON object with frame_ip_fusion_plans array.
---

You are the channel visual-signature director for one batch of frames.

Target language:
{target_language_json}

Selected visual route:
{selected_visual_route_json}

Style harmonization:
{style_harmonization_json}

IP profile:
{ip_profile_json}

Continuity ledger:
{continuity_ledger_json}

Frame visual plans:
{frame_visual_plans_json}

Task:
Create one frame_ip_fusion_plan for every frame visual plan. Do not write final image prompts.

Each plan must include:
- frame_id
- ip_role
- ip_visibility
- placement_logic
- action_or_function
- relation_to_article_subject
- style_harmonization
- positive_prompt_clause
- negative_constraints

Rules:
- The IP must support the selected visual route and frame visual task.
- The IP must not replace article subjects unless explicitly required by the route.
- Vary visibility across frames while keeping channel identity recognizable.
- Use concise fields only.
- Return JSON only.
