from types import SimpleNamespace

from pixelle_video.models.storyboard import StoryboardConfig
from pixelle_video.pipelines.linear import PipelineContext
from pixelle_video.pipelines.standard import StandardPipeline


def _workflow_info(key: str) -> dict:
    source, name = key.split("/", 1)
    return {
        "name": name,
        "display_name": f"{name} - {source.title()}",
        "source": source,
        "path": f"workflows/{key}",
        "key": key,
    }


class _ResolverService:
    def __init__(self, defaults: dict[str, str]):
        self.defaults = defaults

    def _resolve_workflow(self, workflow=None, workflow_domain=None):
        key = workflow or self.defaults[workflow_domain or "tts"]
        return _workflow_info(key)


class _DummyCore:
    def __init__(self, *, tts_defaults=None, media_defaults=None):
        self.config = {}
        self.llm = object()
        self.video = object()
        self.frame_processor = SimpleNamespace()
        self.tts = _ResolverService(tts_defaults or {"tts": "selfhost/tts_edge.json"})
        self.media = _ResolverService(
            media_defaults
            or {
                "image": "selfhost/image_z_image_turbo.json",
                "video": "runninghub/video_wan2.1_fusionx.json",
            }
        )


def _build_ctx(
    *,
    frame_template: str = "1080x1920/image_default.html",
    tts_inference_mode: str = "comfyui",
    tts_workflow: str | None = None,
    media_workflow: str | None = None,
) -> PipelineContext:
    ctx = PipelineContext(input_text="topic", params={})
    ctx.config = StoryboardConfig(
        media_width=1080,
        media_height=1920,
        task_id="task-1",
        tts_inference_mode=tts_inference_mode,
        tts_workflow=tts_workflow,
        media_workflow=media_workflow,
        frame_template=frame_template,
    )
    return ctx


def test_resolve_asset_execution_mode_uses_staged_mode_for_default_selfhost_image_workflows():
    pipeline = StandardPipeline(_DummyCore())
    ctx = _build_ctx()

    execution_mode = pipeline._resolve_asset_execution_mode(ctx)

    assert execution_mode.template_type == "image"
    assert execution_mode.tts_workflow_key == "selfhost/tts_edge.json"
    assert execution_mode.media_workflow_key == "selfhost/image_z_image_turbo.json"
    assert execution_mode.media_domain == "image"
    assert execution_mode.is_runninghub is False
    assert execution_mode.use_staged_mode is True


def test_resolve_asset_execution_mode_disables_staged_mode_for_explicit_video_workflow():
    pipeline = StandardPipeline(_DummyCore())
    ctx = _build_ctx(media_workflow="selfhost/video_wan2.1_fusionx.json")

    execution_mode = pipeline._resolve_asset_execution_mode(ctx)

    assert execution_mode.template_type == "image"
    assert execution_mode.media_domain == "video"
    assert execution_mode.media_workflow_key == "selfhost/video_wan2.1_fusionx.json"
    assert execution_mode.use_staged_mode is False


def test_resolve_asset_execution_mode_disables_staged_mode_for_local_tts():
    pipeline = StandardPipeline(_DummyCore())
    ctx = _build_ctx(tts_inference_mode="local")

    execution_mode = pipeline._resolve_asset_execution_mode(ctx)

    assert execution_mode.tts_workflow_key is None
    assert execution_mode.use_staged_mode is False
