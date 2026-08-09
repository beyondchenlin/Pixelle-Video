---
prompt_id: title_generation
version: 1
stage: title_generation
purpose: Generate a concise video title from content.
output_contract: Plain title text only.
---

<!-- template-loader:strip # title_generation -->
Please generate a short, attractive title for the following content.

Content:
{content}

Requirements:
1. **Language Consistency (CRITICAL)**: The title MUST be in the same language as the input content
   - If the input content is in English, the title MUST be in English
   - If the input content is in Chinese, the title MUST be in Chinese
   - Strictly follow the language of the input content

2. **Character Limit (CRITICAL)**: The title MUST NOT exceed {max_length} characters
   - Count each user-perceived character, including spaces
   - The title must be complete and meaningful within this limit
   - Do NOT generate a title that would need to be cut off

3. **Core Message (CRITICAL)**: The title MUST capture the MAIN POINT of the content
   - Identify the central theme or key message
   - Don't focus on just one aspect if the content has multiple important points
   - Ensure the title accurately represents what the content is about

4. **No Punctuation at End**: Do NOT include any punctuation marks at the end of the title
   - No period (.), comma (,), exclamation mark (!), question mark (?), etc.
   - The title should end with a word or number, not punctuation

5. **Completeness**: Ensure the title is a complete, meaningful phrase
   - Do not cut off in the middle of a word or number
   - Do not create incomplete phrases like "Rise Early for" or "How to Make"
   - Use abbreviations or shorter words if needed to fit the limit

6. **Abbreviation Examples** (use when needed to fit character limit):
   - For English:
     * "10,000" → "10K"
     * "per month" → "monthly" or "a month"
     * "early to bed and early to rise" → "Sleep Early" or "Early Habits"
     * "makes you healthy" → "for Health" or "Stay Healthy"
   - For Chinese:
     * "10,000元" → "万元" or "1万"
     * "每个月" → "月入" or "月收"

7. Accurately summarize the core content
8. Attractive and engaging, suitable as a video title
9. Output only the title text, no quotes, no explanations

Title:
