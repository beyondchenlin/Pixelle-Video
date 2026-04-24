from pixelle_video.models.element_animation import ElementMotionBounds
from pixelle_video.services.element_animation_presets import (
    ElementTransform,
    resolve_background_bounds,
    resolve_element_bounds,
    sample_transform,
)


def test_source_image_background_bounds_are_subtle() -> None:
    bounds = resolve_background_bounds("source_image_low_motion", "high")

    assert bounds.translate_px <= 6
    assert bounds.rotate_deg <= 0.5
    assert bounds.scale_delta <= 0.015


def test_sample_transform_is_deterministic_and_within_bounds() -> None:
    bounds = ElementMotionBounds(translate_px=20, rotate_deg=2, scale_delta=0.05)

    for preset in ["float", "pulse", "drift", "pop", "parallax"]:
        first = sample_transform(
            preset,
            time=0.75,
            duration=3.0,
            seed=11,
            bounds=bounds,
        )
        second = sample_transform(
            preset,
            time=0.75,
            duration=3.0,
            seed=11,
            bounds=bounds,
        )

        assert first == second
        assert isinstance(first, ElementTransform)
        assert abs(first.x) <= bounds.translate_px
        assert abs(first.rotate) <= bounds.rotate_deg
        assert 0.95 <= first.scale <= 1.05


def test_element_bounds_scale_by_intensity() -> None:
    low = resolve_element_bounds("low")
    medium = resolve_element_bounds("medium")
    high = resolve_element_bounds("high")

    assert low.translate_px < medium.translate_px < high.translate_px
    assert low.rotate_deg < medium.rotate_deg < high.rotate_deg
    assert low.scale_delta < medium.scale_delta < high.scale_delta
