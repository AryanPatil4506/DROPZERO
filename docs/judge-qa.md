# Judge Q&A (matches the technical pitch)

Owner = who answers first (A stack, B pipeline, C model/data, D features/business). Keep answers
to 20–30 seconds. Numbers come from `models/validation.json`, `models/llm_baseline.json` and
`config/*.yaml`. **If you don't know, say so; never invent a number.**

---

## Data and validation (C)

**Q1. Where does your training data come from?**
MOOCCubeX, from Tsinghua's knowledge-engineering lab (THU-KEG, GPL-3.0): per-viewer watch logs
of online-course lectures plus timestamped captions. We turned the logs into real retention
curves: 1,200 lectures, 310,360 viewers.

**Q2. Why not YouTube data?**
None of us has a channel, so we have no YouTube Studio exports, and YouTube doesn't publish
per-second retention. MOOCCubeX was the only public source of real in-video drop-off we found.
Validating on creators' own YouTube exports is the first roadmap item.

**Q3. Those are Chinese lectures. Why would it work on Hindi or English YouTube?**
Fair concern, and it's not proven yet. What transfers: the inputs are language-independent by
design. Pace is relative to the video's own median; novelty, repetition and topic shifts come
from LaBSE, a multilingual embedding model. What doesn't necessarily transfer: lecture viewers
behave differently from YouTube viewers. That's why we label curves as model estimates and why
YouTube validation is next.

**Q4. Is there leakage between train and test?**
No. We split by lecture with a fixed hash, 980 train, 220 test. Segments of one lecture never
appear on both sides. Thresholds and the band are fitted on training lectures only.

**Q5. Your recall is lower than the baseline. Isn't that a fail?**
We're more precise (0.48 vs 0.41) and slightly better on F1 (0.56 vs 0.54), but we catch fewer
drops: 1,100 of 1,660 vs 1,306. The baseline flags far more points (5,270 vs our 3,404), so it
catches more by casting a wider net. We show this on the Validation page instead of hiding it.

**Q6. Does it beat the baseline on everything?**
No. Curve error and correlation: yes (MAE 0.172 vs 0.220, Pearson 0.58 vs 0.53). Ranking which
segment loses the most within one video: barely (0.18 vs 0.17). Recall: no.

**Q7. "Why not just ask ChatGPT?"**
Same 40 held-out lectures, each method names its top 5 drop points: a plain LLM found 63 of 296
real drops, DROPZERO 99, a position-only baseline 94. Caveat we state ourselves: the LLM was
Qwen3-1.7B, the same small local model we use, not a frontier model; a bigger one may do better.
An LLM also can't give a calibrated curve, a band, or the same answer twice.

**Q8. How do you know each feature helps?**
Ablation: retrain without one group. Without pacing, novelty, repetition or topics, detection F1
falls from 0.56 to about 0.49. Without position, curve error rises from 0.172 to 0.202.

**Q9. Can we see the dataset?**
It's not on GitHub: 3.9 GB of third-party data under its own licence. The repo has the trained
model, both validation reports and the scripts that rebuild them (`build_mooc_curves.py`,
`train_model.py`, `run_llm_baseline.py`). We have a local copy here. *(Bring it.)*

---

## Model and retention curve (C)

**Q10. Why a survival-style curve?**
Retention can only be built step by step: R(t) = R(t−1) × (1 − p_drop(t)). The curve declines
naturally, and every dip traces back to one segment and its features, which is what makes flags
explainable.

**Q11. Why gradient boosting and not a neural network or a time-series model?**
Tabular features, about a thousand training videos, and a need to explain every prediction.
Boosted trees are strong on that. Temporal models need far more labelled videos; CLAUDE.md
plans them only once that data exists.

**Q12. Why scikit-learn HistGradientBoosting and not XGBoost or LightGBM?**
Same family of algorithm, no extra dependency, and it supports the monotonic constraints we
needed. On our data size the choice makes little difference.

**Q13. What are monotonic constraints, and why use them?**
They force direction: more repetition can only raise predicted drop; more novelty, information
gain or pace can only lower it. That comes from research (engagement rises with speaking rate;
repetition and low new information raise drop-off). It stops the model learning a backwards rule
from noise, which matters because creators act on the advice.

**Q14. Why predict a per-second rate instead of a drop per segment?**
Otherwise the curve depends on where segments are cut: a longer window means more drop. With a
rate, segment length only converts rate into drop, and simulations stay stable when an edit
moves boundaries. For the same reason we removed segment length as an input (it had learned an
artefact of the first 10 seconds).

**Q15. How is the uncertainty band computed? Is it calibrated?**
Empirical 10th–90th percentile of errors on training lectures, in 10 bins. Nominally 80%; on
test lectures it covers the actual curve 76.2% of the time, so it's slightly narrow.

**Q16. What counts as a "major drop"?**
A segment that loses at least 5% of its viewers. Matched within ±10 seconds. Risk is high above
the 90th percentile of the model's relative drop score and medium above the 75th.

**Q17. Is it deterministic?**
Yes. Fixed random seed, deterministic GPU settings for embeddings, deterministic decoding for
Whisper, transcripts cached by audio hash. Every result stores the model and feature-schema
version, so a validation run can be reproduced.

**Q18. How long did training take? Can it retrain?**
On the order of minutes once curves are built; building curves from 3.9 GB of logs takes longer.
Retraining is a script, not automatic yet; continuous learning is on the roadmap.

---

## Pipeline and stack (A, B)

**Q19. Why Whisper large-v3? How does it handle Hinglish?**
Best open model for Hindi and code-switched speech, with word timestamps. We transcribe in the
project's language and keep English technical terms. Our sentence splitter falls back to pauses
for unpunctuated Hinglish. Honest gap: we haven't measured word error rate on our own Hinglish
recordings.

**Q20. Why LaBSE for embeddings?**
We benchmarked six open models on repeat-vs-new-information pairs with a rule fixed before
running: LaBSE scored AUC 0.932, within 0.01 of the best, and is smaller and faster
(`docs/embedding_benchmark.md`).

**Q21. How do you stop the LLM from hallucinating?**
It never predicts anything. It gets a structured evidence object: feature values, timestamps,
suggested edits. Every number in its answer must appear in that evidence; otherwise we retry
once, then fall back to a template. The UI says which one you're seeing.

**Q22. How do rewrites avoid changing the creator's meaning?**
Four checks: LaBSE similarity to the original ≥ 0.70, at most 80% and at least 35% of the words,
no numbers that weren't in the original, same script mix (Devanagari vs Roman). Failing twice
means no rewrite is shown, with the reason.

**Q23. Latency and cost per video?**
A 4.5-minute video took 72 seconds end to end on an RTX 5050 laptop, model loading included.
Scripts are faster (no transcription). AI explanation: 10–35 s per flag, then cached. Cost: no
API fees; open-source models on one GPU.

**Q24. How would it scale?**
Each stage is independent and stateless apart from SQLite and encrypted storage, so it moves to
a job queue with GPU workers. Script mode is cheap enough to stay generous on a free tier. Not
load-tested yet.

**Q25. Privacy of unpublished videos?**
AES-256-GCM at rest in 1 MB authenticated chunks; playback decrypts only the chunks requested,
nothing decrypted is written to disk; processing copies are deleted after each job; uploads are
purged on a schedule; projects can be deleted. No transcript is sent to a third-party AI service.

---

## Features (D)

**Q26. How does the promise ledger work?**
Promises in the title and opening are matched to later sentences by meaning (LaBSE), not
keywords. Each is kept on time, kept late (with the delay), or never kept. A late or missing
payoff becomes a flag with a MOVE suggestion: preview the payoff right after the promise.

**Q27. Is the simulated improvement real?**
It's a model estimate under an exposure model: cutting a section removes the viewer's exposure
to that section's predicted drop risk; untouched content keeps its prediction. Labelled
"simulated / model-estimated" everywhere. The real test is publishing and importing retention.

**Q28. Why aren't MOVE or REWRITE simulated?**
The model has no notion of reordering or of how good a rewrite is, so a number there would be
invented. Only cuts, trims and speed changes are simulated; the rest is advice, and the UI says so.

**Q29. How does pitch analysis work?**
Our own YIN pitch tracker in numpy (70–400 Hz, 20 ms hop), voiced frames only, range measured in
semitones (90th minus 10th percentile), compared with the speaker's own typical range. Below 60%
of it is "flatter delivery". Evidence only: a calm delivery isn't boring by itself.

**Q30. How do you detect what's on screen?**
CLIP ViT-B/32, one frame per second, zero-shot against a fixed list (slide, diagram, chart,
screen recording, talking head, footage, blank). A multilingual CLIP text model scores how well
the picture matches the words. Honest caveat: the prompt list is checked on one real video; the
first version mistook a lightboard lecture for a screen recording, and we fixed it with general
board/lightboard prompts.

**Q31. "Monotone voice but great visuals should keep viewers": do you model that?**
As a labelled rule, not in the model, because our training data has no video frames. If most of
a slow-pace or low-information stretch has frequent cuts, or a diagram/chart/footage that
matches the words, that rule flag's risk drops by 30% and says why. The curve isn't changed. To
learn it properly we need retention data for videos we can also analyse visually.

**Q32. Do you use OCR or read on-screen text?**
Not yet. CLIP tells us a slide is on screen, not what it says. OCR (e.g. EasyOCR with Devanagari)
is the next visual step: "60-word slide shown for 4 seconds".

**Q33. What about thumbnails and the YouTube algorithm?**
Out of scope: we model what happens after the click, in-video retention. Of packaging, we cover
title-to-content promises. Thumbnail upload is reserved in the data model, not built.

**Q34. How does the hook A/B simulator differ from a real A/B test?**
It runs two script versions through the same pipeline and model and compares hook signals and
curves. If the curves are within the uncertainty band it says "no clear difference". No viewers
are involved, and it's labelled as a simulation.

---

## Product and business (D)

**Q35. Who pays, and how much?**
Mid-size creators (10K–1M subscribers), editing agencies, edtech teams (lecture drop-off is
course completion). Proposed tiers: Free, Creator ~₹999, Pro ~₹2,499, Agency ~₹9,999. Not tested
with customers yet.

**Q36. Competitors?**
YouTube Studio shows retention only after publishing. Tools like vidIQ and TubeBuddy focus on
SEO, titles and tags. We work before publishing, on the content itself, with timestamped edits
and an edited render.

**Q37. What's your moat?**
Per-channel calibration from creators' own retention data (a data flywheel), Hindi/Hinglish
depth, and sitting in the editing workflow (edit plans, renders, NLE export later).

**Q38. What would you build next?**
1. Import YouTube Studio retention CSVs and validate on YouTube. 2. Per-channel calibration.
3. Add visual features to the model once we have frames plus retention. 4. OCR for slides.
5. Shorts/Reels and Premiere/DaVinci edit-list export.

---

## Curveballs

**Q39. What's the weakest part of the system?**
The domain gap: trained on lectures, demoed on YouTube-style content. Second: audio and visual
signals are rules, not validated.

**Q40. Your demo video is synthetic. Isn't that cheating?**
We say so up front: it's our test script voiced with text-to-speech so it shows every feature in
under 3 minutes. The analysis on it runs live. We can analyse any video you give us.

**Q41. Did an AI tool write your code?**
*(Answer honestly, as a team, if asked.)*
