# Reference Image API Gray Release

This document describes the gray reference-image API surface introduced after the prompt-only and workflow-binding PRs.

## Scope

This release exposes only a controlled upload/artifact-ID flow. Public video generation requests must not send server-local paths, remote URLs, data URLs, or base64 image payloads.

Supported flow:

1. Enable the gray API:

```bash
export PIXELLE_REFERENCE_IMAGE_API_ENABLED=true
```

2. Upload a reference image:

```bash
curl -X POST \
  -F "file=@reference.png" \
  http://localhost:6789/api/reference-images/uploads
```

3. Use the returned `upload_id` or `artifact_id` in video generation:

```json
{
  "text": "生成一个关于小白兔的儿童故事",
  "mode": "generate",
  "reference_image": {
    "upload_id": "rimg_example",
    "analysis_mode": "auto",
    "workflow_injection_mode": "off",
    "profile_merge_mode": "supplement"
  }
}
```

## Gray switches

The API upload endpoint is disabled by default.

Environment variables:

```bash
PIXELLE_REFERENCE_IMAGE_API_ENABLED=false
PIXELLE_REFERENCE_IMAGE_UPLOAD_BASE_PATH=_runtime/reference_image_uploads
PIXELLE_REFERENCE_IMAGE_MAX_UPLOAD_SIZE_MB=20
PIXELLE_REFERENCE_IMAGE_MAX_EDGE_PX=8192
PIXELLE_REFERENCE_IMAGE_MAX_PIXELS=40000000
PIXELLE_REFERENCE_IMAGE_UPLOAD_TTL_SECONDS=604800
```

Core config still controls analysis and workflow behavior:

```yaml
reference_image:
  enabled: false
  web_ui_enabled: false
  analysis_mode: off
  workflow_injection_mode: off
  profile_merge_mode: supplement
  workflow_param_overrides: {}
```

Request-scoped `reference_image.analysis_mode`, `reference_image.workflow_injection_mode`, and `reference_image.profile_merge_mode` are gray controls. Use them only for trusted/internal testing until your deployment policy is ready. The Streamlit Web UI reference-image uploader remains hidden unless both `reference_image.enabled=true` and `reference_image.web_ui_enabled=true`.

## Selfhost workflow whitelist example

Physical workflow injection is allowed only when `workflow_injection_mode` is `auto` or `required` and the selected selfhost workflow declares a reference-image parameter or is explicitly whitelisted.

Example whitelist:

```yaml
reference_image:
  workflow_injection_mode: off
  workflow_param_overrides:
    "selfhost/image_reference.json": "reference_image"
    "image_reference.json":
      param_names: ["reference_image"]
```

The override key can be the full workflow key, the workflow filename, or `*`. Keep `workflow_injection_mode: off` for prompt-only gray validation, then test `auto` and `required` only after confirming the workflow actually consumes the listed parameter.

## Upload validation

The upload store validates both file metadata and actual image bytes:

- Allowed file extensions: `.jpg`, `.jpeg`, `.png`, `.webp`.
- Allowed decoded image formats: JPEG, PNG, WEBP.
- Disguised files are rejected, for example BMP bytes uploaded as `reference.png`.
- Empty files, invalid images, unsupported true formats, oversize byte payloads, and oversized dimensions are rejected.
- Pillow decompression-bomb warnings are treated as upload errors.
- Resolving an upload re-checks path containment, file hash, format, and dimensions before returning a record.

## Safety boundaries

- `VideoGenerateRequest.reference_image` accepts only `upload_id` or `artifact_id`.
- `ref_image`, `path`, `local_path`, `source_path`, URLs, and base64 payloads are rejected by the public schema.
- Uploaded files are stored under the controlled API upload root.
- The generation pipeline receives a controlled server-local file path resolved from the upload store, not a user-supplied path.
- For async generation, the internal worker execution params may contain this server-controlled upload-store path so the worker can open the file. This path must not appear in user responses, media result artifacts, or public trace payloads; public/audit payloads use `reference_image_api_source` instead.
- Trace payloads store ID, hash, MIME type, dimensions, and byte size; they do not store user-supplied paths.
- Workflow physical injection remains gated by `workflow_injection_mode` and workflow capability/whitelist checks.

## Current non-goals

- No public arbitrary artifact path resolver.
- No remote image URL resolver.
- No direct base64 image input in video generation requests.
- No production UI default-on behavior.
