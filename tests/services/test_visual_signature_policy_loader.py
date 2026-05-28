from pixelle_video.services.visual_signature_policy_loader import load_visual_signature_policy


def test_visual_signature_policy_loads_markdown_yaml(tmp_path):
    policy_file = tmp_path / "visual_signature_policy.md"
    policy_file.write_text(
        """
        # policy

        ```yaml
        visible_frame_budget_ratio: 0.2
        suppress_named_subject_count: 3
        forbidden_overlay_terms:
          - 自定义角落坏词
        allowed_visible_carrier_types:
          - bookplate_or_stamp
          - unsupported_corner_badge
        positive_prompt_guards:
          - 细节必须属于真实场景物体。
        ```
        """,
        encoding="utf-8",
    )

    policy = load_visual_signature_policy(policy_file)

    assert policy.visible_frame_budget_ratio == 0.2
    assert policy.suppress_named_subject_count == 3
    assert "自定义角落坏词" in policy.forbidden_overlay_terms
    assert "bookplate_or_stamp" in policy.allowed_visible_carrier_types
    assert "unsupported_corner_badge" not in policy.allowed_visible_carrier_types
    assert policy.contains_forbidden_overlay_text("画面右下角")
