from types import SimpleNamespace

import pytest

from api.routers.image import image_generate
from api.schemas.content import ImagePromptGenerateResponse
from api.schemas.image import ImageGenerateRequest


@pytest.mark.asyncio
async def test_image_generate_writes_final_prompt_trace_before_media_call(tmp_path):
    events: list[tuple[str, str]] = []

    class _FakeMedia:
        def resolve_workflow_key(self, *, workflow=None, media_type="image"):
            assert workflow == "selfhost/image_z.json"
            assert media_type == "image"
            return "selfhost/image_z.json"

        async def __call__(self, **kwargs):
            trace_files = list(tmp_path.rglob("final_visual_prompts.md"))
            events.append(("media", kwargs["prompt"]))
            assert trace_files
            assert "A quiet moonlit garden" in trace_files[0].read_text(encoding="utf-8")
            return SimpleNamespace(url="generated.png", is_video=False)

    class _FakePixelleVideo:
        prompt_trace_output_dir = tmp_path
        media = _FakeMedia()

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


@pytest.mark.asyncio
async def test_image_generate_persists_upstream_content_prompt_provenance(tmp_path):
    upstream = ImagePromptGenerateResponse(
        image_prompts=["A quiet moonlit garden"],
        negative_prompt="blur, watermark",
        planning_snapshot={
            "llm_trace_refs": [
                {"trace_id": "trace-image-1", "stage": "image_prompt_batch"}
            ],
            "final_visual_prompt_template": {"prompt_id": "final_visual_prompt"},
        },
        prompt_plan_bundle={
            "storyboard_plan_id": "plan-1",
            "prompt_plans": [
                {
                    "prompt_plan_id": "prompt-plan-1",
                    "frame_id": "frame-1",
                    "final_prompt": "A quiet moonlit garden",
                }
            ],
        },
        llm_trace_refs=[{"trace_id": "trace-image-1", "stage": "image_prompt_batch"}],
    )

    class _FakeMedia:
        def resolve_workflow_key(self, *, workflow=None, media_type="image"):
            assert workflow == "selfhost/image_z.json"
            assert media_type == "image"
            return "selfhost/image_z.json"

        async def __call__(self, **kwargs):
            assert kwargs["negative_prompt"] == "blur, watermark"
            trace_context = kwargs["media_prompt_trace_context"]
            assert trace_context["negative_prompt"] == "blur, watermark"
            trace_content = next(tmp_path.rglob("final_visual_prompts.md")).read_text(
                encoding="utf-8"
            )
            assert '"upstream_prompt_provenance"' in trace_content
            assert '"trace_id": "trace-image-1"' in trace_content
            assert '"prompt_plan_id": "prompt-plan-1"' in trace_content
            assert "```text\nblur, watermark\n```" in trace_content
            return SimpleNamespace(url="generated.png", is_video=False)

    class _FakePixelleVideo:
        prompt_trace_output_dir = tmp_path
        media = _FakeMedia()

    response = await image_generate(
        ImageGenerateRequest(
            prompt=upstream.image_prompts[0],
            negative_prompt=upstream.negative_prompt,
            planning_snapshot=upstream.planning_snapshot,
            prompt_plan_bundle=upstream.prompt_plan_bundle,
            llm_trace_refs=upstream.llm_trace_refs,
            width=1024,
            height=1024,
            workflow="selfhost/image_z.json",
        ),
        _FakePixelleVideo(),
    )

    assert response.image_path == "generated.png"
