# DROPZERO build status

**As of 2026-10-03.** Build order: steps 1–4 done, step 5 (model) next.

## Done

| Step | What | Where |
|---|---|---|
| 1 | Projects, video/script upload, content-based type checks, ffprobe, AES-GCM encryption at rest, per-job work dirs always deleted, purge at startup | `api/`, `ingestion/`, `storage/` |
| 2 | faster-whisper large-v3 wrapper (deterministic settings, encrypted cache), script mode with *estimated* timing, sentence splitting (`.?!।` + pause fallback for unpunctuated Hinglish), DP segmenter (5–15 s, tiles the whole video, long silences as own segments) | `transcription/`, `segmentation/` |
| 3 | Text features: words/sec and pace vs this video's median, fillers (EN/HI/Hinglish dictionaries), questions, number claims, semantic novelty, information gain, repetition (sentence + segment level, ≥ 20 s apart), topic shifts and sections | `features/text/`, `config/text_features.yaml`, `config/fillers.yaml` |
| 4 | Visual: tiny grayscale frames via ffmpeg, scene cuts (absolute + local-median test), static ratio, longest static run, seconds since last cut. Audio: silence ratio relative to the video's own loudness, energy and its variation vs the video median. Scene cuts are fed to the segmenter as boundary hints. | `features/visual/`, `features/audio/`, `features/av.py`, `config/av_features.yaml` |

Endpoints added: `GET /api/projects/{id}/features/text`, `GET /api/projects/{id}/features/av`
(404 in script mode).

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
7. Not built: thumbnail upload (field reserved), video streaming for the player.
8. Nothing is committed to git yet.

## Blocker for steps 5 and 10 (model + validation)

The retention model and the validation page need **real audience-retention curves**: the
per-video "Audience retention" export from YouTube Studio (Analytics → Engagement → Audience
retention → export). Without them, step 5 can only be a transparent hand-weighted baseline, and
validation (a judging criterion) has nothing to measure against. See the conversation notes for
options.
