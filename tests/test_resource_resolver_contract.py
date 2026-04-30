import inspect
from types import MappingProxyType

import pytest

from pixelle_video.services.resource_resolver import (
    ResolvedResource,
    ResourceIdInvalidError,
    ResourceNotFoundError,
    ResourceResolver,
    ResourceResolverError,
    StaticResourceResolver,
)

RESOURCE_METHODS = {
    "resolve_style_id",
    "resolve_template_id",
    "resolve_voice_id",
    "resolve_bgm_id",
    "resolve_workflow_preset_id",
    "resolve_provider_preset_id",
}


def test_resource_resolver_protocol_exposes_required_methods():
    for method_name in RESOURCE_METHODS:
        assert hasattr(ResourceResolver, method_name)
        assert not inspect.iscoroutinefunction(getattr(ResourceResolver, method_name))


def test_static_resource_resolver_resolves_configured_resource_ids():
    resolver = StaticResourceResolver(
        styles={
            "cinematic": ResolvedResource(
                resource_id="cinematic",
                resolved_value="style:cinematic",
                metadata={"label": "Cinematic"},
            )
        },
        templates={"reel": "template:reel"},
        voices={"narrator": "voice:narrator"},
        bgms={"ambient": "bgm:ambient"},
        workflow_presets={"imageTurbo": "workflow-preset:image-turbo"},
        provider_presets={"defaultProvider": "provider-preset:default"},
    )

    assert resolver.resolve_style_id("cinematic") == ResolvedResource(
        resource_id="cinematic",
        resolved_value="style:cinematic",
        metadata=MappingProxyType({"label": "Cinematic"}),
    )
    assert resolver.resolve_template_id("reel") == ResolvedResource(
        resource_id="reel",
        resolved_value="template:reel",
        metadata=MappingProxyType({}),
    )
    assert resolver.resolve_voice_id("narrator") == ResolvedResource(
        resource_id="narrator",
        resolved_value="voice:narrator",
        metadata=MappingProxyType({}),
    )
    assert resolver.resolve_bgm_id("ambient") == ResolvedResource(
        resource_id="ambient",
        resolved_value="bgm:ambient",
        metadata=MappingProxyType({}),
    )
    assert resolver.resolve_workflow_preset_id("imageTurbo") == ResolvedResource(
        resource_id="imageTurbo",
        resolved_value="workflow-preset:image-turbo",
        metadata=MappingProxyType({}),
    )
    assert resolver.resolve_provider_preset_id("defaultProvider") == ResolvedResource(
        resource_id="defaultProvider",
        resolved_value="provider-preset:default",
        metadata=MappingProxyType({}),
    )


def test_unknown_valid_resource_id_raises_stable_not_found_error():
    resolver = StaticResourceResolver(styles={"cinematic": "style:cinematic"})

    with pytest.raises(ResourceNotFoundError, match="style"):
        resolver.resolve_style_id("missing")


def test_static_resource_resolver_copies_configured_mappings():
    styles = {"cinematic": "style:cinematic"}
    templates = {"reel": "template:reel"}
    voices = {"narrator": "voice:narrator"}
    bgms = {"ambient": "bgm:ambient"}
    workflow_presets = {"imageTurbo": "workflow-preset:image-turbo"}
    provider_presets = {"defaultProvider": "provider-preset:default"}
    resolver = StaticResourceResolver(
        styles=styles,
        templates=templates,
        voices=voices,
        bgms=bgms,
        workflow_presets=workflow_presets,
        provider_presets=provider_presets,
    )

    styles["cinematic"] = "style:mutated"
    templates["reel"] = "template:mutated"
    voices["narrator"] = "voice:mutated"
    bgms["ambient"] = "bgm:mutated"
    workflow_presets["imageTurbo"] = "workflow-preset:mutated"
    provider_presets["defaultProvider"] = "provider-preset:mutated"

    assert resolver.resolve_style_id("cinematic").resolved_value == "style:cinematic"
    assert resolver.resolve_template_id("reel").resolved_value == "template:reel"
    assert resolver.resolve_voice_id("narrator").resolved_value == "voice:narrator"
    assert resolver.resolve_bgm_id("ambient").resolved_value == "bgm:ambient"
    assert (
        resolver.resolve_workflow_preset_id("imageTurbo").resolved_value
        == "workflow-preset:image-turbo"
    )
    assert (
        resolver.resolve_provider_preset_id("defaultProvider").resolved_value
        == "provider-preset:default"
    )


def test_mismatched_configured_resolved_resource_id_raises_contract_error():
    with pytest.raises(ResourceResolverError, match="resource_id"):
        StaticResourceResolver(
            styles={
                "cinematic": ResolvedResource(
                    resource_id="other",
                    resolved_value="style:cinematic",
                )
            }
        )


@pytest.mark.parametrize(
    "resource_id",
    [
        "C:/foo",
        "C:\\foo",
        "D:foo",
        "/tmp/file",
        "/workflows/selfhost/image.json",
        "../x",
        "style/../x",
        "..",
        "http://example.test/resource",
        "https://example.test/resource",
        "selfhost/image_z_image_turbo.json",
        "workflows/selfhost/image_z_image_turbo.json",
        "image_z_image_turbo.json",
        "",
        " ",
        " cinematic",
        "cinematic ",
        "style\\cinematic",
        "style/cinematic",
        None,
        123,
        object(),
    ],
)
def test_invalid_resource_ids_raise_stable_invalid_error_before_lookup(resource_id):
    class ExplodingMapping(dict):
        def __contains__(self, key):
            raise AssertionError("invalid IDs must fail before lookup")

        def __getitem__(self, key):
            raise AssertionError("invalid IDs must fail before lookup")

    resolver = StaticResourceResolver(styles=ExplodingMapping({"cinematic": "unused"}))

    with pytest.raises(ResourceIdInvalidError):
        resolver.resolve_style_id(resource_id)


def test_valid_id_grammar_allows_alphanumeric_underscore_and_hyphen():
    resolver = StaticResourceResolver(
        styles={
            "Style_1-a": ResolvedResource(
                resource_id="Style_1-a",
                resolved_value="style:Style_1-a",
                metadata={"kind": "style"},
            )
        }
    )

    resolved = resolver.resolve_style_id("Style_1-a")

    assert resolved.resource_id == "Style_1-a"
    assert resolved.resolved_value == "style:Style_1-a"
    assert resolved.metadata == MappingProxyType({"kind": "style"})
