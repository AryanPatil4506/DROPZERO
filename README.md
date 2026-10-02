# DROPZERO

DROPZERO is an AI-powered pre-publish audience simulator that analyzes a video’s transcript, audio, visuals, pacing, and structure to predict where viewers may lose interest. It explains the likely causes, suggests exact edits, simulates their potential impact on retention, and can compare predictions with real retention data after publishing.

**Status:** build order steps 1–8 done: upload + storage, transcription + segmentation, text /
audio / visual features, retention model trained and validated on real viewing data, drop-off
flags with evidence, edit suggestions, before/after simulation. Details: `docs/build-status.md`. Details and known gaps: `docs/build-status.md`.

Everything runs locally with open-source models (faster-whisper large-v3, a multilingual
sentence-embedding model). No hosted APIs.

## Setup (Windows, demo laptop)

Needs Python 3.12, [uv](https://docs.astral.sh/uv/), an NVIDIA GPU with a recent driver, and ffmpeg.

```powershell
winget install --id Gyan.FFmpeg -e          # ffmpeg + ffprobe (found automatically, no PATH edit needed)
uv venv .venv --python 3.12
uv pip install --python .venv\Scripts\python.exe -r requirements.txt
# CUDA build of torch for the embedding model (cu124 wheels work on RTX 40xx).
# RTX 50xx (Blackwell, sm_120) needs a cu128 build instead: --index-url .../whl/cu128
uv pip install --python .venv\Scripts\python.exe --reinstall torch --index-url https://download.pytorch.org/whl/cu124
.venv\Scripts\python scripts\gen_key.py      # copy the printed line into .env (see .env.example)
```

The CUDA math libraries for Whisper (cuBLAS, cuDNN 9) come from pip wheels and are registered by
`backend/app/gpu.py`, so no PATH or `LD_LIBRARY_PATH` edits are needed. PyAV is pinned below 17
because newer versions break faster-whisper 1.2.1; we never decode with PyAV (ffmpeg produces the
16 kHz WAV).

First analysis downloads model weights into the Hugging Face cache (~3 GB Whisper large-v3,
~1 GB embedding model). After that everything works offline.

## Run

```powershell
.venv\Scripts\uvicorn backend.app.main:app --reload
# API docs: http://127.0.0.1:8000/docs     health: GET /api/health
```

### API

| Method | Path | |
|---|---|---|
| POST | `/api/projects` | create: `{title, category: tech\|education\|vlog, language: en\|hi\|hinglish, creator?, target_audience?}` |
| GET | `/api/projects`, `/api/projects/{id}` | |
| POST | `/api/projects/{id}/video` | multipart `file` (MP4/MOV, 60 s–20 min; outside 5–15 min gives a warning) |
| POST | `/api/projects/{id}/script` | multipart `file` (TXT/MD) or JSON `{"text": "..."}` — timing is *estimated* |
| POST | `/api/projects/{id}/analyze` | starts the pipeline, returns a job |
| GET | `/api/jobs/{job_id}` | `status`, `stage`, `progress` 0–1, `error` |
| GET | `/api/projects/{id}/transcript` | words + sentences with timestamps |
| GET | `/api/projects/{id}/segments` | 5–15 s analysis windows tiling the whole video |
| GET | `/api/projects/{id}/features/text` | per-segment text features + topic sections |
| GET | `/api/projects/{id}/features/av` | per-segment audio + visual features, scene cuts (video only) |
| GET | `/api/projects/{id}/prediction` | model-estimated retention curve with band + per-segment risk |
| GET | `/api/projects/{id}/flags` | drop-off flags with evidence, title-promise check, suggested edits |
| POST | `/api/projects/{id}/simulate` | `{"edit_ids": [...]}` → original vs simulated curve (model-estimated) |
| GET | `/api/validation` | held-out validation report of the current model |
| DELETE | `/api/projects/{id}` | deletes encrypted media and all derived data |

Example:

```powershell
$p = Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/projects -ContentType application/json -Body '{"title":"I Built an AI Agent in 24 Hours","category":"tech","language":"en"}'
curl.exe -F "file=@my_video.mp4" "http://127.0.0.1:8000/api/projects/$($p.id)/video"
$j = Invoke-RestMethod -Method Post "http://127.0.0.1:8000/api/projects/$($p.id)/analyze"
Invoke-RestMethod "http://127.0.0.1:8000/api/jobs/$($j.id)"
```

## Data handling (unpublished videos are sensitive)

- Uploads are type-checked by content (container magic bytes + ffprobe), then **only an
  AES-256-GCM encrypted copy** is kept (`var/media/<project>/original.enc`). The creator's file is
  never modified.
- Decrypted media exists only in `var/work/<job>/` while a job runs and is deleted when it ends,
  failed jobs included. Leftover work dirs are wiped at startup.
- Transcripts, segments, features and the ASR cache are stored encrypted.
- Encrypted uploads older than `DROPZERO_MEDIA_RETENTION_HOURS` (default 72) are purged at startup.
- Nothing is sent to third parties: ASR and embeddings run locally.

## Tests

```powershell
.venv\Scripts\python -m pytest -q          # default: no GPU or model weights needed
.venv\Scripts\python -m pytest -m model    # real embedding model on the EN/HI/Hinglish fixtures
.venv\Scripts\python -m pytest -m gpu      # real Whisper on recorded clips (see below)
.venv\Scripts\ruff check . ; .venv\Scripts\black --check .
```

Fixtures (`backend/tests/fixtures/`): an English, a Hindi (Devanagari) and a Hinglish (Roman) script,
each with a planted repeated explanation, questions, numbers and fillers. The `asr_*.json` files are
**synthetic**: generated from the scripts by `scripts/make_asr_fixtures.py` with seeded timing, not
real ASR output. They test segmentation and feature logic only.

The GPU test needs two real 30 s clips recorded by the team, which are not in git:
`backend/tests/fixtures/audio/hi_30s.wav` and `hinglish_30s.wav`.

## Model (real viewing data)

The retention model is trained on MOOCCubeX: real per-viewer watch logs of 1,200 online-course
lectures (Chinese, not YouTube), split by lecture. `models/retention_model.pkl` and
`models/validation.json` are committed, so the app works without retraining. To rebuild:

```powershell
# download (~3.9 GB) into data\raw\mooccubex\: relations/video_id-ccid.txt, entities/video.json,
# relations/user-video.json from https://lfs.aminer.cn/misc/moocdata/data/mooccube2/
.venv\Scripts\python scripts\build_mooc_curves.py   # real retention curves
.venv\Scripts\python scripts\train_model.py         # train + held-out validation
```

## Scripts

- `scripts/gen_key.py` — new media encryption key.
- `scripts/make_asr_fixtures.py` — regenerate the synthetic ASR fixtures (deterministic).
- `scripts/build_mooc_curves.py`, `scripts/train_model.py` — real retention curves, model + validation.
- `scripts/export_api_samples.py` — real API responses into `frontend/mock/` for UI work.
- `scripts/embedding_benchmark.py` — compares open multilingual embedding models on
  repeat-vs-progress separation; results in `docs/embedding_benchmark.md`.
