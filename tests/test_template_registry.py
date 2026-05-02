from pathlib import Path

from pixelle_video.models.layered_template import LayeredTemplateSpec, RectSpec
from pixelle_video.models.template_preset import TemplatePreset
from pixelle_video.repositories.template_presets import TemplatePresetRepository
from pixelle_video.services.template_registry import (
    TemplateRegistry,
    build_system_template_presets,
)
from pixelle_video.utils.template_util import TemplateDisplayInfo, TemplateInfo


def _demo_spec() -> LayeredTemplateSpec:
    return LayeredTemplateSpec(
        version="layered_template.v1",
        template_id="preset-demo",
        template_name="Demo",
        template_type="image",
        canvas_width=1080,
        canvas_height=1920,
        media_width=1080,
        media_height=1920,
        safe_area=RectSpec(x=64, y=64, width=952, height=1792),
        layers=(),
        metadata={},
    )


def test_registry_merges_system_and_user_presets(monkeypatch):
    system_spec = _demo_spec()
    user_spec = LayeredTemplateSpec(
        **{
            **system_spec.to_dict(),
            "template_id": "user-demo",
            "template_name": "My Demo",
        }
    )

    monkeypatch.setattr(
        "pixelle_video.services.template_registry.build_system_template_presets",
        lambda: [
            TemplatePreset(
                preset_id="system:image_default",
                name="image_default.html",
                source="system",
                orientation="portrait",
                template_type="image",
                spec=system_spec,
                editable=False,
            )
        ],
    )

    class FakeRepo:
        def list_all(self, *, source=None):
            presets = [
                TemplatePreset(
                    preset_id="user:demo",
                    name="My Demo",
                    source="user",
                    orientation="portrait",
                    template_type="image",
                    spec=user_spec,
                )
            ]
            if source is None:
                return presets
            return [preset for preset in presets if preset.source == source]

        def list_recent(self, limit=5):
            return self.list_all()[:limit]

    presets = TemplateRegistry(repository=FakeRepo()).list_presets(source="all")

    assert [preset.preset_id for preset in presets] == ["system:image_default", "user:demo"]


def test_build_system_template_presets_wraps_legacy_templates(monkeypatch):
    monkeypatch.setattr(
        "pixelle_video.services.template_registry.get_all_templates_with_info",
        lambda: [
            TemplateInfo(
                template_path="1080x1920/image_default.html",
                display_info=TemplateDisplayInfo(
                    name="image_default.html",
                    size="1080x1920",
                    width=1080,
                    height=1920,
                    orientation="portrait",
                    is_standard=True,
                ),
            )
        ],
    )

    presets = build_system_template_presets()

    assert len(presets) == 1
    preset = presets[0]
    assert preset.preset_id == "system:1080x1920/image_default.html"
    assert preset.editable is False
    assert preset.spec.metadata["source_kind"] == "legacy_html"
    assert preset.spec.metadata["legacy_template_path"] == "1080x1920/image_default.html"


def test_registry_mark_used_persists_system_preset_for_recent(tmp_path: Path, monkeypatch):
    system_preset = TemplatePreset(
        preset_id="system:1080x1920/image_default.html",
        name="image_default.html",
        source="system",
        orientation="portrait",
        template_type="image",
        spec=_demo_spec(),
        editable=False,
    )
    repo = TemplatePresetRepository(root=tmp_path)
    registry = TemplateRegistry(repository=repo)

    monkeypatch.setattr(
        "pixelle_video.services.template_registry.build_system_template_presets",
        lambda: [system_preset],
    )

    registry.mark_used(system_preset.preset_id, "2026-05-02T09:30:00Z")
    recent = registry.list_presets(source="recent")

    assert [preset.preset_id for preset in recent] == [system_preset.preset_id]
    assert recent[0].source == "system"
    assert recent[0].last_used_at == "2026-05-02T09:30:00Z"
