from dataclasses import dataclass

from pixelle_video.models.final_visual_prompt_contract import FinalVisualPromptContract
from pixelle_video.services.model_prompt_renderer import select_model_prompt_renderer


@dataclass
class Capabilities:
    supports_negative_prompt: bool


def _contract():
    return FinalVisualPromptContract(
        scene="A teacher explains dog intelligence.",
        composition="medium shot, single unified image",
        style_assignment="The IP human character is the only photorealistic element.",
        character_layer_style="photorealistic human teacher",
        world_layer_style="flat monochrome illustration world",
        integration_priority="preserve style separation",
        negative_rules=("do not make the whole scene photorealistic",),
    )


def test_z_image_renderer_embeds_negative_rules_in_positive_prompt():
    renderer = select_model_prompt_renderer(
        workflow="selfhost/image_z_image_turbo_gguf.json",
        capabilities=Capabilities(False),
    )
    rendered = renderer.render(_contract(), capabilities=Capabilities(False))
    assert rendered.negative_prompt is None
    assert "do not make the whole scene photorealistic" in rendered.prompt


def test_negative_capable_renderer_uses_negative_prompt_field():
    renderer = select_model_prompt_renderer(
        workflow="selfhost/image_flux.json",
        capabilities=Capabilities(True),
    )
    rendered = renderer.render(_contract(), capabilities=Capabilities(True))
    assert rendered.negative_prompt == "do not make the whole scene photorealistic"
    assert "do not make the whole scene photorealistic" not in rendered.prompt
