from __future__ import annotations

import argparse
import json
from pathlib import Path

from pixelle_video.services.render_qualification import RenderQualificationSuite


def _report_summary(report: dict) -> dict:
    return {
        "kind": report["kind"],
        "ok": report["ok"],
        "errors": list(report.get("errors") or []),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run real final-video qualification gates.")
    parser.add_argument(
        "mode",
        choices=("golden", "long", "performance", "hardware", "history", "full"),
    )
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--history-task")
    parser.add_argument("--use-gpu", action="store_true")
    parser.add_argument(
        "--expectations",
        default="tests/fixtures/render_qualification/golden_expectations.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    suite = RenderQualificationSuite(output_root=args.output_root)
    reports = []
    if args.mode in {"golden", "full"}:
        reports.append(
            suite.run_golden_matrix(
                expectations_path=args.expectations,
                use_gpu=args.use_gpu,
            )
        )
    if args.mode in {"long", "full"}:
        reports.append(suite.run_long_duration_matrix(use_gpu=args.use_gpu))
    if args.mode in {"performance", "full"}:
        reports.append(suite.run_performance_gate())
    if args.mode in {"hardware", "full"}:
        reports.append(suite.run_hardware_matrix())
    if args.mode in {"history", "full"}:
        if not args.history_task:
            raise SystemExit("--history-task is required for history and full modes")
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
