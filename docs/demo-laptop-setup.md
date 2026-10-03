# Demo laptop setup and to-do list

Everything needed to get DROPZERO running end to end on the demo laptop (RTX 5050), plus what is
still open. Work from the repo root unless a step says otherwise.

Heavy files (Python, packages, model weights, data) go on a drive with space. The commands below
use `D:\dropzero\`; change the path if the demo laptop's spare drive is different.

## 1. Get the code

```powershell
git clone https://github.com/AryanPatil4506/DROPZERO.git
cd DROPZERO
git fetch origin
git checkout promise-ledger-ui        # or main, once the promise-ledger-ui PR is merged
```

- [ ] Merge the `promise-ledger-ui` pull request into `main` (Promises tab, compact score lanes).

## 2. Tools

- [ ] **uv** (Python package manager): `pip install uv` or see https://docs.astral.sh/uv/
- [ ] **ffmpeg + ffprobe**: `winget install --id Gyan.FFmpeg -e`
      (or unzip the "release essentials" build from https://www.gyan.dev/ffmpeg/builds/ to
      `D:\dropzero\ffmpeg` and set `DROPZERO_FFMPEG` / `DROPZERO_FFPROBE` in `.env`, step 4)
- [ ] **NVIDIA driver**: recent enough for CUDA 12.8 (`nvidia-smi` should report it). For GPU
      video encoding in *Render edited version*, ffmpeg 9 needs driver **610 or newer**; with an
      older driver the render falls back to the CPU encoder (still ~5–15 s per minute of video).
- [ ] **Node.js 20+** for the frontend

## 3. Python environment (on D:)

Set these in the same PowerShell window before installing, so caches stay off C::

```powershell
$env:UV_CACHE_DIR = "D:\dropzero\cache\uv"
$env:UV_PYTHON_INSTALL_DIR = "D:\dropzero\python"
$env:UV_LINK_MODE = "copy"
```

```powershell
uv python install 3.12
uv venv D:\dropzero\venv --python 3.12
uv pip install --python D:\dropzero\venv\Scripts\python.exe -r requirements.txt scikit-learn
# RTX 50xx (Blackwell) needs the CUDA 12.8 build of torch:
uv pip install --python D:\dropzero\venv\Scripts\python.exe --reinstall torch --index-url https://download.pytorch.org/whl/cu128
D:\dropzero\venv\Scripts\python -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

- [ ] The last line prints `True` and the RTX 5050.
- [ ] **Add `scikit-learn` to `requirements.txt`.** The trained model (`models/retention_model.pkl`)
      needs it, and the backend tests fail without it.

## 4. Configuration

```powershell
D:\dropzero\venv\Scripts\python scripts\gen_key.py     # prints DROPZERO_MEDIA_KEY=...
copy .env.example .env
```

Edit `.env`:

```
DROPZERO_MEDIA_KEY=<the printed key>
DROPZERO_DATA_DIR=D:/dropzero/var
```

Keep model downloads on D: by setting this before starting the backend (or once, as a user
environment variable):

```powershell
$env:HF_HOME = "D:\dropzero\cache\hf"
```

## 5. Run

Backend (first analysis downloads about 8 GB of model weights into `HF_HOME`: Whisper large-v3
~3 GB, LaBSE ~1.8 GB, Qwen3-1.7B ~3.4 GB for "Explain with AI"; after that it works offline):

```powershell
$env:HF_HOME = "D:\dropzero\cache\hf"
D:\dropzero\venv\Scripts\uvicorn backend.app.main:app --reload
# API docs: http://127.0.0.1:8000/docs   health: http://127.0.0.1:8000/api/health
```

Frontend, live mode (second window):

```powershell
cd frontend
npm install
npm run dev          # http://localhost:5173 ; /api is proxied to the backend
```

- [ ] `GET /api/health` reports the media key and GPU.
- [ ] Tests pass: `D:\dropzero\venv\Scripts\python -m pytest -q`, then `-m model` and `-m gpu`
      (the GPU test needs `backend/tests/fixtures/audio/hi_30s.wav` and `hinglish_30s.wav`,
      30 s clips recorded by the team).

## 6. Check the features that have only been seen on mock data

- [ ] **Score lanes:** on a project, Timeline → *Lanes: Scores*. Four thin lanes (pace, content,
      visual, audio) appear; hover shows the inputs. The Audio lane fills only after re-analysis.
- [ ] **Promises tab:** shows the ledger (kept on time / kept late / open loop); *See fix* opens
      the matching flag.
- [ ] **Explain with AI** in the "Why would I leave?" panel returns an explanation (first call
      downloads Qwen3-1.7B).
- [ ] **Background video:** upload a real video; it plays behind the dashboard via
      `GET /api/projects/{id}/media`, and seeking from the curve/transcript moves it.
- [ ] **Editor:** trim start/end, cut, speed ×1.25/×1.5, *Preview with cuts*, *Simulate my edit plan*.
- [ ] Re-analyse the existing projects (stored analyses predate the ledger and score lanes).

## 7. Refresh the recorded mock data

So the frontend's mock mode (`npm run dev:mock`) also shows the ledger and score lanes:

```powershell
$env:HF_HOME = "D:\dropzero\cache\hf"
D:\dropzero\venv\Scripts\python scripts\export_api_samples.py
```

- [ ] Commit the updated `frontend/mock/` files.

## 8. Demo prep

- [ ] Pre-compute results for ~10 sample videos (`scripts/precompute.py`) so the demo never waits
      on analysis.
- [ ] Rehearse the judge path: upload → click a red point → "Why would I leave?" → evidence →
      *Show me what to cut* → *Simulate fix* → original vs simulated → Promises tab → validation.
- [ ] Check the dashboard on the projector resolution (1366×768) and at 1920×1080.
- [ ] Record a backup video of the full demo in case the network or GPU fails.
- [ ] Delete `frontend/public/demo/` before any production build (it holds a local test clip and
      is git-ignored, but `npm run build` would copy it into `dist/`).

## 9. Later features (not started)

- [x] Before/after render: done (Edit plan → *Render edited version*). Test it on a real video.
- [ ] Script rewrite suggestions for weak sections (local LLM), in the video's language.

## Note about the development machine

A partial setup was started on the development PC in `D:\dropzero\` (Python 3.12, a venv and
package cache, about 2.6 GB) and then stopped. It isn't used by anything; delete the folder there
if the space is needed.
