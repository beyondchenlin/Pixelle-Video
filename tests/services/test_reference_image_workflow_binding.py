from pathlib import Path
from types import SimpleNamespace

import pytest

from pixelle_video.services import reference_image_workflow_binding as binding_module
from pixelle_video.services.reference_image_workflow_binding import (
    apply_reference_image_workflow_binding_trace,
    build_reference_image_workflow_binding,
    normalize_reference_image_workflow_injection_mode,
    resolve_reference_image_workflow_injection_mode,
)


class _FakeMediaService:
    def __init__(self, source="selfhost"):
        self.source = source

    def _resolve_workflow(self, *, workflow=None, workflow_domain=None):
        return {
            "key": workflow or "selfhost/image_reference.json",
            "source": self.source,
            "path": "/tmp/fake_workflow.json",
        }


def _asset_trace():
    return {
        "sha256": "a" * 64,
        "mime_type": "image/jpeg",
        "width": 100,
        "height": 120,
        "workflow_asset_relative_path": "reference_image/workflow_abcd1234.jpg",
    }


def test_workflow_binding_injects_declared_param(monkeypatch, tmp_path):
    monkeypatch.setattr(
        binding_module,
        "get_workflow_capabilities",
        lambda workflow_info: SimpleNamespace(reference_image_param_names=("reference_image",)),
    )
    asset_path = tmp_path / "workflow.jpg"
    asset_path.write_bytes(b"fake-image")

    binding = build_reference_image_workflow_binding(
        media_service=_FakeMediaService(),
        workflow="selfhost/image_reference.json",
        media_type="image",
        injection_mode="auto",
        reference_image_asset_path=str(asset_path),
        reference_image_asset_trace=_asset_trace(),
    )

    assert binding.status == "injected"
    assert binding.injected_params == {"reference_image": str(asset_path)}
    assert binding.workflow_param_trace_values["reference_image"]["workflow_asset_relative_path"] == "reference_image/workflow_abcd1234.jpg"
    assert str(asset_path) not in str(binding.to_trace_dict())


def test_workflow_binding_required_fails_for_runninghub(tmp_path):
    asset_path = tmp_path / "workflow.jpg"
    asset_path.write_bytes(b"fake-image")

    binding = build_reference_image_workflow_binding(
        media_service=_FakeMediaService(source="runninghub"),
        workflow="runninghub/image_reference.json",
        media_type="image",
        injection_mode="required",
        reference_image_asset_path=str(asset_path),
        reference_image_asset_trace=_asset_trace(),
    )

    assert binding.status == "failed"
    assert binding.reason == "reference_image_workflow_injection_requires_selfhost"


def test_workflow_binding_override_param_names(monkeypatch, tmp_path):
    monkeypatch.setattr(
        binding_module,
        "get_workflow_capabilities",
        lambda workflow_info: SimpleNamespace(reference_image_param_names=()),
    )
    asset_path = tmp_path / "workflow.jpg"
    asset_path.write_bytes(b"fake-image")

    binding = build_reference_image_workflow_binding(
        media_service=_FakeMediaService(),
        workflow="selfhost/custom.json",
        media_type="image",
        injection_mode="auto",
        reference_image_asset_path=str(asset_path),
        reference_image_asset_trace=_asset_trace(),
        workflow_param_overrides={"selfhost/custom.json": ["init_image"]},
    )

    assert binding.status == "injected"
    assert binding.injected_params == {"init_image": str(asset_path)}


def test_apply_reference_binding_trace_replaces_absolute_path(tmp_path):
    asset_path = tmp_path / "workflow.jpg"
    workflow_params = {"prompt": "hello", "reference_image": str(asset_path), "width": 512}
    binding_trace = {
        "workflow_param_trace_values": {
            "reference_image": {
                "asset_sha256": "a" * 64,
                "workflow_asset_relative_path": "reference_image/workflow_abcd1234.jpg",
            }
        }
    }

    trace_params = apply_reference_image_workflow_binding_trace(workflow_params, binding_trace)

    assert trace_params["reference_image"]["workflow_asset_relative_path"] == "reference_image/workflow_abcd1234.jpg"
    assert str(asset_path) not in str(trace_params)


def test_resolve_workflow_injection_mode_precedence():
    assert normalize_reference_image_workflow_injection_mode("required") == "required"
    assert resolve_reference_image_workflow_injection_mode(
        {"reference_image_workflow_injection_mode": "auto"},
        {"workflow_injection_mode": "off"},
    ) == "auto"
    assert resolve_reference_image_workflow_injection_mode({}, {"workflow_injection_mode": "required"}) == "required"
