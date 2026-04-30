from importlib import import_module
import inspect
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def assert_protocol_exposes_async_methods(protocol: type, method_names: set[str]) -> None:
    for method_name in method_names:
        assert hasattr(protocol, method_name)
        assert inspect.iscoroutinefunction(getattr(protocol, method_name))


def test_repository_protocols_expose_required_methods():
    artifacts = import_module("pixelle_video.repositories.artifacts")
    assets = import_module("pixelle_video.repositories.assets")
    prompt_plans = import_module("pixelle_video.repositories.prompt_plans")
    trace = import_module("pixelle_video.repositories.trace")

    assert_protocol_exposes_async_methods(
        trace.TraceRepository,
        {
            "append_llm_interaction",
            "list_llm_interactions",
            "append_generation_event",
            "list_generation_events",
        },
    )
    assert_protocol_exposes_async_methods(
        artifacts.ArtifactRepository,
        {
            "create_artifact",
            "create_artifact_version",
            "select_artifact_version",
            "list_artifact_versions",
            "mark_artifact_failed",
        },
    )
    assert_protocol_exposes_async_methods(
        artifacts.ArtifactObjectStore,
        {
            "put_file",
            "get_file_url",
            "exists",
        },
    )
    assert_protocol_exposes_async_methods(
        assets.AssetBibleRepository,
        {
            "save_asset_bible",
            "load_asset_bible",
            "save_scene_cast",
            "load_scene_cast",
        },
    )
    assert_protocol_exposes_async_methods(
        prompt_plans.PromptPlanRepository,
        {
            "save_prompt_plan_bundle",
            "load_prompt_plans_by_storyboard",
            "mark_prompt_plan_stale",
        },
    )
