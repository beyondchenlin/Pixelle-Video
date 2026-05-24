---
prompt_id: final_visual_prompt_clauses
version: 1
stage: final_visual_prompt_clause_assembly
purpose: Render reusable final visual prompt clause bodies from structured variables
output_contract: plain_text_visual_prompt_clause
---
<!-- if no_text_positive_rule -->
no visible text, no Chinese characters, no English letters, no words, no subtitles, no captions, no watermark, no logo text, convey the idea through objects, symbols, composition, and scene elements instead of written text
<!-- endif -->
<!-- if no_text_negative_rules -->
text, letters, words, typography, subtitles, captions, watermark, logo, Chinese characters, English letters, handwriting, calligraphy, printed text
<!-- endif -->
<!-- if planned_text_positive_guard -->
only render the explicitly requested planned text, no extra captions, no extra subtitles, no watermark, no logo text, no random letters
<!-- endif -->
<!-- if planned_text_negative_rules -->
unplanned text, random letters, watermark, logo text, extra captions, extra subtitles
<!-- endif -->
<!-- if visible_text_whitelist -->
画面文字只允许白名单内容：{visible_text_whitelist}；only whitelisted text may appear, no extra words.
<!-- endif -->
<!-- if style_ip_world_visual_parts -->
adapted into a coherent style world with {style_ip_world_visual_parts}
<!-- endif -->
<!-- if style_hybrid_visual_parts -->
using an integrated hybrid visual style with {style_hybrid_visual_parts}
<!-- endif -->
<!-- if style_default_visual_parts -->
rendered with {style_default_visual_parts}
<!-- endif -->
<!-- if world_identity -->
set in the {world_identity} world
<!-- endif -->
<!-- if style_core -->
rendered as {style_core}
<!-- endif -->
<!-- if camera_parts -->
framed as {camera_parts}
<!-- endif -->
<!-- if world_elements -->
with {world_elements} integrated into the environment
<!-- endif -->
