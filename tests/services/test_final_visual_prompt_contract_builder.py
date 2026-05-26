from pixelle_video.models.asset_bible import IPProfile
from pixelle_video.services.final_visual_prompt_contract_builder import FinalVisualPromptContractBuilder


def test_builder_creates_mixed_style_sections_for_photoreal_ip():
    profile = IPProfile.from_dict(
        {
            "ip_profile_id": "teacher",
            "workspace_id": "workspace",
            "project_id": "project",
            "name": "Teacher",
            "visual_summary": "young male teacher in white T-shirt and thin-frame glasses",
            "rendering_style": "photorealistic_human",
            "style_scope": "ip_character_only",
            "exclusive_visual_layer": True,
            "style_boundary_rules": ["Only this IP human character may be photorealistic."],
        }
    )
    contract = FinalVisualPromptContractBuilder().build(
        base_prompt="A teacher explains dog intelligence beside a board.",
        frame_context={"shot_type": "medium shot", "world_elements": ["dog", "teaching board", "books"]},
        ip_profile=profile,
        ip_adaptation={
            "ip_presence_type": "balanced_narrative",
            "role_slot": "supporting",
            "appearance_description": "young male teacher in white T-shirt and thin-frame glasses",
            "negative_constraints": ["cartoon human"],
        },
    )
    assert "only photorealistic element" in contract.style_assignment
    assert "flat monochrome" in contract.world_layer_style
    assert "cartoon human" in contract.negative_rules
