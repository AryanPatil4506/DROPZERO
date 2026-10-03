# DROPZERO build status

**As of 2026-10-03.** Build order: steps 1–8 done, plus model v2, exposure-based simulation, editor (trim/cut/speed), LLM flag explanations. Next: demo prep on the RTX 5050.

## Done

| Step | What | Where |
|---|---|---|
| 1 | Projects, video/script upload, content-based type checks, ffprobe, AES-GCM encryption at rest, per-job work dirs always deleted, purge at startup | `api/`, `ingestion/`, `storage/` |
| 2 | faster-whisper large-v3 wrapper (deterministic settings, encrypted cache), script mode with *estimated* timing, sentence splitting (`.?!।` + pause fallback for unpunctuated Hinglish), DP segmenter (5–15 s, tiles the whole video, long silences as own segments) | `transcription/`, `segmentation/` |
| 3 | Text features: words/sec and pace vs this video's median, fillers (EN/HI/Hinglish dictionaries), questions, number claims, semantic novelty, information gain, repetition (sentence + segment level, ≥ 20 s apart), topic shifts and sections | `features/text/`, `config/text_features.yaml`, `config/fillers.yaml` |
| 4 | Visual: tiny grayscale frames via ffmpeg, scene cuts (absolute + local-median test), static ratio, longest static run, seconds since last cut. Audio: silence ratio relative to the video's own loudness, energy and its variation vs the video median. Scene cuts are fed to the segmenter as boundary hints. | `features/visual/`, `features/audio/`, `features/av.py`, `config/av_features.yaml` |

Endpoints added: `GET /api/projects/{id}/features/text`, `GET /api/projects/{id}/features/av`
(404 in script mode).

| Step | What | Where |
|---|---|---|
| 5 | Retention model on **real** viewing data: 1,200 MOOCCubeX lectures (310,360 viewers), split by lecture (980 train / 220 test). Predicts a per-second drop rate per segment, so curves don't depend on how the video is sliced; survival-style curve with a 10–90% band. | `model/`, `scripts/build_mooc_curves.py`, `scripts/train_model.py`, `models/` |
| 6 | Drop-off detector: model risk (relative to a typical video at the same position) + evidence rules (late title promise, slow hook, repetition, low new information, pacing, silence, static picture). Every flag has timestamps, evidence, explanation and a `source` label. | `detection/`, `config/detection.yaml` |
| 7 | Edit suggestions (deterministic rules): CUT / MOVE / SHORTEN / REWRITE / ADD_VISUAL with timestamps and reasons. Explanations are templates built only from evidence values. LLM wording not added yet. | `detection/flags.py` |
| 8 | Before/after simulation: CUT/MOVE applied to the transcript timeline, then the same segmentation, features and model are rerun. Labelled "Simulated / model-estimated". | `simulate/` |

Endpoints added: `GET /api/projects/{id}/prediction`, `GET /api/projects/{id}/flags`,
`POST /api/projects/{id}/simulate`, `GET /api/validation`.

## Validation (model `mooc-hgb3-0e371ea6`, 220 held-out lectures)

| | Model v2 | Category-average baseline |
|---|---|---|
| Curve MAE / RMSE | **0.172 / 0.207** | 0.220 / 0.265 |
| Pearson / Spearman (curve) | **0.58 / 0.58** | 0.53 / 0.51 |
| Median end retention (actual 0.30) | **0.30** | — |
| Major drops detected (±10 s) | 1,100 of 1,660 | 1,306 of 1,660 |
| Drop flags precision / F1 | **0.48 / 0.56** | 0.41 / 0.54 |
| 10–90% band covers actual | 76% | — |
| Ranking which segments lose most (within video) | 0.18 | **0.17** |

Model v2 (vs v1): the training target keeps re-watching (v1 clipped it and under-predicted the level:
0.12 vs 0.30), direction constraints from research priors (Guo et al. 2014: engagement rises with
speaking rate; repetition and low new information raise drop risk), one global rate multiplier
calibrated on training lectures, an empirical band, and a dedicated drop classifier for flags.
Honest misses: the drop classifier catches fewer drops than the baseline (higher precision, lower
recall), and the curve does not beat the baseline at ranking segments within a video.

Two model fixes made during development (both for correctness, not tuned on test results):
1. Predict a per-second rate instead of a per-segment drop (simulations had depended on segment
   boundaries).
2. Removed segment length as a model input (it had learned an artefact of counting lecture
   starters in the first 10 s; one moved line swung a simulation by +16 points).

## Embedding model

`sentence-transformers/LaBSE` (Apache-2.0), chosen by `scripts/embedding_benchmark.py` with a rule
fixed before running. See `docs/embedding_benchmark.md`. All six candidates are open-licence and run
locally.

## Verification

- `pytest -q`: 90 passed (no GPU or weights needed). Includes a real ffmpeg/ffprobe run on a
  generated clip whose black→white cut at 30 s is found.
- `pytest -m model`: 3 passed. With real LaBSE on the EN/HI/Hinglish fixtures, the planted repeat
  is detected and is the top-ranked segment by segment-level similarity, in every language.
- `ruff check .` and `black --check .`: clean.

## Known gaps and honest caveats

1. **No real-speech ASR check on this machine yet.** Whisper large-v3 (≈3 GB) has not been
   downloaded or run here. The Hindi/Hinglish GPU test (`pytest -m gpu`) needs two 30 s clips
   recorded by the team: `backend/tests/fixtures/audio/hi_30s.wav`, `hinglish_30s.wav`.
2. **Machine mismatch.** Developed on an RTX 4060 laptop. The demo machine is an RTX 5050
   (Blackwell, sm_120), which needs a cu128 torch build (see README). CTranslate2 must also be
   checked there. Redo the GPU check on the 5050 before the demo.
3. **Fixture timing is synthetic.** `asr_*.json` comes from the scripts with seeded timing, so it
   tests logic, not ASR behaviour.
4. **Repetition threshold over-matches in Hindi/Hinglish.** At the benchmark threshold 0.527,
   sentence-level matching produces false matches at 0.53–0.61 in the Hindi and Hinglish fixtures
   (4 segments each); English had none. Segment-level ranking was correct in all three. The
   threshold was deliberately *not* re-tuned on these author-written fixtures (that would be
   overfitting). Phase 6 detection should rank by segment-level similarity and combine evidence,
   and the threshold should be re-derived from real transcripts.
5. **The benchmark data is small and author-written** (40 items). Its ranking is indicative only.
6. **Visual features are low-level** (cuts and motion on 64×36 grayscale). No content
   understanding, no B-roll detection yet.
7. Not built: thumbnail upload (field reserved).
8. Rule-based flags (repetition etc.) are not validated against retention data; the model alone is.
9. Plain-LLM baseline ("why not ChatGPT?") not run yet.

## Backend update needed for the dashboard video (added 2026-10-03, review before merging)

The dashboard plays the project video full-screen behind its panels. That needs the new
`GET /api/projects/{id}/media` endpoint, added in `backend/app/api/projects.py`
(+ `MediaStore.plaintext_size` / `iter_range` in `storage/media_store.py`):

- Streams the encrypted original, decrypting **only the 1 MiB chunks a request needs**; every
  chunk is still authenticated, and nothing decrypted is written to disk.
- Single-range HTTP Range support (`bytes=a-b`, `a-`, `-n`) → 206 with `Content-Range`; 416 when
  unsatisfiable. `Cache-Control: no-store` so unpublished video isn't cached by the browser.
- 404 for script projects or missing uploads; 503 if `DROPZERO_MEDIA_KEY` is unset.
- Tests: `backend/tests/test_media_api.py` (full file, chunk-crossing ranges, suffix range, 416,
  script 404) and `test_media_store.py` (range decrypt at chunk edges, tamper detection).

**If you pull the frontend without this backend change, video projects show "Video streaming
isn't available from the API yet" and a *Load local copy* button instead of auto-playing.**

## Data used for steps 5 and 10

No team member has a YouTube channel, so no YouTube retention exports exist. The only public
source of real in-video drop-off found was MOOCCubeX (THU-KEG, GPL-3.0). Its watch logs record
which parts of each lecture every viewer played, and its captions carry timestamps. Rebuild:
`python scripts/build_mooc_curves.py` then `python scripts/train_model.py` (raw data in the
gitignored `data/raw/mooccubex/`, about 3.9 GB).

## Added in the final sprint

- **Simulation v2 (exposure model):** a cut, trim or speed-up removes the viewer's exposure to that
  time's predicted drop risk; untouched content keeps its prediction (no re-segmentation noise).
  Custom editor edits (`custom_edits`: CUT / TRIM_START / TRIM_END / SPEED) are simulated too.
- **LLM explanations:** `POST /api/projects/{id}/flags/{fid}/explain`, local Qwen3-1.7B
  (Apache-2.0). Input is the evidence object; every number in the answer must exist in the
  evidence, else retry then template fallback (`source` says which). On the team videos all
  tested answers passed the check. About 10–35 s per flag on the GPU, cached.
- **Flags:** dead air (quiet audio) vs music/visuals without speech; cut points never inside a word.
- **Not built (roadmap):** real before/after render, promise ledger beyond the title, plain-LLM
  baseline comparison.

## Before/after render (added 2026-10-03)

`POST /api/projects/{id}/render` (same body as `/simulate`) builds an edited copy of the edit plan
with FFmpeg; `GET /api/projects/{id}/renders/{render_id}` reports status and
`.../renders/{render_id}/media` streams it with HTTP Range. Code: `backend/app/render/`
(`plan.py` reuses the simulator's `to_ops`, so the render and the simulated curve remove the same
seconds; MOVE edits are rendered but not simulated). One pass: trim, speed (video `setpts`, audio
`atempo`), 15 ms audio fades at every join, concat, height capped at 720p (`config/render.yaml`).
NVENC first, CPU (libx264) fallback. Output is encrypted in the media store as
`render-<plan key>`, cached per plan, purged with the project; the decrypted working copy is always
deleted. Tests: `backend/tests/test_render.py` (plan logic + a real ffmpeg render through the API).

Also fixed: `MediaStore.iter_range` now opens the file per chunk, so a browser holding a video
stream open no longer blocks deleting a project on Windows (regression test added).
