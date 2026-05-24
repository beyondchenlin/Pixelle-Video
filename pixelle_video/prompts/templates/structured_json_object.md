---
prompt_id: structured_json_object
version: 2026-05-24
stage: llm_gateway
purpose: Wrap a caller-owned prompt with a traceable JSON-object output contract.
output_contract: valid JSON object only
---
# Source Prompt

{prompt}

# JSON output requirements

- Return JSON only.
- You MUST respond with ONLY a valid JSON object.
- Do not include Markdown fences, commentary, headings, or extra text.
- Output ONLY the JSON object, nothing else.
