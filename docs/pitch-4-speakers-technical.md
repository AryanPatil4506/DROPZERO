# DROPZERO: 4-speaker technical pitch (about 4 minutes)

Speakers: **A** tech stack, **B** pipeline, **C** retention-curve model and parameters,
**D** features. Every parameter below is from `config/*.yaml`; every number from
`models/validation.json` / `models/llm_baseline.json`.

---

## A · Tech stack (0:00–0:50)

> "DROPZERO is a pre-publish audience simulator: it predicts where viewers will leave a video
> before it's published, explains why, and proposes the fix. It runs entirely locally on
> open-source components.
>
> The **backend** is Python with FastAPI, Pydantic v2 schemas and SQLite. Uploaded videos are
> encrypted at rest with AES-256-GCM in 1 MB chunks, so we can stream them for playback by
> decrypting only the chunks the player needs.
>
> The **models**: faster-whisper large-v3 for speech-to-text with word timestamps; LaBSE, a
> multilingual sentence-embedding model, for meaning; a scikit-learn gradient-boosting model for
> retention; CLIP ViT-B/32 for what's on screen; and Qwen3-1.7B as a local LLM that only explains
> and rewrites. FFmpeg does audio, frames and rendering.
>
> The **frontend** is React 18, TypeScript and Vite, with Tailwind, Recharts for the curve and
> TanStack Query for data. Everything runs on one laptop GPU, an RTX 5050, so no transcript
> leaves the machine and there are no per-video API fees."

---

## B · Pipeline (0:50–1:50)

> "Here's what happens to an upload, stage by stage.
>
> **One, ingestion.** FFmpeg extracts 16 kHz mono audio, tiny 64×36 grayscale frames at 2 fps for
> cut detection, and 224-pixel colour frames at 1 fps for content analysis. Scripts skip this:
> timing is estimated at 2.5 words per second for English, 2.2 for Hindi, 2.4 for Hinglish, and
> labelled as estimated.
>
> **Two, transcription.** Whisper large-v3, beam size 5, voice-activity filter on, word-level
> timestamps.
>
> **Three, segmentation.** A dynamic-programming segmenter cuts the timeline into windows of 5 to
> 15 seconds, target 12, snapping to sentence ends and scene cuts. One segment is one row of
> features.
>
> **Four, features.** Text, audio and visual, all deterministic: same input, same numbers.
>
> **Five, prediction** of the retention curve, then **six, detection**: model risk plus evidence
> rules produce flags with timestamps and evidence.
>
> **Seven, explanation**: the LLM gets only a structured evidence object; any number in its answer
> that isn't in the evidence gets it rejected. **Eight, simulation and render**: edits are
> replayed on the model, and FFmpeg renders the edited copy."

---

## C · The retention curve: model and parameters (1:50–3:00)

> "The curve is survival-style. For every segment we predict a drop probability, and retention
> is a running product: R(0) = 1, R(t) = R(t−1) × (1 − p_drop(t)). So every dip traces back to
> a specific segment and its features.
>
> The model predicts a **per-second drop rate**, not a per-segment drop, so the curve doesn't
> depend on how the video is sliced. Its inputs are 16 features in five groups:
> - **Position:** relative start and end, log start time, first segment. This is the baseline
>   shape every video shares.
> - **Pacing:** words per second against *this video's own* median, plus silence.
> - **Novelty:** semantic novelty and information gain from LaBSE embeddings, and their average
>   over the previous three segments, which we call attention debt.
> - **Repetition:** similarity to material at least 20 seconds earlier, the share of repeated
>   sentences, and how many times it repeats.
> - **Topics:** topic shift, topic boundaries, and time since the topic started.
>
> It's scikit-learn's histogram gradient boosting: 300 iterations, learning rate 0.05, 15 leaves
> per tree, at least 40 samples per leaf, L2 regularisation 1.0, random seed 0. We add
> **monotonic constraints** from research: more repetition can only raise drop risk; more
> novelty, more information gain and a faster pace can only lower it. So the model can't learn
> something backwards from noise.
>
> The band is the empirical 10th to 90th percentile of errors on training lectures, in 10 bins;
> on test lectures it contains the actual curve 76% of the time. Flags use a separate drop
> classifier: a major drop is a segment losing at least 5% of its viewers, matched within ±10
> seconds; risk is high above the 90th percentile and medium above the 75th.
>
> Training data is **MOOCCubeX**: real watch logs, 1,200 lectures, 310,360 viewers, split by
> lecture into 980 train and 220 test. On the test lectures: curve error 0.172 against 0.220 for
> the average-curve baseline, drop precision 0.48 against 0.41, but fewer drops caught, 1,100 of
> 1,660 against 1,306. A plain LLM found 63 of 296 drops; we found 99. Remove any one feature
> group and detection F1 falls from 0.56 to 0.49."

---

## D · Features (3:00–4:00)

> "On top of the curve, the features creators actually use:
> - **Flags with evidence**: slow hook, repetition, low new information, slow pacing, dead air,
>   static picture, and a **promise ledger** that tracks every promise in the opening to its
>   payoff, with the delay.
> - **Delivery evidence**: pitch range from our own YIN pitch tracker in semitones against your
>   own range, pauses between words of 1.5 seconds or more, and three-word phrases said three or
>   more times.
> - **On-screen content**: CLIP labels each frame as slide, diagram, chart, screen recording,
>   talking head, footage or blank, and scores how well the picture matches the words. If the
>   visuals carry a flat stretch, the rule softens that flag. These audio and visual signals are
>   labelled rules, not validated, because our training data has no video frames.
> - **Fixes**: CUT, MOVE, SHORTEN, REWRITE, ADD_VISUAL with exact timestamps, cut points snapped
>   to pauses; **Show me what to cut**; **Simulate fix**; and **Render**, which produces the edited
>   copy side by side with the original.
> - **Rewrites** with a meaning check: LaBSE similarity at least 0.70, shorter, no new numbers,
>   same script.
> - **Hook A/B simulator**, **score lanes**, a **PDF creator report**, in English, Hindi and
>   Hinglish.
>
> DROPZERO: find the drop-off before your viewers do."

---

## Parameter cheat sheet

| Area | Parameter | Value |
|---|---|---|
| ASR | Whisper | large-v3, beam 5, VAD on, word timestamps |
| Script timing | words/s | en 2.5, hi 2.2, hinglish 2.4 |
| Segments | window | 5–15 s, target 12 s |
| Repetition | min gap / threshold | 20 s / cosine 0.527 (sentences), flag ≥ 0.60 and above the video's 90th percentile |
| Model | HistGradientBoosting | 300 iter, lr 0.05, 15 leaves, min leaf 40, L2 1.0, seed 0 |
| Monotonic | +1 / −1 | repetition +1; novelty, gain, pace −1 |
| Band | quantiles | 10–90%, 10 bins, 76.2% test coverage |
| Major drop | hazard / tolerance | ≥ 5% of viewers / ±10 s |
| Risk levels | quantiles | high 0.90, medium 0.75 |
| Pitch | YIN | 70–400 Hz, 40 ms frames, 20 ms hop, flat < 60% of own range |
| Pauses | long pause | ≥ 1.5 s |
| Phrases | n-gram | 3 words, ≥ 3 times, ≤ 1 stopword |
| Visual | CLIP | 1 fps, 224 px, min confidence 0.35, weak match < 80% of own median |
| Compensation | rule | ≥ 6 cuts/min or matching diagram/chart/screen/footage → rule risk × 0.7 |
| Rewrite | checks | similarity ≥ 0.70, ≤ 80% of words, ≥ 35%, no new numbers |
