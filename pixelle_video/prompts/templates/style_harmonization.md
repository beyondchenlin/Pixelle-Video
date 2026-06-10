---
prompt_id: style_harmonization
version: 3
stage: style_harmonization
purpose: Decide how route style and IP native style should coexist.
output_contract: JSON object matching StyleHarmonizationPlan fields.
---

Selected route:
{selected_route_json}

Compatibility report:
{compatibility_report_json}

IP profile summary:
{ip_profile_json}

Task:
Create a style harmonization plan. The IP may inherit the route style, be redrawn in route style, stay hybrid-layered, appear only as a symbolic signature, or keep a deliberate cameo contrast. Choose the least disruptive solution that preserves both article meaning and IP recognizability.

Return JSON only with keys: mode, route_style_family, ip_native_style, output_style_rule, preserve_ip_identity_rules, negative_style_rules, reason.
