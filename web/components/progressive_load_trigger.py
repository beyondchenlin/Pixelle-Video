"""Viewport-driven progressive loading with a compatible manual fallback."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import streamlit as st

_PROGRESSIVE_LOAD_HTML = """
<button type="button" data-progressive-load></button>
"""

_PROGRESSIVE_LOAD_CSS = """
:host {
  display: block;
  min-height: 1px;
}

[data-progressive-load] {
  width: 1px;
  height: 1px;
  margin: 0;
  padding: 0;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
  border: 0;
}

[data-progressive-load]:focus-visible,
[data-progressive-load].progressive-load-fallback {
  width: 100%;
  height: 2.25rem;
  margin: 0.5rem 0;
  padding: 0 1rem;
  overflow: visible;
  clip-path: none;
  color: var(--st-text-color);
  background: var(--st-secondary-background-color);
  border: 1px solid color-mix(in srgb, var(--st-text-color) 20%, transparent);
  border-radius: 0.5rem;
  cursor: pointer;
}
"""

_PROGRESSIVE_LOAD_JS = """
export default function(component) {
  const { data, parentElement, setTriggerValue } = component;
  const trigger = parentElement.querySelector('[data-progressive-load]');

  if (!trigger) {
    return;
  }

  trigger.textContent = data.label;
  let requested = false;

  const requestMore = () => {
    if (requested) {
      return;
    }
    requested = true;
    setTriggerValue('request_more', true);
  };

  trigger.onclick = requestMore;

  const showFallback = () => {
    trigger.classList.add('progressive-load-fallback');
  };

  if (!('IntersectionObserver' in window)) {
    showFallback();
    return () => {
      trigger.onclick = null;
    };
  }

  let observer;
  try {
    observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          observer.disconnect();
          requestMore();
        }
      },
      {
        root: null,
        rootMargin: '800px 0px',
        threshold: 0,
      },
    );

    observer.observe(trigger);
  } catch (_error) {
    showFallback();
  }

  return () => {
    observer?.disconnect();
    trigger.onclick = null;
  };
}
"""


def _declare_progressive_load_component() -> Callable[..., Any] | None:
    try:
        from streamlit.components.v2 import component
    except ImportError:
        return None

    return component(
        "pixelle_progressive_load_trigger",
        html=_PROGRESSIVE_LOAD_HTML,
        css=_PROGRESSIVE_LOAD_CSS,
        js=_PROGRESSIVE_LOAD_JS,
        isolate_styles=True,
    )


_PROGRESSIVE_LOAD_COMPONENT = _declare_progressive_load_component()


def render_progressive_load_trigger(
    *,
    label: str,
    key: str,
    on_request_more: Callable[[], None],
    ui: Any = st,
) -> bool:
    """Load the next batch near the viewport, or expose a manual fallback."""
    if _PROGRESSIVE_LOAD_COMPONENT is not None:
        _PROGRESSIVE_LOAD_COMPONENT(
            key=key,
            data={"label": str(label)},
            height="content",
            on_request_more_change=on_request_more,
        )
        return True

    return bool(
        ui.button(
            str(label),
            key=f"{key}_fallback",
            on_click=on_request_more,
            width="stretch",
        )
    )


__all__ = ["render_progressive_load_trigger"]
