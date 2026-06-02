import logging

import pytest

from pixelle_video.utils.template_util import (
    get_template_type,
    get_supported_template_orientations,
    get_template_orientation,
    get_template_preview_path,
    lint_repository_media_templates,
    parse_template_contract,
    resolve_compatible_template_for_orientation,
    resolve_default_template_for_type_and_orientation,
)


def test_get_template_orientation_from_size_directory():
    assert get_template_orientation("1920x1080/image_full.html") == "landscape"
    assert get_template_orientation("1080x1920/image_default.html") == "portrait"
    assert get_template_orientation("1080x1080/image_minimal_framed.html") == "square"


def test_parse_template_contract_exposes_design_size_and_orientation():
    contract = parse_template_contract("1920x1080/image_landscape_minimal.html")

    assert contract.template_path == "1920x1080/image_landscape_minimal.html"
    assert contract.template_design_width == 1920
    assert contract.template_design_height == 1080
    assert contract.template_orientation == "landscape"


def test_template_contract_does_not_claim_final_output_size():
    contract = parse_template_contract("1080x1920/image_default.html")

    assert not hasattr(contract, "canvas_width")
    assert not hasattr(contract, "canvas_height")


def test_parse_template_contract_exposes_square_orientation():
    contract = parse_template_contract("1080x1080/image_minimal_framed.html")

    assert contract.template_design_width == 1080
    assert contract.template_design_height == 1080
    assert contract.template_orientation == "square"


def test_get_template_preview_path_resolves_gallery_asset():
    preview_path = get_template_preview_path(
        "1920x1080/image_landscape_minimal.html",
        language="zh_CN",
    )

    assert preview_path == "docs/images/1920x1080/image_landscape_minimal.png"


def test_get_template_preview_path_prefers_language_asset():
    preview_path = get_template_preview_path(
        "1920x1080/image_landscape_minimal.html",
        language="en_US",
    )

    assert preview_path == "docs/images/1920x1080/image_landscape_minimal_en.png"


def test_resolve_compatible_template_switches_to_matching_orientation():
    selected = resolve_compatible_template_for_orientation(
        current_template="1080x1920/image_default.html",
        template_type="image",
        orientation="landscape",
    )

    assert selected == "1920x1080/image_landscape_minimal.html"


def test_resolve_default_template_uses_type_and_orientation_registry():
    assert (
        resolve_default_template_for_type_and_orientation("image", "landscape")
        == "1920x1080/image_landscape_minimal.html"
    )
    assert (
        resolve_default_template_for_type_and_orientation("image", "square")
        == "1080x1080/image_minimal_framed.html"
    )


def test_get_template_type_accepts_asset_composition_templates_without_warning(caplog):
    caplog.set_level(logging.WARNING, logger="pixelle_video.utils.template_util")

    assert get_template_type("asset_default.html") == "image"

    assert caplog.records == []


def test_resolve_compatible_template_switches_type_even_when_orientation_matches():
    selected = resolve_compatible_template_for_orientation(
        current_template="1080x1920/static_default.html",
        template_type="image",
        orientation="portrait",
    )

    assert selected == "1080x1920/image_default.html"


def test_supported_template_orientations_are_based_on_template_inventory():
    assert get_supported_template_orientations("static") == ("portrait",)
    assert get_supported_template_orientations("video") == ("portrait",)
    assert get_supported_template_orientations("image") == (
        "portrait",
        "landscape",
        "square",
    )


def test_resolve_compatible_template_rejects_missing_orientation_for_type():
    with pytest.raises(ValueError, match="No landscape template"):
        resolve_compatible_template_for_orientation(
            current_template="1080x1920/static_default.html",
            template_type="static",
            orientation="landscape",
        )


def test_lint_repository_media_templates_reports_no_template_bypass():
    assert lint_repository_media_templates() == {}
