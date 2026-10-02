# DROPZERO frontend brief

For the teammate building the dashboard in parallel with the backend. This file is the contract
between frontend and backend. DROPZERO predicts, before publishing, where viewers are likely to
drop off in a video or script, explains why from measured evidence, proposes timestamped edits,
simulates their effect, and validates predictions against real viewing data.

## 0. Ground rules

- **Work only inside `frontend/`.** The backend is being changed in parallel; don't edit
  `backend/`, `config/` or `scripts/`. If the contract below is missing something, write it down in
  `frontend/CONTRACT_REQUESTS.md` instead of changing the backend.
- **Build against the mocks first** (`frontend/mock/`), then switch to the live API with one env flag.
- The judge demo is the priority: **upload → click a red point on the curve → "Why would I leave?"
  → evidence → edit → "Simulate fix" → original vs simulated curve → validation page.** If time is
  short, polish this path and drop everything else.

## 1. Stack

| Concern | Choice |
|---|---|
| App | React 18 + Vite + TypeScript |
| Styling | Tailwind CSS |
| Charts | Recharts (area + line + reference areas/dots are enough) |
| Data fetching | TanStack Query (polling the job endpoint is trivial with it) |
| Routing | React Router |
| Video | Plain HTML `<video>` element |

Dev setup: Vite dev server on `:5173`, with a **Vite proxy** sending `/api` to
`http://127.0.0.1:8000` (so no CORS changes are needed in the backend). Mock mode: env
`VITE_USE_MOCKS=true` makes the API client return files from `frontend/mock/` instead of fetching.

## 2. Screens (in priority order)

### P1. Dashboard (the judge screen): `/projects/:id`
One shared timeline drives everything. Clicking anywhere (curve, risk marker, transcript line,
segment bar) sets the **current time** and the **selected segment/flag**.

```
┌──────────────────────────────────────────────────────────────────────┐
│ Title · language · category · duration · [estimated timing] badge    │
├───────────────────────────────┬──────────────────────────────────────┤
│ Video player (or script view  │  Risk drawer (selected flag)         │
│ in script mode)               │  ▸ 02:03–02:31 HIGH · Repetition     │
│                               │  ▸ "This section repeats …"          │
├───────────────────────────────┤  ▸ Evidence bullets (2–4)            │
│ Retention curve + band        │  ▸ Suggested edit (CUT 02:03–02:20)  │
│ red/yellow risk markers       │  ▸ [Show me what to cut] [Simulate]  │
│ playhead line                 │                                      │
├───────────────────────────────┤                                      │
│ Segment bar (coloured by risk,│                                      │
│ topic sections labelled)      │                                      │
├───────────────────────────────┴──────────────────────────────────────┤
│ Transcript: sentences with timestamps, current one highlighted,      │
│ click → seek; flagged ranges underlined in red/yellow                │
└──────────────────────────────────────────────────────────────────────┘
```

- **Retention curve:** x = time (mm:ss), y = 0–100 %. Line = `retention`, shaded band =
  `lower..upper`. Red dots on `risk: "high"` segments, yellow on `"medium"`. Hover tooltip shows the
  time, retention %, risk, and the flag title if there is one. Vertical playhead at the current time.
  Caption under the chart: the `label` string from the API, verbatim.
- **Risk drawer:** title, time range, severity, `explanation`, evidence as bullets (value plus unit;
  if `ref_start`/`ref_end` exist, render "matches 01:10–01:30" as a link that seeks there), the
  suggested edit(s), and two buttons:
  - **Show me what to cut**: highlights the edit range on the curve, segment bar and transcript.
  - **Simulate fix**: calls simulate with that flag's edit ids and opens the simulation view.
- **Flags list:** a compact list of all flags sorted by time (or severity), so judges can jump.
- **Script mode** (`project.source_type === "script"`): no video; show the transcript large on the
  left. Show an **"Estimated timing"** badge everywhere times appear (`timing_source === "estimated"`).
- Video playback: `GET /api/projects/{id}/media` (section 4, not built yet). Until then, play a local
  file the user picks with `<input type=file>` (object URL); it is the same video.

### P2. Simulation view: `/projects/:id/simulate` (or a panel on the dashboard)
- Original curve (grey) vs simulated curve (green) on the same axes, with the applied edits listed
  (action, time range, reason) and the `delta` numbers.
- A big, always-visible label: the `label` field (it says "Simulated / model-estimated").
  **Never** write "will improve", "guaranteed" or similar.
- Checkbox list of all suggested edits so the user can toggle which ones to simulate.

### P3. Upload + processing: `/new`
- Form: title, category (tech/education/vlog), language (en/hi/hinglish), creator (optional),
  target audience (optional). Tabs: **Video** (MP4/MOV) | **Script** (TXT/MD file or paste text).
- After upload → `POST /analyze` → poll `GET /api/jobs/{job_id}` every second. Show the stages from
  `job.stages` as a stepper with the current `job.stage` active and `progress` as a bar.
- Show `project.warnings` (e.g. "outside the tested 5–15 min range"). Show `job.error` verbatim if
  the job fails.

### P4. Validation page: `/validation`
- Headline metric cards: MAE, RMSE, Pearson, Spearman, **next to the baseline's numbers**.
- Detection: precision / recall / F1 at the stated tolerance, plus **"41 of 71 major drops
  detected"**, written that way. Misses are shown, never hidden.
- Example overlay chart: actual (solid) vs predicted (dashed) for a few test videos, with drops
  marked detected (green) or missed (red).
- Dataset caption verbatim from `dataset` (it says these are lecture-viewing logs, not YouTube).

### P5. Projects list: `/`
Simple table of `GET /api/projects` with status; click → dashboard.

### Not needed (roadmap only)
Creator report export, hook A/B, personas, root cause tree, auth.

## 3. Copy and honesty rules (these are judged)

- Times: the API sends **seconds (float)**; format to `mm:ss` only in the UI.
- Label simulations "Simulated / model-estimated", internal scores "DROPZERO internal score",
  script timing "Estimated timing". Use the API's `label` strings verbatim where provided.
- Plain creator language: "Cut 01:43–01:58: repeated explanation", not ML jargon.
- Show confidence (the band) and show misses on the validation page.

## 4. API contract

All endpoints are under `/api`. Errors are `{"detail": "message"}` with a 4xx/5xx status.

### Exists now (real samples: `frontend/mock/en/`, `hi/`, `hinglish/`)

| Method | Path | Notes |
|---|---|---|
| POST | `/projects` | body `{title, category, language, creator?, target_audience?}` → Project |
| GET | `/projects` / `/projects/{id}` | Project |
| POST | `/projects/{id}/video` | multipart `file` → Project (422 with `detail` if rejected) |
| POST | `/projects/{id}/script` | multipart `file`, or JSON `{"text": "..."}` → Project |
| POST | `/projects/{id}/analyze` | → Job (202) |
| GET | `/jobs/{job_id}` | Job: `status` queued/running/done/failed, `stages`, `stage`, `progress` 0–1, `error` |
| GET | `/projects/{id}/transcript` | `words[]`, `sentences[]` (each with `start`, `end`, `text`) |
| GET | `/projects/{id}/segments` | `[{id, index, kind: speech/silence, start, end, text, boundary, timing_source}]` |
| GET | `/projects/{id}/features/text` | per-segment text features + `topics[]` (sections for the segment bar) |
| GET | `/projects/{id}/features/av` | per-segment audio/visual features (video only; 404 in script mode) |
| DELETE | `/projects/{id}` | 204 |
| GET | `/health` | status and versions |

The full schemas are on the live OpenAPI page (`http://127.0.0.1:8000/docs`) and in
`backend/app/schemas/`.

### Coming next (mock files in `frontend/mock/contract/`; build the UI on these now)

```ts
type Risk = "low" | "medium" | "high";
interface CurvePoint { t: number; retention: number; lower: number; upper: number }  // 0..1

// GET /api/projects/{id}/prediction
interface Prediction {
  project_id: string; model_version: string; feature_schema_version: string;
  timing_source: "asr" | "estimated";
  label: string;                       // show verbatim under the chart
  points: CurvePoint[];                // starts at {t: 0, retention: 1}
  segments: { segment_id: string; index: number; start: number; end: number;
              p_drop: number; risk: Risk }[];
}

// GET /api/projects/{id}/flags
type FlagCategory = "slow_hook" | "repetition" | "low_information" | "payoff_delay"
  | "visual_monotony" | "pacing" | "fillers" | "silence";
interface Evidence { label: string; value: number | string; unit?: string;
                     ref_start?: number; ref_end?: number }   // ref = "matches 01:10–01:30"
interface Flag { id: string; start: number; end: number; severity: "high" | "medium";
  category: FlagCategory; risk_score: number; title: string; explanation: string;
  evidence: Evidence[]; secondary_categories: FlagCategory[]; edit_ids: string[] }
type Action = "CUT" | "MOVE" | "SHORTEN" | "REWRITE" | "ADD_HOOK" | "ADD_VISUAL" | "KEEP";
interface Edit { id: string; flag_id: string; action: Action; start: number; end: number;
  target_time: number | null;          // MOVE destination
  reason: string; rewrite_text: string | null }
interface FlagsResponse { flags: Flag[]; edits: Edit[] }

// POST /api/projects/{id}/simulate   body: { edit_ids: string[] }
interface Simulation { label: string; applied_edit_ids: string[];
  original: CurvePoint[]; simulated: CurvePoint[];
  original_duration_s: number; simulated_duration_s: number;
  delta: { end_retention_pp: number; avg_retention_pp: number } }   // percentage points

// GET /api/validation
interface Validation { dataset: string; model_version: string; n_videos_test: number;
  split: string;
  metrics: { mae: number; rmse: number; pearson: number; spearman: number };
  baseline: { name: string; mae: number; rmse: number; pearson: number; spearman: number };
  detection: { tolerance_s: number; precision: number; recall: number; f1: number;
               detected: number; total: number };
  examples: { video_id: string; title: string;
              actual: { t: number; retention: number }[];
              predicted: { t: number; retention: number }[];
              drops: { t: number; detected: boolean }[] }[] }

// GET /api/projects/{id}/media   → the original video bytes, supports HTTP Range (for <video>)
```

The contract mocks contain a `_mock` field. Their *predicted numbers are placeholders*: never put
them in a screenshot or slide. Simulated curves are shorter than the original (cut time is removed),
so plot them on their own time axis.

## 5. Definition of done

- The judge path in §0 works end to end on mocks, then on the live API for a script project.
- Works at 1366×768 (projector) and 1920×1080.
- No console errors; loading and error states on every fetch.
- `npm run build` passes; `npm run lint` clean.
- A `frontend/README.md` with `npm install`, `npm run dev`, and the mock flag.
