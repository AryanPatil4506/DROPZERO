# Demo script (under 3 minutes)

The **golden project** is a demo video built to show every feature: *I Built an AI Agent in 24
Hours* (`demo_ai_agent.mp4`, 2:41). It is our English test script voiced with Windows' built-in
text-to-speech, plus a 12 s silent opening and a colour change per paragraph. **Say that it is a
synthetic demo video** if anyone asks; the analysis on it is real and live.

## Before going on stage (once per machine)

1. Start both servers (README → Run, or the two commands below).
2. If the golden project is missing:
   `.venv\Scripts\python scripts\make_demo_video.py` then `.venv\Scripts\python scripts\precompute.py`.
3. Warm everything (AI answers, rewrites, render, A/B are then instant):
   `.venv\Scripts\python scripts\warm_demo.py` (it prints the project link).
4. Open the link once, play two seconds of video, close other apps using the GPU.

```powershell
# window 1
cd C:\Users\aryan\EPOCH; .venv\Scripts\activate; $env:HF_HUB_OFFLINE="1"
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
# window 2
cd C:\Users\aryan\EPOCH\frontend; npx vite --host 127.0.0.1 --port 5173
```

## The path (what to click, what to say)

| # | Click | Say |
|---|---|---|
| 1 | Landing page → **Sign in** (any email) → the golden project | "A creator uploads a draft before publishing." |
| 2 | Point at the curve, the band and the score lanes | "Predicted retention with its likely range. The model is trained on real viewing logs of 310,000 viewers." |
| 3 | Click the red point at **0:00** → *Slow hook: nothing is said for the first 12 s* | "Every flag shows measured evidence and timestamps." |
| 4 | **Explain with AI** | "A local open-source model explains the evidence. Every number it uses is checked against the evidence; if it invents one, we fall back." |
| 5 | Flag **Promise at 00:34 kept only at 02:30** (Promises tab shows the ledger) | "The video promises a booking demo and makes viewers wait two minutes for it." |
| 6 | Flag **Repeats 00:38–00:49** → **Show me what to cut** → **Simulate fix** | "Cutting the repeat: model-estimated effect, clearly labelled as a simulation." |
| 7 | **Rewrite** on the repetition flag → it is **refused** (meaning similarity 0.696 < 0.70) | "It refuses to show a rewrite that changes the creator's meaning." Then **Rewrite** on the late-title flag, which passes. |
| 8 | Edit plan → **Render** → side-by-side compare | "An edited copy is rendered on the GPU; the original is never touched." |
| 9 | Sidebar hook icon → **A/B**: paste `data\private\demo\ab_original.txt` and `ab_promise_first.txt` | "Promise-first hook: title addressed at 0:12 instead of 0:40, half the fillers. The curves are within uncertainty, and we say so." |
| 10 | **Report (PDF)** → Download PDF; then **Validation** | "Beats the average-curve baseline on curve error and drop precision; catches fewer drops than it. We show the misses." |

## If something goes wrong

| Problem | Do this |
|---|---|
| Spinner never ends / page errors | Backend window: is it running? Restart it, refresh the page. |
| An AI answer is slow | It wasn't warmed: say "it runs locally on this laptop" and move on, or skip step 4/7. |
| Video won't play | Uploads are purged after 72 h: rerun `precompute.py` + `warm_demo.py`. |
| Anything else | Switch to the recorded backup video. |

Numbers to have ready: curve MAE 0.172 vs 0.220 baseline; drop precision 0.48 vs 0.41;
1,100 of 1,660 drops caught (baseline 1,306); plain LLM found 63 of 296 drops vs our 99.
