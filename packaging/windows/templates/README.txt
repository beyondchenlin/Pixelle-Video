========================================
  Pixelle-Video - Windows Portable
========================================

AI-powered video creation platform

Version: {VERSION}
Build Date: {BUILD_DATE}

========================================
  Quick Start
========================================

1. Double-click "start.bat" to launch the Pixelle API and Web UI
2. Browser will open automatically at http://localhost:8501
3. Configure your API keys in the Web UI (Settings section)

That's it! Just one click to start.
The launcher uses a stable port and never switches silently. It reuses an already healthy Pixelle API, rejects a different service on the same port, and opens the Web UI only after the API is healthy.

========================================
  First-Time Setup
========================================

1. On first run, the Pixelle API starts on http://localhost:6789 and the Web UI starts on http://localhost:8501
2. Click on "Settings" in the Web UI to configure:
   - LLM API Key (OpenAI/Qwen/DeepSeek/etc)
   - LLM Base URL and Model
   - ComfyUI settings (use RunningHub or local ComfyUI)
3. Click "Save Config" to save your settings
4. Configuration will be automatically saved to config.yaml

========================================
  Configuration
========================================

Configuration is done through the Web UI:

1. Launch the application using start.bat
2. Click on "Settings" in the Web UI
3. Fill in the required fields:
   - LLM API Key: Your LLM provider API key
   - LLM Base URL: LLM API endpoint
   - LLM Model: Model name (e.g., gpt-4o, qwen-max)
   - ComfyUI URL: For local ComfyUI (default: http://127.0.0.1:8188)
   - RunningHub API Key: For cloud image generation (optional)
4. Click "Save Config" to save

The configuration will be automatically saved to Pixelle-Video/config.yaml.

Note: You can also manually edit config.yaml if needed, but the Web UI is recommended.

========================================
  Folder Structure
========================================

python/           - Python 3.11 embedded runtime
tools/            - FFmpeg and other utilities
Pixelle-Video/    - Main application
data/             - User data (BGM, templates, workflows)
output/           - Generated videos

========================================
  System Requirements
========================================

- Windows 10/11 (64-bit)
- 4GB RAM minimum (8GB recommended)
- Internet connection (for API calls and ComfyUI cloud)
- Modern web browser (Chrome/Edge/Firefox)

========================================
  Troubleshooting
========================================

Problem: "Python not found"
Solution: Ensure python/ folder exists and is not corrupted

Problem: "Failed to start"
Solution: Check if Python and dependencies are installed correctly

Problem: "Port already in use"
Solution: Port 6789 is used by the Pixelle API and port 8501 is used by the Web UI. Stop the foreign service, or set PIXELLE_API_PORT and PIXELLE_API_BASE_URL to the same unused port before launching.

Problem: "Module not found"
Solution: Re-extract the package completely, don't move files

========================================
  Support
========================================

GitHub: https://github.com/AIDC-AI/Pixelle-Video
Documentation: https://aidc-ai.github.io/Pixelle-Video
Issues: https://github.com/AIDC-AI/Pixelle-Video/issues

========================================
  License
========================================

See LICENSE file in Pixelle-Video/ folder

Copyright (c) 2025 Pixelle.AI
