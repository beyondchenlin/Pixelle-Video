from pixelle_video.utils.template_util import (
    get_template_orientation,
    parse_template_contract,
    resolve_compatible_template_for_orientation,
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


def test_resolve_compatible_template_switches_to_matching_orientation():
    selected = resolve_compatible_template_for_orientation(
        current_template="1080x1920/image_default.html",
        template_type="image",
        orientation="landscape",
    )

    assert selected.startswith("1920x1080/")
    assert selected.split("/")[-1].startswith("image_")
