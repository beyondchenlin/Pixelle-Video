---
prompt_id: structured_schema_output
version: 2026-05-24
stage: llm_gateway
purpose: Wrap a caller-owned prompt with a traceable Pydantic schema output contract.
output_contract: JSON object matching the supplied schema
---
# Source Prompt

{prompt}

# JSON output requirements

- Return JSON only.
- You MUST respond with ONLY a valid JSON object.
- Do not include Markdown fences, commentary, headings, or extra text.
- The JSON object must strictly follow this schema for `{response_type_name}`:

```json
{schema_json}
```

- Output ONLY the JSON object, nothing else.
