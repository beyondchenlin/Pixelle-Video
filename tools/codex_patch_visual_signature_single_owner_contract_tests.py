from __future__ import annotations

from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"{label}: target block not found")
    return text.replace(old, new, 1)


path = Path("tests/services/test_series_visual_signature_image_prompt_composer.py")
text = path.read_text(encoding="utf-8")

text = replace_once(
    text,
    "async def test_canonical_prompt_composer_uses_signature_free_base_then_projection(\n",
    "async def test_canonical_prompt_composer_uses_validated_context_without_legacy_projection_inputs(\n",
    "canonical image test name",
)

old_image_assertions = '''    assert captured_generation["series_visual_signature_enabled"] is True
    assert captured_generation["series_visual_signature_request"] is not None
    assert captured_generation["series_visual_signature_request"].enabled is True
    assert captured_generation["ip_profile"] is not None
    assert captured_generation["scene_casts_by_frame"] is None
'''
new_image_assertions = '''    assert captured_generation["series_visual_signature_enabled"] is False
    assert captured_generation["series_visual_signature_request"] is None
    assert captured_generation["ip_profile"] is None
    assert captured_generation["scene_casts_by_frame"] is None
    canonical_request = captured_generation["canonical_series_visual_signature_request"]
    canonical_profile = captured_generation[
        "canonical_series_visual_signature_profile_snapshot"
    ]
    assert canonical_request is not None
    assert canonical_request.enabled is True
    assert canonical_request.profile_id == "dog_1"
    assert canonical_profile is not None
    assert canonical_profile.profile_id == "dog_1"
    assert canonical_profile.display_name == "Dalmatian"
    assert canonical_profile.identity_traits == (
        "black spots",
        "black sunglasses",
        "red collar",
        "small round ears",
    )
'''
text = replace_once(
    text,
    old_image_assertions,
    new_image_assertions,
    "canonical image generator contract",
)

text = replace_once(
    text,
    "async def test_video_prompt_path_uses_same_canonical_visual_signature_projection(\n",
    "async def test_video_prompt_path_uses_same_canonical_context_without_legacy_projection(\n",
    "canonical video test name",
)

old_video_assertions = '''    assert captured_generation["media_type"] == "video"
    assert captured_generation["series_visual_signature_enabled"] is True
    assert "Dalmatian" in result.prompts[0]
'''
new_video_assertions = '''    assert captured_generation["media_type"] == "video"
    assert captured_generation["series_visual_signature_enabled"] is False
    assert captured_generation["series_visual_signature_request"] is None
    assert captured_generation["ip_profile"] is None
    canonical_request = captured_generation["canonical_series_visual_signature_request"]
    canonical_profile = captured_generation[
        "canonical_series_visual_signature_profile_snapshot"
    ]
    assert canonical_request is not None
    assert canonical_request.enabled is True
    assert canonical_profile is not None
    assert canonical_profile.profile_id == "dog_1"
    assert "Dalmatian" in result.prompts[0]
'''
text = replace_once(
    text,
    old_video_assertions,
    new_video_assertions,
    "canonical video generator contract",
)

path.write_text(text, encoding="utf-8")
