from __future__ import annotations

import argparse
import json
from pathlib import Path

from pixelle_video.services.render_qualification import RenderQualificationSuite
from pixelle_video.utils.ffmpeg_encoder import supported_hardware_h264_codecs


def _report_summary(report: dict) -> dict:
    summary = {
        "kind": report["kind"],
        "ok": report["ok"],
        "errors": list(report.get("errors") or []),
    }
    if report["kind"] == "hardware_host_matrix":
        summary.update(
            {
                "passed_codecs": list(report.get("passed_codecs") or []),
                "unavailable_codecs": list(
                    report.get("unavailable_codecs") or []
                ),
                "complete_on_host": report.get("complete_on_host") is True,
            }
        )
    elif report["kind"] == "hardware_cross_device_certification":
        summary.update(
            {
                "passed_codecs": list(report.get("passed_codecs") or []),
                "missing_codecs": list(report.get("missing_codecs") or []),
            }
        )
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run real final-video qualification gates.")
    parser.add_argument(
        "mode",
        choices=(
            "golden",
            "long",
            "performance",
            "hardware",
            "hardware-certify",
            "history",
            "host-full",
            "full",
        ),
    )
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--history-task")
    parser.add_argument(
        "--hardware-codec",
        choices=supported_hardware_h264_codecs(),
        help="Require one exact hardware codec; unavailable devices fail closed.",
    )
    parser.add_argument("--hardware-evidence-root")
    parser.add_argument("--expected-revision")
    parser.add_argument("--expected-run-id")
    parser.add_argument("--use-gpu", action="store_true")
    parser.add_argument(
        "--expectations",
        default="tests/fixtures/render_qualification/golden_expectations.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.hardware_codec and args.mode != "hardware":
        raise SystemExit("--hardware-codec is valid only in hardware mode")
    certification_options = (
        args.hardware_evidence_root,
        args.expected_revision,
        args.expected_run_id,
    )
    if any(certification_options) and args.mode not in {
        "hardware-certify",
        "full",
    }:
        raise SystemExit(
            "hardware certification options are valid only in "
            "hardware-certify or full mode"
        )
    if args.mode == "full":
        if not args.hardware_evidence_root:
            raise SystemExit(
                "--hardware-evidence-root is required for release-complete full mode"
            )
        if not args.expected_run_id:
            raise SystemExit(
                "--expected-run-id is required for release-complete full mode"
            )
    if args.mode == "hardware-certify" and not args.expected_run_id:
        raise SystemExit(
            "--expected-run-id is required for hardware-certify mode"
        )
    suite = RenderQualificationSuite(output_root=args.output_root)
    reports = []
    full_modes = {"host-full", "full"}
    if args.mode == "golden" or args.mode in full_modes:
        reports.append(
            suite.run_golden_matrix(
                expectations_path=args.expectations,
                use_gpu=args.use_gpu,
            )
        )
    if args.mode == "long" or args.mode in full_modes:
        reports.append(suite.run_long_duration_matrix(use_gpu=args.use_gpu))
    if args.mode == "performance" or args.mode in full_modes:
        reports.append(suite.run_performance_gate())
    if args.mode in {"hardware", "host-full"}:
        reports.append(
            suite.run_hardware_matrix(required_codec=args.hardware_codec)
        )
    if args.mode in {"hardware-certify", "full"}:
        if not args.hardware_evidence_root:
            raise SystemExit(
                "--hardware-evidence-root is required for hardware-certify mode"
            )
        reports.append(
            suite.aggregate_hardware_reports(
                evidence_root=args.hardware_evidence_root,
                expected_revision=args.expected_revision,
                expected_run_id=args.expected_run_id,
            )
        )
    if args.mode == "history" or args.mode in full_modes:
        if not args.history_task:
            raise SystemExit(
                "--history-task is required for history, host-full, and full modes"
            )
        reports.append(
            suite.run_historical_task(
                task_dir=args.history_task,
                use_gpu=args.use_gpu,
            )
        )
    print(
        json.dumps(
            {
                "reports": [
                    _report_summary(item) for item in reports
                ],
                "output_root": str(Path(args.output_root).resolve()),
                "ok": all(item["ok"] for item in reports),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if all(item["ok"] for item in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
