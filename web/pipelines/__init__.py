# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Pipeline UI Package

Exports a lightweight catalog and lazily imports selected pipeline modules.
"""

from importlib import import_module

from web.pipelines.base import (
    PipelineUI,
    register_pipeline_ui,
)
from web.pipelines.base import (
    get_all_pipeline_uis as _get_all_registered_pipeline_uis,
)
from web.pipelines.base import (
    get_pipeline_ui as _get_registered_pipeline_ui,
)
from web.pipelines.catalog import (
    PipelineCatalogEntry,
    PipelineSelectionEntry,
    get_pipeline_catalog,
    get_pipeline_catalog_entry,
)


def get_pipeline_ui(name: str) -> PipelineUI | None:
    """Load one allowlisted pipeline and validate its registered identity."""
    entry = get_pipeline_catalog_entry(name)
    if entry is None:
        return _get_registered_pipeline_ui(name)

    pipeline = _get_registered_pipeline_ui(name)
    if pipeline is None:
        import_module(entry.module_name)
        pipeline = _get_registered_pipeline_ui(name)
    if pipeline is None:
        raise RuntimeError(
            f"Pipeline module {entry.module_name!r} did not register {entry.name!r}"
        )
    is_builtin_implementation = type(pipeline).__module__ == entry.module_name
    if is_builtin_implementation and (
        pipeline.name != entry.name
        or pipeline.icon != entry.icon
        or pipeline.display_name != entry.display_name
        or pipeline.description != entry.description
    ):
        raise RuntimeError(
            f"Pipeline catalog metadata drift for {entry.name!r}: "
            f"registered name={pipeline.name!r}, icon={pipeline.icon!r}"
        )
    return pipeline


def _selection_entry_from_pipeline(pipeline: PipelineUI) -> PipelineSelectionEntry:
    return PipelineSelectionEntry(
        name=pipeline.name,
        icon=pipeline.icon,
        display_name=pipeline.display_name,
        description=pipeline.description,
    )


def get_pipeline_selection_entries() -> tuple[PipelineSelectionEntry, ...]:
    """Resolve Home metadata without importing inactive built-in pipelines."""
    registered = {
        pipeline.name: pipeline for pipeline in _get_all_registered_pipeline_uis()
    }
    entries: list[PipelineSelectionEntry] = []
    catalog_names: set[str] = set()
    for catalog_entry in get_pipeline_catalog():
        catalog_names.add(catalog_entry.name)
        pipeline = registered.get(catalog_entry.name)
        if pipeline is not None and type(pipeline).__module__ != catalog_entry.module_name:
            entries.append(_selection_entry_from_pipeline(pipeline))
        else:
            entries.append(
                PipelineSelectionEntry(
                    name=catalog_entry.name,
                    icon=catalog_entry.icon,
                    display_name=catalog_entry.display_name,
                    description=catalog_entry.description,
                )
            )
    entries.extend(
        _selection_entry_from_pipeline(pipeline)
        for pipeline in registered.values()
        if pipeline.name not in catalog_names
    )
    return tuple(entries)


def get_all_pipeline_uis() -> list[PipelineUI]:
    """Load built-ins in catalog order and retain registered extensions."""
    pipelines: list[PipelineUI] = []
    for entry in get_pipeline_catalog():
        pipeline = get_pipeline_ui(entry.name)
        if pipeline is None:  # pragma: no cover - catalog entries are validated above
            raise RuntimeError(f"Pipeline {entry.name!r} is unavailable")
        pipelines.append(pipeline)
    catalog_names = {pipeline.name for pipeline in pipelines}
    pipelines.extend(
        pipeline
        for pipeline in _get_all_registered_pipeline_uis()
        if pipeline.name not in catalog_names
    )
    return pipelines

__all__ = [
    "PipelineUI",
    "PipelineCatalogEntry",
    "PipelineSelectionEntry",
    "register_pipeline_ui",
    "get_pipeline_ui",
    "get_all_pipeline_uis",
    "get_pipeline_catalog",
    "get_pipeline_catalog_entry",
    "get_pipeline_selection_entries",
]
