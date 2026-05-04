from pixelle_video.models.ip_prompt_planning import (
    IPFrameAdaptationPackage,
    IPImageTextPlan,
    IPPresenceType,
)


def test_ip_frame_adaptation_package_serializes_presence_text_and_color_terms():
    package = IPFrameAdaptationPackage(
        frame_id="frame_0001",
        ip_presence_type=IPPresenceType.SCENE_INTEGRATED,
        presence_mode="support",
        semantic_reason="opening establishing frame should keep the gate as the primary subject",
        identity_anchors_visible=("white rabbit silhouette", "blue tie"),
        identity_color_terms=("纯白色身体", "鲜明宝蓝色领带"),
        image_text_plan=IPImageTextPlan(
            summary_text="从长乐门出发",
            scene_text=("长乐门", "正定古城"),
            visible_text_whitelist=("从长乐门出发", "长乐门", "正定古城"),
        ),
        negative_constraints=("避免角色贴纸感", "避免多余文字"),
    )

    payload = package.to_dict()

    assert payload["ip_presence_type"] == "scene_integrated"
    assert payload["image_text_plan"]["summary_text"] == "从长乐门出发"
    assert "#5A2A12" not in str(payload)


def test_ip_frame_adaptation_package_round_trips_nested_image_text_plan():
    package = IPFrameAdaptationPackage(
        frame_id="frame_0002",
        ip_presence_type=IPPresenceType.BALANCED_NARRATIVE,
        presence_mode="guide",
        semantic_reason="keep the guide visible without replacing the landmark",
        must_not_replace=("长乐门",),
        identity_anchors_visible=("white rabbit silhouette",),
        identity_anchors_suppressed=("oversized mascot head",),
        identity_color_terms=("纯白色身体",),
        outfit_theme="古城导览员",
        accessories=("小旗子",),
        action="指向城门",
        expression="温和微笑",
        pose="侧身站立",
        camera_relationship="mid-ground support subject",
        depth_layer="middle",
        interaction_target="长乐门",
        continuity_from_previous="keeps blue tie visible",
        shot_fit_notes="do not dominate the establishing shot",
        image_text_plan=IPImageTextPlan(
            summary_text="长乐门导览",
            scene_text=("长乐门", "古城入口"),
            visible_text_whitelist=("长乐门导览", "长乐门", "古城入口"),
            text_safety_rules=("不要生成额外标语",),
        ),
        prompt_weight=0.65,
        negative_constraints=("避免角色贴纸感",),
    )

    restored = IPFrameAdaptationPackage.from_dict(package.to_dict())

    assert restored == package
    assert restored.to_dict()["image_text_plan"]["scene_text"] == ["长乐门", "古城入口"]
