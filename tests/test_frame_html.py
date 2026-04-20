from pathlib import Path

from pixelle_video.services.frame_html import HTMLFrameGenerator
from web.utils.async_helpers import run_async


def test_run_async_can_render_html_frames_across_multiple_calls(tmp_path):
    template = Path("templates/1080x1080/image_minimal_framed.html")
    image = Path("resources/example.png")
    generator = HTMLFrameGenerator(str(template))

    first_output = tmp_path / "first.png"
    second_output = tmp_path / "second.png"

    first_path = run_async(
        generator.generate_frame(
            title="First",
            text="first render",
            image=str(image),
            ext={"index": 1},
            output_path=str(first_output),
        )
    )
    second_path = run_async(
        generator.generate_frame(
            title="Second",
            text="second render",
            image=str(image),
            ext={"index": 2},
            output_path=str(second_output),
        )
    )

    assert Path(first_path).exists()
    assert Path(second_path).exists()
