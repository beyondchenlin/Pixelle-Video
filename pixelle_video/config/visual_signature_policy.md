# Visual Signature Policy

This file controls the runtime policy for the recurring channel IP / visual signature.
V1.0 uses mandatory IP participation: when a series visual signature profile is active,
every final image prompt must contain a concrete, scene-bound channel IP contribution.

Edit only the YAML block. Python hard gates still forbid canvas-corner overlays,
watermark-like marks, floating badges, UI badges, and unsupported carrier families even if
this document is edited incorrectly.

```yaml
version: visual_signature_policy.v1_0_mandatory_ip_participation
coverage_mode: every_frame
suppress_allowed: false
fallback_strategy: inject_safe_carrier
projection_failure: repair_or_fail
require_concrete_identity: true

# Fail closed means: if the LLM plan is invalid or unavailable, the frame is repaired
# with a deterministic in-scene carrier. The final provider prompt must not silently
# continue without the recurring IP when a signature profile is active.
fail_closed_on_llm_error: true
fail_closed_on_rejected_candidate: true
prefer_suppressed_when_uncertain: false

# V1.0 does not sparsify visibility. Sensitive scenes use low-intrusion duties such as
# companion_witness or background_signature, but they still require a real in-scene carrier.
suppress_named_subject_count: 0
visible_frame_budget_ratio: 1.0
max_consecutive_visible_frames: 0

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

forbidden_overlay_terms:
  - 鐢婚潰瑙掕惤
  - 灏忓彿瑙掓爣
  - 鍥哄畾瑙掕惤灞?
  - 鍙版爣鍖?
  - 鐢婚潰杈圭紭璐寸墖

final_prompt_forbidden_terms:
  - 鐢婚潰瑙掕惤
  - 灏忓彿瑙掓爣
  - 鍥哄畾瑙掕惤灞?
  - 鍙版爣鍖?
  - 鐢婚潰杈圭紭璐寸墖

high_risk_subject_terms:
  - 濂ョ壒鏇?
  - 瓒呬汉
  - Superman
  - Ultraman
  - 鐪熷疄浜虹墿
  - 鍘嗗彶浜虹墿
  - 瀹楁暀浜虹墿

high_risk_scene_terms:
  - 涓ヨ們绾疄
  - 鐏鹃毦
  - 鎮煎康
  - 瀹楁暀鍦烘櫙

# Positive-only downstream model guards. Keep these as affirmative image descriptions.
# Do not write negated forbidden forms here; the renderer and final gate reject them.
positive_prompt_guards:
  - 鏂板璇嗗埆缁嗚妭蹇呴』灞炰簬鍦烘櫙鍐呯湡瀹炵墿浣撱€佺粨鏋勩€佽鑹插姩浣滄垨鏉愯川琛ㄩ潰鐨勪竴閮ㄥ垎銆?
  - 涓昏鐢婚潰涓讳綋淇濇寔娓呮櫚锛屾柊澧炶瘑鍒粏鑺傛湇浠庡綋鍓嶅抚鐨勫彊浜嬩笌瑙ｉ噴浠诲姟銆?
```

## V1.0 operating model

- Every frame with an active channel IP profile must keep the recurring IP present.
- The IP can participate through duties such as host_explainer, evidence_curator,
  emotional_proxy, threshold_guardian, background_signature, and other duty presets.
- The system should vary duty, action, carrier, and presentation form, not visibility.
- If a natural carrier is missing, inject a small content-compatible in-scene carrier.
- The final provider prompt must be repaired or rejected if the IP projection fails.
