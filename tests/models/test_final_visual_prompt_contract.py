from pixelle_video.models.final_visual_prompt_contract import FinalVisualPromptContract


def test_final_visual_prompt_contract_sections_are_stable():
    contract = FinalVisualPromptContract(
        scene="scene",
        composition="composition",
        style_assignment="style assignment",
        character_layer_style="character layer",
        world_layer_style="world layer",
        integration_priority="priority",
    )
    assert set(contract.prompt_sections()) == {
        "scene",
        "composition",
        "style_assignment",
        "character_layer_style",
        "world_layer_style",
        "integration_priority",
    }


def test_negative_rules_are_not_prompt_sections():
    contract = FinalVisualPromptContract("s", "c", "a", "char", "world", "priority", negative_rules=("no collage",))
    assert "negative_rules" not in contract.prompt_sections()
