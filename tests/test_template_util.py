from pixelle_video.utils.template_util import (
    get_template_orientation,
    resolve_compatible_template_for_orientation,
)


def test_get_template_orientation_from_size_directory():
    assert get_template_orientation("1920x1080/image_full.html") == "landscape"
    assert get_template_orientation("1080x1920/image_default.html") == "portrait"
    assert get_template_orientation("1080x1080/image_minimal_framed.html") == "square"


def test_resolve_compatible_template_switches_to_matching_orientation():
    selected = resolve_compatible_template_for_orientation(
        current_template="1080x1920/image_default.html",
        template_type="image",
        orientation="landscape",
    )

    assert selected.startswith("1920x1080/")
    assert selected.split("/")[-1].startswith("image_")
