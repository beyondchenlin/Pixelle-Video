from __future__ import annotations

from dataclasses import dataclass

from web.i18n import tr


@dataclass(frozen=True)
class PipelineCatalogEntry:
    """Lightweight metadata for a lazily imported Home pipeline."""

    name: str
    module_name: str
    icon: str
    display_name_key: str
    description_key: str

    @property
    def display_name(self) -> str:
        return tr(self.display_name_key)

    @property
    def description(self) -> str:
        return tr(self.description_key)


@dataclass(frozen=True)
class PipelineSelectionEntry:
    """Resolved selector metadata for either a built-in or an extension."""

    name: str
    icon: str
    display_name: str
    description: str


# This tuple defines built-in Home ordering and import targets.
# Runtime validation in web.pipelines rejects metadata drift after a module loads.
PIPELINE_CATALOG: tuple[PipelineCatalogEntry, ...] = (
    PipelineCatalogEntry(
        name="quick_create",
        module_name="web.pipelines.standard",
        icon="⚡",
        display_name_key="pipeline.quick_create.name",
        description_key="pipeline.quick_create.description",
    ),
    PipelineCatalogEntry(
        name="action_transfer",
        module_name="web.pipelines.action_transfer",
        icon="💃",
        display_name_key="pipeline.action_transfer.name",
        description_key="pipeline.action_transfer.description",
    ),
    PipelineCatalogEntry(
        name="custom_media",
        module_name="web.pipelines.asset_based",
        icon="🎨",
        display_name_key="pipeline.custom_media.name",
        description_key="pipeline.custom_media.description",
    ),
    PipelineCatalogEntry(
        name="digital_human",
        module_name="web.pipelines.digital_human",
        icon="🤖",
        display_name_key="pipeline.digital_human.name",
        description_key="pipeline.digital_human.description",
    ),
    PipelineCatalogEntry(
        name="image_to_video",
        module_name="web.pipelines.i2v",
        icon="🎥",
        display_name_key="pipeline.i2v.name",
        description_key="pipeline.i2v.description",
    ),
    PipelineCatalogEntry(
        name="stage2_prompt_plan_projection",
        module_name="web.pipelines.stage2_projection",
        icon="🧭",
        display_name_key="pipeline.stage2_projection.name",
        description_key="pipeline.stage2_projection.description",
    ),
)


def get_pipeline_catalog() -> tuple[PipelineCatalogEntry, ...]:
    return PIPELINE_CATALOG


def get_pipeline_catalog_entry(name: str) -> PipelineCatalogEntry | None:
    return next((entry for entry in PIPELINE_CATALOG if entry.name == name), None)


__all__ = [
    "PIPELINE_CATALOG",
    "PipelineCatalogEntry",
    "PipelineSelectionEntry",
    "get_pipeline_catalog",
    "get_pipeline_catalog_entry",
]
