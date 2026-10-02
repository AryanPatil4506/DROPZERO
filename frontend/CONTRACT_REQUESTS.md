# Contract requests from the frontend

Things the UI needs that the current contract (`docs/frontend-brief.md` §4) doesn't provide. The
frontend works without them today (fallbacks noted); none of these were changed in `backend/`.

## 1. `GET /api/projects/{id}/media` with HTTP Range — **implemented, backend owner to review**
Added on 2026-10-03 in `backend/app/api/projects.py` (details and tests in `docs/build-status.md`,
"Backend update needed for the dashboard video"). The dashboard needs this backend change to
auto-play the video in the background. Without it, video projects fall back to a *Load local copy*
picker that plays the user's file from the browser.

## 2. Prediction and flags for every project — done
All three samples now have real model output. Please keep **404** (not 500 or an empty 200) for
"model step hasn't run", so the UI can tell "unavailable" apart from "no flags".

## 3. Topic labels
`features/text` → `topics[]` has `start/end/first_segment/last_segment` but no name, so the topic
lane shows "Section 1, 2, 3…". Requested: an optional `label: string` per topic
(e.g. "Intro", "What is an agent", "Demo"). The type already has `label?: string` and renders it
when present.

## 4. Auth endpoints (for the sign-in screen)
The app has a sign-in page because the product needs one, but the brief lists auth as roadmap only.
Today it is a **demo session** (sessionStorage flag, no network). When accounts exist, the UI expects:

```
POST /api/auth/login   { email, password }  → 200 { user: { id, email } } + httpOnly session cookie
POST /api/auth/logout                        → 204
GET  /api/auth/me                            → 200 { user } | 401
```
401 from any endpoint would then redirect to `/login`.

## 5. Simulation honours `edit_ids` — done (live API)
The live endpoint recomputes for the `edit_ids` sent. Mock mode only has the recorded all-edits
simulation and returns a clear error for other combinations.

## 6. Simulate custom cuts
Creators can mark their own cuts on the timeline (Edit plan → Mark in / Mark out). They are kept in
the browser and are **not simulated** today (the UI says so). Requested: let `POST /simulate` also
accept `custom_cuts: [{start, end}]` alongside `edit_ids`.

## 7. Persist the edit plan (optional)
Accepted edits and custom cuts live in page state and are lost on reload. If wanted:
`PUT /api/projects/{id}/edit-plan { accepted_edit_ids, custom_cuts }` and a matching `GET`.

## 8. Nice to have
- `Prediction.segments[].flag_ids: string[]`, so a risk point maps to its flag without the UI
  intersecting time ranges.
- `Flag.matched_range` for repetition flags is currently encoded as evidence `ref_start/ref_end`;
  fine as is, just keep it.
