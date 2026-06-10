---
prompt_id: frame_ip_fusion
version: 3
stage: frame_ip_fusion
purpose: Plan frame-level IP or visual-signature participation after route selection.
output_contract: JSON array of FrameIPFusionPlan-compatible objects.
---

Selected route:
{selected_route_json}

Style harmonization:
{style_harmonization_json}

Frame visual plans:
{frame_visual_plans_json}

IP profile summary:
{ip_profile_json}

Compatibility report:
{compatibility_report_json}

Task:
For every frame visual plan, produce one frame-level IP fusion plan. IP must reinforce the selected route and frame local claim. Vary visibility across frames so the channel signature is memorable but not repetitive.

Return JSON only. Return an array. Each item must include frame_id, role, visibility_tier, scene_function, placement_strategy, identity_preservation, style_harmony_rule, negative_rules, reason.
