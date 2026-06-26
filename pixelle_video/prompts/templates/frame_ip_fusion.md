---
prompt_id: frame_ip_fusion
version: 6
stage: frame_ip_fusion
purpose: Plan frame-level content-bound recurring IP presence after route selection.
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
For every frame visual plan, produce one content-bound IP presence plan. The IP must be visibly present in every frame, but it must be visually necessary to the frame's article explanation.

Choose exactly one `ip_participation_mechanism`: action_executor, reader_proxy, observation_gateway, system_component, conflict_participant, scale_reference, explanation_director, or transformation_medium.

Every item must include frame_id, ip_participation_mechanism, ip_role, ip_visibility, placement_logic, action_or_function, relation_to_article_subject, style_harmonization, positive_prompt_clause, negative_constraints, ip_duty_preset, duty_goal, action_verb, interaction_target, scene_binding, presentation_form, fallback_presentation, semantic_removal_test, channel_identity_removal_test, cognitive_anchor, physical_metaphor, content_relation_type, decorative_risk_score, rewrite_required, rewrite_instruction, and content_bound_ip_presence_plan.

Rules:
- `content_relation_type` must be `content_bound`.
- The IP must be a visible actor, state bearer, observer, system part, conflict participant, scale reference, explanation director, or transformation medium.
- Do not use a sticker, logo, corner badge, watermark, bookmark, label, stamp, bookplate, surface mark, or decorative card.
- If the existing frame metaphor cannot host the IP as a meaningful participant, set rewrite_required=true with a precise rewrite_instruction.
- Serious/sensitive frames must use a neutral explanation space and not place the IP in the literal sensitive event.
- Return JSON only.
