# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Template utility functions for size parsing and template management
"""

import functools
import logging
from collections import defaultdict
from pathlib import Path
from typing import List, Literal, Optional, Tuple

from pydantic import BaseModel, Field

from pixelle_video.utils.os_util import (
    clear_resource_cache,
    get_pixelle_video_root_path,
    get_resource_path,
    list_resource_dirs,
    list_resource_files,
)

logger = logging.getLogger(__name__)

TemplateOrientation = Literal["portrait", "landscape", "square"]
TemplateType = Literal["static", "image", "video"]

DEFAULT_STATIC_TEMPLATE = "1080x1920/static_default.html"
DEFAULT_IMAGE_TEMPLATE = "1080x1920/image_default.html"
DEFAULT_IMAGE_LANDSCAPE_TEMPLATE = "1920x1080/image_landscape_minimal.html"
DEFAULT_IMAGE_SQUARE_TEMPLATE = "1080x1080/image_minimal_framed.html"
DEFAULT_VIDEO_TEMPLATE = "1080x1920/video_default.html"
LEGACY_DEFAULT_TEMPLATE = "1080x1920/default.html"
DEFAULT_TEMPLATE_BY_TYPE: dict[TemplateType, str] = {
    "static": DEFAULT_STATIC_TEMPLATE,
    "image": DEFAULT_IMAGE_TEMPLATE,
    "video": DEFAULT_VIDEO_TEMPLATE,
}
DEFAULT_TEMPLATE_BY_TYPE_AND_ORIENTATION: dict[TemplateType, dict[TemplateOrientation, str]] = {
    "static": {
        "portrait": DEFAULT_STATIC_TEMPLATE,
    },
    "image": {
        "portrait": DEFAULT_IMAGE_TEMPLATE,
        "landscape": DEFAULT_IMAGE_LANDSCAPE_TEMPLATE,
        "square": DEFAULT_IMAGE_SQUARE_TEMPLATE,
    },
    "video": {
        "portrait": DEFAULT_VIDEO_TEMPLATE,
    },
}


def parse_template_size(template_path: str) -> Tuple[int, int]:
    """
    Parse the template design-coordinate size from a template path.
    
    Args:
        template_path: Template path like "templates/1080x1920/image_default.html"
                      or "1080x1920/image_default.html"
    
    Returns:
        Tuple of (width, height) in template design-coordinate pixels
    
    Raises:
        ValueError: If template path format is invalid
    
    Examples:
        >>> parse_template_size("templates/1080x1920/image_default.html")
        (1080, 1920)
        >>> parse_template_size("1920x1080/modern.html")
        (1920, 1080)
    """
    path = Path(template_path)
    
    # Get parent directory name (should be like "1080x1920")
    dir_name = path.parent.name
    
    # Special case: if parent is "templates", go up one more level
    if dir_name == "templates":
        # This shouldn't happen in new structure, but handle it
        raise ValueError(
            f"Invalid template path format: {template_path}. "
            f"Expected format: 'WIDTHxHEIGHT/template.html' or 'templates/WIDTHxHEIGHT/template.html'"
        )
    
    # Parse size from directory name
    if 'x' not in dir_name:
        raise ValueError(
            f"Invalid size format in path: {template_path}. "
            f"Directory name should be 'WIDTHxHEIGHT' (e.g., '1080x1920')"
        )
    
    try:
        width_str, height_str = dir_name.split('x')
        width = int(width_str)
        height = int(height_str)
        
        # Sanity check
        if width < 100 or height < 100 or width > 10000 or height > 10000:
            raise ValueError(f"Invalid size dimensions: {width}x{height}")
        
        return (width, height)
    except ValueError as e:
        raise ValueError(
            f"Failed to parse size from path: {template_path}. "
            f"Expected format: 'WIDTHxHEIGHT/template.html' (e.g., '1080x1920/image_default.html'). "
            f"Error: {e}"
        )


def _template_orientation_from_dimensions(width: int, height: int) -> TemplateOrientation:
    if width > height:
        return "landscape"
    if height > width:
        return "portrait"
    return "square"


class TemplateContract(BaseModel):
    """
    Template design-coordinate metadata parsed from the template path.

    This contract describes the template layout coordinate system only. It does
    not define the final output, media, or canvas size.
    """

    template_path: str = Field(..., description="Template path as provided by the caller")
    template_design_width: int = Field(
        ...,
        description="Template design-coordinate width parsed from the template directory",
    )
    template_design_height: int = Field(
        ...,
        description="Template design-coordinate height parsed from the template directory",
    )
    template_orientation: TemplateOrientation = Field(
        ...,
        description="Template design-coordinate orientation; does not imply final output orientation",
    )


def parse_template_contract(template_path: str) -> TemplateContract:
    """
    Parse template design-coordinate metadata from a template path.

    The WIDTHxHEIGHT directory in a template path defines the template design
    coordinate system and layout orientation only. Final output, media, and
    canvas size are defined elsewhere.
    """
    width, height = parse_template_size(template_path)

    return TemplateContract(
        template_path=template_path,
        template_design_width=width,
        template_design_height=height,
        template_orientation=_template_orientation_from_dimensions(width, height),
    )


def get_template_preview_path(template_path: str, language: str = "zh_CN") -> str:
    """
    Resolve the gallery preview image for a template.

    Returns a project-relative docs/images path so Streamlit can render the same
    asset from every UI surface. Chinese uses the base asset; other languages
    prefer the `_en` variant and fall back to the base asset.
    """
    normalized = str(template_path or "").replace("\\", "/").strip()
    parts = [part for part in normalized.split("/") if part]
    size = ""
    template_file = ""
    for index, part in enumerate(parts[:-1]):
        if "x" not in part:
            continue
        try:
            width, height = part.split("x", 1)
            int(width)
            int(height)
        except ValueError:
            continue
        size = part
        template_file = parts[index + 1]

    if not size or not template_file:
        return ""

    template_name = Path(template_file).stem
    suffixes = [""] if language == "zh_CN" else ["_en", ""]
    project_root = Path(get_pixelle_video_root_path())

    for suffix in suffixes:
        for extension in (".jpg", ".png"):
            relative_path = (
                Path("docs")
                / "images"
                / size
                / f"{template_name}{suffix}{extension}"
            )
            if (project_root / relative_path).exists():
                return relative_path.as_posix()
    return ""


def list_available_sizes() -> List[str]:
    """
    List all available template design-coordinate sizes.
    
    Returns:
        List of size strings like ["1080x1920", "1920x1080", "1080x1080"]
    
    Examples:
        >>> list_available_sizes()
        ['1080x1920', '1920x1080', '1080x1080']
    """
    # Use new resource API to merge default and custom directories
    all_dirs = list_resource_dirs("templates")
    
    # Filter to only valid size formats (WIDTHxHEIGHT)
    sizes = []
    for dir_name in all_dirs:
        if 'x' in dir_name:
            try:
                width, height = dir_name.split('x')
                int(width)
                int(height)
                sizes.append(dir_name)
            except (ValueError, AttributeError):
                # Skip invalid directories
                continue
    
    return sorted(sizes)


def list_templates_for_size(size: str) -> List[str]:
    """
    List all templates available for a given size (merged from templates/ and data/templates/)
    
    Args:
        size: Size string like "1080x1920"
    
    Returns:
        List of template filenames (without path) like ["image_default.html", "image_modern.html"]
    
    Examples:
        >>> list_templates_for_size("1080x1920")
        ['image_cartoon.html', 'image_default.html', 'image_elegant.html', 'image_modern.html', ...]
    """
    # Use new resource API to merge default and custom templates
    all_files = list_resource_files("templates", size)
    
    # Filter to only HTML files
    templates = [f for f in all_files if f.endswith('.html')]
    
    return sorted(templates)


def get_template_full_path(size: str, template_name: str) -> str:
    """
    Get full template path from size and template name (checks data/templates/ first, then templates/)
    
    Args:
        size: Size string like "1080x1920"
        template_name: Template filename like "image_default.html"
    
    Returns:
        Full path like "templates/1080x1920/image_default.html" or "data/templates/1080x1920/image_default.html"
    
    Raises:
        FileNotFoundError: If template file doesn't exist in either location
    
    Examples:
        >>> get_template_full_path("1080x1920", "image_default.html")
        'templates/1080x1920/image_default.html'
    """
    # Use new resource API to search custom first, then default
    try:
        return get_resource_path("templates", size, template_name)
    except FileNotFoundError:
        available_templates = list_templates_for_size(size)
        raise FileNotFoundError(
            f"Template not found: {size}/{template_name}\n"
            f"Available templates for size {size}: {available_templates}"
        )


class TemplateDisplayInfo(BaseModel):
    """Template display information for UI layer"""
    
    name: str = Field(..., description="Template name without extension")
    size: str = Field(..., description="Template design-coordinate size like '1080x1920'")
    width: int = Field(..., description="Template design-coordinate width")
    height: int = Field(..., description="Template design-coordinate height")
    orientation: TemplateOrientation = Field(
        ..., 
        description="Template layout orientation"
    )
    is_standard: bool = Field(
        ..., 
        description="True only for standard sizes: 1080x1920, 1920x1080, 1080x1080"
    )


class TemplateInfo(BaseModel):
    """Complete template information with path and display info"""
    
    template_path: str = Field(..., description="Full template path like '1080x1920/image_default.html'")
    display_info: TemplateDisplayInfo = Field(..., description="Display information")


def format_template_display_info(template_name: str, size: str) -> TemplateDisplayInfo:
    """
    Format template display information for UI
    
    Returns structured data for UI layer to handle display and i18n.
    
    Args:
        template_name: Template filename like "image_default.html"
        size: Size string like "1080x1920"
    
    Returns:
        TemplateDisplayInfo object with name, size, dimensions, orientation, and standard flag
    
    Examples:
        >>> info = format_template_display_info("image_default.html", "1080x1920")
        >>> info.name
        'image_default'
        >>> info.is_standard
        True
        
        >>> info = format_template_display_info("custom.html", "1080x1921")
        >>> info.orientation
        'portrait'
        >>> info.is_standard
        False
    """
    # Keep full template name with .html extension
    name = template_name
    
    # Parse size
    width, height = map(int, size.split('x'))
    
    orientation = _template_orientation_from_dimensions(width, height)
    
    # Check if it's a standard size (only these three)
    is_standard = (width, height) in [(1080, 1920), (1920, 1080), (1080, 1080)]
    
    return TemplateDisplayInfo(
        name=name,
        size=size,
        width=width,
        height=height,
        orientation=orientation,
        is_standard=is_standard
    )


@functools.lru_cache(maxsize=1)
def get_all_templates_with_info() -> List[TemplateInfo]:
    """
    Get all templates with their display information
    
    Returns:
        List of TemplateInfo objects
    
    Example:
        >>> templates = get_all_templates_with_info()
        >>> for t in templates:
        ...     print(f"{t.display_info.name} - {t.display_info.orientation}")
        ...     print(f"  Path: {t.template_path}")
        ...     print(f"  Standard: {t.display_info.is_standard}")
    """
    result = []
    sizes = list_available_sizes()
    
    for size in sizes:
        templates = list_templates_for_size(size)
        for template in templates:
            display_info = format_template_display_info(template, size)
            full_path = f"{size}/{template}"
            result.append(TemplateInfo(
                template_path=full_path,
                display_info=display_info
            ))
    
    return result


def clear_template_cache():
    """Clear cached template scan results so the next call rescans from disk."""
    get_all_templates_with_info.cache_clear()
    clear_resource_cache()


def get_templates_grouped_by_size() -> dict:
    """
    Get templates grouped by size
    
    Returns:
        Dict with size as key, list of TemplateInfo as value
        Ordered by orientation priority: portrait > landscape > square
    
    Example:
        >>> grouped = get_templates_grouped_by_size()
        >>> for size, templates in grouped.items():
        ...     print(f"Size: {size}")
        ...     for t in templates:
        ...         print(f"  - {t.display_info.name}")
    """
    templates = get_all_templates_with_info()
    grouped = defaultdict(list)
    
    for t in templates:
        grouped[t.display_info.size].append(t)
    
    # Sort groups by orientation priority: portrait > landscape > square
    orientation_priority = {'portrait': 0, 'landscape': 1, 'square': 2}
    
    sorted_grouped = {}
    for size in sorted(grouped.keys(), key=lambda s: (
        orientation_priority.get(grouped[s][0].display_info.orientation, 3),
        s
    )):
        sorted_grouped[size] = sorted(grouped[size], key=lambda t: t.display_info.name)
    
    return sorted_grouped


def resolve_template_path(template_input: Optional[str]) -> str:
    """
    Resolve template input to full path with validation (checks data/templates/ first, then templates/)
    
    Args:
        template_input: Can be:
            - None: Use the default image template
            - "template.html": Use default size + this template
            - "1080x1920/template.html": Full relative path
            - "templates/1080x1920/template.html": Absolute-ish path (legacy)
            - "data/templates/1080x1920/template.html": Custom path (legacy)
    
    Returns:
        Resolved full path (custom if exists, otherwise default)
    
    Raises:
        FileNotFoundError: If template doesn't exist in either location
    
    Examples:
        >>> resolve_template_path(None)
        'templates/1080x1920/image_default.html'
        >>> resolve_template_path("image_modern.html")
        'templates/1080x1920/image_modern.html'
        >>> resolve_template_path("1920x1080/image_book.html")
        'templates/1920x1080/image_book.html'
    """
    # Default case
    if template_input is None:
        template_input = DEFAULT_IMAGE_TEMPLATE
    
    # Parse input to extract size and template name
    size = None
    template_name = None
    
    # Handle different input formats
    if template_input.startswith("templates/") or template_input.startswith("data/templates/"):
        # Legacy full path format - extract size and name
        parts = Path(template_input).parts
        if len(parts) >= 3:
            size = parts[-2]
            template_name = parts[-1]
    elif '/' in template_input and 'x' in template_input.split('/')[0]:
        # "1080x1920/template.html" format
        size, template_name = template_input.split('/', 1)
    else:
        # Just template name - use default size
        size = "1080x1920"
        template_name = template_input
    
    # Backward compatibility: migrate "default.html" to "image_default.html"
    if template_name == "default.html":
        migrated_name = "image_default.html"
        try:
            # Try migrated name first
            path = get_resource_path("templates", size, migrated_name)
            logger.info(f"Backward compatibility: migrated '{template_input}' to '{size}/{migrated_name}'")
            return path
        except FileNotFoundError:
            # Fall through to try original name
            logger.warning(f"Migrated template '{size}/{migrated_name}' not found, trying original name")
    
    # Use resource API to resolve path (custom > default)
    try:
        return get_resource_path("templates", size, template_name)
    except FileNotFoundError:
        available_sizes = list_available_sizes()
        raise FileNotFoundError(
            f"Template not found: {size}/{template_name}\n"
            f"Available sizes: {available_sizes}\n"
            f"Hint: Use format 'SIZExSIZE/template.html' (e.g., '1080x1920/image_default.html')"
        )


def get_template_type(template_name: str) -> TemplateType:
    """
    Detect template type from template filename
    
    Template naming convention:
    - static_*.html: Static style templates (no AI-generated media)
    - image_*.html: Templates requiring AI-generated images
    - video_*.html: Templates requiring AI-generated videos
    
    Args:
        template_name: Template filename like "image_default.html" or "video_simple.html"
    
    Returns:
        Template type: 'static', 'image', or 'video'
    
    Examples:
        >>> get_template_type("static_simple.html")
        'static'
        >>> get_template_type("image_default.html")
        'image'
        >>> get_template_type("video_simple.html")
        'video'
    """
    name = Path(template_name).name
    
    if name.startswith("static_"):
        return "static"
    elif name.startswith("video_"):
        return "video"
    elif name.startswith("image_"):
        return "image"
    else:
        # Fallback: try to detect from legacy names
        logger.warning(
            f"Template '{template_name}' doesn't follow naming convention (static_/image_/video_). "
            f"Defaulting to 'image' type."
        )
        return "image"


def filter_templates_by_type(
    templates: List[TemplateInfo], 
    template_type: TemplateType,
) -> List[TemplateInfo]:
    """
    Filter templates by type
    
    Args:
        templates: List of TemplateInfo objects
        template_type: Type to filter by ('static', 'image', or 'video')
    
    Returns:
        Filtered list of TemplateInfo objects
    
    Examples:
        >>> all_templates = get_all_templates_with_info()
        >>> image_templates = filter_templates_by_type(all_templates, 'image')
        >>> len(image_templates) > 0
        True
    """
    filtered = []
    for t in templates:
        template_name = t.display_info.name
        if get_template_type(template_name) == template_type:
            filtered.append(t)
    return filtered


def get_templates_grouped_by_size_and_type(
    template_type: Optional[TemplateType] = None,
) -> dict:
    """
    Get templates grouped by size, optionally filtered by type
    
    Args:
        template_type: Optional type filter ('static', 'image', or 'video')
    
    Returns:
        Dict with size as key, list of TemplateInfo as value
        Ordered by orientation priority: portrait > landscape > square
    
    Examples:
        >>> # Get all templates
        >>> all_grouped = get_templates_grouped_by_size_and_type()
        
        >>> # Get only image templates
        >>> image_grouped = get_templates_grouped_by_size_and_type('image')
    """
    templates = get_all_templates_with_info()
    
    # Filter by type if specified
    if template_type is not None:
        templates = filter_templates_by_type(templates, template_type)
    
    grouped = defaultdict(list)
    
    for t in templates:
        grouped[t.display_info.size].append(t)
    
    # Sort groups by orientation priority: portrait > landscape > square
    orientation_priority = {'portrait': 0, 'landscape': 1, 'square': 2}
    
    sorted_grouped = {}
    for size in sorted(grouped.keys(), key=lambda s: (
        orientation_priority.get(grouped[s][0].display_info.orientation, 3),
        s
    )):
        sorted_grouped[size] = sorted(grouped[size], key=lambda t: t.display_info.name)
    
    return sorted_grouped


def get_template_orientation(template_path: str) -> TemplateOrientation:
    width, height = parse_template_size(template_path)
    return _template_orientation_from_dimensions(width, height)


def validate_template_canvas_orientation(
    template_path: str,
    canvas_orientation: TemplateOrientation,
) -> None:
    template_orientation = get_template_orientation(template_path)
    if template_orientation == canvas_orientation:
        return
    raise ValueError(
        "Template orientation mismatch: "
        f"Template orientation is {template_orientation!r}, "
        f"but final video canvas orientation is {canvas_orientation!r}. "
        f"Select a {canvas_orientation} template or change the video canvas."
    )


def get_supported_template_orientations(
    template_type: TemplateType,
) -> tuple[TemplateOrientation, ...]:
    grouped = get_templates_grouped_by_size_and_type(template_type)
    supported = {
        template.display_info.orientation
        for templates in grouped.values()
        for template in templates
    }
    orientation_order: tuple[TemplateOrientation, ...] = ("portrait", "landscape", "square")
    return tuple(orientation for orientation in orientation_order if orientation in supported)


def iter_repository_media_templates(
    templates_root: str | Path = "templates",
) -> list[Path]:
    root = Path(templates_root)
    return [
        path
        for path in sorted(root.rglob("*.html"))
        if path.name.startswith(("image_", "video_", "asset_"))
    ]


def lint_repository_media_templates(
    templates_root: str | Path = "templates",
) -> dict[str, list[str]]:
    from pixelle_video.services.template_media_lint import lint_media_template

    failures: dict[str, list[str]] = {}
    for path in iter_repository_media_templates(templates_root):
        result = lint_media_template(path)
        if result.errors:
            failures[str(path)] = result.errors
    return failures


def _get_templates_for_orientation(
    template_type: TemplateType,
    orientation: TemplateOrientation,
) -> list[TemplateInfo]:
    grouped = get_templates_grouped_by_size_and_type(template_type)
    return [
        template
        for templates in grouped.values()
        for template in templates
        if template.display_info.orientation == orientation
    ]


def _raise_missing_orientation_template(
    template_type: TemplateType,
    orientation: TemplateOrientation,
) -> None:
    raise ValueError(
        f"No {orientation} template is available for {template_type} storyboard type."
    )


def _resolve_registered_default_template(
    template_type: TemplateType,
    orientation: TemplateOrientation,
    candidates: list[TemplateInfo],
) -> str:
    default_template = DEFAULT_TEMPLATE_BY_TYPE_AND_ORIENTATION.get(template_type, {}).get(
        orientation
    )
    if default_template is None:
        _raise_missing_orientation_template(template_type, orientation)

    if any(template.template_path == default_template for template in candidates):
        return default_template

    raise ValueError(
        f"Registered default template '{default_template}' is not available "
        f"for {template_type} {orientation}."
    )


def resolve_default_template_for_type_and_orientation(
    template_type: TemplateType,
    orientation: TemplateOrientation,
) -> str:
    candidates = _get_templates_for_orientation(template_type, orientation)
    if not candidates:
        _raise_missing_orientation_template(template_type, orientation)

    return _resolve_registered_default_template(template_type, orientation, candidates)


def resolve_compatible_template_for_orientation(
    *,
    current_template: str,
    template_type: TemplateType,
    orientation: TemplateOrientation,
) -> str:
    current_name = Path(current_template).name
    if (
        get_template_orientation(current_template) == orientation
        and get_template_type(current_name) == template_type
    ):
        return current_template

    candidates = _get_templates_for_orientation(template_type, orientation)
    if not candidates:
        _raise_missing_orientation_template(template_type, orientation)

    same_name = [
        template
        for template in candidates
        if Path(template.template_path).name == current_name
    ]
    if same_name:
        return same_name[0].template_path

    return _resolve_registered_default_template(template_type, orientation, candidates)
