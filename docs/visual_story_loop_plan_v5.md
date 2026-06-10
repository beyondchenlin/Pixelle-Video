# Visual Story Loop Plan v5.1

Visual Story Loop Plan introduces local batch orchestration for long-form article visual generation.

## Runtime sequence

1. Source text is prepared.
2. VisualStoryEngineService analyzes article visual routes, route/IP compatibility, and style harmonization.
3. When `visual_story_loop_enabled=true`, frame-level visual/IP plans are delegated to VisualStoryBatchOrchestrator.
4. The orchestrator creates a deterministic VisualStoryExecutionPlan.
5. Each batch receives a bounded Context Contract.
6. Batch LLM calls generate FrameVisualPlan and FrameIPFusionPlan.
7. The resulting compact plans are attached to per-frame prompt contexts.
8. image_generation and visual_anchor_integration consume only bounded contracts.

## Non-goals

- Do not send full article history to downstream prompt stages.
- Do not duplicate selected_visual_route in every frame for anchor integration.
- Do not store full batch products in request params.

## Default controls

- `visual_story_loop_enabled`: true
- `visual_story_batch_size`: 4
- `visual_story_context_budget`: 9000
