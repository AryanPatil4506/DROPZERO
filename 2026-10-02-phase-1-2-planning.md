# DROPZERO: Planning conversation for Phases 1–2

**Date:** 2026-10-02
**Participants:** project team
**Status:** Approved and implemented (Phases 1–2), then extended with Phase 3 (text features) and Phase 4 (audio + visual features). Current state: `docs/build-status.md`.

---

## Request

> Read the project guide fully. We're building DROPZERO for a hackathon, so we need a working end-to-end MVP fast.
>
> Do this in order, and don't write feature code until I approve the plan:
>
> 1. Summarize your understanding of the product, the MVP scope and the non-negotiable rules in under 10 bullets, so I can catch any misunderstanding.
> 2. Propose a concrete plan for Phases 1–2 of the build order (project creation + upload + storage, then timestamped transcription + segmentation). Include the exact folder structure, the tech choices (confirm or challenge the suggested stack), the pydantic schemas for Project, Transcript and Segment, and the API endpoints.
> 3. List any assumptions or open questions that would change the plan (hardware/GPU, hosting, LLM provider, dataset availability). Ask me only the ones that truly block you.
> 4. Propose a minimal test plan, including one Hindi and one Hinglish fixture.
>
> Keep the plan short and decision-oriented. Wait for my approval before implementing.

## Environment at the time of planning

- The folder contained only the project guide. It was not yet a git repository.
- GPU: NVIDIA GeForce RTX 5050 Laptop GPU, 8 GB VRAM (Blackwell, sm_120).
- Python 3.14.7 installed, Node v24.20.0 installed, ffmpeg **not** installed.

---

## 1. What we understand

- **Product:** DROPZERO predicts, before publish, where viewers will drop off in a 5–15 minute English, Hindi or Hinglish video or script. It explains why using measured evidence, proposes exact timestamped edits, simulates their effect, and checks predictions against real retention CSVs.
- **Must-have for judging:** a predicted retention curve, reasoned flags, actionable edits with simulated improvement, and validation against real retention data.
- **MVP scope:** upload, ASR, segments, text and visual features, a tabular model with a survival-style curve, a drop-off detector with evidence, LLM explanations, cut/move simulation, a promise/payoff tracker, CSV validation, and one shared-timeline dashboard. Everything else waits until the core is frozen.
- **Prediction comes from deterministic features plus a tabular model.** The LLM only narrates the evidence object. Any number it outputs that isn't in the evidence gets rejected.
- **Timestamps (float seconds) on everything.** `model_version` and `feature_schema_version` are stored on every artifact.
- **Honest labels:** simulations say "model-estimated", internal scores say "DROPZERO internal score", script timing says "estimated", and misses are always shown.
- **Never fabricate ground truth.** Retention data comes from creator CSVs; "Most replayed" heatmaps count only as a labelled proxy.
- **Never touch the original file.** Work on copies, encrypt at rest, purge processed media, and keep transcripts away from third parties.
- **Validation is the main credibility lever.** We must beat a category-average baseline and a plain-LLM baseline, run ablations, and split by video so data doesn't leak.

---

## 2. Plan for Phases 1–2

### Stack: what we keep and what we change

| Concern | Decision | Why |
|---|---|---|
| Python | **3.12 via `uv`**, not the installed 3.14 | ctranslate2, torch and librosa wheels lag behind new Python versions. Pinning 3.12 avoids losing hours on builds. |
| ASR | **faster-whisper `large-v3`** instead of openai-whisper | 2–4× faster, lower VRAM (fits in 8 GB at float16/int8), word timestamps, built-in VAD. |
| ASR settings | `temperature=0`, `beam_size=5`, `vad_filter=True`, **`condition_on_previous_text=False`** | Determinism, plus Whisper's repetition hallucinations would otherwise create **fake repetition flags** later. Results are cached by `sha256(audio)+asr_config`. |
| Backend | FastAPI + pydantic v2 + SQLAlchemy 2 on **SQLite** | No Postgres needed for a single-machine demo. |
| Jobs | FastAPI background task + `jobs` table + polling, with a GPU lock | No Celery or Redis. One ASR job runs at a time. |
| Media | Local `MediaStore` with **chunked AES-GCM** (key from env) | Meets rule 13 now; adding it later would be harder. Chunking keeps HTTP Range playback possible later. |
| Frontend | **React + Vite + TS** (no Streamlit) | The dashboard needs click-curve → seek video. Streamlit would be thrown away. The scaffold isn't part of Phases 1–2, but a teammate can start now against the OpenAPI schema. |

**Main technical risk: the RTX 5050 is a Blackwell GPU (sm_120).** CTranslate2 and torch need recent CUDA 12.8+ builds for it. So the plan starts with a 30-minute **spike** (`scripts/asr_spike.py`): transcribe a 30 s Hindi clip and a 30 s Hinglish clip on the GPU. On the Hinglish clip it also compares `language="hi"` against auto-detect. If the GPU fails, the fallbacks in order are:

1. openai-whisper on torch cu128.
2. `large-v3-turbo` on CPU int8 (slow, but works offline).
3. A hosted ASR API, only with explicit opt-in, because it sends unpublished audio to a third party.

### Folder structure (Phase 1–2 files only; the `PS/` folder becomes the repo root)

```
PS/
├── pyproject.toml  .env.example  .gitignore
├── config/
│   ├── asr.yaml              # model, compute_type, beam, vad, per-language options
│   └── segmentation.yaml     # target 12s / min 5s / max 15s, pause gap, script-mode words/sec
├── backend/app/
│   ├── main.py  settings.py  versions.py      # version constants live in one place
│   ├── api/            projects.py  jobs.py
│   ├── schemas/        project.py  transcript.py  segment.py  job.py
│   ├── storage/        db.py  media_store.py   # (addition to the planned layout)
│   ├── ingestion/      validate.py  probe.py  audio.py   # magic bytes, ffprobe, 16 kHz mono wav
│   ├── transcription/  asr.py  script_timing.py
│   ├── segmentation/   sentences.py  windows.py
│   └── pipeline/       runner.py               # stages + job progress (addition)
├── backend/tests/  fixtures/  test_*.py
├── scripts/        asr_spike.py  precompute.py
└── var/            # gitignored: dropzero.db, media/<id>/original.enc, work/<id>/ (purged after each run)
```

### Schemas (pydantic v2, abridged)

```python
class Language(StrEnum):      EN="en"; HI="hi"; HINGLISH="hinglish"
class SourceType(StrEnum):    VIDEO="video"; SCRIPT="script"
class Category(StrEnum):      TECH="tech"; EDUCATION="education"; VLOG="vlog"
class TimingSource(StrEnum):  ASR="asr"; ESTIMATED="estimated"
class ProjectStatus(StrEnum): CREATED; UPLOADED; PROCESSING; READY; FAILED

class Project(BaseModel):
    id: str                       # ULID
    title: str                    # used later for promise tracking
    creator: str | None
    category: Category
    language: Language            # creator-declared
    target_audience: str | None
    source_type: SourceType | None
    duration_s: float | None
    thumbnail_ref: str | None
    status: ProjectStatus
    warnings: list[str] = []      # e.g. "duration outside tested 5–15 min range"
    created_at: datetime

class Word(BaseModel):
    text: str; start: float; end: float; confidence: float | None

class Sentence(BaseModel):
    idx: int; start: float; end: float; text: str
    word_start: int; word_end: int        # half-open slice into words

class Transcript(BaseModel):
    project_id: str
    language_declared: Language
    language_detected: str | None; language_prob: float | None
    timing_source: TimingSource           # "estimated" in script mode → shown in UI
    asr_model: str | None                 # "faster-whisper/large-v3@float16" or None
    asr_config_hash: str | None
    words: list[Word]; sentences: list[Sentence]
    mean_confidence: float | None
    transcript_schema_version: str

class Segment(BaseModel):
    id: str                               # f"{project_id}:{index:04d}", stable
    project_id: str; index: int
    start: float; end: float              # segments tile [0, duration] with no gaps
    speech_start: float | None; speech_end: float | None
    text: str; sentence_ids: list[int]
    boundary: Literal["sentence", "pause", "forced_split", "end"]
    timing_source: TimingSource
    segmenter_version: str
    features: dict[str, float] = {}       # becomes typed SegmentFeatures in Phase 3
    feature_schema_version: str | None = None
```

### Segmentation rules (deterministic)

1. Split sentences on `. ? !` and the Hindi danda `।`. If punctuation is missing (common in Hinglish ASR), fall back to pauses of 0.6 s or more between words.
2. Pack sentences greedily toward a 12 s target, staying within 5–15 s.
3. Split any sentence longer than 15 s at its largest internal pause.
4. Place each boundary at the midpoint of the gap between sentences, so every second belongs to exactly one segment. The survival-style curve R(t) needs this.
5. Scene boundaries come in Phase 4 as an optional `boundary_hints` input. The interface is ready for it now.

**Script mode:** words ÷ a per-language words/sec value from config, plus a sentence pause, then the same segmenter. The result is marked `timing_source="estimated"` everywhere.

### API

```
POST   /api/projects                    create (JSON metadata) → Project
GET    /api/projects | /api/projects/{id}
POST   /api/projects/{id}/video         multipart MP4/MOV → magic-byte + ffprobe check, encrypted copy, sha256 stored
POST   /api/projects/{id}/script        TXT/MD file or JSON body
POST   /api/projects/{id}/analyze       start pipeline → Job   (Phase 2 stages: extract_audio → transcribe → segment)
GET    /api/jobs/{job_id}               stage, progress 0–1, error
GET    /api/projects/{id}/transcript
GET    /api/projects/{id}/segments
DELETE /api/projects/{id}               deletes our encrypted copy and derived data
GET    /api/health                      GPU visible, ASR model loaded, version constants
```

Uploads under 60 s or over 20 min are rejected. Anything outside 5–15 min is accepted with a warning.

---

## 3. Assumptions and open questions

### Blocking (need answers before implementation)

1. **Toolchain installs: OK to proceed?** `git init`, install `uv` and Python 3.12, install ffmpeg through `winget`, and install CUDA runtime wheels plus faster-whisper (about 3 GB of model downloads).
2. **Is this laptop the demo machine?** Assumed yes: everything runs locally on this GPU with no cloud hosting. If the demo will be hosted, the storage and job choices change.
3. **May we use a hosted ASR API as a last resort if the GPU spike fails?** It would send unpublished audio to a third party. Default: no; we'd use CPU instead.

### Not blocking now, but needed soon

- **Retention CSVs are the biggest risk to the whole plan.** The Phase 5 model needs labelled curves to train. Without them it's hand-weighted heuristics, and validation has nothing to measure. How many YouTube Studio exports can the team get, and when?
- **LLM provider:** needed in Phase 7. A provider-agnostic wrapper will be built; we need to know which provider has keys.
- **Team size:** if someone else does frontend, the API contract gets frozen first so frontend work can run in parallel.
- **Hinglish ASR output:** assumed we keep whatever script Whisper produces (often Devanagari with English words transliterated) and rely on multilingual embeddings later. The spike will check this.

---

## 4. Minimal test plan (pytest, no GPU needed by default)

### Fixtures (`backend/tests/fixtures/`)

- `en_script.txt`, `hi_script.txt` (Devanagari, `।` punctuation), `hinglish_script.txt` (Roman-script code-mixed text with fillers like "toh", "matlab", "basically").
- `asr_en.json`, `asr_hi.json`, `asr_hinglish.json`: word-level ASR outputs in faster-whisper's shape. The Hinglish one includes a 20 s stretch with no punctuation, to exercise the pause fallback.
- Real audio clips (two 30 s clips the team records) are used only by the `@pytest.mark.gpu` integration test. No synthesized fake speech data.

### Tests

| Area | Checks |
|---|---|
| Ingestion | Bad extension or spoofed magic bytes rejected; duration bounds and warnings (ffprobe mocked); **source file's sha256 unchanged after upload**; bytes on disk ≠ plaintext and decrypt round-trips. |
| Sentences | EN `.?!`, HI `।`, Hinglish pause fallback; Devanagari word counts correct. |
| Segmenter | All three languages: segments tile [0, duration] with no gaps or overlaps; every segment is 5–15 s except documented exceptions; boundaries land on sentence ends where possible; **two runs give identical output**; IDs stay stable. |
| Script timing | Monotonic, deterministic, `timing_source="estimated"` on the transcript and every segment. |
| ASR wrapper | Maps faster-whisper output to the `Transcript` schema; cache hit skips the model; version and config hash stamped. |
| API (end-to-end) | Create → upload script → analyze → poll job → read segments, for EN, HI and Hinglish, with ASR mocked from the JSON fixtures. |
| GPU (opt-in) | Real faster-whisper on the two recorded clips: non-empty words, monotonic timestamps, determinism across two runs. |

---

## Next step

Once the plan is approved and the three blocking questions are answered: setup and the ASR spike come first, then Phase 1.
