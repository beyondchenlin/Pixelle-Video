import os
import sys
import types
from importlib.util import find_spec
from pathlib import Path

import pytest

from tests.support.test_client import close_test_clients

REPO_ROOT = Path(__file__).resolve().parents[1]


def _pytest_basetemp_root() -> Path:
    configured_runtime = os.environ.get("PIXELLE_VIDEO_RUNTIME_ROOT", "").strip()
    runtime_root = Path(configured_runtime) if configured_runtime else REPO_ROOT / "_runtime"
    return runtime_root / "pytest-basetemp"


def _has_comfykit_workflow_parser() -> bool:
    try:
        from comfykit.comfyui.workflow_parser import WorkflowParser  # noqa: F401
    except Exception:
        return False
    return True


HAS_COMFYKIT_WORKFLOW_PARSER = _has_comfykit_workflow_parser()
HAS_SQLALCHEMY = find_spec("sqlalchemy") is not None


def _install_optional_dependency_stubs() -> None:
    if HAS_COMFYKIT_WORKFLOW_PARSER:
        return

    module = sys.modules.get("comfykit")
    if module is None:
        module = types.ModuleType("comfykit")
        module.__path__ = []  # type: ignore[attr-defined]

    class ComfyKit:  # pragma: no cover - test dependency shim
        pass

    module.ComfyKit = getattr(module, "ComfyKit", ComfyKit)
    sys.modules["comfykit"] = module

    comfyui_module = types.ModuleType("comfykit.comfyui")
    comfyui_module.__path__ = []  # type: ignore[attr-defined]
    parser_module = types.ModuleType("comfykit.comfyui.workflow_parser")

    class WorkflowParser:  # pragma: no cover - test dependency shim
        def parse_workflow_file(self, path):
            raise RuntimeError(
                "comfykit.comfyui.workflow_parser is unavailable in this test environment"
            )

    parser_module.WorkflowParser = WorkflowParser
    comfyui_module.workflow_parser = parser_module
    module.comfyui = comfyui_module
    sys.modules["comfykit.comfyui"] = comfyui_module
    sys.modules["comfykit.comfyui.workflow_parser"] = parser_module


_install_optional_dependency_stubs()

repo_root_path = str(REPO_ROOT)
if sys.path[0] != repo_root_path:
    sys.path.insert(0, repo_root_path)


@pytest.fixture(autouse=True)
def _close_registered_test_clients():
    try:
        yield
    finally:
        close_test_clients()


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    os.environ["PIXELLE_VIDEO_ROOT"] = str(REPO_ROOT)
    if not os.environ.get("PIXELLE_VIDEO_RUNTIME_ROOT"):
        os.environ["PIXELLE_VIDEO_RUNTIME_ROOT"] = str(REPO_ROOT / "_runtime")
    pytest_basetemp_root = _pytest_basetemp_root()
    pytest_basetemp_root.mkdir(parents=True, exist_ok=True)
    config.option.basetemp = str(pytest_basetemp_root / str(os.getpid()))


def pytest_ignore_collect(collection_path, config):
    path = Path(str(collection_path))
    if path.name == "test_selfhost_workflows.py" and not HAS_COMFYKIT_WORKFLOW_PARSER:
        return True
    if path.name == "test_postgres_task_store_schema.py" and not HAS_SQLALCHEMY:
        return True
    return False
