```yaml
version: visual_signature_policy.v2_0_content_bound_mandatory_ip
coverage_mode: every_frame
suppress_allowed: false
fallback_strategy: rewrite_content_action
projection_failure: repair_or_fail
require_concrete_identity: true
fail_closed_on_llm_error: true
fail_closed_on_rejected_candidate: true
prefer_suppressed_when_uncertain: false
suppress_named_subject_count: 0
visible_frame_budget_ratio: 1.0
max_consecutive_visible_frames: 0

allowed_visible_carrier_types:
  - content_bound_ip_actor
  - content_bound_system_component
  - content_bound_scale_reference
  - content_bound_explanation_director

forbidden_overlay_terms:
  - 画面角落
  - 画面边角
  - 画布角落
  - 画布边角
  - 角标
  - 水印
  - 悬浮
  - 漂浮
  - floating sticker
  - watermark
  - overlay
  - corner logo
  - corner bug
  - canvas corner
  - screen corner

final_prompt_forbidden_terms:
  - 贴纸
  - 标签
  - 小标签
  - 卡片
  - 小卡片
  - 书签
  - 藏书票
  - 印章
  - 表面图案
  - 压印
  - 雕刻纹样
  - logo
  - sticker
  - label
  - card
  - bookmark
  - bookplate
  - stamp
  - printed mark
  - surface graphic
  - badge

high_risk_subject_terms:
  - 真实人物
  - 历史人物
  - 严肃历史
  - 严肃纪实
  - 纪录片
  - 灾难
  - 悼念
  - 战争
  - 犯罪

high_risk_scene_terms:
  - 事故现场
  - 灾难现场
  - 犯罪现场
  - 战争现场
  - 悼念现场
  - 医疗风险
  - 金融风险
  - 政治冲突
  - real person
  - disaster
  - crime scene
  - war scene
  - memorial

positive_prompt_guards:
  - Recurring identity appears through visible content action, not through a mark.
  - The article subject remains primary; the recurring character explains, operates, carries, weighs, connects, or arranges the content metaphor.
```
