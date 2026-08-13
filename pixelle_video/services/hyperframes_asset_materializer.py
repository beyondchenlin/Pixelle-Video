from pathlib import Path
from typing import Dict

from pixelle_video.utils.filesystem import copy_file, ensure_directory


class HyperFramesAssetMaterializer:
    def materialize(
        self,
        *,
        project_dir: Path,
        audio_sources: Dict[str, Path],
        image_sources: Dict[str, Path],
        video_sources: Dict[str, Path],
    ) -> dict:
        assets_dir = project_dir / "assets"
        audio_dir = assets_dir / "audio"
        image_dir = assets_dir / "images"
        video_dir = assets_dir / "video"

        for directory in (audio_dir, image_dir, video_dir):
            ensure_directory(directory)

        def _copy_group(group: Dict[str, Path], target_dir: Path, prefix: str) -> Dict[str, str]:
            results: Dict[str, str] = {}
            for filename, source in group.items():
                target = target_dir / filename
                copy_file(source, target)
                results[filename] = f"assets/{prefix}/{filename}"
            return results

        return {
            "audio": _copy_group(audio_sources, audio_dir, "audio"),
            "images": _copy_group(image_sources, image_dir, "images"),
            "video": _copy_group(video_sources, video_dir, "video"),
        }
