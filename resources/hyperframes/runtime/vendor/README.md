# HyperFrames Runtime Vendor Assets

This directory is the only approved home for runtime libraries vendored for
compiled Pixelle HyperFrames templates.

Rules:
- Store only repository-local runtime assets here.
- Do not reference CDN-hosted scripts or styles from compiled templates.
- `@hyperframes/producer` remains the runtime authority; vendored files here are
  template dependencies, not a replacement for the producer package.
