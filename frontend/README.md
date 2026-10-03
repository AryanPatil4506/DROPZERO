# DROPZERO frontend

React 18 + Vite + TypeScript, Tailwind CSS v4, Recharts, TanStack Query, React Router.
Built against `docs/frontend-brief.md`. Mock mode serves the recorded API responses in `mock/`
(regenerate with `python scripts/export_api_samples.py`).

## Run

```powershell
cd frontend
npm install
npm run dev:mock     # mock mode: serves frontend/mock/, no backend needed
npm run dev          # live mode: /api is proxied to http://127.0.0.1:8000 (start the backend first)
```

Open http://localhost:5173. The mock flag is `VITE_USE_MOCKS=true`: `npm run dev:mock` sets it via
`.env.mock`, or set it yourself in `.env.local` (see `.env.example`).

```powershell
npm run build        # type-check + production build
npm run lint         # eslint
```

## Routes

| Route | Screen |
|---|---|
| `/` | Redirects to the landing page (`/landing/index.html`) |
| `/login` | Sign-in (demo session, see below) |
| `/projects` | Projects list |
| `/new` | Upload video/script, then a live stage stepper while the job runs |
| `/projects/:id` | Dashboard: video full-bleed in the background, glass panels in front (analysis, transcript, flags, "Why would I leave?"), transport, Timeline / Edit plan shelf |
| `/projects/:id/simulate?edits=e1,e2` | Original vs simulated curves, edit checklist, model-estimated deltas |
| `/validation` | Metrics vs baseline, drop detection ("41 of 71 detected"), actual vs predicted overlay |
| `/landing/index.html` | Static marketing page (from `public/landing/`), the first page visitors see; "Sign in" goes to `/login` |

## Judge demo path

Sign in → open *I Built an AI Agent in 24 Hours* → click the red point on the curve → read
"Why would I leave?" and the evidence → **Show me what to cut** (highlights the range on the curve,
segment bar and transcript) → **Simulate fix** → original vs simulated → rail icon ✓ → validation.

## Dashboard controls

- **Background video** plays `GET /api/projects/{id}/media`; until that exists use **Load local copy**
  (video projects) or **Attach recording** (script projects, preview only: script timing is
  estimated, so it may not line up). Files stay in the browser. Script projects without a recording
  show a teleprompter of the current line instead.
- **Transport:** restart · −10 s · play/pause · +10 s · ✂ edited preview. Clicking the video also
  toggles play/pause.
- **Rewrite this section** ("Why would I leave?" panel): the local LLM suggests a tighter version
  of the flagged lines in the video's language, with word counts, an estimated time saving and the
  meaning-match score. The server refuses rewrites that change the meaning, aren't shorter, cut too
  much, add numbers or switch script, and the panel says why. Hindi output carries an extra caution.
- **Render edited version** (Edit plan, video projects): FFmpeg builds an edited copy of the plan
  (accepted suggestions including moves, plus your trims/cuts/speed-ups) and opens
  `/projects/:id/compare`: original and edited play side by side with shared play / pause /
  restart, each with its curve (original prediction / model-simulated edit). The copy is encrypted
  and purged with the upload; the original is never modified.
- **Promises** (shelf tab): the promise ledger from `flags.ledger`: each promise made in the title or
  opening, when it pays off, the wait, and its status (kept on time / kept late / open loop). Rows
  seek the timeline; *See fix* opens the matching payoff-delay flag.
- **Lanes: Structure / Scores** (timeline header, shown when `/scores` returns data): Structure shows
  risk, topics and edits; Scores shows risk plus four thin pace / content / visual / audio lanes
  (DROPZERO internal scores; hover a block for its inputs).
- The recorded mocks predate the ledger and score lanes. Re-run `python scripts/export_api_samples.py`
  (needs the full backend environment) to include them in mock mode.
- **Edit plan** (shelf tab, or "Add to edit plan" in the drawer): accept suggested edits, **Mark in /
  Mark out** your own cuts at the playhead, **Preview with cuts** (playback skips accepted CUT/SHORTEN
  ranges and your cuts; skipped transcript lines are struck through), **Simulate accepted edits**,
  and **Export edit list (JSON)**. This is an edit decision list only; the original file is never
  modified.
- Dev only: `?demoVideo=/demo/clip.mp4` plays a file from `public/demo/` (git-ignored) behind the
  dashboard, for rehearsing the visuals without the media endpoint.

## Notes

- **One shared timeline.** Clicking the curve, a risk segment, a topic, an edit, a flag or a
  transcript line sets the current time and the selected flag (`components/dashboard/timeline-context.ts`).
- **Script mode** has no media, so ▶ moves a virtual playhead through the *estimated* timing; the
  "Estimated timing" badge is shown wherever times appear.
- **Video mode** plays `GET /api/projects/{id}/media`; until that exists, the player offers a local
  file picker (the file stays in the browser).
- **Sign-in is a demo session.** There is no auth API yet, so any valid email + non-empty password
  stores a flag in `sessionStorage` for the tab. Nothing is sent or stored server-side.
- **Mock mode shows a banner.** Responses with a `_mock` field (placeholder numbers) also get a
  "Mock · placeholder numbers" badge. Recorded simulations cover all suggested edits together; other
  combinations need the live backend, and the UI says so.
- **Flag source tags:** *Model* (validated retention model), *Evidence rule* (not validated against
  retention data) or *Model + rule*. Only `simulatable` edits (CUT/MOVE) are offered for simulation.
- The validation page shows the baseline beside every metric, including the drop-ranking rows where
  the model does not beat it, plus detection vs baseline, band coverage and ablations.
- Chart colours were checked for contrast and colour-blind separation on the dark surface:
  predicted `#6a8fe0`, simulated `#2aa37e`, original `#8a8a93`; risk red/amber always carry a text label.
- API gaps found while building are listed in `CONTRACT_REQUESTS.md`.
