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
HTML-based Frame Generator Service

Renders HTML templates to frame images using Playwright for headless browser rendering.

Linux Environment Requirements:
    - fontconfig package must be installed
    - Basic fonts (e.g., fonts-liberation, fonts-noto) recommended
    
    Ubuntu/Debian: sudo apt-get install -y fontconfig fonts-liberation fonts-noto-cjk
    CentOS/RHEL: sudo yum install -y fontconfig liberation-fonts google-noto-cjk-fonts
    
    Playwright browser install: playwright install --with-deps chromium
"""

import asyncio
import os
import re
import shutil
import tempfile
import threading
import uuid
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import unquote, urlparse

from loguru import logger
from PIL import Image

from pixelle_video.models.media_placement import (
    MediaPlacement,
    calculate_media_box,
    project_canvas_box_to_template,
    resolve_media_placement,
)
from pixelle_video.models.template_parameters import is_reserved_template_param
from pixelle_video.services.frame_render_readiness import FrameRenderReadiness
from pixelle_video.utils.os_util import get_temp_path
from pixelle_video.utils.template_util import parse_template_size


@dataclass
class _BrowserState:
    browser: Any
    playwright: Any


class HTMLFrameGenerator:
    """
    HTML-based frame generator
    
    Renders HTML templates to frame images with variable substitution.
    Uses Playwright for reliable headless browser rendering.
    
    Usage:
        >>> generator = HTMLFrameGenerator("templates/modern.html")
        >>> frame_path = await generator.generate_frame(
        ...     topic="Why reading matters",
        ...     text="Reading builds new neural pathways...",
        ...     image="/path/to/image.png",
        ...     ext={"content_title": "Sample Title", "content_author": "Author Name"}
        ... )
    """
    
    _browser_states: dict[int, _BrowserState] = {}
    _browser_locks: dict[int, asyncio.Lock] = {}
    _state_guard = threading.Lock()

    def __init__(
        self,
        template_path: str,
        *,
        canvas_width: int | None = None,
        canvas_height: int | None = None,
        canvas_fit: str = "contain",
        render_readiness: FrameRenderReadiness | None = None,
    ):
        """
        Initialize HTML frame generator
        
        Args:
            template_path: Path to HTML template file (e.g., "templates/1080x1920/image_default.html")
        """
        self.template_path = template_path
        self.template = self._load_template(template_path)
        
        self.template_width, self.template_height = parse_template_size(template_path)
        if canvas_width is None and canvas_height is None:
            canvas_width = self.template_width
            canvas_height = self.template_height
        elif canvas_width is None or canvas_height is None:
            raise ValueError("canvas_width and canvas_height must be provided together")

        self.width = int(canvas_width)
        self.height = int(canvas_height)
        if self.width <= 0 or self.height <= 0:
            raise ValueError("canvas dimensions must be positive")
        if canvas_fit not in {"contain", "cover"}:
            raise ValueError("canvas_fit must be 'contain' or 'cover'")
        self.canvas_fit = canvas_fit
        self.render_readiness = render_readiness or FrameRenderReadiness()
        
        self._check_linux_dependencies()
        logger.debug(
            "Loaded HTML template: "
            f"{template_path} "
            f"(template: {self.template_width}x{self.template_height}, "
            f"canvas: {self.width}x{self.height})"
        )
    
    
    def _check_linux_dependencies(self):
        """Check Linux system dependencies and warn if missing"""
        if os.name != 'posix':
            return
        
        try:
            import subprocess
            
            result = subprocess.run(
                ['fc-list'], 
                capture_output=True, 
                timeout=2
            )
            
            if result.returncode != 0:
                logger.warning(
                    "fontconfig not found or not working properly. "
                    "Install with: sudo apt-get install -y fontconfig fonts-liberation fonts-noto-cjk"
                )
            elif not result.stdout:
                logger.warning(
                    "No fonts detected by fontconfig. "
                    "Install fonts with: sudo apt-get install -y fonts-liberation fonts-noto-cjk"
                )
            else:
                logger.debug(f"Fontconfig detected {len(result.stdout.splitlines())} fonts")
                
        except FileNotFoundError:
            logger.warning(
                "fontconfig (fc-list) not found on system. "
                "Install with: sudo apt-get install -y fontconfig"
            )
        except Exception as e:
            logger.debug(f"Could not check fontconfig status: {e}")
    
    def _load_template(self, template_path: str) -> str:
        """Load HTML template from file"""
        path = Path(template_path)
        if not path.exists():
            raise FileNotFoundError(f"Template not found: {template_path}")
        
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        logger.debug(f"Template loaded: {len(content)} chars")
        return content
    
    def _parse_media_size_from_meta(self) -> tuple[Optional[int], Optional[int]]:
        """
        Parse media size from meta tags in template
        
        Looks for meta tags:
        - <meta name="template:media-width" content="1024">
        - <meta name="template:media-height" content="1024">
        
        Returns:
            Tuple of (width, height) or (None, None) if not found
        """
        from bs4 import BeautifulSoup
        
        try:
            soup = BeautifulSoup(self.template, 'html.parser')
            
            width_meta = soup.find('meta', attrs={'name': 'template:media-width'})
            height_meta = soup.find('meta', attrs={'name': 'template:media-height'})
            
            if width_meta and height_meta:
                width = int(width_meta.get('content', 0))
                height = int(height_meta.get('content', 0))
                
                if width > 0 and height > 0:
                    logger.debug(f"Found media size in meta tags: {width}x{height}")
                    return width, height
            
            return None, None
            
        except Exception as e:
            logger.warning(f"Failed to parse media size from meta tags: {e}")
            return None, None
    
    def get_media_size(self) -> tuple[int, int]:
        """
        Get media size for image/video generation
        
        Returns media size specified in template meta tags.
        
        Returns:
            Tuple of (width, height)
        """
        media_width, media_height = self._parse_media_size_from_meta()
        
        if media_width and media_height:
            return media_width, media_height
        
        logger.warning(f"No media size meta tags found in template {self.template_path}, using fallback 1024x1024")
        return 1024, 1024
    
    def parse_template_parameters(self) -> Dict[str, Dict[str, Any]]:
        """
        Parse custom parameters from HTML template
        
        Supports syntax: {{param:type=default}}
        - {{param}} -> text type, no default
        - {{param=value}} -> text type, with default
        - {{param:type}} -> specified type, no default
        - {{param:type=value}} -> specified type, with default
        
        Supported types: text, number, color, bool
        
        Returns:
            Dictionary of custom parameters with their configurations:
            {
                'param_name': {
                    'type': 'text' | 'number' | 'color' | 'bool',
                    'default': Any,
                    'label': str  # same as param_name
                }
            }
        """
        PARAM_PATTERN = r'\{\{([a-zA-Z_][a-zA-Z0-9_]*)(?::([a-z]+))?(?:=([^}]+))?\}\}'
        
        params = {}
        
        for match in re.finditer(PARAM_PATTERN, self.template):
            param_name = match.group(1)
            param_type = match.group(2) or 'text'
            default_value = match.group(3)
            
            if is_reserved_template_param(param_name):
                continue
            
            if param_name in params:
                continue
            
            if param_type not in {'text', 'number', 'color', 'bool'}:
                logger.warning(f"Unknown parameter type '{param_type}' for '{param_name}', defaulting to 'text'")
                param_type = 'text'
            
            parsed_default = self._parse_default_value(param_type, default_value)
            
            params[param_name] = {
                'type': param_type,
                'default': parsed_default,
                'label': param_name,
            }
        
        if params:
            logger.debug(f"Parsed {len(params)} custom parameter(s) from template: {list(params.keys())}")
        
        return params
    
    def _parse_default_value(self, param_type: str, value_str: Optional[str]) -> Any:
        """
        Parse default value based on parameter type
        
        Args:
            param_type: Type of parameter (text, number, color, bool)
            value_str: String value to parse (can be None)
        
        Returns:
            Parsed value with appropriate type
        """
        if value_str is None:
            return {
                'text': '',
                'number': 0,
                'color': '#000000',
                'bool': False,
            }.get(param_type, '')
        
        if param_type == 'number':
            try:
                if '.' in value_str:
                    return float(value_str)
                else:
                    return int(value_str)
            except ValueError:
                logger.warning(f"Invalid number value '{value_str}', using 0")
                return 0
        
        elif param_type == 'bool':
            return value_str.lower() in {'true', '1', 'yes', 'on'}
        
        elif param_type == 'color':
            if value_str.startswith('#'):
                return value_str
            else:
                return f'#{value_str}'
        
        else:  # text
            return value_str
    
    def _replace_parameters(self, html: str, values: Dict[str, Any]) -> str:
        """
        Replace parameter placeholders with actual values
        
        Supports DSL syntax: {{param:type=default}}
        - If value provided in values dict, use it
        - Otherwise, use default value from placeholder
        - If no default, use empty string
        
        Args:
            html: HTML template content
            values: Dictionary of parameter values
        
        Returns:
            HTML with placeholders replaced
        """
        PARAM_PATTERN = r'\{\{([a-zA-Z_][a-zA-Z0-9_]*)(?::([a-z]+))?(?:=([^}]+))?\}\}'
        
        def replacer(match):
            param_name = match.group(1)
            default_value_str = match.group(3)
            
            if param_name in values:
                value = values[param_name]
                if isinstance(value, bool):
                    return 'true' if value else 'false'
                return str(value) if value is not None else ''
            
            elif default_value_str:
                return default_value_str
            
            else:
                return ''
        
        return re.sub(PARAM_PATTERN, replacer, html)

    def _prepare_html_for_render(self, html: str) -> str:
        """Inject a template-root base href so relative assets resolve from the template directory."""
        if re.search(r"<base\b", html, flags=re.IGNORECASE):
            return html

        template_root = Path(self.template_path).resolve().parent.as_uri().rstrip("/") + "/"
        base_tag = f'<base href="{template_root}">'

        head_match = re.search(r"<head[^>]*>", html, flags=re.IGNORECASE)
        if head_match:
            insert_at = head_match.end()
            return f"{html[:insert_at]}{base_tag}{html[insert_at:]}"

        html_match = re.search(r"<html[^>]*>", html, flags=re.IGNORECASE)
        if html_match:
            insert_at = html_match.end()
            return f"{html[:insert_at]}<head>{base_tag}</head>{html[insert_at:]}"

        return f"{base_tag}{html}"

    def _resolve_media_source_size(
        self,
        media_url: str,
        *,
        media_width: int | None,
        media_height: int | None,
    ) -> tuple[int, int]:
        source_path = self._media_url_to_local_path(media_url)
        if source_path and source_path.exists():
            try:
                with Image.open(source_path) as source:
                    return source.width, source.height
            except Exception as exc:
                logger.debug(
                    f"Could not inspect media dimensions with PIL: {source_path} ({exc})"
                )

        return (
            max(1, int(media_width or self.width)),
            max(1, int(media_height or self.height)),
        )

    def _media_url_to_local_path(self, media_url: str) -> Path | None:
        if not media_url:
            return None
        if media_url.startswith("file://"):
            parsed = urlparse(media_url)
            if parsed.scheme != "file":
                return None
            path = unquote(parsed.path)
            if os.name == "nt" and path.startswith("/") and re.match(r"^/[a-zA-Z]:", path):
                path = path[1:]
            return Path(path)
        if media_url.startswith(("http://", "https://", "data:")):
            return None

        path = Path(media_url)
        if not path.is_absolute():
            path = Path.cwd() / path
        return path

    def _build_standard_media_layer(
        self,
        *,
        media_url: str,
        media_type: str,
        media_placement: MediaPlacement,
        media_width: int | None,
        media_height: int | None,
    ) -> tuple[str, dict[str, str]]:
        normalized_media_type = str(media_type or "image").strip().lower()
        if normalized_media_type not in {"image", "video"}:
            raise ValueError("media_type must be 'image' or 'video'")

        source_width, source_height = self._resolve_media_source_size(
            media_url,
            media_width=media_width,
            media_height=media_height,
        )
        canvas_box = calculate_media_box(
            canvas_width=self.width,
            canvas_height=self.height,
            media_source_width=source_width,
            media_source_height=source_height,
            placement=media_placement,
        )
        template_box = project_canvas_box_to_template(
            canvas_box,
            canvas_width=self.width,
            canvas_height=self.height,
            template_width=self.template_width,
            template_height=self.template_height,
            canvas_fit=self.canvas_fit,
        )
        escaped_url = escape(media_url or "", quote=True)
        if normalized_media_type == "video":
            media_tag = (
                f'<video class="pixelle-media" src="{escaped_url}" '
                "muted playsinline></video>"
            )
        else:
            media_tag = f'<img class="pixelle-media" src="{escaped_url}" alt="">'

        layer = (
            '<div class="pixelle-media-layer">'
            '<div class="pixelle-media-box" data-pixelle-media-box>'
            f"{media_tag}"
            "</div>"
            "</div>"
        )
        variables = {
            "pixelle_media_display_width": f"{round(template_box.width)}px",
            "pixelle_media_display_height": f"{round(template_box.height)}px",
            "pixelle_media_left": f"{round(template_box.left)}px",
            "pixelle_media_top": f"{round(template_box.top)}px",
        }
        return layer, variables

    def _inject_standard_media_css(self, html: str, variables: dict[str, str]) -> str:
        css = f"""
<style data-pixelle-media-placement>
:root {{
  --pixelle-media-display-width: {variables["pixelle_media_display_width"]};
  --pixelle-media-display-height: {variables["pixelle_media_display_height"]};
  --pixelle-media-left: {variables["pixelle_media_left"]};
  --pixelle-media-top: {variables["pixelle_media_top"]};
}}
.pixelle-media-layer {{
  position: fixed;
  inset: 0;
  pointer-events: none;
}}
.pixelle-media-box {{
  position: absolute;
  box-sizing: border-box;
  width: var(--pixelle-media-display-width);
  height: var(--pixelle-media-display-height);
  left: var(--pixelle-media-left);
  top: var(--pixelle-media-top);
}}
.pixelle-media {{
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
}}
</style>"""
        head_match = re.search(r"</head>", html, flags=re.IGNORECASE)
        if head_match:
            return f"{html[:head_match.start()]}{css}{html[head_match.start():]}"
        return f"{css}{html}"

    def _build_render_html(
        self,
        *,
        title: str,
        text: str,
        image: str,
        ext: Optional[Dict[str, Any]],
        media_placement: MediaPlacement | dict[str, Any] | None,
        media_type: str,
        media_width: int | None,
        media_height: int | None,
    ) -> str:
        if not self._template_consumes_standard_media_layer():
            context = {
                "title": title,
                "text": text,
                "image": image,
            }
            if ext:
                context.update(ext)
            return self._replace_parameters(self.template, context)

        layer, media_variables = self._build_standard_media_layer(
            media_url=image,
            media_type=media_type,
            media_placement=resolve_media_placement(media_placement),
            media_width=media_width,
            media_height=media_height,
        )
        context = dict(ext or {})
        context.update(
            {
                "title": title,
                "text": text,
                "image": image,
                "pixelle_media_layer": layer,
                **media_variables,
            }
        )
        html = self._replace_parameters(self.template, context)
        return self._inject_standard_media_css(html, media_variables)

    def _template_consumes_standard_media_layer(self) -> bool:
        return bool(
            re.search(
                r"\{\{\s*pixelle_media_(?:layer|display_width|display_height|left|top)\b",
                self.template,
            )
        )

    def _normalize_canvas_output(self, output_path: str) -> None:
        target_size = (int(self.width), int(self.height))
        if target_size == (int(self.template_width), int(self.template_height)):
            return

        with Image.open(output_path) as image:
            frame = image.convert("RGBA")
            if frame.size == target_size:
                return

            if self.canvas_fit == "cover":
                scale = max(target_size[0] / frame.width, target_size[1] / frame.height)
            else:
                scale = min(target_size[0] / frame.width, target_size[1] / frame.height)

            resized_size = (
                max(1, int(round(frame.width * scale))),
                max(1, int(round(frame.height * scale))),
            )
            resized = frame.resize(resized_size, Image.Resampling.LANCZOS)

            if self.canvas_fit == "cover":
                left = max(0, (resized.width - target_size[0]) // 2)
                top = max(0, (resized.height - target_size[1]) // 2)
                normalized = resized.crop(
                    (left, top, left + target_size[0], top + target_size[1])
                )
            else:
                normalized = Image.new("RGBA", target_size, (0, 0, 0, 0))
                left = (target_size[0] - resized.width) // 2
                top = (target_size[1] - resized.height) // 2
                normalized.alpha_composite(resized, (left, top))

            normalized.save(output_path)

    def _preserve_debug_html(self, tmp_html_path: str, output_path: str) -> str | None:
        try:
            target = Path(output_path).with_suffix(".debug.html")
            shutil.copy2(tmp_html_path, target)
            return str(target)
        except Exception as exc:
            logger.warning(f"Failed to preserve debug HTML: {exc}")
            return None

    def _remove_temp_html(self, tmp_html_path: str) -> None:
        try:
            os.unlink(tmp_html_path)
        except Exception as exc:
            logger.debug(f"Failed to delete temporary HTML: {exc}")

    @classmethod
    def _get_browser_lock(cls, loop: asyncio.AbstractEventLoop) -> asyncio.Lock:
        loop_id = id(loop)
        with cls._state_guard:
            lock = cls._browser_locks.get(loop_id)
            if lock is None:
                lock = asyncio.Lock()
                cls._browser_locks[loop_id] = lock
            return lock

    @classmethod
    def _get_browser_state(cls, loop: asyncio.AbstractEventLoop) -> Optional[_BrowserState]:
        with cls._state_guard:
            return cls._browser_states.get(id(loop))

    @classmethod
    def _set_browser_state(cls, loop: asyncio.AbstractEventLoop, state: _BrowserState):
        with cls._state_guard:
            cls._browser_states[id(loop)] = state

    @classmethod
    def _clear_browser_state(
        cls,
        loop: asyncio.AbstractEventLoop,
        expected_state: Optional[_BrowserState] = None,
    ):
        loop_id = id(loop)
        with cls._state_guard:
            state = cls._browser_states.get(loop_id)
            if expected_state is not None and state is not expected_state:
                return
            cls._browser_states.pop(loop_id, None)
            cls._browser_locks.pop(loop_id, None)

    @classmethod
    async def _close_browser_state(
        cls,
        loop: asyncio.AbstractEventLoop,
        state: _BrowserState,
    ):
        try:
            if state.browser:
                await state.browser.close()
            if state.playwright:
                await state.playwright.stop()
        except Exception as e:
            logger.debug(f"Failed to close Playwright browser cleanly: {e}")
        finally:
            logger.debug("Playwright browser closed")
            cls._clear_browser_state(loop, expected_state=state)

    @classmethod
    async def _ensure_browser(cls):
        """Lazily initialize a per-event-loop Playwright browser instance."""
        current_loop = asyncio.get_running_loop()
        browser_lock = cls._get_browser_lock(current_loop)

        async with browser_lock:
            state = cls._get_browser_state(current_loop)
            if state is not None and state.browser.is_connected():
                return state.browser

            if state is not None:
                await cls._close_browser_state(current_loop, state)

            from playwright.async_api import async_playwright

            playwright = await async_playwright().start()
            browser = await playwright.chromium.launch(
                args=[
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-extensions',
                ]
            )
            cls._set_browser_state(
                current_loop,
                _BrowserState(browser=browser, playwright=playwright),
            )
            logger.debug("Initialized Playwright Chromium browser")
            return browser

    @classmethod
    async def close_browser(cls):
        """Shutdown the shared browser instance for the current event loop."""
        current_loop = asyncio.get_running_loop()
        browser_lock = cls._get_browser_lock(current_loop)

        async with browser_lock:
            state = cls._get_browser_state(current_loop)
            if state is None:
                return
            await cls._close_browser_state(current_loop, state)

    async def generate_frame(
        self,
        title: str,
        text: str,
        image: str,
        ext: Optional[Dict[str, Any]] = None,
        output_path: Optional[str] = None,
        media_placement: MediaPlacement | dict[str, Any] | None = None,
        media_type: str = "image",
        media_width: int | None = None,
        media_height: int | None = None,
    ) -> str:
        """
        Generate frame from HTML template
        
        Video size is automatically determined from template path during initialization.
        
        Args:
            title: Video title
            text: Narration text for this frame
            image: Path to AI-generated image (supports relative path, absolute path, or HTTP URL)
            ext: Additional data (content_title, content_author, etc.)
            output_path: Custom output path (auto-generated if None)
        
        Returns:
            Path to generated frame image
        """
        if image and not image.startswith(('http://', 'https://', 'data:', 'file://')):
            image_path = Path(image)
            if not image_path.is_absolute():
                image_path = Path.cwd() / image
            
            if not image_path.exists():
                logger.warning(f"Image file not found: {image_path}")
            else:
                image = image_path.as_uri()
                logger.debug(f"Converted image path to: {image}")
        
        html = self._build_render_html(
            title=title,
            text=text,
            image=image,
            ext=ext,
            media_placement=media_placement,
            media_type=media_type,
            media_width=media_width,
            media_height=media_height,
        )
        html = self._prepare_html_for_render(html)

        if output_path is None:
            from pixelle_video.utils.os_util import get_output_path
            output_filename = f"frame_{uuid.uuid4().hex[:16]}.png"
            output_path = get_output_path(output_filename)
        else:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        logger.debug(
            "Rendering HTML template to "
            f"{output_path} "
            f"(template: {self.template_width}x{self.template_height}, "
            f"canvas: {self.width}x{self.height})"
        )
        tmp_html_path = None
        debug_html_path = None
        rendered = False
        try:
            browser = await self._ensure_browser()
            page = await browser.new_page(
                viewport={'width': self.template_width, 'height': self.template_height},
                device_scale_factor=1,
            )
            try:
                # Write HTML to a temp file and navigate via file:// URL so that
                # local file:// image references are loaded under the same origin.
                fd, tmp_html_path = tempfile.mkstemp(
                    suffix='.html',
                    prefix='pv_frame_',
                    dir=get_temp_path(),
                )
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    f.write(html)
                
                await page.goto(
                    Path(tmp_html_path).as_uri(),
                    wait_until=self.render_readiness.navigation_wait_until,
                    timeout=self.render_readiness.navigation_timeout_ms,
                )
                await self.render_readiness.wait(page)
                await page.screenshot(path=output_path, type='png', omit_background=True)
                self._normalize_canvas_output(output_path)
                rendered = True
            finally:
                try:
                    await page.close()
                except Exception as close_error:
                    logger.debug(f"Failed to close Playwright page cleanly: {close_error}")
                if tmp_html_path and os.path.exists(tmp_html_path):
                    if rendered:
                        self._remove_temp_html(tmp_html_path)
                    else:
                        debug_html_path = self._preserve_debug_html(
                            tmp_html_path,
                            output_path,
                        )
                        self._remove_temp_html(tmp_html_path)
            
            logger.info(f"Frame generated: {output_path}")
            return output_path
            
        except Exception as e:
            diagnostic = (
                f" Debug HTML: {debug_html_path}"
                if debug_html_path
                else ""
            )
            logger.error(f"Failed to render HTML template: {e}{diagnostic}")
            raise RuntimeError(f"HTML rendering failed: {e}{diagnostic}") from e
