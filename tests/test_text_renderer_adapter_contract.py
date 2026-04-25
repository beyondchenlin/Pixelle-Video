from pathlib import Path

import pytest

from pixelle_video.models.render_package import RenderManifest
from pixelle_video.models.text_render_package import TextRenderPackage
from pixelle_video.services.text_renderer_adapter import (
    TextRenderExportResult,
    TextRendererAdapter,
)


def _package(enabled: bool = True) -> TextRenderPackage:
    return TextRenderPackage(
        task_id="task-adapter",
        diagnostics={"enabled": enabled},
    )


def _manifest() -> RenderManifest:
    return RenderManifest(
        task_id="task-adapter",
        title="Adapter",
        canvas_width=1080,
        canvas_height=1920,
        fps=30,
        template_id="default",
    )


class ToyAdapter:
    target = "toy"

    def supports(self, package: TextRenderPackage) -> bool:
        return bool(package.diagnostics.get("enabled", True))

    def export(
        self,
        *,
        package: TextRenderPackage,
        manifest: RenderManifest,
        output_dir: Path,
    ) -> TextRenderExportResult:
        return TextRenderExportResult(
            target=self.target,
            enabled=self.supports(package),
            artifacts={"manifest": str(output_dir / f"{manifest.task_id}.json")},
            cue_count=2,
            style_profile_ids=("caption-default", "overlay-default"),
            fallbacks=("missing-style",),
            warnings=("toy warning",),
            duration_ms=12.5,
            diagnostics={"adapter": {"target": self.target}},
        )


def _export_with_adapter(
    adapter: TextRendererAdapter,
    package: TextRenderPackage,
    manifest: RenderManifest,
    output_dir: Path,
) -> TextRenderExportResult:
    assert adapter.supports(package) is True
    return adapter.export(package=package, manifest=manifest, output_dir=output_dir)


def test_export_result_to_dict_round_trips_required_diagnostics_fields():
    result = ToyAdapter().export(
        package=_package(),
        manifest=_manifest(),
        output_dir=Path("out"),
    )

    restored = TextRenderExportResult.from_dict(result.to_dict())

    assert restored == result
    assert restored.to_dict() == {
        "target": "toy",
        "enabled": True,
        "artifacts": {"manifest": str(Path("out") / "task-adapter.json")},
        "cue_count": 2,
        "style_profile_ids": ["caption-default", "overlay-default"],
        "fallbacks": ["missing-style"],
        "warnings": ["toy warning"],
        "duration_ms": 12.5,
        "diagnostics": {"adapter": {"target": "toy"}},
    }


def test_toy_adapter_satisfies_runtime_protocol_and_exports_standard_shape():
    adapter = ToyAdapter()

    assert isinstance(adapter, TextRendererAdapter)
    payload = _export_with_adapter(
        adapter,
        _package(),
        _manifest(),
        Path("out"),
    ).to_dict()

    assert payload["target"] == "toy"
    assert payload["enabled"] is True
    assert payload["cue_count"] == 2
    assert payload["diagnostics"]["adapter"]["target"] == "toy"


def test_export_result_freezes_nested_artifacts_and_diagnostics():
    result = TextRenderExportResult(
        target="toy",
        enabled=True,
        artifacts={"files": ["a.ass"], "nested": {"kind": "manifest"}},
        diagnostics={"adapter": {"target": "toy"}},
    )

    with pytest.raises(TypeError):
        result.artifacts["nested"]["kind"] = "changed"
    with pytest.raises(TypeError):
        result.diagnostics["adapter"]["target"] = "changed"

    payload = result.to_dict()
    payload["artifacts"]["nested"]["kind"] = "changed"
    payload["diagnostics"]["adapter"]["target"] = "changed"

    assert payload["artifacts"]["files"] == ["a.ass"]
    assert result.artifacts["nested"]["kind"] == "manifest"
    assert result.diagnostics["adapter"]["target"] == "toy"
