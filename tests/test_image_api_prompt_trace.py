from types import SimpleNamespace

import pytest

from api.routers.image import image_generate
from api.schemas.image import ImageGenerateRequest


@pytest.mark.asyncio
async def test_image_generate_writes_final_prompt_trace_before_media_call(tmp_path):
    events: list[tuple[str, str]] = []

    class _FakePixelleVideo:
        prompt_trace_output_dir = tmp_path

        async def media(self, **kwargs):
            trace_files = list(tmp_path.rglob("final_visual_prompts.md"))
            events.append(("media", kwargs["prompt"]))
            assert trace_files
            assert "A quiet moonlit garden" in trace_files[0].read_text(encoding="utf-8")
            return SimpleNamespace(url="generated.png", is_video=False)

    response = await image_generate(
        ImageGenerateRequest(
            prompt="A quiet moonlit garden",
            width=1024,
            height=1024,
            workflow="selfhost/image_z.json",
        ),
        _FakePixelleVideo(),
    )

    assert response.image_path == "generated.png"
    assert events == [("media", "A quiet moonlit garden")]
    trace_content = next(tmp_path.rglob("final_visual_prompts.md")).read_text(encoding="utf-8")
    assert '"source": "api.image.generate"' in trace_content
    assert '"workflow": "selfhost/image_z.json"' in trace_content
    assert '"requested_workflow": "selfhost/image_z.json"' in trace_content


@pytest.mark.asyncio
async def test_image_generate_records_resolved_default_workflow_in_prompt_trace(tmp_path):
    class _FakeMedia:
        def resolve_workflow_key(self, *, workflow=None, media_type="image"):
            assert workflow is None
            assert media_type == "image"
            return "selfhost/default_image_workflow.json"

        async def __call__(self, **kwargs):
            trace_content = next(tmp_path.rglob("final_visual_prompts.md")).read_text(
                encoding="utf-8"
            )
            assert '"requested_workflow": null' in trace_content
            assert '"workflow": "selfhost/default_image_workflow.json"' in trace_content
            return SimpleNamespace(url="generated.png", is_video=False)

    class _FakePixelleVideo:
        prompt_trace_output_dir = tmp_path
        media = _FakeMedia()

    response = await image_generate(
        ImageGenerateRequest(
            prompt="A warm library corner",
            width=768,
            height=512,
            workflow=None,
        ),
        _FakePixelleVideo(),
    )

    assert response.image_path == "generated.png"
