import subprocess
import sys

from web.pipelines import (
    get_all_pipeline_uis,
    get_pipeline_catalog,
    get_pipeline_selection_entries,
)


def test_home_pipeline_order_keeps_quick_create_first():
    pipelines = get_all_pipeline_uis()

    assert [pipeline.name for pipeline in pipelines][:5] == [
        "quick_create",
        "action_transfer",
        "custom_media",
        "digital_human",
        "image_to_video",
    ]


def test_home_pipeline_catalog_keeps_quick_create_first_without_loading_modules():
    assert [entry.name for entry in get_pipeline_catalog()][:5] == [
        "quick_create",
        "action_transfer",
        "custom_media",
        "digital_human",
        "image_to_video",
    ]


def test_home_pipeline_selection_metadata_matches_loaded_builtin_pipelines():
    pipelines = {pipeline.name: pipeline for pipeline in get_all_pipeline_uis()}

    for entry in get_pipeline_selection_entries():
        pipeline = pipelines[entry.name]
        assert (entry.icon, entry.display_name, entry.description) == (
            pipeline.icon,
            pipeline.display_name,
            pipeline.description,
        )


def test_importing_pipeline_package_does_not_eagerly_import_implementations():
    code = """
import sys
import web.pipelines
modules = [
    'web.pipelines.standard',
    'web.pipelines.action_transfer',
    'web.pipelines.asset_based',
    'web.pipelines.digital_human',
    'web.pipelines.i2v',
    'web.pipelines.stage2_projection',
]
raise SystemExit(1 if any(name in sys.modules for name in modules) else 0)
"""
    result = subprocess.run([sys.executable, "-c", code], check=False)

    assert result.returncode == 0


def test_registered_extension_remains_available_through_compatibility_apis():
    code = """
from web.pipelines import (
    PipelineUI,
    get_all_pipeline_uis,
    get_pipeline_selection_entries,
    get_pipeline_ui,
    register_pipeline_ui,
)

class ExtensionPipelineUI(PipelineUI):
    name = 'extension_pipeline'
    icon = 'X'

    def render(self, pixelle_video):
        return None

register_pipeline_ui(ExtensionPipelineUI)
if get_pipeline_ui('extension_pipeline').name != 'extension_pipeline':
    raise SystemExit(1)
if 'extension_pipeline' not in [pipeline.name for pipeline in get_all_pipeline_uis()]:
    raise SystemExit(2)
if 'extension_pipeline' not in [entry.name for entry in get_pipeline_selection_entries()]:
    raise SystemExit(3)
"""
    result = subprocess.run([sys.executable, "-c", code], check=False)

    assert result.returncode == 0


def test_loading_quick_create_does_not_import_inactive_pipeline_modules():
    code = """
import sys
from web.pipelines import get_pipeline_ui
pipeline = get_pipeline_ui('quick_create')
inactive = [
    'web.pipelines.action_transfer',
    'web.pipelines.asset_based',
    'web.pipelines.digital_human',
    'web.pipelines.i2v',
    'web.pipelines.stage2_projection',
]
if pipeline is None or pipeline.name != 'quick_create':
    raise SystemExit(2)
raise SystemExit(1 if any(name in sys.modules for name in inactive) else 0)
"""
    result = subprocess.run([sys.executable, "-c", code], check=False)

    assert result.returncode == 0
