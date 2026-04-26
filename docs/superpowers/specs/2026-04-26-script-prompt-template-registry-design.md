# Script Prompt Template Registry Design

## Goal

Move AI script-generation creative guidance out of Python code while keeping the machine contract enforced by code. Users can enter a topic in AI creation, and Pixelle will generate one complete `source_text` script through a stable JSON contract.

This is a source-level fix for future copywriting quality work: prompt strategy becomes editable and versioned, while output schema, validation, and normalization remain centralized and testable.

## Current State

`pixelle_video/prompts/script_generation.py` builds the script-generation prompt in code. The prompt includes both creative instructions and protocol instructions:

- generate one complete `source_text`
- do not split into storyboard frames
- do not generate image prompts
- return JSON only

That works, but it makes future copywriting iteration require Python edits and mixes creative policy with system contract.

## Design

Introduce a script prompt template registry with three layers.

1. Creative Template Layer

Markdown files define copywriting strategy, tone, structure, and constraints that humans will iterate on.

Example location:

`pixelle_video/prompts/script_templates/default.md`

The Markdown template can contain front matter for identity and metadata:

```md
---
id: default
version: 1
language: zh-CN
name: Default Short Video Script
---

You are a short-video script strategist.

Write a complete script from the user's topic.

Creative requirements:
- Open with the topic quickly.
- Keep the logic coherent before storyboard splitting.
- Use clear progression and a natural ending.
```

2. Prompt Assembly Layer

Python loads the selected template, injects runtime variables, and assembles the final prompt payload.

Runtime variables stay code-owned:

- `topic`
- `length_instruction`
- selected template id/version
- optional future fields such as audience, platform, tone, language, and script archetype

3. Contract Layer

Python always appends and enforces the output contract. This must not be editable only through Markdown.

Contract rules:

- return only a valid JSON object
- match `ScriptGenerationResponse`
- include exactly `source_text`
- no storyboard frames
- no image prompts
- no Markdown fences or prose outside JSON

`ScriptGenerationResponse` remains the Pydantic boundary. Raw model output is parsed, normalized, and validated before entering storyboard planning.

## Data Flow

1. User enters topic in AI creation.
2. UI/API passes topic plus script length settings.
3. `ScriptGenerationService` resolves the active script template.
4. Template registry loads Markdown and metadata.
5. Prompt builder assembles:
   - creative template content
   - runtime inputs
   - code-owned JSON schema contract
6. LLM returns JSON content.
7. `LLMService` parses the JSON into `ScriptGenerationResponse`.
8. Text normalization removes model transport artifacts such as literal newline escapes.
9. Storyboard generation receives canonical `source_text`.

## Template Selection

Initial implementation should support a code/config-selected template id with `default` as fallback. This keeps the feature source-clean without taking on a Web UI editor yet.

Future UI can list templates from the registry and let operators choose one per creation request. Editing templates in the Web UI should be a later feature, with validation and version history.

## Error Handling

- Missing selected template: fall back to `default` only if the configured id is absent; emit a warning.
- Missing default template: raise a startup/runtime configuration error.
- Invalid front matter: raise a clear template validation error.
- Empty template body: raise a clear template validation error.
- Invalid model JSON: use existing structured output repair behavior.
- Dirty text artifacts after parsing: normalize at the script-output boundary, not in TTS/subtitle/UI.

## Testing

Add focused tests for:

- default template is loaded and included in the prompt
- runtime topic and length instruction are injected
- JSON contract is always appended by code
- template body cannot override or remove the schema contract
- missing selected template falls back to default
- missing default template fails clearly
- literal `\n` and `\\n` artifacts are normalized before storyboard planning

## Non-Goals

- No Web UI template editor in the first pass.
- No database-backed prompt management in the first pass.
- No provider-specific prompt branching in templates.
- No relaxing JSON/Pydantic output contracts.

## Acceptance Criteria

- Script generation creative guidance is editable in Markdown.
- Protocol/schema instructions remain enforced by Python.
- Existing AI creation flow works with the default template.
- Tests prove the registry, prompt assembly, and contract boundary.
- The change does not touch TTS, subtitles, image generation, or storyboard rendering except through cleaner `source_text`.
