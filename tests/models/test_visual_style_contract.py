from pixelle_video.models.visual_style_contract import (
    VisualLayerTarget,
    VisualRenderingStyle,
    VisualStyleLayer,
    VisualStyleLayerContract,
)


def test_visual_style_layer_contract_round_trip():
    contract = VisualStyleLayerContract(
        layers=(
            VisualStyleLayer(
                layer_id="world",
                targets=(VisualLayerTarget.ALL_NON_HUMAN,),
                rendering_style=VisualRenderingStyle.FLAT_MONOCHROME_ILLUSTRATION,
                positive_rules=("flat monochrome",),
                boundary_rules=("not photorealistic",),
            ),
        ),
        integration_rules=("single unified image",),
        negative_rules=("collage",),
    )
    payload = contract.to_dict()
    restored = VisualStyleLayerContract.from_dict(payload)
    assert restored.layers[0].rendering_style is VisualRenderingStyle.FLAT_MONOCHROME_ILLUSTRATION
    assert restored.negative_rules == ("collage",)


def test_contract_prompt_layer_clause_filters_targets():
    contract = VisualStyleLayerContract.from_dict(
        {"layers": [{"layer_id": "world", "targets": ["all_non_human"], "rendering_style": "flat_monochrome_illustration", "positive_rules": ["flat monochrome"]}]}
    )
    assert "flat monochrome" in contract.prompt_layer_clause(VisualLayerTarget.ALL_NON_HUMAN)
