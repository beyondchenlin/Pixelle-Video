---
prompt_id: direct_media_prompt
version: 1
stage: direct_media_prompt_assembly
purpose: Render final media prompts for direct asset-based ComfyUI workflows
output_contract: plain_text_visual_prompt
---
<!-- if digital_human_generated_image_video_synthesis -->
Direct digital human video synthesis from generated image and narration audio.
<!-- endif -->
<!-- if digital_human_goods_image_combine -->
Direct digital human product image combination from character and goods assets.
<!-- endif -->
<!-- if digital_human_goods_video_synthesis -->
Direct digital human video synthesis from product image and narration audio.
<!-- endif -->
<!-- if digital_human_goods_type_synthesis -->
Direct digital human product image synthesis for goods type: {goods_type}
<!-- endif -->
<!-- if digital_human_generated_product_video_synthesis -->
Direct digital human video synthesis from generated product image and narration audio.
<!-- endif -->
