# DROPZERO pitch

**PS 5: Retention Predictor. Find the drop-off before you publish.**

> DROPZERO is a pre-publish audience simulator. Upload a script or a cut, and it shows where
> viewers are likely to leave, why, the exact edit that fixes it, and the model-estimated effect
> of that edit, all before a single viewer sees the video.

Every number in this document comes from a reproducible run in this repository (sources in the
[numbers sheet](#numbers-sheet)). Nothing is rounded up. Where we lose, we say so.

---

## 1. The 3-minute spoken pitch

Timings are a guide; the live demo carries the middle. Full click path: `docs/demo-script.md`.

**0:00 – Problem (20 s)**
"Retention is one of YouTube's strongest ranking signals, and creators only see their drop-off
graph *after* publishing, when the video is already out. But most drops have boring, predictable
causes: a slow intro, a repeated explanation, a payoff promised at the start and delivered three
minutes later. Those causes are in the script. You can measure them before you hit publish."

**0:20 – What DROPZERO is (20 s)**
"DROPZERO reads your script or your edit and gives you one timeline: a predicted retention curve
with its uncertainty band, red and yellow flags at the exact seconds, the evidence behind each
flag, and the edit that fixes it. Then it simulates that edit, and it renders the edited copy."

**0:40 – Why it's not a chatbot wrapper (20 s)**
"Prediction comes from measured features: pace against *your own* average, semantic repetition,
new information and topic structure, turned into a curve by a model trained on real viewing data.
Rule checks add what the model can't see yet: promise-to-payoff delay, silence, a static picture,
flat pitch, long pauses. The language model only *explains* the evidence it is handed, and if it
uses a single number that isn't in the evidence, we refuse the answer."

**1:00 – Live demo (90 s)** (the golden project, `docs/demo-script.md` steps 2–8)
1. The curve and the band: "trained on real drop-off from 310,360 viewers."
2. Click the red point at 0:00: *Slow hook, nothing is said for the first 12 s*. Evidence and timestamps.
3. *Promise at 00:34 kept only at 02:30*: the promise ledger.
4. *Repeats 00:38–00:49* → **Show me what to cut** → **Simulate fix**: "model-estimated, labelled as such."
5. **Rewrite**: one rewrite is refused because it changed the meaning (similarity 0.696 < 0.70). "It
   won't put words in your mouth."
6. Edit plan → **Render** → side by side: "the original file is never touched."

**2:30 – Proof (20 s)**
"On 220 held-out lectures, we beat the average-curve baseline on curve error, 0.172 against 0.220,
and on drop precision, 0.48 against 0.41. We catch fewer drops than it: 1,100 of 1,660 against
1,306. And a plain LLM, given the same transcripts, found 63 of 296 real drops; we found 99. Our
Validation page shows every one of those numbers, including the misses."

**2:50 – Close (10 s)**
"Hindi and Hinglish native, private by default, runs on one laptop GPU. DROPZERO: find the
drop-off before your viewers do."

---

## 2. Slides

Ten slides, matching the problem statement's four required capabilities and the judging flow.

### Slide 1 · Title
**DROPZERO** · Find the drop-off before you publish.
Pre-publish audience simulator for video creators. English, Hindi, Hinglish.
*[Team names]*

### Slide 2 · The problem
- Creators see their retention graph only after publishing.
- Most drops have predictable causes: slow intro, long tangent, repeated explanation, delayed payoff.
- Those causes are measurable in the script and the cut, before release.

*Notes:* open on a real drop-off curve (the Validation page example lecture), then ask "what if
you had this before publishing?"

### Slide 3 · What you get (the four required capabilities)

| Requirement | DROPZERO |
|---|---|
| Predicted retention curve | Per-segment survival curve, R(t) = R(t−1)·(1 − p_drop), with a 10–90% band |
| Reasoned flags | "Repeats 00:38–00:49", "Promise at 00:34 kept only at 02:30", "12 s before the first word", each with its evidence and a source tag: *model*, *rule* or *model+rule* |
| Actionable edits | CUT / MOVE / SHORTEN / REWRITE / ADD_VISUAL / ADD_HOOK with exact timestamps; cut points snapped to pauses between words |
| Validation | Held-out test on real viewing logs, against a baseline and a plain LLM, misses shown |

### Slide 4 · Architecture

```
Upload (video or script) ─► Whisper large-v3 (word timestamps) ─► 5–15 s segments
   ─► Model features (transcript): position, pace vs your average, novelty, information gain,
                                   repetition, topic structure
   ─► Retention model (gradient boosting, trained on real drop-off) ─► curve + band
   ─► Drop detector: model risk + evidence rules (title/intro promises, slow hook, silence,
      static picture, fillers; pitch, pauses and repeated phrases as extra evidence)
   ─► Evidence engine ─► flags + edits
   ─► Local LLM (Qwen3-1.7B): explains evidence, rewrites lines; every number checked
   ─► Exposure simulation ─► FFmpeg render of the edit plan
```

- **ML predicts, the LLM narrates.** The LLM never sees anything but the evidence object.
- **The model uses transcript features only** (that is what the training data has). Audio and
  visual signals drive rule flags, which are labelled as rules and not validated against retention.
- **Deterministic:** same input, same features, same prediction; model and feature versions are
  stamped on every result.
- **All local and open source:** Whisper, LaBSE embeddings, Qwen3, FFmpeg. No transcript goes to
  a third-party AI service.

### Slide 5 · Live demo
Golden project *I Built an AI Agent in 24 Hours* (2:41). It is a synthetic demo video (our English
test script voiced with Windows text-to-speech); the analysis on it is real and runs live. Follow
`docs/demo-script.md`; warm it first with `scripts/warm_demo.py`.

### Slide 6 · Beyond the curve

| Feature | What it does |
|---|---|
| Promise ledger | Promises made in the opening, tracked to their payoff: kept on time, kept late, never kept |
| Show me what to cut | Smallest range that removes the problem; edit plan with cuts, trims, speed changes |
| Before/after render | FFmpeg renders the edited copy; original and edited play side by side, each with its curve |
| Rewrite with a meaning check | Local LLM tightens flagged lines in the video's language; refused if it changes the meaning (LaBSE ≥ 0.70), adds numbers, or isn't shorter |
| Hook A/B simulator | Two versions of an opening, simulated side by side; "no clear difference" when the curves are within the band |
| Delivery evidence | Flat pitch against your own range, long pauses, phrases said again and again, attached to the flags they explain |
| Score lanes | Pace, content, visual and audio scores per segment; *DROPZERO internal scores* |
| Creator report | One printable page: top issues, exact edits, ledger, validation |

### Slide 7 · Validation: does it work?

Model `mooc-hgb3-0e371ea6`, trained on 980 lectures and tested on 220 **held-out lectures**
(split by lecture, so no leakage), from real viewing logs of 310,360 viewers (MOOCCubeX).

| | DROPZERO | Category-average baseline |
|---|---|---|
| Curve error (MAE) | **0.172** | 0.220 |
| Curve correlation (Pearson) | **0.58** | 0.53 |
| Drop precision (±10 s) | **0.48** | 0.41 |
| Drop F1 | **0.56** | 0.54 |
| Major drops caught | 1,100 of 1,660 | **1,306 of 1,660** |
| 10–90% band covers the actual curve | 76% | — |

*Say it:* "We are more precise; the baseline flags more and catches more. 560 drops we miss are on
the Validation page."

### Slide 8 · Why not just ask ChatGPT?

Same 40 held-out lectures, each method names its top 5 drop points, scored against real drops.

| | Real drops found | Precision |
|---|---|---|
| **DROPZERO** | **99 of 296** | **0.66** |
| Position baseline | 94 of 296 | 0.61 |
| Plain LLM (transcript only) | 63 of 296 | 0.56 |

*Caveat to say out loud:* the plain LLM is the same small local model we use (Qwen3-1.7B), not a
frontier chatbot; a larger LLM may do better. **Ablation:** removing any one feature group (pacing,
novelty, repetition, topics) drops detection F1 from 0.56 to 0.49; removing position raises curve
error from 0.172 to 0.202. Every group earns its place.

### Slide 9 · Built for Indian creators, private by default
- English, Hindi (Devanagari) and Hinglish: Whisper large-v3 transcription, LaBSE multilingual
  embeddings, filler dictionaries in both scripts ("basically", "matlab", "toh"), rewrites that keep
  the creator's own script mix.
- Unpublished video is encrypted at rest (AES-256-GCM), streamed by decrypting only the chunks a
  player asks for, deleted on a schedule or on request. Everything runs on one laptop GPU.

### Slide 10 · Business and roadmap
- **Buyers:** mid-size creators (10K–1M subscribers), editing agencies, edtech teams (lecture
  drop-off is course completion), Hindi and regional creators.
- **Proposed tiers** (not validated with customers yet): Free (2 videos/month, curve + top 3 flags),
  Creator (~₹999), Pro (~₹2,499: render, A/B, calibration), Agency (~₹9,999: multi-channel, client
  review links).
- **Cost:** no per-video API fees; open-source models on one GPU. Script analysis is much cheaper
  than video, so script mode can stay generous.
- **Next:** import creators' YouTube Studio retention exports to validate on YouTube itself, then
  per-channel calibration; Shorts and Reels; editor integrations (Premiere / DaVinci edit lists).

---

## Numbers sheet

| Claim | Value | Source |
|---|---|---|
| Training data | 1,200 lectures, 310,360 viewers (MOOCCubeX; online-course lectures, not YouTube) | `models/validation.json`, `docs/build-status.md` |
| Split | 980 train / 220 test, held out by lecture | `models/validation.json` |
| Curve MAE / RMSE | 0.172 / 0.207 (baseline 0.220 / 0.265) | `models/validation.json` |
| Pearson / Spearman | 0.58 / 0.58 (baseline 0.53 / 0.51) | `models/validation.json` |
| Drop detection | P 0.48, R 0.66, F1 0.56; 1,100 of 1,660 (baseline P 0.41, R 0.79, F1 0.54; 1,306) | `models/validation.json` |
| Band coverage | 76.2% | `models/validation.json` |
| Median end retention | actual 0.30, predicted 0.30 | `models/validation.json` |
| Plain-LLM baseline | DROPZERO 99, position 94, LLM 63 of 296 drops (40 lectures, top 5) | `models/llm_baseline.json` |
| Ablation | without pacing / novelty / repetition / topics: F1 0.49 each; without position: MAE 0.202 | `models/validation.json` |
| Rewrites | 8 of 12 accepted on the three sample scripts (similarity 0.72–0.97) | `docs/build-status.md` |
| Speed (RTX 5050 laptop) | 4.5-minute video fully analysed in 72 s, model loading included; render of a 70 s clip in 12 s on the CPU encoder; pitch tracking ~2 s per 15 min of audio; AI explanation 10–35 s per flag, then cached | measured 2026-10-03 |
| Tests | 174 backend tests passing; frontend typecheck, lint and build clean | `pytest -q` |

---

## Honest limits (say them before a judge does)

1. **Trained on lectures, not YouTube.** No team member has a channel, so no YouTube retention
   exports exist. MOOCCubeX is the only public source of real in-video drop-off we found. Importing
   creator retention CSVs is the first roadmap item.
2. **We miss drops.** Recall 0.66 against the baseline's 0.79; within-video ranking of which
   segment loses most is barely above baseline (0.18 vs 0.17).
3. **Rule flags are not validated against retention**, only the model is. Every flag says which it
   came from (*model*, *rule*, *model+rule*).
4. **Hindi is the weakest language** for rewrites (1.7B model) and repetition thresholds; the UI asks
   creators to read Hindi rewrites carefully.
5. **Visual understanding is low-level:** cuts and motion, not what is on screen.
6. **Simulations are model estimates**, and hook A/B differences are often within the uncertainty
   band, which we report as "no clear difference".

---

## Judge Q&A

**Where does the training data come from? Any leakage?**
MOOCCubeX lecture-viewing logs (310,360 viewers). Split by lecture with a fixed hash, thresholds
chosen on training lectures only, metrics on 220 unseen lectures.

**Why not just use an LLM?**
Slide 8: on the same lectures a plain LLM found 63 real drops, DROPZERO 99. And the LLM can't give a
calibrated curve, a band, or reproducible numbers. We use an LLM only where it is good: wording.

**How do you stop the LLM from making things up?**
It receives a structured evidence object only. Every number and timestamp in its answer must exist
in that evidence, otherwise we retry, then fall back to a template. Rewrites are also checked for
meaning (LaBSE similarity), length and script.

**Cost and latency per video?**
No API fees: all models are open source and local. A 4.5-minute video took 72 s end to end on an
RTX 5050 laptop; scripts are faster because there is no transcription.

**Hindi and Hinglish weaknesses?**
Transcription and embeddings are multilingual; fillers are matched in both scripts. Weakest parts:
small-model Hindi rewrites and repetition thresholds that over-match in Hindi (documented, not
re-tuned on our own fixtures to avoid overfitting).

**You don't model thumbnails or the recommendation algorithm.**
Correct. DROPZERO predicts what happens *after* the click: in-video retention. Title-to-content
promise tracking is the part of packaging we do cover.

**Privacy of unpublished videos?**
AES-256-GCM at rest, decrypted in memory only for the chunks being played, purged on a schedule,
deletable from the Projects page, never sent to a third-party AI service.

**Is the before/after improvement real?**
It is a model estimate under an exposure model (a cut removes the viewer's exposure to that
section's predicted drop risk) and is labelled that way everywhere. The real test is publishing and
importing the retention data, which is the roadmap's first item.
