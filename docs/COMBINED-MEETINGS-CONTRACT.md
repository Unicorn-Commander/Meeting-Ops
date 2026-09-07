# Combined meetings — API contract (v1)

Decided by Aaron 2026-09-07: do NOT merge audio. A *combined meeting* is a new
session row that links to its parts in time order. Parts stay untouched (own
audio, transcript, speakers, player). The combined row owns only a unified
summary, insights and action items generated over the parts' transcripts.

## Data model

- `recording_sessions.is_combined BOOLEAN NOT NULL DEFAULT false`
- New table `session_group_members`:
  - `combined_session_id INT NOT NULL REFERENCES recording_sessions(id) ON DELETE CASCADE`
  - `member_session_id  INT NOT NULL REFERENCES recording_sessions(id) ON DELETE CASCADE`
  - `position INT NOT NULL`
  - PK (`combined_session_id`, `member_session_id`), index on `member_session_id`
- Alembic migration under `backend/alembic/versions/` (additive only, reversible).
- Combined row values: `organization_id` = parts' org; `started_at` = earliest
  part start; `ended_at` = latest part end; `duration` = SUM(part durations);
  `meeting_date/meeting_time` from earliest part; `status` = `processing` →
  `completed` | `failed`; `name` default `"<earliest part name> (combined, N parts)"`.
  No `audio_file`, no `transcriptions` rows of its own.
- Deleting a combined session deletes only that row + link rows. Deleting a
  member removes its link row; the combined row stays with fewer parts.
- No nesting in v1: a combined session cannot be a member.

## Endpoints (router `backend/api/sessions.py`, prefix `/api`)

### `POST /api/sessions/combine`
Body: `{"session_ids": [int, ...], "name": string | null}`
- ≥ 2 distinct ids; every id resolved via
  `session_permissions.resolve_session_for_user(db, active_org_id, sid, user, min_level="editor")`;
  all in the same org; none `is_combined`. Else 400/403/404 with `detail`.
- Creates the combined row, link rows ordered by part `started_at` (ties: id),
  enqueues `combine_sessions_job(combined_session_id)` on the INTERACTIVE arq
  lane, returns **202**:
```json
{"id": 941, "name": "Call with Tom Kim1 (combined, 2 parts)", "status": "processing",
 "is_combined": true,
 "parts": [{"id": 731, "name": "Call with Tom Kim1", "started_at": "2026-08-13T21:05:49", "duration": 1228.1, "status": "completed"},
           {"id": 730, "name": "Call with Tom Kim2", "started_at": "2026-08-13T21:30:42", "duration": 1193.5, "status": "completed"}]}
```

### `POST /api/sessions/{id}/combine/rerun`
Re-enqueues the job for an existing combined session (editor). 202, same shape.

### Existing session detail (the endpoint SessionDetails.tsx already calls)
Add to the response:
- `is_combined: bool`
- `parts: [ {id, name, started_at, duration, status} ]` — present only when `is_combined`
- `part_of: [ {id, name} ]` — combined sessions this session belongs to (may be empty)

### Existing session list (the endpoint Sessions.tsx already calls)
Add to each item: `is_combined: bool`, `parts_count: int` (0 when not combined),
`part_of: [ {id, name} ]`.

## Worker job `combine_sessions_job(ctx, combined_session_id)`
- Lives in `backend/workers/` next to `finalize_session_job`; registered in the
  interactive worker `functions` list (see `workers/bulk_import_worker.py`).
- Uses the `processing_job_id` drift-guard pattern from finalize.
- Builds the input text from each part, in `position` order, from
  `transcriptions` ordered by `start_time`, speaker-labelled the same way the
  finalize summarizer formats them, separated by a line:
  `=== Part k of N: <part name> — <started_at YYYY-MM-DD HH:MM UTC> (<mm:ss>) ===`
- Generates summary + insights + action items with the SAME service functions
  `finalize_session_job` uses (map-reduce summarizer, gateway model), and writes
  them to the combined row exactly as finalize does for a normal session, then
  `status='completed'`. On exception: `status='failed'`, error recorded the
  way finalize records it, never silently dropped.
- Does NOT write `transcriptions`, does NOT touch parts, does NOT index the
  combined row into Qdrant (parts are already indexed), does NOT brigade-sync.

## Frontend
- `Sessions.tsx`: BulkActionsToolbar gains **Combine** (enabled when ≥ 2 selected
  and none is combined). Dialog lists the selected parts ordered by
  `started_at`, name input prefilled with the default, Confirm → POST →
  navigate to the new session. Row badge `Combined · N parts`; small
  `Part of <name>` link on members.
- `SessionDetails.tsx`: when `is_combined`: badge, parts list (name, date,
  duration, link), summary/insights/action items as usual, audio player and
  transcript panels replaced by a one-line note ("Combined meeting — open a
  part for audio and transcript"), a **Re-run summary** button (rerun
  endpoint). When `part_of` non-empty: `Part of <name>` link in the header.
- Status `processing` shows the existing processing indicator; poll as the
  page already does for processing sessions.

## Tests
- Backend: combine endpoint (validation, permissions, same-org, no nesting),
  job builds text with separators in position order and writes summary using
  the existing LLM mocking pattern (`test_reprocess_indexing.py`,
  `test_reprocess_lock.py`), delete semantics.
- Frontend: vitest for the Combine dialog default name/order if the page has
  tests; otherwise a smoke render.
