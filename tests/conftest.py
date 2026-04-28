import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTEST_BASETEMP_ROOT = REPO_ROOT / "_runtime" / "pytest-basetemp"


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    os.environ["PIXELLE_VIDEO_ROOT"] = str(REPO_ROOT)
    if not os.environ.get("PIXELLE_VIDEO_RUNTIME_ROOT"):
        os.environ["PIXELLE_VIDEO_RUNTIME_ROOT"] = str(REPO_ROOT / "_runtime")
    PYTEST_BASETEMP_ROOT.mkdir(parents=True, exist_ok=True)
    config.option.basetemp = str(PYTEST_BASETEMP_ROOT / str(os.getpid()))
