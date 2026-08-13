---
prompt_id: frame_visual_plan_batch
version: 3
stage: frame_visual_plan_batch
purpose: Produce bounded content-bound visual plans for one execution batch.
output_contract: JSON object with frame_visual_plans array.
---

You are the visual planning director for one batch of article frames.

Target language:
{target_language_json}

Article summary:
{article_summary_json}

Selected visual route:
{selected_visual_route_json}

Continuity ledger:
{continuity_ledger_json}

Current batch payload:
{batch_payload_json}

Task:
Create one frame_visual_plan for every frame in the current batch. Do not plan frames outside the batch. Do not write final image prompts.

For every frame, first find the frame's cognitive anchor: the mental action this frame explains, such as filtering, comparing, connecting, blocking, transforming, weighing, enduring, observing, repairing, or guiding. Then turn that abstract point into one concrete physical metaphor and one scene arena where the configured recurring IP can later participate as a content actor.

Each plan must include:
- frame_id
- frame_index
- source_text
- local_claim
- visual_task
- visual_logic
- cognitive_anchor
- physical_metaphor
- scene_arena
- ip_action_affordance
- required_subjects
- forbidden_losses
- forbidden_ip_forms
- evidence_refs
- visible_text_policy

Rules:
- Preserve the source frame meaning and required subjects.
- The IP is not inserted here, but the base scene must contain a natural action affordance for the IP.
- Do not solve IP presence by inventing a sticker, logo, corner badge, watermark, bookmark, label, stamp, bookplate, surface mark, or small decorative card.
- If the current article point is serious or sensitive, use a neutral explanation space such as an archive desk, model table, relationship map, or evidence wall. Do not place the recurring IP inside a literal disaster, crime, mourning, medical, financial, or political-conflict scene.
- Keep each field concise and provider-safe.
- Return one top-level JSON object with exactly one frame_visual_plans array.
- Return JSON only, without markdown fences, commentary, or alternative wrapper keys.

Required response shape:

{{
  "frame_visual_plans": [
    {{
      "frame_id": "copy the exact frame_id from the batch",
      "frame_index": 1,
      "source_text": "copy the source text for this frame",
      "local_claim": "the local article claim",
      "visual_task": "the visual communication task",
      "visual_logic": "how this frame applies the selected route",
      "cognitive_anchor": "one mental action",
      "physical_metaphor": "one concrete physical metaphor",
      "scene_arena": "one concrete scene arena",
      "ip_action_affordance": "a natural later action affordance",
      "required_subjects": [],
      "forbidden_losses": [],
      "forbidden_ip_forms": [],
      "evidence_refs": [],
      "visible_text_policy": "no_visible_text"
    }}
  ]
}}

The array must contain exactly one object for every requested frame_id, with no duplicates or extra frame IDs.
