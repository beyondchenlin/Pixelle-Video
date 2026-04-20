from pathlib import Path

from comfykit.comfyui.workflow_parser import WorkflowParser


def test_image_z_image_workflow_is_parseable():
    metadata = WorkflowParser().parse_workflow_file(
        str(Path("workflows/selfhost/image_z_image.json"))
    )

    assert set(metadata.params.keys()) == {"prompt", "width", "height"}


def test_image_z_image_turbo_workflow_is_parseable():
    metadata = WorkflowParser().parse_workflow_file(
        str(Path("workflows/selfhost/image_z_image_turbo.json"))
    )

    assert set(metadata.params.keys()) == {"prompt", "width", "height"}
