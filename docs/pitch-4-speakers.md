# DROPZERO: 4-speaker pitch (about 4 minutes + Q&A)

Speakers: **A** (problem + product), **B** (live demo), **C** (data, model, validation),
**D** (Indian creators, privacy, business, close). Replace with names. Every number comes from
`models/validation.json`, `models/llm_baseline.json` or a measured run; full sources in
`docs/pitch.md` → Numbers sheet.

---

## A · Problem and product (0:00–0:50)

> "Retention is one of YouTube's strongest ranking signals, and creators only see their drop-off
> graph after publishing, when it's too late. But most drops have predictable causes: a slow
> intro, a repeated explanation, a payoff promised at the start and delivered minutes later.
> Those causes are already in the script and the cut.
>
> DROPZERO is a pre-publish audience simulator. Upload a script or your edit, and you get one
> timeline: a predicted retention curve with its uncertainty band, flags at the exact seconds
> viewers are likely to leave, the evidence for each, the edit that fixes it, and the simulated
> effect of that edit. It is not a chatbot wrapper: a model trained on real viewing data
> predicts, and the language model only explains evidence it's handed. If it invents a number,
> we refuse the answer."

*Slide:* problem curve → the four required capabilities ticked (curve, reasoned flags, edits, validation).
**Hand-off:** "B will show you."

---

## B · Live demo (0:50–2:20)

Golden project *I Built an AI Agent in 24 Hours* (synthetic TTS demo video; the analysis is real
and live). Click path: `docs/demo-script.md`.

1. **Curve + band + score lanes + Screen lane.** "Predicted retention with its likely range."
2. **Red point at 0:00 → Slow hook:** "nothing is said for the first 12 seconds." Evidence, timestamps.
3. **Explain with AI:** "a local open-source model; every number is checked against the evidence."
4. **Promises tab → Promise at 00:34 kept only at 02:30.** "Viewers wait two minutes for the demo."
5. **Repeats 00:38–00:49 → Show me what to cut → Simulate fix.** "Model-estimated, labelled as such."
6. **Rewrite:** one is refused (meaning similarity 0.696 < 0.70): "it won't put words in your mouth."
7. **Edit plan → Render → side by side.** "An edited copy; the original is never touched."
8. *(If time)* **Hook A/B** or **Report (PDF)**.

**Hand-off:** "Does it actually work? C."

---

## C · Data, model, validation (2:20–3:20)

> "We had no YouTube channel, so no YouTube retention exports. The only public source of real
> in-video drop-off we found is **MOOCCubeX**, from Tsinghua's knowledge-engineering lab: watch
> logs showing which parts of each lecture every viewer played, plus timestamped captions. We
> built real retention curves from it: 1,200 lectures, 310,360 viewers.
>
> We trained on 980 lectures and tested on 220 held out by lecture, so there is no leakage.
> Against the average-curve baseline: curve error 0.172 versus 0.220, drop precision 0.48
> versus 0.41. We catch fewer drops, 1,100 of 1,660 against 1,306, and our Validation page shows
> every miss.
>
> 'Why not just ask ChatGPT?' On the same 40 lectures, a plain LLM found 63 of 296 real drops;
> DROPZERO found 99. And removing any one feature group (pacing, novelty, repetition, topics)
> drops detection F1 from 0.56 to 0.49, so every group earns its place."

*Slides:* validation table, LLM-baseline table, ablation.
**Be upfront:** lectures, not YouTube; audio and visual signals (pitch, pauses, on-screen
content, "visuals may carry this") are labelled rules, because the dataset has no video frames.
**Hand-off:** "D on who this is for."

---

## D · Indian creators, privacy, business, close (3:20–4:00)

> "It's built for how Indian creators actually talk: English, Hindi and Hinglish, fillers in both
> scripts, rewrites that keep your own mix. Unpublished video is encrypted at rest, deleted on a
> schedule or on request, and no transcript goes to a third-party AI service; everything runs on
> one laptop GPU, so there are no per-video API fees.
>
> Buyers are mid-size creators, editing agencies and edtech teams, where lecture drop-off is
> course completion. Next: import creators' own YouTube retention exports to validate and
> calibrate per channel.
>
> DROPZERO: find the drop-off before your viewers do."

---

## Q&A owners

| Question | Answers |
|---|---|
| Where's the training data? Leakage? | **C**: MOOCCubeX, split by lecture, thresholds on train only |
| Why not an LLM? | **C**: 63 vs 99 drops; LLM only explains, numbers are checked |
| Can we see the data / reproduce it? | **C**: see "The dataset" below |
| Does it work on YouTube? | **C**: not validated on YouTube yet; CSV import is the first roadmap item |
| Visuals, thumbnails, the algorithm? | **B**: CLIP on-screen content is evidence only; we model in-video retention, after the click |
| Hindi weaknesses? | **D**: small-model Hindi rewrites, repetition thresholds over-match in Hindi; documented |
| Cost, latency? | **D**: no API fees; a 4.5-min video analysed in 72 s on an RTX 5050 laptop |
| Privacy? | **D**: AES-256-GCM at rest, chunked decrypt for playback, purge + delete |
| Is the simulated improvement real? | **A**: a model estimate, labelled everywhere; real proof needs publishing + retention data |

---

## The dataset (MOOCCubeX): not on GitHub, on purpose

- **What:** MOOCCubeX (THU-KEG, Tsinghua University), GPL-3.0. We use `relations/video_id-ccid.txt`,
  `entities/video.json` (timestamped captions) and `relations/user-video.json` (per-viewer watch
  segments). About **3.9 GB raw**.
- **Why it's not in the repo:** size, and it is third-party data under its own licence. `data/raw/`
  and `data/processed/` are git-ignored.
- **What *is* in the repo:** the trained model (`models/retention_model.pkl`), the validation
  report (`models/validation.json`), the LLM-baseline report (`models/llm_baseline.json`), and the
  scripts that rebuild everything (`scripts/build_mooc_curves.py`, `scripts/train_model.py`,
  `scripts/run_llm_baseline.py`).
- **Reproduce:** download from `https://lfs.aminer.cn/misc/moocdata/data/mooccube2/` into
  `data\raw\mooccubex\`, then run `build_mooc_curves.py` → `train_model.py` (README → Training).
- **Bring a copy to the venue** (USB / laptop) in case a judge wants to see raw logs, since the
  repo alone won't show them.
