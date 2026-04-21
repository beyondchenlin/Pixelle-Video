import json

from pixelle_video.utils.workflow_capabilities import (
    get_workflow_capabilities,
    infer_media_domain_from_workflow,
)


def test_get_workflow_capabilities_reads_negative_prompt_from_selfhost_metadata(monkeypatch, tmp_path):
    workflow_path = tmp_path / "image_test.json"
    workflow_path.write_text("{}", encoding="utf-8")

    class _Metadata:
        params = {"prompt": object(), "negative_prompt": object()}

    class _Parser:
        def parse_workflow_file(self, path):
            assert path == str(workflow_path)
            return _Metadata()

    monkeypatch.setattr("pixelle_video.utils.workflow_capabilities.WorkflowParser", lambda: _Parser())

    caps = get_workflow_capabilities(
        {
            "source": "selfhost",
            "path": str(workflow_path),
            "key": "selfhost/image_test.json",
        }
    )

    assert caps.supports_negative_prompt is True


def test_get_workflow_capabilities_defaults_wrapper_optional_fields_to_false(tmp_path):
    workflow_path = tmp_path / "image_wrapper.json"
    workflow_path.write_text(
        json.dumps({"source": "runninghub", "workflow_id": "wf-1"}),
        encoding="utf-8",
    )

    caps = get_workflow_capabilities(
        {
            "source": "runninghub",
            "path": str(workflow_path),
            "key": "runninghub/image_wrapper.json",
        }
    )

    assert caps.supports_negative_prompt is False


def test_infer_media_domain_from_workflow_handles_video_prefix():
    assert infer_media_domain_from_workflow("selfhost/video_demo.json") == "video"
    assert infer_media_domain_from_workflow("selfhost/image_demo.json") == "image"
    assert infer_media_domain_from_workflow(None) == "image"
