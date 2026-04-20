# Default Image Workflow Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Centralize workflow default resolution so `selfhost/image_z_image_turbo.json` becomes the effective default image workflow everywhere without overriding saved user choices.

**Architecture:** Add a shared workflow-default resolver in the config layer, then route both service-side workflow resolution and the Web UI selector through that resolver. Keep runtime fallback behavior authoritative in one module, while aligning schema/example/docs as mirrors for bootstrap and documentation.

**Tech Stack:** Python 3.11, Pydantic, Streamlit, pytest, ripgrep

---

### Task 1: Add Shared Workflow Default Resolution Primitives

**Files:**
- Create: `pixelle_video/config/workflow_defaults.py`
- Modify: `pixelle_video/config/__init__.py`
- Test: `tests/test_workflow_resolution.py`

- [ ] **Step 1: Write the failing resolver tests**

```python
from pixelle_video.config.workflow_defaults import (
    BUILTIN_DEFAULT_WORKFLOWS,
    get_configured_default_workflow,
    resolve_default_workflow,
)


def test_resolve_default_workflow_uses_builtin_image_default_when_config_missing():
    available_keys = [
        "runninghub/image_flux.json",
        "selfhost/image_z_image_turbo.json",
    ]

    assert (
        resolve_default_workflow(
            domain="image",
            available_keys=available_keys,
            configured_workflow=None,
        )
        == "selfhost/image_z_image_turbo.json"
    )


def test_resolve_default_workflow_prefers_saved_value_when_available():
    available_keys = [
        "runninghub/image_flux.json",
        "selfhost/image_z_image_turbo.json",
    ]

    assert (
        resolve_default_workflow(
            domain="image",
            available_keys=available_keys,
            configured_workflow="runninghub/image_flux.json",
        )
        == "runninghub/image_flux.json"
    )


def test_resolve_default_workflow_falls_back_to_first_available_when_builtin_missing():
    available_keys = [
        "runninghub/image_flux.json",
        "selfhost/image_z_image.json",
    ]

    assert (
        resolve_default_workflow(
            domain="image",
            available_keys=available_keys,
            configured_workflow="selfhost/missing.json",
        )
        == "runninghub/image_flux.json"
    )


def test_get_configured_default_workflow_normalizes_nested_tts_shape():
    comfyui_config = {
        "tts": {
            "default_workflow": None,
            "comfyui": {"default_workflow": "selfhost/tts_edge.json"},
        }
    }

    assert get_configured_default_workflow(comfyui_config, "tts") == "selfhost/tts_edge.json"
    assert BUILTIN_DEFAULT_WORKFLOWS["image"] == "selfhost/image_z_image_turbo.json"
```

- [ ] **Step 2: Run the resolver tests to verify they fail**

Run: `pytest tests/test_workflow_resolution.py -v`
Expected: FAIL with `ModuleNotFoundError` or missing-symbol errors because `pixelle_video.config.workflow_defaults` does not exist yet.

- [ ] **Step 3: Write the minimal shared resolver module**

```python
from __future__ import annotations

from typing import Mapping, Optional, Sequence


BUILTIN_DEFAULT_WORKFLOWS = {
    "image": "selfhost/image_z_image_turbo.json",
    "video": "runninghub/video_wan2.1_fusionx.json",
    "tts": "selfhost/tts_edge.json",
}


def normalize_workflow_key(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def get_configured_default_workflow(
    comfyui_config: Mapping[str, object],
    domain: str,
) -> Optional[str]:
    domain_config = comfyui_config.get(domain, {})
    if domain == "tts" and isinstance(domain_config, Mapping):
        nested_comfyui = domain_config.get("comfyui", {})
        if isinstance(nested_comfyui, Mapping):
            nested_value = normalize_workflow_key(nested_comfyui.get("default_workflow"))
            if nested_value:
                return nested_value
    if isinstance(domain_config, Mapping):
        return normalize_workflow_key(domain_config.get("default_workflow"))
    return None


def resolve_default_workflow(
    domain: str,
    available_keys: Sequence[str],
    configured_workflow: Optional[str],
) -> Optional[str]:
    normalized_configured = normalize_workflow_key(configured_workflow)
    if normalized_configured and normalized_configured in available_keys:
        return normalized_configured

    builtin_default = BUILTIN_DEFAULT_WORKFLOWS.get(domain)
    if builtin_default and builtin_default in available_keys:
        return builtin_default

    return available_keys[0] if available_keys else None
```

Also export the new helpers from `pixelle_video/config/__init__.py`:

```python
from .workflow_defaults import (
    BUILTIN_DEFAULT_WORKFLOWS,
    get_configured_default_workflow,
    resolve_default_workflow,
)
```

- [ ] **Step 4: Run the resolver tests to verify they pass**

Run: `pytest tests/test_workflow_resolution.py -v`
Expected: PASS for the four new resolver tests.

- [ ] **Step 5: Commit the resolver primitives**

```bash
git add pixelle_video/config/workflow_defaults.py pixelle_video/config/__init__.py tests/test_workflow_resolution.py
git commit -m "feat: add shared workflow default resolver"
```

### Task 2: Route Service-Level Workflow Resolution Through the Shared Resolver

**Files:**
- Modify: `pixelle_video/services/comfy_base_service.py`
- Modify: `pixelle_video/services/media.py`
- Test: `tests/test_workflow_resolution.py`

- [ ] **Step 1: Extend the test file with service-resolution failures**

```python
import pytest

from pixelle_video.services.comfy_base_service import ComfyBaseService
from pixelle_video.services.media import MediaService


def _workflow_info(key: str) -> dict:
    source, name = key.split("/", 1)
    return {
        "name": name,
        "display_name": f"{name} - {source.title()}",
        "source": source,
        "path": f"workflows/{key}",
        "key": key,
    }


class DummyImageService(ComfyBaseService):
    WORKFLOW_PREFIX = "image_"


def test_base_service_uses_builtin_default_when_config_is_unset(monkeypatch):
    service = DummyImageService(
        {"comfyui": {"image": {"default_workflow": None}}},
        service_name="image",
        core=object(),
    )
    monkeypatch.setattr(
        service,
        "_scan_workflows",
        lambda: [
            _workflow_info("runninghub/image_flux.json"),
            _workflow_info("selfhost/image_z_image_turbo.json"),
        ],
    )

    assert service._resolve_workflow()["key"] == "selfhost/image_z_image_turbo.json"


def test_media_service_uses_video_domain_default_for_video_requests(monkeypatch):
    service = MediaService(
        {
            "comfyui": {
                "image": {"default_workflow": None},
                "video": {"default_workflow": None},
            }
        },
        core=object(),
    )
    monkeypatch.setattr(
        service,
        "_scan_workflows",
        lambda: [
            _workflow_info("selfhost/image_z_image_turbo.json"),
            _workflow_info("runninghub/video_wan2.1_fusionx.json"),
        ],
    )

    assert (
        service._resolve_workflow(workflow=None, workflow_domain="video")["key"]
        == "runninghub/video_wan2.1_fusionx.json"
    )


def test_base_service_still_raises_for_explicit_missing_workflow(monkeypatch):
    service = DummyImageService(
        {"comfyui": {"image": {"default_workflow": None}}},
        service_name="image",
        core=object(),
    )
    monkeypatch.setattr(
        service,
        "_scan_workflows",
        lambda: [_workflow_info("selfhost/image_z_image_turbo.json")],
    )

    with pytest.raises(ValueError, match="Workflow 'selfhost/missing.json' not found"):
        service._resolve_workflow(workflow="selfhost/missing.json")
```

- [ ] **Step 2: Run the service-resolution tests to verify they fail**

Run: `pytest tests/test_workflow_resolution.py -v`
Expected: FAIL because `ComfyBaseService._resolve_workflow()` does not yet accept `workflow_domain`, and missing config still raises instead of falling back.

- [ ] **Step 3: Implement shared resolver wiring in the services**

Update `pixelle_video/services/comfy_base_service.py`:

```python
from pixelle_video.config.workflow_defaults import (
    get_configured_default_workflow,
    resolve_default_workflow,
)


def _get_default_workflow(
    self,
    workflow_domain: Optional[str] = None,
    available_keys: Optional[List[str]] = None,
) -> str:
    domain = workflow_domain or self.service_name
    available_keys = available_keys or self.available
    configured_workflow = get_configured_default_workflow(self.global_config, domain)
    resolved_workflow = resolve_default_workflow(domain, available_keys, configured_workflow)

    if not resolved_workflow:
        raise ValueError(
            f"No compatible workflows available for {domain}. "
            f"Available workflows: {', '.join(available_keys) if available_keys else 'none'}"
        )

    return resolved_workflow


def _resolve_workflow(
    self,
    workflow: Optional[str] = None,
    workflow_domain: Optional[str] = None,
) -> Dict[str, Any]:
    available_workflows = self._scan_workflows()
    available_keys = [wf["key"] for wf in available_workflows]

    if workflow is None:
        workflow = self._get_default_workflow(
            workflow_domain=workflow_domain,
            available_keys=available_keys,
        )
```

Update `pixelle_video/services/media.py` so the selected `media_type` chooses the correct domain default:

```python
workflow_info = self._resolve_workflow(
    workflow=workflow,
    workflow_domain=media_type,
)
```

- [ ] **Step 4: Run the service-resolution tests to verify they pass**

Run: `pytest tests/test_workflow_resolution.py -v`
Expected: PASS for both new service tests and the resolver tests from Task 1.

- [ ] **Step 5: Commit the service-level wiring**

```bash
git add pixelle_video/services/comfy_base_service.py pixelle_video/services/media.py tests/test_workflow_resolution.py
git commit -m "fix: resolve workflow defaults through shared service logic"
```

### Task 3: Route the Streamlit Workflow Selector Through the Shared Resolver

**Files:**
- Create: `web/utils/workflow_defaults.py`
- Modify: `web/components/style_config.py`
- Test: `tests/test_workflow_resolution.py`

- [ ] **Step 1: Add UI helper tests that fail first**

```python
from web.utils.workflow_defaults import resolve_selectbox_default_index


def test_resolve_selectbox_default_index_uses_shared_image_default():
    workflow_keys = [
        "runninghub/image_flux.json",
        "selfhost/image_z_image_turbo.json",
    ]

    assert (
        resolve_selectbox_default_index(
            domain="image",
            workflow_keys=workflow_keys,
            configured_workflow=None,
        )
        == 1
    )


def test_resolve_selectbox_default_index_returns_zero_when_no_workflows_exist():
    assert (
        resolve_selectbox_default_index(
            domain="image",
            workflow_keys=[],
            configured_workflow=None,
        )
        == 0
    )
```

- [ ] **Step 2: Run the UI helper tests to verify they fail**

Run: `pytest tests/test_workflow_resolution.py -v`
Expected: FAIL with `ModuleNotFoundError` for `web.utils.workflow_defaults`.

- [ ] **Step 3: Implement the UI helper and replace the old index-0 fallback**

Create `web/utils/workflow_defaults.py`:

```python
from pixelle_video.config.workflow_defaults import resolve_default_workflow


def resolve_selectbox_default_index(
    domain: str,
    workflow_keys: list[str],
    configured_workflow: str | None,
) -> int:
    resolved_key = resolve_default_workflow(
        domain=domain,
        available_keys=workflow_keys,
        configured_workflow=configured_workflow,
    )
    return workflow_keys.index(resolved_key) if resolved_key in workflow_keys else 0
```

Update the workflow selector in `web/components/style_config.py`:

```python
from web.utils.workflow_defaults import resolve_selectbox_default_index


saved_workflow = comfyui_config.get(media_config_key, {}).get("default_workflow")
default_workflow_index = resolve_selectbox_default_index(
    domain=media_config_key,
    workflow_keys=workflow_keys,
    configured_workflow=saved_workflow,
)

if workflow_options:
    workflow_selected_index = workflow_options.index(workflow_display)
    workflow_key = workflow_keys[workflow_selected_index]
else:
    workflow_key = None
```

Keep the existing `No workflows found` selectbox label, but remove the hardcoded `runninghub/image_flux.json` fallback so the UI does not pretend a workflow exists when it does not.

- [ ] **Step 4: Run the UI helper tests to verify they pass**

Run: `pytest tests/test_workflow_resolution.py -v`
Expected: PASS for the new selector-index tests plus all previously added resolver/service tests.

- [ ] **Step 5: Commit the UI default-selection wiring**

```bash
git add web/utils/workflow_defaults.py web/components/style_config.py tests/test_workflow_resolution.py
git commit -m "fix: use shared workflow defaults in streamlit selector"
```

### Task 4: Align Bootstrap Defaults, Comments, and User-Facing Documentation

**Files:**
- Modify: `pixelle_video/config/schema.py`
- Modify: `config.example.yaml`
- Modify: `README.md`
- Modify: `docs/en/reference/config-schema.md`
- Modify: `docs/zh/reference/config-schema.md`
- Modify: `pixelle_video/services/media.py`
- Modify: `pixelle_video/services/comfy_base_service.py`
- Test: `tests/test_workflow_resolution.py`

- [ ] **Step 1: Add a bootstrap-default test that fails first**

```python
from pixelle_video.config.schema import PixelleVideoConfig


def test_schema_bootstrap_defaults_match_the_new_image_workflow():
    config = PixelleVideoConfig()

    assert config.comfyui.image.default_workflow == "selfhost/image_z_image_turbo.json"
    assert config.comfyui.video.default_workflow == "runninghub/video_wan2.1_fusionx.json"
```

- [ ] **Step 2: Run the bootstrap-default test to verify it fails**

Run: `pytest tests/test_workflow_resolution.py -v`
Expected: FAIL because `PixelleVideoConfig().comfyui.image.default_workflow` is still `None`.

- [ ] **Step 3: Update bootstrap defaults and stale documentation**

Update `pixelle_video/config/schema.py`:

```python
class ImageSubConfig(BaseModel):
    default_workflow: Optional[str] = Field(
        default="selfhost/image_z_image_turbo.json",
        description="Default image workflow (optional)",
    )


class VideoSubConfig(BaseModel):
    default_workflow: Optional[str] = Field(
        default="runninghub/video_wan2.1_fusionx.json",
        description="Default video workflow (optional)",
    )
```

Update the YAML example in `config.example.yaml`:

```yaml
image:
  # Required: Default workflow to use
  # Options: selfhost/image_z_image_turbo.json (recommended for this repo's default illustration flow)
  #          runninghub/image_flux.json (cloud alternative)
  default_workflow: selfhost/image_z_image_turbo.json
```

Update the user-facing docs so they stop claiming `image_flux.json` is the default:

```md
- Default image workflow: `selfhost/image_z_image_turbo.json`
- Saved user configuration still overrides the built-in default
```

Also update the stale developer-facing comments/docstrings in `pixelle_video/services/media.py` and `pixelle_video/services/comfy_base_service.py` so examples no longer describe `image_flux.json` as the implied default path.

- [ ] **Step 4: Run the targeted regression tests after the doc/bootstrap alignment**

Run: `pytest tests/test_workflow_resolution.py tests/test_selfhost_workflows.py -v`
Expected: PASS for the new schema-default test and the existing selfhost workflow parsing tests.

- [ ] **Step 5: Commit the bootstrap and documentation alignment**

```bash
git add pixelle_video/config/schema.py config.example.yaml README.md docs/en/reference/config-schema.md docs/zh/reference/config-schema.md pixelle_video/services/media.py pixelle_video/services/comfy_base_service.py tests/test_workflow_resolution.py
git commit -m "docs: align bootstrap defaults with shared workflow resolver"
```

### Task 5: Run Final Verification Before Claiming Completion

**Files:**
- Verify: `tests/test_workflow_resolution.py`
- Verify: `tests/test_selfhost_workflows.py`
- Verify: `tests/test_comfykit_config.py`
- Verify: `web/components/style_config.py`
- Verify: `pixelle_video/services/comfy_base_service.py`

- [ ] **Step 1: Run the focused regression suite**

Run: `pytest tests/test_workflow_resolution.py tests/test_selfhost_workflows.py tests/test_comfykit_config.py -v`
Expected: PASS with coverage for resolver behavior, selfhost workflow parsing, and existing ComfyKit config behavior.

- [ ] **Step 2: Run a linter pass on touched Python files**

Run: `ruff check pixelle_video/config/workflow_defaults.py pixelle_video/services/comfy_base_service.py pixelle_video/services/media.py web/utils/workflow_defaults.py web/components/style_config.py tests/test_workflow_resolution.py`
Expected: PASS with no import-order or syntax violations.

- [ ] **Step 3: Inspect the final commit set before handoff**

Run: `git log --stat --oneline -n 4`
Expected: the last four commits correspond to the resolver, service, UI, and bootstrap/docs tasks from this feature.
