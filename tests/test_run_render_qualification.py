from argparse import Namespace

import pytest

from scripts import run_render_qualification as qualification_cli
from scripts.run_render_qualification import _report_summary


def test_report_summary_preserves_actionable_gate_errors():
    summary = _report_summary(
        {
            "kind": "golden_matrix",
            "ok": False,
            "errors": ["portrait-contain: media boundary drift"],
        }
    )

    assert summary == {
        "kind": "golden_matrix",
        "ok": False,
        "errors": ["portrait-contain: media boundary drift"],
    }


def test_hardware_host_summary_does_not_hide_incomplete_device_coverage():
    summary = _report_summary(
        {
            "kind": "hardware_host_matrix",
            "ok": True,
            "errors": [],
            "passed_codecs": ["h264_nvenc"],
            "unavailable_codecs": ["h264_qsv", "h264_vaapi"],
            "complete_on_host": False,
        }
    )

    assert summary["ok"] is True
    assert summary["passed_codecs"] == ["h264_nvenc"]
    assert summary["unavailable_codecs"] == ["h264_qsv", "h264_vaapi"]
    assert summary["complete_on_host"] is False


def test_release_complete_full_mode_requires_cross_device_evidence(monkeypatch):
    monkeypatch.setattr(
        qualification_cli,
        "parse_args",
        lambda: Namespace(
            mode="full",
            output_root="unused",
            history_task="history",
            hardware_codec=None,
            hardware_evidence_root=None,
            expected_revision=None,
            expected_run_id=None,
            use_gpu=False,
            expectations="expectations.json",
        ),
    )

    with pytest.raises(SystemExit, match="hardware-evidence-root"):
        qualification_cli.main()


def test_hardware_certification_mode_requires_trusted_workflow_run(monkeypatch):
    monkeypatch.setattr(
        qualification_cli,
        "parse_args",
        lambda: Namespace(
            mode="hardware-certify",
            output_root="unused",
            history_task=None,
            hardware_codec=None,
            hardware_evidence_root="evidence",
            expected_revision=None,
            expected_run_id=None,
            use_gpu=False,
            expectations="expectations.json",
        ),
    )

    with pytest.raises(SystemExit, match="expected-run-id"):
        qualification_cli.main()
