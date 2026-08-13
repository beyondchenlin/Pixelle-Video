# Installation

This page will guide you through installing Pixelle-Video.

---

## System Requirements

### Required

- **Python**: 3.11 or higher
- **Node.js**: 22.12.0 or higher
- **Operating System**: Windows, macOS, or Linux
- **Package Manager**: uv (recommended) or pip

### Optional

- **GPU**: NVIDIA GPU with 6GB+ VRAM recommended for local ComfyUI
- **Network**: Stable internet connection for LLM API and image generation services

---

## 🪟 Windows All-in-One Package (Recommended for Windows Users)

**No need to install Python, uv, or ffmpeg - ready to use out of the box!**

### Download and Install

1. Visit [GitHub Releases](https://github.com/AIDC-AI/Pixelle-Video/releases/latest) to download the latest version
2. Download the latest Windows All-in-One Package and extract it to any directory
3. Double-click `start.bat` to launch the Web interface
4. Your browser will automatically open `http://localhost:8501`

!!! success "Installation Complete!"
    The package includes all dependencies, no need to manually install any environment. On first use, you only need to configure API keys in "⚙️ System Configuration" to get started.

!!! tip "Next Steps"
    After installation, check out the [Configuration Guide](configuration.md) to set up LLM and image generation services, then see [Quick Start](quick-start.md) to create your first video.

---

## Install from Source (For macOS / Linux Users or Users Who Need Customization)

### Step 1: Clone the Repository

```bash
git clone https://github.com/AIDC-AI/Pixelle-Video.git
cd Pixelle-Video
```

### Step 2: Install Dependencies

The complete installer uses both lock files, downloads the browser pinned by Puppeteer, and verifies the HyperFrames bridge before it succeeds:

```bash
# Windows
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/install-runtime-dependencies.ps1

# macOS / Linux
sh scripts/install-runtime-dependencies.sh
```

---

## Verify Installation

Run the following command to verify the installation:

```bash
# Recommended: start both the Pixelle API and Web UI
# Windows
start_web.bat

# macOS / Linux
./start_web.sh

# Or start the Pixelle API manually (terminal 1)
uv run uvicorn api.app:app --host 127.0.0.1 --port 6789

# Then start the Web UI manually (terminal 2)
uv run streamlit run web/app.py

```

Your browser should automatically open `http://localhost:8501` and display the Pixelle-Video web interface. The Pixelle API runs on `http://localhost:6789` by default, with health check at `http://localhost:6789/health` and Swagger docs at `http://localhost:6789/docs`.

!!! note "The API must be running"
    `uv run streamlit run web/app.py` only starts the Web UI. It does not start the Pixelle API automatically. Stage1/Stage2 workbench, storyboard image candidates, status queries, and related features require `http://localhost:6789/api`.

!!! success "Installation Successful!"
    If you can see the web interface, the installation was successful! Next, check out the [Configuration Guide](configuration.md) to set up your services.

---

## Optional: Install ComfyUI (Local Deployment)

If you want to run image generation locally, you'll need to install ComfyUI:

### Quick Install

```bash
# Clone ComfyUI
git clone https://github.com/comfyanonymous/ComfyUI.git
cd ComfyUI

# Install dependencies
pip install -r requirements.txt
```

### Start ComfyUI

```bash
python main.py
```

ComfyUI runs on `http://127.0.0.1:8188` by default.

!!! info "ComfyUI Models"
    ComfyUI requires downloading model files to work. Please refer to the [ComfyUI documentation](https://github.com/comfyanonymous/ComfyUI) for information on downloading and configuring models.

---

## Next Steps

- [Configuration](configuration.md) - Configure LLM and image generation services
- [Quick Start](quick-start.md) - Create your first video
