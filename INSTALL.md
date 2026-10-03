# DROPZERO: install and run (Windows)

## What you need
- Windows 10/11 with an **NVIDIA GPU** (8 GB+ VRAM) and a recent NVIDIA driver
- **Internet once** for setup (~12 GB: packages + AI models). After that it runs offline.
- About **20 GB** of free disk space

Everything else is installed by the setup script: Python 3.12, uv, Node.js, Git, FFmpeg, the
Python and frontend packages, PyTorch for your GPU, and these open-source models:

| Model | Used for | Size |
|---|---|---|
| Whisper large-v3 (faster-whisper) | Speech to text, English / Hindi / Hinglish | ~3 GB |
| LaBSE | Sentence meaning across languages | ~1.8 GB |
| CLIP ViT-B-32 (+ multilingual text) | What is on screen | ~1 GB |
| Qwen3-1.7B | AI explanations and rewrites (runs locally) | ~3.4 GB |
| DROPZERO retention model | Retention prediction (included in `models/`) | 1.2 MB |

## Steps
1. Unzip this folder (for example to `C:\DROPZERO`).
2. Open **PowerShell** in that folder and run:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\setup.ps1
   ```
   If it installs Python or Node for the first time, close PowerShell, open a new one, and run it again.
3. Start the app (every time):
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\start.ps1
   ```
   It opens **http://127.0.0.1:5173**. Sign in with any email (demo session).
4. Optional demo video: `.venv\Scripts\python scripts\make_demo_video.py`, then upload
   `data\private\videos\demo_ai_agent.mp4` in the app (or run `scripts\precompute.py`), then
   `.venv\Scripts\python scripts\warm_demo.py` so the AI answers are instant. See `docs/demo-script.md`.

## Not included on purpose
- **Your encryption key (`.env`) and private videos**: setup creates a new key on each machine.
  Never email the key together with the data.
- **The training dataset** (MOOCCubeX, 3.9 GB): only needed to retrain; the trained model is in `models/`.

## Troubleshooting
| Problem | Fix |
|---|---|
| `cudnnGetLibConfig` / cuDNN error | Re-run `setup.ps1` (it matches the Whisper engine to your PyTorch build). |
| Whisper fails on the GPU | Set `DROPZERO_ASR_DEVICE=cpu` in `.env` (slower, but works). |
| Port 8000 busy | `start.ps1` stops a leftover backend; or restart the computer. |
| Model download errors | Check internet, run `.venv\Scripts\python scripts\download_models.py` again. |
