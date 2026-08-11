from __future__ import annotations

from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"{label}: target block not found")
    return text.replace(old, new, 1)


service_path = Path("pixelle_video/services/series_visual_signature_projection_service.py")
text = service_path.read_text(encoding="utf-8")

text = replace_once(
    text,
    "from pixelle_video.services.series_visual_signature_prompt_presence import (\n"
    "    prompt_contains_term,\n"
    ")\n",
    "from pixelle_video.services.series_visual_signature_prompt_presence import (\n"
    "    prompt_contains_term,\n"
    ")\n"
    "from pixelle_video.services.visible_text_prompt_rewriter import (\n"
    "    NO_VISIBLE_TEXT_NEGATIVE_PROMPT,\n"
    ")\n",
    "visible text import",
)

old_negative = '''        negative_parts.extend(
            (
                "recurring visual signature rendered as a photorealistic mascot",
                "recurring visual signature rendered as a sticker overlay",
                "recurring visual signature rendered as a logo overlay",
                "recurring visual signature rendered as a watermark",
                "duplicate recurring visual signature instances",
            )
        )
        negative_prompt = ", ".join(_dedupe(negative_parts))
'''
new_negative = '''        negative_parts.extend(
            (
                "recurring visual signature rendered as a photorealistic mascot",
                "recurring visual signature rendered as a sticker overlay",
                "recurring visual signature rendered as a logo overlay",
                "recurring visual signature rendered as a watermark",
                "duplicate recurring visual signature instances",
            )
        )
        if signature.profile is not None:
            negative_parts.extend(signature.profile.forbidden_traits)
        if visible_text_policy == "no_visible_text":
            negative_parts.append(NO_VISIBLE_TEXT_NEGATIVE_PROMPT)
        negative_prompt = ", ".join(_dedupe(negative_parts))
'''
text = replace_once(text, old_negative, new_negative, "pass-through negative protections")
service_path.write_text(text, encoding="utf-8")

test_path = Path("tests/services/test_series_visual_signature_projection_service.py")
tests = test_path.read_text(encoding="utf-8")
if "def test_pass_through_reuses_no_visible_text_and_forbidden_trait_protections" in tests:
    raise RuntimeError("review test already present")
tests += '''


def test_pass_through_reuses_no_visible_text_and_forbidden_trait_protections() -> None:
    request = _request(series_visual_signature_role="guide")
    profile = SeriesVisualSignatureProfileSnapshotBuilder().build(
        request=request,
        ip_profile=_ip_profile(forbidden_elements=("blue fur",)),
    )
    llm_prompt = (
        "A worker operates the machine while Dalmatian with black spots, black sunglasses, "
        "red collar, and small round ears points at the process path"
    )

    result = SeriesVisualSignatureProjectionService().project_batch(
        base_prompts=[llm_prompt],
        frame_ids=["frame-1"],
        frame_contexts=[
            {
                "primary_subject": "worker",
                "visible_text_policy": "no_visible_text",
            }
        ],
        request=request,
        profile=profile,
    )

    negative_prompt = result.frames[0].bundle.negative_prompt
    assert "readable text" in negative_prompt
    assert "blue fur" in negative_prompt
'''
test_path.write_text(tests, encoding="utf-8")
