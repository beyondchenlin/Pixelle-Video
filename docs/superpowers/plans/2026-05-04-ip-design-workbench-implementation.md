# IP Design Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a first-class IP Design Workbench so users create and edit AssetBible / SceneCast before consuming them in Storyboard Workbench.

**Architecture:** Keep backend AssetBible / SceneCast APIs as the single source of truth. Add a Streamlit page and design client boundary for IP creation/editing, while the existing Storyboard IP panel remains an apply-only consumer.

**Tech Stack:** Python, Streamlit, FastAPI-backed repository contracts, pytest, ruff.

---

### Task 1: Navigation And Page Shell

**Files:**
- Modify: `web/app.py`
- Create: `web/pages/3_IP_Design_Workbench.py`
- Create: `web/pages/4_🧭_Storyboard_Workbench.py`
- Delete: `web/pages/3_🧭_Storyboard_Workbench.py`
- Test: `tests/test_ip_design_workbench_page.py`

- [x] Write failing tests for navigation and page rendering.
- [x] Add the IP Design page to `build_navigation_pages()`.
- [x] Create the page shell that initializes session/i18n and renders the design workbench.
- [x] Run page tests to green.

### Task 2: IP Design Client Boundary

**Files:**
- Create: `web/ip_design/client.py`
- Create: `web/ip_design/http_client.py`
- Create: `web/ip_design/inprocess_client.py`
- Create: `web/ip_design/__init__.py`
- Create: `web/state/ip_design_client.py`
- Modify: `web/utils/asset_bible_api.py`
- Test: `tests/test_ip_design_client.py`

- [x] Write failing tests for list/create/update/load AssetBible and SceneCast through the client boundary.
- [x] Add HTTP helper functions for load/update while keeping helpers out of formal UI.
- [x] Implement HTTP and in-process clients.
- [x] Resolve clients using the existing workbench client mode.
- [x] Run client tests to green.

### Task 3: IP Design Workbench Component

**Files:**
- Create: `web/components/ip_design_workbench.py`
- Test: `tests/test_ip_design_workbench_ui.py`

- [x] Write failing UI tests for create/edit AssetBible, create/edit SceneCast, empty states, and fail-closed client handling.
- [x] Implement a production UI with separate AssetBible and SceneCast sections.
- [x] Keep Streamlit controls dense and operational; no marketing copy.
- [x] Run UI tests to green.

### Task 4: Localization And Boundary Regression

**Files:**
- Modify: `web/i18n/locales/en_US.json`
- Modify: `web/i18n/locales/zh_CN.json`
- Test: `tests/test_i18n.py`
- Test: `tests/test_ip_design_workbench_page.py`

- [x] Add missing `ip_workbench.panel.*` keys.
- [x] Add new `ip_design.*` keys.
- [x] Add source-boundary tests so formal IP design UI does not import `httpx`, `web.utils.asset_bible_api`, or transport constants.
- [ ] Run focused regression, lint, diff check, then commit and push.
