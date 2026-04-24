from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from PIL import Image

from pixelle_video.models.element_animation import (
    AnimationIntensity,
    ElementAnimation,
    ElementAnimationBackground,
    ElementAnimationCanvas,
    ElementAnimationManifest,
    ElementAnimationRender,
    ElementAnimationSegmentation,
    ElementAnimationTimeline,
    ElementRenderBackend,
    SegmentedElement,
)
from pixelle_video.services.element_animation_presets import (
    resolve_background_bounds,
    resolve_element_bounds,
)

DEFAULT_SEGMENTATION_PROMPT = (
    "main foreground subjects, separated simple drawing elements"
)
PRESET_CYCLE = ["float", "pulse", "drift", "parallax", "pop"]


class ElementSegmentationService:
    def __init__(self, core: Any) -> None:
        self.core = core

    async def segment_image(
        self,
        *,
        image_path: str,
        task_id: str,
        frame_index: int,
        output_dir: str,
        width: int,
        height: int,
        duration: float,
        fps: int,
        selected_count: int,
        candidate_limit: int,
        prompt: str | None,
        workflow: str,
        backend: ElementRenderBackend,
        intensity: AnimationIntensity,
        audio_path: str | None = None,
    ) -> ElementAnimationManifest:
        workflow_prompt = prompt or DEFAULT_SEGMENTATION_PROMPT
        workflow_params = {
            "image": image_path,
            "prompt": workflow_prompt,
            "candidate_limit": candidate_limit,
            "selected_count": selected_count,
            "width": width,
            "height": height,
        }

        kit = await self.core._get_or_create_comfykit()
        result = await kit.execute(workflow, workflow_params)

        stable_dir = Path(output_dir) / "element_animation" / f"frame_{frame_index:03d}"
        stable_dir.mkdir(parents=True, exist_ok=True)

        result_images = list(getattr(result, "images", []) or [])
        expected_with_background = 1 + candidate_limit * 2
        has_background = len(result_images) >= expected_with_background
        background_mode = "inpainted" if has_background else "source_image_low_motion"

        background_source = (
            self._image_path(result_images[0]) if has_background else image_path
        )
        background_path = stable_dir / "background.png"
        await self._copy_media_output(background_source, background_path)

        pair_images = (
            result_images[1 : 1 + candidate_limit * 2]
            if has_background
            else result_images[: candidate_limit * 2]
        )
        if len(pair_images) % 2 != 0:
            expected_count = candidate_limit * 2
            actual_count = len(pair_images)
            raise ValueError(
                "Malformed SAM3.1 segmentation output: "
                f"expected element/mask image count to be even up to "
                f"{expected_count}, actual {actual_count}"
            )
        elements = await self._build_elements(
            pair_images=pair_images,
            stable_dir=stable_dir,
            width=width,
            height=height,
            selected_count=selected_count,
            intensity=intensity,
            frame_index=frame_index,
        )

        return ElementAnimationManifest(
            source_image_path=image_path,
            canvas=ElementAnimationCanvas(width=width, height=height),
            timeline=ElementAnimationTimeline(duration=duration, fps=fps),
            background=ElementAnimationBackground(
                mode=background_mode,
                image_path=str(background_path),
                motion_bounds=resolve_background_bounds(background_mode, intensity),
            ),
            segmentation=ElementAnimationSegmentation(
                provider="comfyui_sam31",
                workflow=workflow,
                prompt=workflow_prompt,
                candidate_limit=candidate_limit,
                selected_count=selected_count,
            ),
            elements=elements,
            render=ElementAnimationRender(backend=backend),
            audio_path=audio_path,
        )

    async def _build_elements(
        self,
        *,
        pair_images: list[Any],
        stable_dir: Path,
        width: int,
        height: int,
        selected_count: int,
        intensity: AnimationIntensity,
        frame_index: int,
    ) -> list[SegmentedElement]:
        elements: list[SegmentedElement] = []
        motion_bounds = resolve_element_bounds(intensity)
        selected_usable_count = 0

        for pair_index in range(0, len(pair_images) - 1, 2):
            element_number = pair_index // 2 + 1
            element_path = stable_dir / f"element_{element_number:03d}.png"
            mask_path = stable_dir / f"mask_{element_number:03d}.png"
            await self._copy_media_output(
                self._image_path(pair_images[pair_index]),
                element_path,
            )
            await self._copy_media_output(
                self._image_path(pair_images[pair_index + 1]),
                mask_path,
            )
            bbox, is_empty_mask = self._mask_bbox(
                mask_path,
                width=width,
                height=height,
            )
            selected = False
            if not is_empty_mask and selected_usable_count < selected_count:
                selected = True
                selected_usable_count += 1

            elements.append(
                SegmentedElement(
                    id=f"element_{element_number:03d}",
                    label=f"subject {element_number}",
                    image_path=str(element_path),
                    mask_path=str(mask_path),
                    bbox=bbox,
                    score=1.0,
                    selected=selected,
                    z_index=element_number,
                    animation=ElementAnimation(
                        preset=PRESET_CYCLE[(element_number - 1) % len(PRESET_CYCLE)],
                        intensity=intensity,
                        seed=(frame_index + 1) * 1000 + element_number,
                        motion_bounds=motion_bounds,
                    ),
                ),
            )

        return elements

    @staticmethod
    def _image_path(image: Any) -> str:
        return str(getattr(image, "path", image))

    async def _copy_media_output(self, source: str, target: Path) -> None:
        resolved_url = self._resolve_download_url(source)
        if resolved_url is not None:
            await self._download_url(resolved_url, target)
            return
        shutil.copy2(source, target)

    def _resolve_download_url(self, source: str) -> str | None:
        parsed = urlparse(source)
        if parsed.scheme in {"http", "https"}:
            return source
        if source.startswith("/view?"):
            config_getter = getattr(self.core, "_get_comfykit_config", None)
            config = config_getter() if config_getter is not None else {}
            base_url = (config or {}).get("comfyui_url")
            if base_url:
                return urljoin(base_url.rstrip("/") + "/", source.lstrip("/"))
        return None

    async def _download_url(self, url: str, target: Path) -> None:
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()
            target.write_bytes(response.content)

    @staticmethod
    def _mask_bbox(mask_path: Path, *, width: int, height: int) -> tuple[list[int], bool]:
        with Image.open(mask_path) as image:
            alpha = image.convert("RGBA").getchannel("A")
            bbox = alpha.getbbox()
        if bbox is None:
            return [0, 0, width, height], True
        return [int(value) for value in bbox], False
