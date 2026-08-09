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
FAQ component for displaying frequently asked questions
"""

import re
from html import unescape
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

import streamlit as st
from loguru import logger

from web.i18n import get_language, tr

_FAQ_IMAGE_TAG_PATTERN = re.compile(r"<img\s+[^>]*>", re.IGNORECASE)
_HTML_ATTRIBUTE_PATTERN = re.compile(
    r"(?P<name>src|alt)\s*=\s*(?P<quote>['\"])(?P<value>.*?)(?P=quote)",
    re.IGNORECASE,
)


def load_faq_content(language: str) -> Optional[str]:
    """
    Load FAQ content based on current language
    
    Args:
        language: Current language code (e.g., "zh_CN", "en_US")
    
    Returns:
        FAQ content as markdown string, or None if file not found
    """
    # Determine which FAQ file to load based on language
    # For Chinese (zh_CN), use FAQ_CN.md
    # For all other languages, use FAQ.md (English)
    project_root = Path(__file__).resolve().parent.parent.parent
    
    if language.startswith("zh"):
        faq_file = project_root / "docs" / "FAQ_CN.md"
    else:
        faq_file = project_root / "docs" / "FAQ.md"
    
    try:
        if faq_file.exists():
            with open(faq_file, "r", encoding="utf-8") as f:
                content = f.read()
            logger.debug(f"Loaded FAQ from: {faq_file}")
            return content
        else:
            logger.warning(f"FAQ file not found: {faq_file}")
            return None
    except Exception as e:
        logger.error(f"Failed to load FAQ file {faq_file}: {e}")
        return None


def parse_faq_sections(content: str) -> list[tuple[str, str]]:
    """
    Parse FAQ content into sections by ### headings
    
    Args:
        content: Raw markdown content
    
    Returns:
        List of (question, answer) tuples
    """
    # Remove the first main heading (starts with #, not ###)
    lines = content.split('\n')
    if lines and lines[0].startswith('#') and not lines[0].startswith('##'):
        content = '\n'.join(lines[1:])
    
    # Split by ### headings (top-level questions)
    # Pattern matches ### at start of line followed by question text
    pattern = r'^###\s+(.+?)$'
    
    sections = []
    current_question = None
    current_answer_lines = []
    
    for line in content.split('\n'):
        match = re.match(pattern, line)
        if match:
            # Save previous section if exists
            if current_question is not None:
                answer = '\n'.join(current_answer_lines).strip()
                sections.append((current_question, answer))
            # Start new section
            current_question = match.group(1).strip()
            current_answer_lines = []
        else:
            current_answer_lines.append(line)
    
    # Save last section
    if current_question is not None:
        answer = '\n'.join(current_answer_lines).strip()
        sections.append((current_question, answer))
    
    return sections


def prepare_faq_answer(answer: str) -> str:
    """Convert allowlisted FAQ image tags to safe Markdown images."""

    def replace_image(match: re.Match[str]) -> str:
        attributes = {
            attribute.group("name").casefold(): unescape(attribute.group("value"))
            for attribute in _HTML_ATTRIBUTE_PATTERN.finditer(match.group(0))
        }
        source = attributes.get("src", "")
        parsed = urlsplit(source)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return ""
        alt = attributes.get("alt", "FAQ image").replace("[", "").replace("]", "")
        safe_source = source.replace("(", "%28").replace(")", "%29")
        return f"![{alt}]({safe_source})"

    return _FAQ_IMAGE_TAG_PATTERN.sub(replace_image, answer)


def render_faq_sidebar():
    """
    Render FAQ in the sidebar
    
    This component displays frequently asked questions in the sidebar,
    allowing users to quickly find answers without leaving the main interface.
    """
    with st.sidebar:
        # FAQ header with icon
        # st.markdown(f"### 🙋‍♀️ {tr('faq.title', fallback='FAQ')}")
        
        # Get current language
        current_language = get_language()
        
        # Load FAQ content
        faq_content = load_faq_content(current_language)
        
        if faq_content:
            # A visual expander does not create an execution boundary in Streamlit.
            # Select one answer explicitly so hidden answers and remote images do not load.
            with st.expander(tr('faq.expand_to_view', fallback='FAQ'), expanded=False):
                # Parse FAQ into sections
                sections = parse_faq_sections(faq_content)
                answers = dict(sections)
                if st.session_state.get("faq_selected_question") not in {None, *answers}:
                    st.session_state.pop("faq_selected_question", None)
                selected_question = st.selectbox(
                    tr("faq.select_question"),
                    options=[None, *answers],
                    index=0,
                    format_func=lambda value: value or tr("faq.select_placeholder"),
                    key="faq_selected_question",
                )
                if selected_question:
                    st.markdown(prepare_faq_answer(answers[selected_question]))
            
            # Add a link to GitHub issues for more help
            st.markdown(
                f"💡 {tr('faq.more_help', fallback='Need more help?')} "
                f"[GitHub Issues](https://github.com/AIDC-AI/Pixelle-Video/issues)"
            )
        else:
            # If FAQ cannot be loaded, only show the GitHub link
            st.markdown(f"### 💡 {tr('faq.more_help', fallback='Need help?')}")
            st.markdown(
                "[GitHub Issues](https://github.com/AIDC-AI/Pixelle-Video/issues) | "
                "[Documentation](https://aidc-ai.github.io/Pixelle-Video)"
            )
