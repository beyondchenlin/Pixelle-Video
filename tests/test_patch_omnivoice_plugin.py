"""Tests for patch_omnivoice_plugin."""

import importlib.util
import os
import sys
import types
from pathlib import Path
from unittest import mock

import pytest

from tools.patch_omnivoice_plugin import (
    OMNIVOICE_NODE_CLASSES,
    OMNIVOICE_PLUGIN_ENV,
    STABLE_PIXELLE_OMNIVOICE_ROUTES,
    PatchResult,
    main,
    patch_plugin,
    resolve_target_path,
)


def test_resolve_target_path_prefers_arg_over_env():
    expected = Path("/from/arg")
    with mock.patch.dict(os.environ, {OMNIVOICE_PLUGIN_ENV: "/from/env"}):
        result = resolve_target_path("/from/arg")
    assert result == expected


def test_resolve_target_path_falls_back_to_env():
    expected = Path("/from/env")
    with mock.patch.dict(os.environ, {OMNIVOICE_PLUGIN_ENV: "/from/env"}):
        result = resolve_target_path(None)
    assert result == expected


def test_resolve_target_path_raises_when_missing():
    with mock.patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError) as exc_info:
            resolve_target_path(None)
    assert OMNIVOICE_PLUGIN_ENV in str(exc_info.value)


def test_patch_plugin_creates_routes_file(tmp_path: Path):
    """Test that patch_plugin creates the pixelle_routes.py file."""
    (tmp_path / "__init__.py").write_text("# init\n")
    result = patch_plugin(tmp_path)
    routes_file = tmp_path / "pixelle_routes.py"
    assert routes_file.exists()
    assert routes_file in result.changed_files


def test_patch_plugin_is_idempotent(tmp_path: Path):
    """Test that patch_plugin can be run multiple times without issues."""
    (tmp_path / "__init__.py").write_text("# init\n")
    # First patch
    patch_plugin(tmp_path)
    # Second patch should report no changes
    result = patch_plugin(tmp_path)
    assert not result.changed_files


def test_main_requires_target_or_env():
    """Test that main raises ValueError when no target is provided."""
    with mock.patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError) as exc_info:
            main([])
    assert OMNIVOICE_PLUGIN_ENV in str(exc_info.value)


def test_omnivoice_node_classes_defined():
    """Verify known OmniVoice node classes are documented."""
    assert "OmniVoiceLongformTTS" in OMNIVOICE_NODE_CLASSES
    assert "OmniVoiceVoiceCloneTTS" in OMNIVOICE_NODE_CLASSES


def test_stable_routes_contains_contract_revision():
    """Verify STABLE_PIXELLE_OMNIVOICE_ROUTES contains contract revision constant."""
    assert "_PIXELLE_OMNIVOICE_RELEASE_CONTRACT_REVISION = 1" in STABLE_PIXELLE_OMNIVOICE_ROUTES


def test_stable_routes_contains_node_classes():
    """Verify STABLE_PIXELLE_OMNIVOICE_ROUTES contains node class names."""
    assert "OmniVoiceLongformTTS" in STABLE_PIXELLE_OMNIVOICE_ROUTES
    assert "OmniVoiceVoiceCloneTTS" in STABLE_PIXELLE_OMNIVOICE_ROUTES


def test_stable_routes_contains_release_endpoint():
    """Verify STABLE_PIXELLE_OMNIVOICE_ROUTES contains the release endpoint."""
    assert '/pixelle/omnivoice/free' in STABLE_PIXELLE_OMNIVOICE_ROUTES


def test_stable_routes_contains_health_endpoint():
    """Verify STABLE_PIXELLE_OMNIVOICE_ROUTES contains the health endpoint."""
    assert '/pixelle/omnivoice/health' in STABLE_PIXELLE_OMNIVOICE_ROUTES


def _load_generated_routes(
    monkeypatch,
    cuda_allocated=(1_000_000_000, 100_000_000),
    cuda_reserved=(1_500_000_000, 500_000_000),
):
    """Load generated routes with mocked CUDA state."""
    spec = importlib.util.spec_from_loader("pixelle_routes", loader=None)
    module = importlib.util.module_from_spec(spec)

    class FakeCUDA:
        def __init__(self):
            self._allocated = list(cuda_allocated)
            self._reserved = list(cuda_reserved)

        def is_available(self):
            return True

        def current_device(self):
            return 0

        def memory_allocated(self, device):
            return self._allocated.pop(0)

        def memory_reserved(self, device):
            return self._reserved.pop(0)

        def synchronize(self):
            pass

        def empty_cache(self):
            pass

        def ipc_collect(self):
            pass

    class FakeModelManagement:
        def unload_all_models(self):
            pass

        def soft_empty_cache(self):
            pass

    class FakeRoutes:
        def get(self, _path):
            return lambda handler: handler

        def post(self, _path):
            return lambda handler: handler

    fake_torch_instance = types.SimpleNamespace(cuda=FakeCUDA())
    comfy_module = types.ModuleType("comfy")
    comfy_module.model_management = FakeModelManagement()
    server_module = types.SimpleNamespace(
        PromptServer=types.SimpleNamespace(instance=types.SimpleNamespace(routes=FakeRoutes()))
    )

    module.torch = fake_torch_instance
    module.gc = __import__("gc")
    module.sys = sys

    # Mock imports for the routes module
    orig_torch = sys.modules.get("torch")
    orig_comfy = sys.modules.get("comfy")
    orig_server = sys.modules.get("server")
    sys.modules["torch"] = fake_torch_instance
    sys.modules["comfy"] = comfy_module
    sys.modules["server"] = server_module

    # Load routes content
    from tools.patch_omnivoice_plugin import STABLE_PIXELLE_OMNIVOICE_ROUTES

    exec(STABLE_PIXELLE_OMNIVOICE_ROUTES, module.__dict__)

    # Restore imports
    if orig_torch:
        sys.modules["torch"] = orig_torch
    else:
        del sys.modules["torch"]
    if orig_comfy:
        sys.modules["comfy"] = orig_comfy
    elif "comfy" in sys.modules:
        del sys.modules["comfy"]
    if orig_server:
        sys.modules["server"] = orig_server
    elif "server" in sys.modules:
        del sys.modules["server"]

    return module


def test_generated_route_returns_cuda_snapshot_fields(monkeypatch):
    """Test that the route returns proper CUDA memory fields."""
    module = _load_generated_routes(
        monkeypatch,
        cuda_allocated=[1_000_000_000, 100_000_000],
        cuda_reserved=[1_500_000_000, 500_000_000],
    )

    result = module.unload_omnivoice_models()

    # Verify CUDA memory fields are present
    assert "cuda_allocated_before" in result
    assert "cuda_allocated_after" in result
    assert "cuda_reserved_before" in result
    assert "cuda_reserved_after" in result
    assert result["cuda_allocated_before"] == 1_000_000_000
    assert result["cuda_allocated_after"] == 100_000_000
    assert result["contract_revision"] == 1


def test_generated_route_returns_expected_fields(monkeypatch):
    """Test that the route returns expected response fields."""
    module = _load_generated_routes(monkeypatch)

    result = module.unload_omnivoice_models()

    # Verify expected fields
    assert "protocol_version" in result
    assert "contract_revision" in result
    assert "extension" in result
    assert "released" in result
    assert "safe_to_continue" in result
    assert "release_confirmation_reason" in result
    assert "objects_seen" in result
    assert "errors" in result
    assert result["extension"] == "omnivoice"
    assert result["contract_revision"] == 1


def test_generated_health_endpoint_returns_expected_fields(monkeypatch):
    """Test that the health endpoint returns expected fields."""
    module = _load_generated_routes(monkeypatch)

    result = module.omnivoice_release_health()

    assert "protocol_version" in result
    assert "contract_revision" in result
    assert "ok" in result
    assert "extension" in result
    assert "release_endpoint" in result
    assert result["protocol_version"] == 2
    assert result["contract_revision"] == 1
    assert result["ok"] is True
    assert result["extension"] == "omnivoice"


def test_find_omnivoice_node_classes_finds_known_classes():
    """Test _find_omnivoice_node_classes finds known classes."""
    module = _load_generated_routes(None)

    # Create a mock OmniVoice class
    class OmniVoiceLongformTTS:
        pass

    # Inject into sys.modules
    mock_module = types.ModuleType("mock_omnivoice_nodes")
    mock_module.OmniVoiceLongformTTS = OmniVoiceLongformTTS
    sys.modules["mock_omnivoice_nodes"] = mock_module

    try:
        classes = module._find_omnivoice_node_classes()
        assert "mock_omnivoice_nodes.OmniVoiceLongformTTS" in classes
    finally:
        del sys.modules["mock_omnivoice_nodes"]
