import os
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTEST_BASETEMP_ROOT = REPO_ROOT / "_runtime" / "pytest-basetemp"



def _install_optional_dependency_stubs() -> None:
    if "comfykit" not in sys.modules:
        module = types.ModuleType("comfykit")

        class ComfyKit:  # pragma: no cover - test dependency shim
            pass

        module.ComfyKit = ComfyKit
        sys.modules["comfykit"] = module


_install_optional_dependency_stubs()

repo_root_path = str(REPO_ROOT)
if sys.path[0] != repo_root_path:
    sys.path.insert(0, repo_root_path)


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    os.environ["PIXELLE_VIDEO_ROOT"] = str(REPO_ROOT)
    if not os.environ.get("PIXELLE_VIDEO_RUNTIME_ROOT"):
        os.environ["PIXELLE_VIDEO_RUNTIME_ROOT"] = str(REPO_ROOT / "_runtime")
    PYTEST_BASETEMP_ROOT.mkdir(parents=True, exist_ok=True)
    config.option.basetemp = str(PYTEST_BASETEMP_ROOT / str(os.getpid()))
