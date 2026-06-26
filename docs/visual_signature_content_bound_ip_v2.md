# Content-bound IP v2 change log

This package replaces the default recurring visual signature workflow with **content-bound mandatory IP presence**.

## Product behavior

- The recurring IP still appears in every generated image when visual signature is enabled.
- The default mode no longer uses cards, stickers, bookmarks, labels, stamps, bookplates, surface graphics, watermarks, or corner marks.
- The IP must appear as a content participant: an action executor, reader proxy, observation gateway, system component, conflict participant, scale reference, explanation director, or transformation medium.
- If a frame has no natural action slot, the frame visual metaphor is repaired/replanned. The system does not inject a small carrier.
- Sensitive/serious content is routed toward neutral explanation spaces such as archive rooms, map tables, evidence walls, or model desks rather than placing the IP inside literal real-world incident scenes.

## Architecture changes

- Added `pixelle_video/models/content_bound_ip.py`.
- Added `pixelle_video/services/content_bound_ip_planner.py`.
- Separated default v2 content-bound policy from explicit legacy mark-based policy.
- Added content-bound carrier enums and projection validation.
- Updated frame visual plans and frame IP fusion plans with cognitive anchors, physical metaphors, scene arenas, action affordances, and content-bound presence payloads.
- Batch and non-batch visual story paths now produce the same content-bound contract.
- `rewrite_required` is consumed by deterministic repair before prompt composition.
- Final provider prompts are image-facing visual descriptions and do not include internal policy rules or negative meta-instructions.
- API and UI now expose `series_visual_signature_presentation_mode`, defaulting to `content_bound_mandatory_ip`.
- Video media prompts now fail explicitly if visual signature is enabled, because the previous video path did not actually run the content-bound image projection chain.

## Legacy compatibility

Legacy visual marks remain in the code for old configurations, but they are only available through explicit legacy policy/mode selection. They are rejected by the default v2 policy.

## Verification run

- `python -m compileall -q pixelle_video api web`
- `PYTHONPATH=. pytest -q tests/test_content_bound_ip_v2.py`
