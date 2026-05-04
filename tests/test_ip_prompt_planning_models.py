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
