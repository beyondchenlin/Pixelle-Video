# Quick Start

Already installed and configured? Let's create your first video!

---

## Start the Web Interface

### Windows All-in-One Package Users

If you're using the Windows All-in-One Package, simply:
1. Double-click `start.bat`
2. Your browser will automatically open `http://localhost:8501`

### Install from Source Users

Use the project launcher when possible. It starts both the Pixelle API and the Web UI:

```bash
# Windows
start_web.bat

# macOS / Linux
./start_web.sh
```

If you need to start them manually, open two terminals:

```bash
# Terminal 1: start the Pixelle API (FastAPI, used by the Web UI)
uv run uvicorn api.app:app --host 127.0.0.1 --port 6789
```

```bash
# Terminal 2: start the Web UI (Streamlit)
uv run streamlit run web/app.py
```

Your browser will automatically open `http://localhost:8501`. The API health check is `http://localhost:6789/health`, and Swagger docs are available at `http://localhost:6789/docs`.

!!! note "The API must be running"
    `uv run streamlit run web/app.py` only starts the Web UI. It does not start the Pixelle API automatically. Stage1/Stage2 workbench, storyboard image candidates, status queries, and related features require `http://localhost:6789/api`.

---

## Create Your First Video

### Step 1: Check Configuration

On first use, expand the「⚙️ System Configuration」panel and confirm:

- **LLM Configuration**: Select an AI model (e.g., Qianwen, GPT) and enter API Key
- **Image Configuration**: Configure ComfyUI address or RunningHub API Key

If not yet configured, see the [Configuration Guide](configuration.md).

Click "Save Configuration" when done.

---

### Step 2: Enter a Topic

In the left panel's「📝 Content Input」section:

1. Select「**AI Generate Content**」mode
2. Enter a topic in the text box, for example:
   ```
   Why develop a reading habit
   ```
3. (Optional) Set number of scenes, default is 5 frames

!!! tip "Topic Examples"
    - Why develop a reading habit
    - How to improve work efficiency
    - The importance of healthy eating
    - The meaning of travel

---

### Step 3: Configure Voice and Visuals

In the middle panel:

**Voice Settings**
- Select TTS workflow (default Edge-TTS works well)
- For voice cloning, upload a reference audio file

**Visual Settings**
- Select image generation workflow (default works well)
- Set image dimensions (default landscape 1280x720)
- Choose video template (recommend portrait 1080x1920)

---

### Step 4: Generate Video

Click the「🎬 Generate Video」button in the right panel!

The system will show real-time progress:
- Generate script
- Generate images (for each scene)
- Synthesize voice
- Compose video

!!! info "Generation Time"
    Generating a 5-scene video takes about 2-5 minutes, depending on: LLM API response speed, image generation speed, TTS workflow type, and network conditions

---

### Step 5: Preview Video

Once complete, the video will automatically play in the right panel!

You'll see:
- 📹 Video preview player
- ⏱️ Video duration
- 📦 File size
- 🎬 Number of scenes
- 📐 Video dimensions

The video file is saved in the `output/` folder.

---

## Next Steps

Congratulations! You've successfully created your first video 🎉

Next, you can:

- **Adjust Styles** - See the [Custom Visual Style](../tutorials/custom-style.md) tutorial
- **Clone Voices** - See the [Voice Cloning with Reference Audio](../tutorials/voice-cloning.md) tutorial
- **Use API** - See the [API Usage Guide](../user-guide/api.md)
- **Develop Templates** - See the [Template Development Guide](../user-guide/templates.md)
