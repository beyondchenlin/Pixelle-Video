# Visual Signature Policy

This file is intentionally editable without touching Python code. It controls
project-specific runtime policy for recurring visual signatures such as a blue-bow
white-rabbit motif, a sparrow mark, a chair silhouette, a stone token, or another
channel identity detail.

Edit only the YAML block. Python hard gates still forbid canvas-corner overlays,
watermarks, floating stickers, UI badges, and unsupported carrier families even if
this document is edited incorrectly.

```yaml
version: visual_signature_policy.v3_2_scene_bound

# Fail closed means: if the LLM plan is invalid or unavailable, the signature is hidden.
fail_closed_on_llm_error: true
fail_closed_on_rejected_candidate: true
prefer_suppressed_when_uncertain: true

# A frame with this many named source subjects is normally too risky for a visible signature.
# Example: "奥特曼 vs 超人" should preserve both subjects first.
suppress_named_subject_count: 2

# Batch-level cadence. 0.35 means at most about one third of frames should show the signature.
visible_frame_budget_ratio: 0.35
max_consecutive_visible_frames: 1

# Markdown may narrow this list, but cannot add unsupported carrier families.
allowed_visible_carrier_types:
  - bookplate_or_stamp
  - printed_mark
  - embossed_mark
  - engraved_mark
  - surface_graphic
  - decorative_object
  - wearable_symbol
  - small_supporting_prop
  - minor_supporting_character

# Project-specific additions are merged with Python hard defaults.
forbidden_overlay_terms:
  - 角落标记
  - 小徽标
  - 固定落款
  - 台标式
  - 画面边缘贴片

final_prompt_forbidden_terms:
  - 角落标记
  - 小徽标
  - 固定落款
  - 台标式
  - 画面边缘贴片

high_risk_subject_terms:
  - 奥特曼
  - 超人
  - Superman
  - Ultraman
  - 真实人物
  - 历史人物
  - 宗教人物

high_risk_scene_terms:
  - 严肃纪实
  - 灾难
  - 悼念
  - 宗教叙事

# Positive-only downstream model guards. Do not write "no logo / no watermark" here.
positive_prompt_guards:
  - 所有新增识别细节都属于场景内真实物体或材质表面的一部分。
  - 主要画面主体保持清晰，画面表面干净完整，细节服从主体叙事。
```

## How to adapt special cases

- To make the signature rarer, lower `visible_frame_budget_ratio`.
- To keep every two-subject comparison clean, keep `suppress_named_subject_count: 2`.
- To force a documentary/religious/historical topic to hide signatures, add terms to
  `high_risk_scene_terms`.
- To forbid a new bad visual habit, add the phrase to both `forbidden_overlay_terms`
  and `final_prompt_forbidden_terms`.
- Do not add `logo`, `watermark`, `sticker`, or corner language to positive prompt
  guards; Python already rejects those forms, and positive-only image models may be
  polluted by negative words.
