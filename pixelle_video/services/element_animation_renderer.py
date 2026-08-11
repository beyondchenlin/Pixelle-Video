from __future__ import annotations

import math
import tempfile
from pathlib import Path

from PIL import Image

from pixelle_video.models.element_animation import ElementAnimationManifest
from pixelle_video.services.element_animation_presets import sample_transform
from pixelle_video.services.video_encoder_executor import UnifiedVideoEncoder
from pixelle_video.utils.os_util import get_temp_path


class PythonElementAnimationRenderer:
    def __init__(self, *, video_encoder: UnifiedVideoEncoder | None = None) -> None:
        self.video_encoder = video_encoder or UnifiedVideoEncoder()

    def render_frame(
        self,
        manifest: ElementAnimationManifest,
        *,
        time: float,
    ) -> Image.Image:
        canvas_size = (manifest.canvas.width, manifest.canvas.height)
        frame = Image.open(manifest.background.image_path).convert("RGBA")
        frame = frame.resize(canvas_size, Image.Resampling.LANCZOS)

        for element in manifest.selected_elements():
            element_image = Image.open(element.image_path).convert("RGBA")
            element_image = element_image.resize(canvas_size, Image.Resampling.LANCZOS)
            mask = Image.open(element.mask_path).convert("L")
            mask = mask.resize(canvas_size, Image.Resampling.LANCZOS)

            alpha = element_image.getchannel("A")
            alpha = Image.composite(alpha, Image.new("L", canvas_size, 0), mask)
            layer = element_image.copy()
            layer.putalpha(alpha)

            transform = sample_transform(
                element.animation.preset,
                time=time,
                duration=manifest.timeline.duration,
                seed=element.animation.seed,
                bounds=element.animation.motion_bounds,
            )
            layer = self._transform_layer(
                layer,
                x=transform.x,
                y=transform.y,
                rotate=transform.rotate,
                scale=transform.scale,
            )
            frame.alpha_composite(layer)

        return frame.convert("RGB")

    def render_video(
        self,
        manifest: ElementAnimationManifest,
        output_path: str,
    ) -> str:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        frame_count = max(
            1,
            round(manifest.timeline.duration * manifest.timeline.fps),
        )

        with tempfile.TemporaryDirectory(dir=get_temp_path()) as temp_dir:
            frame_pattern = Path(temp_dir) / "frame_%06d.png"
            for frame_index in range(frame_count):
                frame_time = frame_index / manifest.timeline.fps
                frame = self.render_frame(manifest, time=frame_time)
                frame.save(Path(temp_dir) / f"frame_{frame_index:06d}.png")

            audio_path = (
                manifest.audio_path
                if manifest.audio_path and Path(manifest.audio_path).exists()
                else None
            )
            self.video_encoder.encode_png_sequence(
                frame_pattern=frame_pattern,
                fps=manifest.timeline.fps,
                output_path=output,
                duration=manifest.timeline.duration,
                audio_path=audio_path,
            )

        return output_path

    def _transform_layer(
        self,
        layer: Image.Image,
        *,
        x: float,
        y: float,
        rotate: float,
        scale: float,
    ) -> Image.Image:
        width, height = layer.size
        center_x = width / 2
        center_y = height / 2
        safe_scale = scale if scale != 0 else 1.0
        radians = math.radians(rotate)
        cos_theta = math.cos(radians) / safe_scale
        sin_theta = math.sin(radians) / safe_scale

        affine = (
            cos_theta,
            sin_theta,
            center_x - cos_theta * (center_x + x) - sin_theta * (center_y + y),
            -sin_theta,
            cos_theta,
            center_y + sin_theta * (center_x + x) - cos_theta * (center_y + y),
        )
        return layer.transform(
            layer.size,
            Image.Transform.AFFINE,
            affine,
            resample=Image.Resampling.BICUBIC,
        )
