---
prompt_id: frame_ip_fusion
version: 5
stage: frame_ip_fusion
purpose: Plan frame-level IP or visual-signature participation after route selection.
output_contract: JSON object with a "frame_ip_fusion_plans" key containing an array of FrameIPFusionPlan-compatible objects.
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
For every frame visual plan, produce one frame-level IP participation plan. The IP must be visibly present in every frame and must reinforce the selected route and frame local claim. Do not vary visibility to hidden or optional; vary duty, action, carrier, presentation form, scale, and scene relationship instead.

Select exactly one `ip_duty_preset` per frame from: host_explainer, guide_explainer, operator_demonstrator, pointer_annotator, companion_witness, evidence_curator, contrast_judge, emotional_proxy, metaphor_symbol, structure_carrier, relationship_mediator, navigator_pathfinder, mechanic_repairer, threshold_guardian, background_signature, comic_counterpoint.

Every item must include frame_id, role, visibility_tier, scene_function, placement_strategy, identity_preservation, style_harmony_rule, negative_rules, reason, ip_duty_preset, duty_goal, action_verb, interaction_target, scene_binding, presentation_form, fallback_presentation, semantic_removal_test, and channel_identity_removal_test. Do not output hidden, suppressed, absent, or decorative-only plans.

Return JSON only. Return an object with a single key "frame_ip_fusion_plans".
