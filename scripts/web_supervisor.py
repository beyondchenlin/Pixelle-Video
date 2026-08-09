from __future__ import annotations

import sys
from pathlib import Path

from pixelle_video.services.application_supervisor import (
    ApplicationSupervisorError,
    run_application_stack,
)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    try:
        return run_application_stack(repo_root)
    except ApplicationSupervisorError as exc:
        print(f"[Pixelle] Application startup failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
