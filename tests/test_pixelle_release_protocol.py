import importlib.util
from pathlib import Path

import pytest

PROTOCOL_PATH = (
    Path(__file__).resolve().parents[1]
    / "tools"
    / "comfyui"
    / "custom_nodes"
    / "ComfyUI-Pixelle-Release-Protocol"
    / "protocol.py"
)
PLUGIN_INIT_PATH = PROTOCOL_PATH.with_name("__init__.py")


def _load_protocol_module():
    spec = importlib.util.spec_from_file_location(
        "pixelle_release_protocol_under_test",
        PROTOCOL_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_plugin_registers_only_collision_free_unified_routes():
    source = PLUGIN_INIT_PATH.read_text(encoding="utf-8")

    assert 'routes.get("/pixelle/health")' in source
    assert 'routes.post("/pixelle/free")' in source
    assert 'routes.get("/pixelle/omnivoice/health")' not in source
    assert 'routes.post("/pixelle/omnivoice/free")' not in source
    assert "get_current_queue_volatile" in source
    assert '"error": "queue_busy"' in source
    assert "status=409" in source


@pytest.mark.parametrize(
    ("function_name", "extension", "contract_revision"),
    (
        ("omnivoice_health", "omnivoice", 1),
        ("gguf_health", "gguf", 2),
        ("indextts2_health", "indextts2", 1),
    ),
)
def test_extension_health_is_constant_time_capability_metadata(
    monkeypatch,
    function_name,
    extension,
    contract_revision,
):
    protocol = _load_protocol_module()
    monkeypatch.setattr(
        protocol,
        "_find_model_objects",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("health must not inspect model objects")
        ),
    )
    monkeypatch.setattr(
        protocol,
        "_cuda_snapshot",
        lambda: (_ for _ in ()).throw(
            AssertionError("health must not access accelerator state")
        ),
    )

    result = getattr(protocol, function_name)()

    assert result == {
        "protocol_version": 2,
        "contract_revision": contract_revision,
        "ok": True,
        "extension": extension,
        "health_endpoint": "/pixelle/health",
        "release_endpoint": "/pixelle/free",
        "legacy_health_endpoint": f"/pixelle/{extension}/health",
        "legacy_release_endpoint": f"/pixelle/{extension}/free",
        "safe_to_continue": True,
    }


def test_unified_health_exposes_complete_extension_contract_without_accelerator_access(
    monkeypatch,
):
    protocol = _load_protocol_module()
    monkeypatch.setattr(
        protocol,
        "_cuda_snapshot",
        lambda: (_ for _ in ()).throw(
            AssertionError("capability discovery must not access accelerator state")
        ),
    )

    result = protocol.unified_health()

    assert result["protocol_version"] == 2
    assert result["contract_revision"] == 1
    assert set(result["extensions"]) == {"omnivoice", "gguf", "indextts2"}
    assert result["extensions"]["omnivoice"]["release_endpoint"] == "/pixelle/free"
    assert result["extensions"]["gguf"]["contract_revision"] == 2


def test_unified_release_only_runs_explicitly_requested_extensions(monkeypatch):
    protocol = _load_protocol_module()
    calls = []

    def _result(extension):
        calls.append(extension)
        return {
            "protocol_version": 2,
            "contract_revision": 1,
            "extension": extension,
            "released": True,
            "safe_to_continue": True,
            "residual_objects": [],
            "errors": [],
        }

    monkeypatch.setattr(protocol, "omnivoice_release", lambda: _result("omnivoice"))
    monkeypatch.setattr(protocol, "gguf_release", lambda: _result("gguf"))
    monkeypatch.setattr(protocol, "indextts2_release", lambda: _result("indextts2"))

    result = protocol.unified_release(["omnivoice"])

    assert calls == ["omnivoice"]
    assert result["released"] == {"omnivoice": True}
    assert set(result["results"]) == {"omnivoice"}


def test_unified_release_returns_structured_failure_when_handler_raises(monkeypatch):
    protocol = _load_protocol_module()
    monkeypatch.setattr(
        protocol,
        "omnivoice_release",
        lambda: (_ for _ in ()).throw(RuntimeError("private diagnostic details")),
    )

    result = protocol.unified_release(["omnivoice"])

    extension_result = result["results"]["omnivoice"]
    assert result["ok"] is False
    assert result["safe_to_continue"] is False
    assert extension_result["released"] is False
    assert extension_result["safe_to_continue"] is False
    assert extension_result["release_confirmation_reason"] == (
        "omnivoice_release_exception"
    )
    assert extension_result["errors"] == ["RuntimeError"]
    assert "private diagnostic details" not in str(result)


@pytest.mark.parametrize(
    ("function_name", "extension", "contract_revision"),
    (
        ("omnivoice_release", "omnivoice", 1),
        ("gguf_release", "gguf", 2),
        ("indextts2_release", "indextts2", 1),
    ),
)
def test_extension_release_returns_confirmable_protocol_contract(
    monkeypatch,
    function_name,
    extension,
    contract_revision,
):
    protocol = _load_protocol_module()
    snapshots = iter(
        (
            {"cuda_allocated": 1_000, "cuda_reserved": 2_000},
            {"cuda_allocated": 0, "cuda_reserved": 0},
        )
    )
    objects = iter(([f"{extension}.model"], []))
    monkeypatch.setattr(protocol, "_cuda_snapshot", lambda: next(snapshots))
    monkeypatch.setattr(
        protocol,
        "_find_model_objects",
        lambda *args, **kwargs: next(objects),
    )
    monkeypatch.setattr(protocol, "_clear_module_attrs", lambda *args, **kwargs: [])
    monkeypatch.setattr(protocol, "_torch_cleanup", lambda: [])

    result = getattr(protocol, function_name)()

    assert result["protocol_version"] == 2
    assert result["contract_revision"] == contract_revision
    assert result["extension"] == extension
    assert result["released"] is True
    assert result["safe_to_continue"] is True
    assert result["objects_seen"] == [f"{extension}.model"]
    assert result["objects_released"] == [f"{extension}.model"]
    assert result["residual_objects"] == []
    assert result["errors"] == []
    assert result["cuda_allocated_before"] == 1_000
    assert result["cuda_allocated_after"] == 0


def test_extension_release_rejects_unreleased_private_model_references(monkeypatch):
    protocol = _load_protocol_module()
    snapshots = iter(
        (
            {"cuda_allocated": 1_000, "cuda_reserved": 2_000},
            {"cuda_allocated": 1_000, "cuda_reserved": 2_000},
        )
    )
    objects = iter((["omnivoice.model"], ["omnivoice.model"]))
    monkeypatch.setattr(protocol, "_cuda_snapshot", lambda: next(snapshots))
    monkeypatch.setattr(
        protocol,
        "_find_model_objects",
        lambda *args, **kwargs: next(objects),
    )
    monkeypatch.setattr(protocol, "_clear_module_attrs", lambda *args, **kwargs: [])
    monkeypatch.setattr(protocol, "_torch_cleanup", lambda: [])

    result = protocol.omnivoice_release()

    assert result["released"] is True
    assert result["safe_to_continue"] is False
    assert result["residual_objects"] == ["omnivoice.model"]
    assert result["release_confirmation_reason"] == "omnivoice_objects_residual"


def test_extension_release_rejects_residual_references_even_when_cuda_drops(
    monkeypatch,
):
    protocol = _load_protocol_module()
    snapshots = iter(
        (
            {"cuda_allocated": 1_000, "cuda_reserved": 2_000},
            {"cuda_allocated": 0, "cuda_reserved": 0},
        )
    )
    objects = iter((["omnivoice.model"], ["omnivoice.model"]))
    monkeypatch.setattr(protocol, "_cuda_snapshot", lambda: next(snapshots))
    monkeypatch.setattr(
        protocol,
        "_find_model_objects",
        lambda *args, **kwargs: next(objects),
    )
    monkeypatch.setattr(protocol, "_clear_module_attrs", lambda *args, **kwargs: [])
    monkeypatch.setattr(protocol, "_torch_cleanup", lambda: [])

    result = protocol.omnivoice_release()

    assert result["released"] is True
    assert result["safe_to_continue"] is False
    assert result["residual_objects"] == ["omnivoice.model"]
    assert result["release_confirmation_reason"] == "omnivoice_objects_residual"


def test_model_discovery_and_cleanup_cover_extension_instance_caches():
    protocol = _load_protocol_module()

    class _OmniVoiceNode:
        pass

    _OmniVoiceNode.__module__ = "omnivoice.nodes"
    node = _OmniVoiceNode()
    node.model = object()
    node._cache = {"voice": object()}

    before = protocol._find_model_objects(
        ["omnivoice"],
        model_attrs=["model"],
        cache_attrs=["_cache"],
    )
    errors = protocol._clear_module_attrs(
        ["omnivoice"],
        model_attrs=["model"],
        cache_attrs=["_cache"],
    )
    after = protocol._find_model_objects(
        ["omnivoice"],
        model_attrs=["model"],
        cache_attrs=["_cache"],
    )

    assert "omnivoice.nodes._OmniVoiceNode.model" in before
    assert "omnivoice.nodes._OmniVoiceNode._cache[entries=1]" in before
    assert errors == []
    assert node.model is None
    assert node._cache == {}
    assert "omnivoice.nodes._OmniVoiceNode.model" not in after
