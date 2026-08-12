from pathlib import Path

import yaml


def test_hardware_certification_workflow_is_manual_and_branch_restricted():
    workflow = _workflow()
    triggers = workflow[True]
    assert set(triggers) == {"workflow_dispatch"}

    device_job = workflow["jobs"]["hardware-device"]
    assert device_job["if"] == (
        "github.ref == 'refs/heads/dev' || github.ref == 'refs/heads/main'"
    )
    assert device_job["runs-on"] == [
        "self-hosted",
        "render-hardware",
        "${{ matrix.runner_label }}",
    ]
    assert device_job["environment"] == "render-hardware-certification"
    assert device_job["strategy"]["fail-fast"] is False
    assert device_job["strategy"]["matrix"]["include"] == [
        {
            "codec": "h264_nvenc",
            "runner_label": "render-h264-nvenc",
            "qsv_device": "",
            "vaapi_device": "",
        },
        {
            "codec": "h264_qsv",
            "runner_label": "render-h264-qsv",
            "qsv_device": "/dev/dri/renderD128",
            "vaapi_device": "",
        },
        {
            "codec": "h264_vaapi",
            "runner_label": "render-h264-vaapi",
            "qsv_device": "",
            "vaapi_device": "/dev/dri/renderD128",
        },
    ]
    assert device_job["env"] == {
        "PIXELLE_FFMPEG_QSV_DEVICE": "${{ matrix.qsv_device }}",
        "PIXELLE_FFMPEG_VAAPI_DEVICE": "${{ matrix.vaapi_device }}",
    }


def test_hardware_workflow_pins_actions_and_aggregates_same_run_evidence():
    workflow = _workflow()
    for job in workflow["jobs"].values():
        for step in job["steps"]:
            uses = step.get("uses")
            if uses and uses.startswith("actions/"):
                assert len(uses.rsplit("@", 1)[1]) == 40
            if uses and uses.startswith("actions/checkout@"):
                assert step["with"]["persist-credentials"] is False

    aggregate_steps = workflow["jobs"]["aggregate-certification"]["steps"]
    aggregate_command = next(
        step["run"]
        for step in aggregate_steps
        if step["name"] == "Require all supported real devices"
    )
    assert '--expected-revision "${GITHUB_SHA}"' in aggregate_command
    assert '--expected-run-id "${GITHUB_RUN_ID}"' in aggregate_command
    assert "hardware-certify" in aggregate_command


def _workflow() -> dict:
    path = Path(".github/workflows/render-hardware-certification.yml")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload
