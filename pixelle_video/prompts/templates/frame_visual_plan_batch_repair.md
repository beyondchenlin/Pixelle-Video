---
prompt_id: frame_visual_plan_batch_repair
version: 1
stage: frame_visual_plan_batch_repair
purpose: Regenerate one frame visual plan batch after a response-schema violation without exposing the invalid response.
output_contract: JSON object with frame_visual_plans array covering exactly the supplied frame IDs.
---

The original visual planning request above remains authoritative. All of its input-safety rules still apply.

The previous response failed validation with this safe reason code:
{error_code_json}

Expected frame IDs:
{expected_frame_ids_json}

Regenerate the requested plans from the original request. Do not discuss or quote the previous response.

Return one top-level JSON object with exactly one frame_visual_plans array. The array must contain exactly one object for every expected frame ID, with no duplicates or extra frame IDs. Preserve each frame_id exactly. Every plan must include at least one non-empty required_subjects item grounded in that frame's source content. Return JSON only, without markdown fences, commentary, or alternative wrapper keys.
