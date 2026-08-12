from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pixelle_video.services.render_hardware_certification import (
    HARDWARE_CERTIFICATION_REPORT_VERSION,
    HARDWARE_HOST_REPORT_VERSION,
    HardwareCertificationAggregator,
    build_file_evidence,
    sanitize_hardware_diagnostic,
)
from pixelle_video.utils.ffmpeg_encoder import supported_hardware_h264_codecs


class _AcceptingProbe:
    def __init__(self) -> None:
        self.paths: list[Path] = []

    def validate(self, **kwargs):
        self.paths.append(Path(kwargs["output_path"]))
        return object()


def test_cross_device_certification_requires_and_verifies_every_supported_codec(
    tmp_path,
):
    evidence_root = tmp_path / "evidence"
    revision = "a" * 40
    run_id = "12345"
    for codec in supported_hardware_h264_codecs():
        _write_host_report(
            evidence_root=evidence_root,
            codec=codec,
            revision=revision,
            run_id=run_id,
        )
    probe = _AcceptingProbe()

    report = HardwareCertificationAggregator(probe=probe).aggregate(
        evidence_root=evidence_root,
        output_path=tmp_path / "hardware_certification_report.json",
        expected_revision=revision,
        expected_run_id=run_id,
    )

    assert report["version"] == HARDWARE_CERTIFICATION_REPORT_VERSION
    assert report["ok"] is True
    assert report["passed_codecs"] == list(supported_hardware_h264_codecs())
    assert report["missing_codecs"] == []
    assert len(probe.paths) == 3


def test_cross_device_certification_fails_when_one_device_report_is_missing(tmp_path):
    evidence_root = tmp_path / "evidence"
    revision = "b" * 40
    for codec in ("h264_nvenc", "h264_vaapi"):
        _write_host_report(
            evidence_root=evidence_root,
            codec=codec,
            revision=revision,
            run_id="77",
        )

    report = HardwareCertificationAggregator(probe=_AcceptingProbe()).aggregate(
        evidence_root=evidence_root,
        output_path=tmp_path / "hardware_certification_report.json",
        expected_revision=revision,
        expected_run_id="77",
    )

    assert report["ok"] is False
    assert report["missing_codecs"] == ["h264_qsv"]
    assert any("h264_qsv" in error for error in report["errors"])


def test_cross_device_certification_rejects_mixed_revision_and_workflow_evidence(
    tmp_path,
):
    evidence_root = tmp_path / "evidence"
    revision = "c" * 40
    for codec in supported_hardware_h264_codecs():
        _write_host_report(
            evidence_root=evidence_root,
            codec=codec,
            revision=("d" * 40 if codec == "h264_qsv" else revision),
            run_id=("old-run" if codec == "h264_vaapi" else "current-run"),
        )

    report = HardwareCertificationAggregator(probe=_AcceptingProbe()).aggregate(
        evidence_root=evidence_root,
        output_path=tmp_path / "hardware_certification_report.json",
        expected_revision=revision,
        expected_run_id="current-run",
    )

    assert report["ok"] is False
    assert report["missing_codecs"] == ["h264_qsv", "h264_vaapi"]
    assert any("source revision mismatch" in error for error in report["errors"])
    assert any("workflow run mismatch" in error for error in report["errors"])


def test_cross_device_certification_rejects_artifact_path_escape(tmp_path):
    evidence_root = tmp_path / "evidence"
    revision = "e" * 40
    report_path = _write_host_report(
        evidence_root=evidence_root,
        codec="h264_nvenc",
        revision=revision,
        run_id="88",
    )
    outside = evidence_root / "outside.mp4"
    outside.write_bytes(b"outside")
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    payload["results"][0]["artifact"] = {
        "relative_path": "../outside.mp4",
        "size_bytes": outside.stat().st_size,
        "sha256": hashlib.sha256(outside.read_bytes()).hexdigest(),
    }
    report_path.write_text(json.dumps(payload), encoding="utf-8")

    report = HardwareCertificationAggregator(probe=_AcceptingProbe()).aggregate(
        evidence_root=evidence_root,
        output_path=tmp_path / "hardware_certification_report.json",
        expected_revision=revision,
        expected_run_id="88",
    )

    assert report["ok"] is False
    assert any("escapes its report root" in error for error in report["errors"])


def test_cross_device_certification_rejects_tampered_artifact_digest(tmp_path):
    evidence_root = tmp_path / "evidence"
    revision = "f" * 40
    report_path = _write_host_report(
        evidence_root=evidence_root,
        codec="h264_nvenc",
        revision=revision,
        run_id="99",
    )
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    artifact_path = report_path.parent / payload["results"][0]["artifact"][
        "relative_path"
    ]
    artifact_path.write_bytes(b"tampered")

    report = HardwareCertificationAggregator(probe=_AcceptingProbe()).aggregate(
        evidence_root=evidence_root,
        output_path=tmp_path / "hardware_certification_report.json",
        expected_revision=revision,
        expected_run_id="99",
    )

    assert report["ok"] is False
    assert any("does not match report" in error for error in report["errors"])


def test_cross_device_certification_rejects_nonportable_probe_path(tmp_path):
    evidence_root = tmp_path / "evidence"
    revision = "1" * 40
    report_path = _write_host_report(
        evidence_root=evidence_root,
        codec="h264_nvenc",
        revision=revision,
        run_id="100",
    )
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    result = payload["results"][0]
    probe_path = report_path.parent / result["probe_artifact"]["relative_path"]
    probe_payload = json.loads(probe_path.read_text(encoding="utf-8"))
    probe_payload["path"] = "C:/runner/private/final.mp4"
    probe_payload.pop("path_kind")
    probe_path.write_text(json.dumps(probe_payload), encoding="utf-8")
    result["probe_artifact"] = build_file_evidence(
        path=probe_path,
        evidence_root=report_path.parent,
    )
    report_path.write_text(json.dumps(payload), encoding="utf-8")

    report = HardwareCertificationAggregator(probe=_AcceptingProbe()).aggregate(
        evidence_root=evidence_root,
        output_path=tmp_path / "hardware_certification_report.json",
        expected_revision=revision,
        expected_run_id="100",
    )

    assert report["ok"] is False
    assert any("probe path is not portable" in error for error in report["errors"])


def test_uploaded_hardware_diagnostic_redacts_private_roots_and_is_bounded(
    tmp_path,
):
    private_repo = tmp_path / "private-user" / "repository"
    private_output = tmp_path / "private-user" / "evidence"
    message = f"failed at {private_repo} then {private_output}: " + ("x" * 3000)

    sanitized = sanitize_hardware_diagnostic(
        message,
        private_roots=(private_repo, private_output),
    )

    assert str(tmp_path) not in sanitized
    assert "<repo>" in sanitized
    assert "<private-root>" in sanitized
    assert len(sanitized) == 2000


def test_hardware_diagnostic_prefers_specific_private_root_over_parent(
    monkeypatch,
):
    monkeypatch.setenv("GITHUB_WORKSPACE", "/home/runner/work/project")
    private_repo = Path("/home/runner/work/project/repository")
    private_output = Path("/home/runner/work/project/evidence")

    sanitized = sanitize_hardware_diagnostic(
        f"{private_repo} {private_output}",
        private_roots=(private_repo, private_output),
    )

    assert sanitized == "<repo> <private-root>"


def test_cross_device_certification_rejects_wrong_vendor_identity(tmp_path):
    evidence_root = tmp_path / "evidence"
    revision = "2" * 40
    report_path = _write_host_report(
        evidence_root=evidence_root,
        codec="h264_nvenc",
        revision=revision,
        run_id="101",
    )
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    payload["host"]["hardware_devices"] = ["Intel Graphics"]
    report_path.write_text(json.dumps(payload), encoding="utf-8")

    report = HardwareCertificationAggregator(probe=_AcceptingProbe()).aggregate(
        evidence_root=evidence_root,
        output_path=tmp_path / "hardware_certification_report.json",
        expected_revision=revision,
        expected_run_id="101",
    )

    assert report["ok"] is False
    assert any("does not match" in error for error in report["errors"])


def _write_host_report(
    *,
    evidence_root: Path,
    codec: str,
    revision: str,
    run_id: str,
) -> Path:
    report_root = evidence_root / f"hardware-{codec}"
    artifact = report_root / "hardware" / f"{codec}.mp4"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(f"final-video-{codec}".encode())
    probe_path = artifact.with_name(f"{codec}.render_probe.json")
    probe_path.write_text(
        json.dumps(
            {
                "ok": True,
                "path": f"hardware/{codec}.mp4",
                "path_kind": "relative_to_report_root",
                "encoder_backend": codec,
                "lossy_encode_count": 1,
            }
        ),
        encoding="utf-8",
    )
    payload = {
        "version": HARDWARE_HOST_REPORT_VERSION,
        "kind": "hardware_host_matrix",
        "source_revision": revision,
        "source_tree_clean": True,
        "host": {
            "operating_system": "TestOS",
            "operating_system_release": "1",
            "architecture": "x86_64",
            "ffmpeg_version": "ffmpeg test",
            "hardware_devices": [
                {
                    "h264_nvenc": "NVIDIA test device",
                    "h264_qsv": "Intel test device",
                    "h264_vaapi": "driver=i915 | pci_id=8086:0000",
                }[codec]
            ],
        },
        "ci": {
            "provider": "github_actions",
            "run_id": run_id,
            "run_attempt": "1",
            "job": f"hardware-{codec}",
        },
        "supported_codecs": list(supported_hardware_h264_codecs()),
        "required_codec": codec,
        "requested_codecs": [codec],
        "results": [
            {
                "codec": codec,
                "hardware": True,
                "available_on_host": True,
                "status": "passed",
                "measurement": {
                    "elapsed_seconds": 1.0,
                    "peak_rss_bytes": 1024,
                },
                "artifact": build_file_evidence(
                    path=artifact,
                    evidence_root=report_root,
                ),
                "probe_artifact": build_file_evidence(
                    path=probe_path,
                    evidence_root=report_root,
                ),
                "encoder_backend": codec,
                "ok": True,
            }
        ],
        "available_codecs": [codec],
        "unavailable_codecs": [],
        "passed_codecs": [codec],
        "host_ok": True,
        "complete_on_host": False,
        "errors": [],
        "ok": True,
    }
    report_path = report_root / "hardware_report.json"
    report_path.write_text(json.dumps(payload), encoding="utf-8")
    return report_path
