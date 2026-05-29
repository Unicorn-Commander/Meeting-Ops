## [Unreleased]

## [3.18.2] - 2026-05-29

### Security — generative-endpoint tier gating
Continues the v3.18.1 moat restoration. v3.18.1 closed the audio-upload + server-recording paths; v3.18.2 closes the remaining server-LLM-on-content paths called out in the Codex code audit table.

- **`/api/ai-chat/sessions/{id}/messages`** (`backend/api/ai_chat.py:231`): per-session AI chat runs server LLM with meeting transcript as context. Now `gate_feature_for_caller(current_user, "canonical_reprocess")` rejects free users with 403 before any work starts.
- **`/api/ai-chat/rag/query`** (`backend/api/ai_chat.py:496`): cross-meeting RAG calls the server LLM over retrieved transcript chunks. Same gate.
- **`/api/simple/recording-sessions/{id}/insights`** + **`/insights/regenerate`** (`backend/api/ai_insights.py`): the gate sits just before `_generate_ai_insights` so cached reads stay open for any tier (cached insights only exist if a paid run generated them earlier) while new generation is paid-tier.
- **`/api/digests`** (`backend/api/digests.py:222`): the gate sits between the cache-check and `_generate_digest`. Cached digest reads stay open; new digest generation is paid-tier.

### Performance — async event-loop hygiene
- **`backend/api/ai_insights.py`**: 6 `svc.chat_sync(...)` calls inside async helper functions (`_generate_summary`, `_extract_keywords`, `_analyze_speaker_sentiment`, `_analyze_overall_sentiment`, `_extract_action_items`, `_extract_decisions`) were blocking the asyncio event loop for tens of seconds per LLM round-trip. Each is now wrapped in `await asyncio.to_thread(svc.chat_sync, ...)` so the loop stays responsive to other requests while the LLM runs. Test guard ensures every `chat_sync` is paired with a `to_thread` wrap (regression catches a future refactor that re-introduces a bare sync call inside an async handler).

### Tests
- `backend/tests/test_free_tier_enforcement.py` (+5 tests): ai-chat messages 403, ai-chat rag/query 403, insights regenerate 403, digest generation 403 (free + force=true with sessions present), and the chat_sync→to_thread regression guard.
- `backend/tests/test_session_watchdog.py` (+2 tests): double-run idempotency (a second consecutive pass over already-failed sessions marks zero new rows), and `SESSION_WATCHDOG_MAX_PER_PASS` cap behavior.

### Audit context
- Findings from the 2026-05-29 Codex code audit, sections "Tier-Gating Audit" + "Performance Findings" (S1). PO P-00055 task `622e44b8-6f9e-4f5c-aa66-d4701cb9794f` tracks the v3.18.x sequence.

### Deferred to v3.18.3
- Background-jobification of long handlers — `api/recording.py:840` (always-on finalize), `api/digests.py:_generate_digest` (LLM chain), `api/tts.py:214,415` (sync render). These need arq job IDs + status-polling endpoints + frontend integration; bigger refactor than fits cleanly here.
- Full before-snapshot drift checks in `services/agent_write_tools.py` (S2).
- Tier gates for `api/session_emails.py` + `api/batch_export.py` + `api/speakers.py` (defense-in-depth; not S0/S1).


## [3.18.1] - 2026-05-29

### Security — moat restoration
- **`/api/uploads/start` transcribe action now tier-gated** (`backend/api/uploads.py`). Free-tier users could previously POST `action="transcribe"` with the 500MB/month quota and trigger the full server STT/diarization/summary pipeline — a moat violation. Now `gate_feature_for_caller(current_user, "canonical_reprocess")` rejects free users at 403 before any work starts.
- **`/api/simple/recording-sessions/{id}/start` tier-gated** (`backend/api/simple_recording_db.py`). Legacy server-recording start triggered STT/diarization/summary on stop. Free is browser-only.
- **`/api/rooms/{id}/recordings/start` tier-gated** (`backend/api/rooms.py`). RoomRecorder posts chunks via `InternalServiceCaller` (legitimately bypassing the gate once running), so we gate at start to prevent free orgs from kicking off the server pipeline.
- **Satellite `/upload-audio` and `/transcript` endpoints now tier-gated by org plan** (`backend/api/satellite_api.py`). Satellites authenticate by device secret OR user session and resolve to an owning org. Free-plan orgs cannot use satellite capture even with a valid device secret. New `_gate_satellite_for_org` helper reads `Organization.plan` (the actual schema column — `Organization` has no `tier` column).
- **`backend/auth/tier.py`: added `get_org_tier(org)` helper** that reads `Organization.plan`, mirroring `get_user_tier` for org-keyed gates. Defaults to `"free"` when missing/None.
- **`backend/api/websocket_remote_audio.py`: WebSocket org/tier authorization**. Previously any valid JWT could connect to any `session_id` UUID (cross-org audio injection). Now: tier-gates on `canonical_reprocess` before `accept()` (close 4403), org-scopes the session lookup via the user's `UserOrganization` membership set (superusers bypass), and returns 4403 on both cross-org miss and not-found (avoids existence-leak).
- **`backend/api/live_transcription.py`: admin check fix on all 3 endpoints**. Previously called `current_user.get("is_superuser", False)` on a SQLAlchemy `User` object — that's a dict method on an ORM object and raised `AttributeError` → 500 instead of 403. Replaced with `not current_user.is_superuser` on start/stop/configure (all three had the same bug).
- **`backend/services/always_on_recorder.py`: org/user injection on `_start_new_meeting()`**. Previously inserted `RecordingSession` rows without `organization_id` or `user_id` (NOT NULL columns). Added `attach_owner(org_id, user_id)` instance method, owner injection in `_start_new_meeting()`, and an early skip-with-warning when both are still `None` at insert time. State machine untouched. `backend/api/simple_recording_db.py:start_always_on` now calls `attach_owner()` immediately after `start()`.

### Security — unauth admin surface lockdown
- **`backend/api/simple_settings.py`, `ai_settings.py`, `agent_management_api.py`, `unified_agent_api.py`**: added `Depends(get_current_user)` + `is_superuser` checks to mutation endpoints (defense-in-depth — a pre-existing prefix double-mount bug in `main.py` made these routes unreachable from outside the container, so the auth changes will engage when that bug is fixed in a follow-up PR).
- **`backend/api/meeting_intelligence_real.py` removed from `main.py` router includes**. Had sync `requests.post(..., timeout=30)` calls that blocked the asyncio loop, no auth, and duplicated functionality covered by `services/providers/impl_llm.py`. File preserved on disk for history.

### Compose hygiene
- **`deploy/bigboy/docker-compose.bigboy.yml` + `.env.bigboy.example`**: added 26 missing env pass-throughs to both `meet-backend` and `meet-bulk-import-worker` (`GARAGE_AUDIO_BUCKET`, `SESSION_WATCHDOG_*`, `ALWAYS_ON_AUTO_SEGMENT`, `MEDIA_RETENTION_*`, `APP_BASE_URL`, `APP_PUBLIC_URL`, `MEETING_RAG_GRAPH_AUGMENTATION`, `PROJECTOPS_*`, `BRIGADE_*`, `STT_DEFAULT_PROVIDER`, `WHISPER_SERVER_URL`, etc.) — closes the env-file-vs-YAML gotcha that caused silent default-value boots. `.env.bigboy.example` updated to match. Build context paths intentionally unchanged (`../../src/backend` is correct for the bigboy symlink-src deploy layout per the "Cloud deployment (bigboy)" section above).

### Tests
- `backend/tests/test_v3_18_1_authz.py` (new, 6 tests): live_transcription 403-not-500, always_on owned/unowned session creation, ws_remote_audio cross-org + free-tier + unauth rejection.
- `backend/tests/test_free_tier_enforcement.py` (+7 tests): uploads transcribe, simple_recording start, room recording start, satellite-via-`get_org_tier`, plus `meeting_intelligence_real`-not-mounted and unauth admin routers xfail (citing the unreachable-prefix bug).

### Audit context
- All findings sourced from the 2026-05-29 Codex code + UI/UX audits. See `~/Documents/meeting-ops-codex-code-audit.md` for the prompt template, and PO P-00055 task `622e44b8-6f9e-4f5c-aa66-d4701cb9794f` for the full v3.18.1 + v3.18.2 + prod-launch plan.

### Pre-existing follow-ups (NOT in v3.18.1)
- Router prefix double-mount bug (`simple_settings`/`ai_settings`/`agent_management`/`unified_agent`).
- `services/working_audio_service.py` hardcodes `/home/ucadmin` paths.
- Python 3.14 + `audioop` removal blocks `api/streaming.py` import on dev machine.
- v3.18.2: background-jobification of long handlers (`recording.py:840`, `digests.py:107`, `tts.py:214,415`), `ai_insights.py:292` async fix, full before-snapshot drift checks in `agent_write_tools.py`, remaining tier gates for `ai_chat` / `ai_insights` / `digests` / `session_emails`.


## [3.17.0] - 2026-05-28

### Added
- **Project-Ops action-items bridge (ships dark; opt-in per deployment).** When a meeting completes (reprocess or live finalize), Meeting-Ops's existing `action_items` rows are written as Project-Ops tasks on a per-org PO project, modeled on the proven `services/brigade_writer` pattern (best-effort, swallow-all, never blocks the meeting pipeline).
  - `services/projectops_client.py` — httpx Bearer-JWT client to PO NestJS API at `PROJECTOPS_BASE_URL` (default `http://project-ops-backend:3201/api/v1`). Resolves `projectNumber → UUID` by paging `GET /projects` client-side because PO exposes no by-number REST route. `is_live` gate; `create_task` and `update_task_status`; no-op when unconfigured.
  - `services/projectops_writer.write_action_items_to_projectops` — orchestrator with target resolution order: (1) session-level PO link (`session.project_app=project-ops` + `session.project_id` UUID), (2) `session.processing_metadata.po_project_override`, (3) org-level `Organization.settings.projectops_default_project_number`, (4) skip (`mode=no-target`). Idempotent via `raw_payload` stamp on each action_item (`po_task_id`, `po_project_number`, `po_synced_at`); replay never duplicates.
  - Hooks in `api/recording.py` on both reprocess finalize and live finalize. `action_items` PATCH propagates done → COMPLETED via PO `update_task_status` when the row carries `po_task_id`. Every PO call is swallowed.
  - `scripts/backfill_action_items_to_projectops.py` — idempotent reconcile over completed sessions; `--set-default-project ORG=P-XXXXX` helper for the org-level target setting.
  - 8 new tests + the 12 existing Brigade-writer tests still green.

### Activation
- The bridge is **dark** until you mint a Keycloak service-account JWT for a Project-Ops ADMIN/MANAGER identity, set it as `PROJECTOPS_API_KEY` on `meet-backend`, optionally override `PROJECTOPS_BASE_URL`, then set the per-org target with `docker exec meet-backend python3 scripts/backfill_action_items_to_projectops.py --set-default-project <orgid>=P-XXXXX`.

### Future
- Per-org integration toggles (UI for enabling Brigade / Project-Ops / Contact-Ops / Accounting-Ops per org instead of by env-var) tracked as a v1.1 follow-up.


## [3.16.0] - 2026-05-28

### Fixed
- **Graph-augmented retrieval — tuned magnitudes + direct-text dominance rule, closing the v3.11.0 regression.** Live A/B on prod data (4 anchor queries, 80-meeting corpus, 477-node graph): `automatic summarization manual button transcription` no longer demotes the title-matching meeting (the regression case); 3/4 queries reorder usefully with the graph engaged on 4/4. Specific changes in `backend/services/graph_augmented_retrieval.py`:
  - `_MAX_GRAPH_BONUS` reduced 3.0 → 1.5 (now sits below the v3.10.1 `_title_boost` ceiling of 2.5).
  - `_meeting_bonus` per-component values halved: 2.0/1.25/1.0/0.5 → 1.0/0.6/0.5/0.25.
  - New `_title_boost()` mirrors `SemanticSearchService._title_boost` so the rerank composer sees the same direct-text signal as the seed retriever.
  - New `_final_score()` applies a direct-text dominance cap: `title_boost >= 1.0` caps graph_bonus at 0.25; `>= 0.5` caps at 0.5; no direct-text signal lets the full graph bonus through (up to 1.5).
- Three new tests cover the regression (`test_exact_title_outranks_graph_sibling`), the no-direct-text case (`test_graph_signal_still_works_without_direct_text`), and magnitude bounds.
- New `scripts/eval_graph_rag.py`: idempotent A/B harness over the 4 anchor queries; prints a paste-ready comparison table.

### Operational note
- `MEETING_RAG_GRAPH_AUGMENTATION` env var default remains `"0"` (flag off). With the regression fixed and the live eval clean, flipping it to `"1"` on bigboy is now a safe default-on. Per-request `scope.graph_augmented_retrieval=true` continues to override.


## [3.15.1] - 2026-05-28

### Fixed
- Speaker Library layout: the v3.15.0 "Unassigned voice fingerprints" section rendered as a single full-height list outside the page's `overflow-hidden` grid, so a long unassigned list (e.g. 35 rows) pushed the enrolled-speakers two-column grid entirely below the fold with no way to reach it. The section is now **collapsible** (chevron toggle, default open) and its inner list is height-capped (`max-h-96`) with internal vertical scrolling — so however many unassigned fingerprints you have, the enrolled speakers + detail panel below stay in view.

## [3.15.0] - 2026-05-28

### Added
- **Speaker Library — unassigned voice fingerprints + speaker merge.** Closes the gap where diarized clusters (raw `SPEAKER_00` labels) from across meetings couldn't be seen or assigned globally — previously only the per-session inline tagger surfaced them.
  - `GET /api/speakers/unassigned-links` — paginated, org-scoped list of `SpeakerSessionLink` rows where `speaker_id IS NULL`, joined with session context (title, date, duration aggregated from `transcript_diarized` segments, preview text, segment count) and a `top_matches` array (up to 3 enrolled speakers ranked by cosine similarity to the cluster's centroid derived from inline segment embeddings). Verified live: real "Incoherent Transcript Analysis" cluster correctly suggests Aaron Stransky at 0.50 over David (0.18) / Ricky (0.12).
  - `GET /api/speakers/voice-samples/{sample_id}/audio` — proxy for `SpeakerVoiceSample.audio_path` (gated on `STORE_SPEAKER_AUDIO=true`).
  - `POST /api/speakers/{target_id}/merge` — transactional bulk-repoint of `SpeakerVoiceSample` + `SpeakerSessionLink` rows from source to target, recompute target centroid, delete source, audit row (`action="speaker_merge"`, `details={merged_from, source_name, samples_moved, links_moved}`). Refuses `target == source` (400) and cross-org (404). Admin-only. Rollback + 500 on any failure.
  - `services/speaker_service.cosine_similarity` (shared helper).
- **Frontend** (`SpeakerLibrary.tsx`): "Unassigned voice fingerprints" section with count badge, per-row session metadata, suggested-match chips (one-shot assign), and an "Assign…" dialog with searchable speakers dropdown + "Create new speaker + assign" path. Reuses the existing `PATCH /api/sessions/{id}/speaker-links/{link_id}` endpoint. "Merge into another speaker…" action on speaker detail with a rose-accent destructive modal that requires typing the source speaker's display name before Confirm enables.

### Verified
- Full backend suite green; new `tests/test_speakers_unassigned_and_merge.py` (20 pass); frontend vitest (105 pass / 20 files); `npm run build` clean. **Live on bigboy**: routes registered; org-1 baseline is 35 unassigned voice fingerprints across 44 total links, 4 enrolled speakers — Aaron can now see and assign all 35 from the Speaker Library page.

### Architecture note
- This is a direct admin tool, not an agent action — does NOT route through `services/agent_actions.py` propose → confirm → mutate. Per-session inline tagger and the global Library now both reach the same backend mutation surface (`PATCH /api/sessions/{id}/speaker-links/{link_id}`).

## [3.14.1] - 2026-05-28

### Added
- **Typed-confirmation input on the in-app proposal card.** Closes the v3.14.0 gap where `delete_session` (and any future high-friction action) couldn't be confirmed through the RAG chat UI — the card now renders an input field, surfaces the `confirmation_instructions` text, switches to a red/destructive visual treatment (alert icon, rose accent, "Destructive action proposal", "Confirm permanent deletion" button label), and keeps the Confirm button disabled until the user's input matches `required_typed_confirmation` exactly (trimmed). The standard non-destructive card path is unchanged. Test coverage in `__tests__/AgentActionProposalCard.test.tsx`.
- Type system updated: `AgentActionName` now includes `delete_session` / `start_recording` / `stop_recording`; `AgentActionProposal` carries optional `required_typed_confirmation` + `confirmation_instructions`. `confirmAgentAction` accepts an optional `typedConfirmation` arg and only sends `typed_confirmation` in the request body when non-empty (clean wire shape for the common path).

### Verified
- Frontend build (vite + tsc strict) passes. Deployed bundle contains the new behavior strings ("Destructive action proposal", "Confirm permanent deletion", "typed-confirmation", "Confirm stays disabled until").

## [3.14.0] - 2026-05-28

### Added
- **Three new agent write actions, on the v3.12.0 propose → confirm machinery:**
  - **`delete_session`** with high-friction typed-confirmation. The proposal envelope now includes `required_typed_confirmation` (= `"delete-{id}"`) and human-readable `confirmation_instructions`; the user (or chat UI / MCP client) must echo the exact string in `typed_confirmation` on the confirm call, or it 409s. Propose itself refuses while the session is currently recording. Applier cascades: local audio file unlink + `session_media.purge_session_media` (Garage prefix delete) + transcript rows + session row.
  - **`start_recording`** — wraps `WorkingAudioService.start_recording`. Refuses to propose if the session is already recording / completed / processing; applier revalidates status hasn't drifted before invoking the audio service.
  - **`stop_recording`** — wraps `WorkingAudioService.stop_recording`; refuses unless current status is `recording`; sets `status=processing`, `ended_at`, `duration` on apply.
- `typed_confirmation` plumbed through `confirm_action` and `AgentActionConfirmRequest` (only consulted for actions whose builder set `required_typed_confirmation`; ignored otherwise). `_proposal_response` now forwards the optional friction fields (`required_typed_confirmation`, `confirmation_instructions`) so the chat UI / MCP envelope sees them.
- `tests/test_agent_write_tools_v16.py` — 9 cases: typed-confirm positive + missing + wrong-value + recording-blocked; start/stop happy path + status-blocked; reuses the `_set_fake_redis`/`_seed_user_org`/`_seed_session` helpers.

### Verified
- Full backend suite green. **Live on bigboy**: created a throwaway session, propose returned `required_typed_confirmation="delete-126"`, confirm without typed → 409 + session preserved, confirm with wrong typed → 409, confirm with correct typed → applied and session **gone**.

### Note for the Stable voice arc (parallel investigation)
- The home-ops voice + barge-in stack lives at `/Volumes/Studio Storage/Development/smart-home-agent/Home-Ops/voice/` (voice-router + wake-word service) — the reference pattern to lift into Stable when the Stable voice work picks up.

## [3.13.0] - 2026-05-28

### Added
- **Phase 2 v1.5 — Personal Access Tokens (PATs) + MCP write surface.** The agent can now propose, confirm, and cancel write actions over MCP **as the real user**, not as a shared admin. The shared `MEETING_OPS_USER`/`MEETING_OPS_PASS` login path in the MCP server is deleted entirely (no fallback). Per-user identity at the boundary, RBAC enforced by the existing backend auth.
  - `personal_access_tokens` table (alembic `032`): `mops_pat_` + 32 base32 chars (~160-bit entropy), sha256-hashed at rest, `token_prefix` for UI recognition, `last_used_at`/`revoked_at` for hygiene. Per-user FK with `ON DELETE CASCADE`.
  - `backend/auth/pat.py`: `create_pat` (returns plaintext **once**), `resolve_pat` (looks up via hash, updates `last_used_at`, refuses revoked), `revoke_pat`.
  - `backend/auth/dependencies.py`: the auth dependency now dispatches `Authorization: Bearer mops_pat_...` to `resolve_pat()` **before** JWT decode; JWT/SSO paths are unchanged (zero regression on the web app).
  - `backend/api/personal_access_tokens.py`: `POST /api/auth/pats` (plaintext shown once), `GET /api/auth/pats` (never returns plaintext or hash), `DELETE /api/auth/pats/{id}` (revoke).
  - `mcp/meeting_ops_mcp.py`: reads `MEETING_OPS_PAT` env var and sends as Bearer on every backend call. Adds the v3.12.0 `propose_*` tools (+ `confirm_action` / `cancel_action`) as MCP tools — thin proxies, no MCP-side auth logic.
  - Frontend: Settings → **Personal Access Tokens** (`PersonalAccessTokens.tsx`) — list + create + revoke, copy-once modal for the plaintext.

### Verified
- 42 backend tests for PATs + MCP round-trip + agent-actions + tier enforcement; 99 frontend tests; frontend build passes. **Live on bigboy**: minted a real PAT, resolved to the correct user, proposed `rename_session` via the PAT, confirmed → audit rows carry the **real user_id** (not a shared admin), revoked PAT rejected.

### Architecture note
- Built **without** the UC Commander federation layer; PATs are simpler, ship now, and are forward-compatible with federation later (UC could mint PATs on the user's behalf in a future phase). One MCP server codebase, per-user identity per request via PATs.

## [3.12.0] - 2026-05-28

### Added
- **Phase 2 v1 — safe agent write/control via propose → confirm → mutate (in-app).** The agent can now propose mutating actions; the user explicitly confirms; only then does the backend mutate, atomically, with state re-validated against drift. Every mutating action is auditable. The MCP write surface is deferred to v1.5 once per-user MCP identity is wired — v1 ships through the in-app chat where per-user JWT/SSO identity is already solved (Codex's point that a fixed shared MCP login can't enforce per-user scoping).
  - `backend/services/agent_actions.py`: Redis-backed one-shot tokens (`GETDEL`, TTL 300s) bound to `(user_id, org_id, action, payload_hash, expires_at, proposal_id)`. Scope re-validated on confirm AND cancel. Payload tamper detection via sha256.
  - `backend/services/agent_write_tools.py`: 6 actions (`propose_create_session`, `propose_rename_session`, `propose_add_tag`, `propose_remove_tag`, `propose_trigger_reprocess`, `propose_draft_followup_email`). Each confirm path re-fetches the target row, checks owner/org, and verifies the `before` snapshot still matches before applying — refuses with **409 "state changed, please re-propose"** on drift.
  - `backend/api/agent_actions.py`: `POST /api/agent-actions/{propose,confirm,cancel}` — 400 unknown action / 403 tier/ownership/org / 404 missing-or-replayed token / 409 payload-tamper or state-drift / 410 expired token or invalid precondition.
  - `auth/tier.py`: new tier flags `agent_write_basic` (free+), `agent_write_reprocess` (pro+), `agent_write_email_draft` (pro+). `test_free_tier_enforcement.py` tightened — free tier must deny the two pro+ flags.
  - Audit lifecycle reuses `auth_models.audit_logs` with actions `agent_action_proposed` / `agent_action_confirmed` / `agent_action_cancelled`, tied by `resource_id = proposal_id`. Full `before` / `after` / `diff` / `payload_hash` / `result` recorded in `details` JSONB.
  - Frontend: `RAGChat.tsx` renders the new `AgentActionProposalCard` (preview + diff + Confirm/Cancel) when the agent stream returns `needs_confirmation`. Cribbed from the Crisis Ops `IntakePlanReview` pattern.
  - Graph-augmented retrieval (v3.11.0) path preserved alongside the new write surface.
  - `scripts/verify_agent_actions.py`: ratified safety contract as runnable script (post-deploy sanity check).

### Verified
- 36 backend tests for the agent-action surface pass (round-trip per tool + expired/replayed/cross-org/tier/payload-tamper/state-drift negatives) plus 7 frontend tests + the existing full backend suite. **Live end-to-end on bigboy**: real `propose → confirm` on session 122 mutated the row; both `agent_action_proposed` and `agent_action_confirmed` audit rows landed tied by `proposal_id`; **replay correctly rejected** (one-shot GETDEL).

### Not in v1 (deliberately)
- MCP write tools (deferred to v1.5 — needs per-user MCP identity).
- `delete_session`, `send_email`, `start_recording`, `stop_recording` (each has its own friction/safety model worth designing separately).

## [3.11.0] - 2026-05-27

### Added
- **Graph-augmented retrieval (read-only, feature-flagged OFF).** A new layer on top of the existing meeting-rag loop in `backend/services/graph_augmented_retrieval.py`: Qdrant seed → entity extraction → Brigade FalkorDB neighborhood expansion (via the existing read-only `BrigadeClient.fetch_entity_context`) → re-rank with a capped graph bonus (`_MAX_GRAPH_BONUS = 3.0`) → graph evidence block injected into the `ask_about_meetings` LLM prompt. Wired into `search_meetings_impl` and `ask_about_meetings_impl` only.
- Feature flag: env `MEETING_RAG_GRAPH_AUGMENTATION` (default `0` / off) for the global default; per-request `scope.graph_augmented_retrieval` (or `.graph_augment`) wins over env so the same backend can A/B both modes per call. Safe to deploy off; flip on per-request to evaluate.
- Brigade graph backfilled over all 80 completed sessions (`agent_meeting_ops_canonical` went from ~4 smoke-test nodes to 477) so the corpus the new layer expands into is real, not synthetic.
- `scripts/backfill_brigade_graph.py` (idempotent reconcile via `write_meeting_to_brigade`).

### Verified
- 61 backend tests pass (`test_graph_augmented_retrieval` + `test_cross_org_isolation` + `test_semantic_search_service_retrieval` + `test_search_analytics`); cross-org isolation preserved (the graph bonus is applied after the org-filtered Qdrant query). Live A/B on a real cross-meeting query confirms `type=semantic` → `type=graph_augmented` with bounded score boosts and no regression in the OFF path.

## [3.10.1] - 2026-05-27

### Fixed
- **Cross-meeting retrieval (RAG) was broken** — completed meetings were missing from the Qdrant corpus (stale index: org 1 had 81 sessions but only ~178 points), so `ask_about_meetings` / cross-meeting search couldn't surface the right meeting even by exact title. Root cause was corpus coverage, not org filtering (which was correct). Fixes in `semantic_search_service.py`: reindexed the corpus (org 1 → 81 sessions / 398 points); prefix embedded chunk/summary/title texts with the meeting title so titles contribute to the dense + sparse vectors; title-aware additive score boost so exact/near-exact title matches rank deterministically (applied *after* the org-filtered query — org isolation unaffected); `reindex_all` falls back to `final_summary` (structured/legacy shapes) when `summary` is empty. Verified: session 122 now ranks #1 for both exact-title and topical queries. Single-meeting chat was already correct. (Foundation for the agent-platform arc — see `docs/agent-platform-roadmap.md`.)

## [3.10.0] - 2026-05-27

### Added
- **Self-managing local-disk retention (completes the Garage cutover).** A new `services/media_retention.py` plus a daily Arq cron (`media_retention_task`, 04:30 UTC, on the existing `meet-bulk-import-worker`) keeps local disk in check without manual script runs:
  - `evict_completed_local` — deletes the local working file of completed sessions older than `MEDIA_RETENTION_KEEP_DAYS` (default 7), but only when a byte-size-verified Garage copy exists (verified via list, not HEAD). Reversible — audio re-materializes from Garage on next read.
  - `cap_media_cache` — LRU-evicts the re-materialization cache (`MEDIA_CACHE_ROOT`) down to `MEDIA_CACHE_MAX_GB` (default 20); cache entries are re-fetchable from Garage.
  - Safe by construction: never deletes a Garage object, never deletes a local file without a verified durable copy. Env: `MEDIA_RETENTION_ENABLED` / `MEDIA_RETENTION_KEEP_DAYS` / `MEDIA_RETENTION_STATUSES` / `MEDIA_CACHE_MAX_GB`.
- `media_storage.object_size()` — list-based Garage object-size lookup (HEAD-free) used by retention/eviction to verify durable copies.

### Docs
- `docs/agent-platform-roadmap.md`: recorded the Phase 1 audit results + ratified decisions (use Brigade FalkorDB, strict propose→confirm→mutate writes, graph-augmented read-only retrieval) and the re-sequenced near-term order (fix base retrieval + backfill the graph before graph-augmented retrieval). Corrected the stale "vector-only" note (retrieval is hybrid dense + BM25).

## [3.9.1] - 2026-05-27

### Added
- **Help page: a practical "Using Meeting-Ops" guide** above the existing "How it works" architecture tour. Covers recording (Just me / Me + system audio), Sessions & Folders (tags-as-folders, multi-folder membership), Conference rooms & the multi-mic picker, reading a meeting (transcript / summary / Ask-about-this-meeting chat / export), where recordings are stored (self-hosted object storage, delete-means-delete, free-tier stays in-browser), and a Free/Pro/Enterprise plans-at-a-glance.
- `docs/audio-storage-garage.md`: operator + developer guide for the Garage audio storage (modules, columns, read/write/delete flow, backfill + eviction scripts, bucket provisioning, the HEAD-400 gotcha). Linked from the docs index.

### Changed
- README refreshed: latest tag, implementation status (through v3.9.0), tier model (free-tier live + signup status), and a new "Audio storage & data durability" section.



### Changed
- **Garage cutover — Garage is now the authoritative home for canonical meeting audio.** Local disk becomes a transient working cache that can be evicted once a durable Garage copy is verified. To make this safe, the last audio read path that wasn't Garage-aware — `identify_speakers`' embedding re-extraction fallback (`speaker_service.py`) — now resolves via `session_media.resolve_local_path` (local-first, else pull from Garage). The common inline-embeddings path is untouched (it never reads the wav).
- `scripts/evict_local_audio.py`: the cutover tool. Deletes a session's local audio **only after** confirming the Garage object exists with a byte-size match (verified via list, not HEAD). Idempotent, reversible (bytes stay in Garage; reads re-materialize on demand), and never touches a session without a verified durable copy. Run on bigboy to reclaim local disk for completed sessions.

### Notes
- The write/processing pipeline still writes local first (ffmpeg/STT/diarize need a file on disk), then pushes to Garage — so the bind-mount stays `:rw`; "cutover" means Garage-authoritative + local-evictable, not local-free.
- Re-materialized audio lands in the local media-cache; an LRU cache-eviction policy is a follow-up (fine at current volume).

## [3.8.0] - 2026-05-27

### Added
- **Per-room microphone picker (multi-mic).** A Conference Room can now select one *or several* server-attached mics in one flow, each with a friendly per-source label (e.g. "Podium", "Audience"), with a per-device "Test mic" RMS/peak probe before adding. The room's current sources render in the Settings tab with a status badge (idle/recording/error/disabled) and a remove action. Frontend-only; reuses the existing `/api/rooms/{id}/sources` + `/api/system/audio-devices` endpoints. (merge of `rooms-mic-picker`)
- **Sessions folders (tags-as-folders).** A new Folders grouping mode on the Sessions page: the rail lists each tag as a folder with a session count (plus "All sessions" / "Ungrouped"), clicking filters to that tag, and bulk-select lets you add/remove sessions to a folder. A session can live in multiple folders because folders are just tags (deliberate — a meeting can belong to several). Available on mobile too. The flat list + search + filters remain. (merge of `sessions-folders`)

### Changed
- `GET /api/simple/recording-sessions/tags` now also returns `tag_counts`, `total_sessions`, and `untagged_sessions` (additive — new fields with defaults) so the folder rail renders counts without extra queries.

## [3.7.0] - 2026-05-27

### Added
- **Canonical meeting audio now lives in Garage object storage.** The main meeting audio (the irreplaceable asset) was on a single host's local disk; it now also has a durable copy in the `meeting-ops-audio` Garage bucket, mirroring how session attachments already work. New nullable columns on `recording_sessions` (alembic `031`): `audio_storage_backend` (`garage`|`local`|NULL) and `audio_object_key` (`{org}/{session_id}/audio/{name}`).
  - `services/media_storage.py`: Garage S3 client for the audio bucket — `put_path`/`put_stream`/`open_object`/`iter_object`/`cached_local_path`/`delete_object`/`delete_prefix`, with a local-first spool fallback and a `MEDIA_STORAGE_DISABLED` escape hatch (tests force-local).
  - `services/session_media.py`: `persist_session_audio` (best-effort push + record columns), `resolve_local_path` (local-first, else pull from Garage into cache), `purge_session_media` (delete the whole session prefix).
  - **Writes**: durable copy pushed on always-on finalize, both upload paths, and bulk-import. All best-effort and additive — the local file stays the working copy / source-of-truth; a Garage hiccup just leaves the columns NULL to retry.
  - **Reads**: `download/audio` resolves local-first, else proxy-streams the bytes from Garage (range-capable `FileResponse`; Garage is never exposed to the browser).
  - **Delete**: deleting a session now purges its Garage objects too — so "delete my data" is actually honored (GDPR/CCPA).
  - **Backfill**: `scripts/backfill_audio_to_garage.py` (idempotent, additive) seeded the existing recordings into Garage (15 sessions / ~993 MB on bigboy).
  - Free-tier audio is unaffected (browser-only; never reaches the server, never uploaded).

### Changed
- **Bulk-import Garage upload consolidated** onto `services.session_media`. The previous bespoke `_upload_to_garage` used a job-scoped key (`{org}/{job_id}/{file_id}`) and had been silently failing because the `meeting-ops-audio` bucket never existed; it's replaced by the single canonical session-scoped path so the download fallback + delete-cascade find bulk-imported audio too.

### Fixed
- **Garage `HEAD` returns 400** with this botocore (same family as the `@aws-sdk` checksum/HEAD gotchas). `cached_local_path` now streams via `get_object` instead of `download_file` (which issues a `head_object` first) — fixing the evicted-cache / disaster-recovery read path — and `ensure_bucket` no longer probes with `head_bucket`.

### Ops
- Provisioned the `meeting-ops-audio` Garage bucket and granted the `meetingops` data key read/write/owner (it couldn't self-create buckets — the root cause of the prior silent failures).

### Not yet (gated / follow-ups)
- Local stays the source-of-truth; **no cutover** to Garage-primary or local eviction yet (that's the next, separately-confirmed step). Retention/lifecycle policy per tier, encryption-at-rest (HIPAA path), and TTS-output durability are deferred follow-ups.

## [3.6.1] - 2026-05-27

### Removed
- The "Voice Activity Detection (removes silence)" toggle + threshold from Settings -> Audio. It persisted a preference (`enableVAD`/`vadThreshold`) that **no recording path ever read** — the always-on VAD engine ignores it, and the parallel full-session recorder captures everything continuously regardless of VAD. So the toggle was misleading. A true no-VAD live-transcription mode would be a separate feature (a time-based chunker), not this toggle.

## [3.6.0] - 2026-05-27

### Changed
- **Live Recording page: one summary surface.** Removed the legacy page-level "Meeting Summary (Live AI Updates)", "Key Points", and optional "Live Transcript" panels (driven by the old `/ws/transcription-auto` `autoSummary`/`summaryFormats` path) that duplicated the recorder's own rolling Live summary and got pushed to the bottom of the page. `AlwaysOnControl`'s Live summary is the single live-summary surface now; the structured summary + key points + action items remain in Session Details (post-meeting), and the gated `ServerLiveTranscript` (Pro server-live) stays. (The now-dead legacy summary state + `/ws/transcription-auto` handlers are left as harmless no-ops; `noUnusedLocals` is off so they do not break the build — deeper removal is a follow-up.)

## [3.5.1] - 2026-05-27

### Fixed
- Public pages now reachable at real paths. The app is a HashRouter SPA, so only `/#/pricing` (etc.) rendered; landing on `/pricing` with no hash fell back to `/` -> /dashboard. Added an `index.html` bootstrap that rewrites `/pricing`, `/signup`, `/login` to their hash form before the router mounts, so those URLs are typeable and shareable. (Anonymous access still needs the oauth2-proxy skip-routes per docs/consumer-signup.md.)

## [3.5.0] - 2026-05-27

### Added
- **Consumer signup / login / pricing frontend.** Public `/signup` (email + username + password -> `POST /api/auth/register`, then a "check your email to verify" state), `/login` (email-or-username + password via `AuthContext.login`, the existing enterprise SSO button kept, and verification banners for `?verify=success|invalid` with a resend flow), and `/pricing` (Free / Pro / Enterprise comparison; Pro at a placeholder $16/mo, Enterprise contact-sales). The free-tier upgrade prompt now links to `/pricing`. Routes are public (outside ProtectedRoute); the rest of the app stays auth-gated. Backend was already built (v3.2.0); this is frontend-only and reuses AuthContext for token storage.

### Notes
- Inert for current enterprise users (authed via SSO; /login keeps the SSO button). **Anonymous access to /signup + /login still requires the oauth2-proxy skip-route change + `ALLOW_REGISTRATION=true`** (see `docs/consumer-signup.md`) — that ops activation is the remaining gate before strangers can sign up. /pricing is reachable now for authed users.

## [3.4.1] - 2026-05-27

### Fixed
- Browser tab favicon now uses the branded `icon-192.png` instead of the default Vite logo (`index.html`). Interim until the real logo lands; the PWA/apple-touch icons were already branded.

## [3.4.0] - 2026-05-27

### Changed
- **Record page: one live transcript + a collapsible pipeline panel.** Removed the legacy page-level "Live Transcription" panel — it mirrored the old `/ws/transcription-auto` feed and duplicated the recorder's own live transcript (the code even noted "the user sees BOTH transcripts"). The live transcript now comes only from the active recorder (`AlwaysOnControl`), plus the gated `ServerLiveTranscript` pane for Pro server-live. Collapsed the "Agent & Pipeline Status" panel (per-session STT / diarizer / summarizer / server-vs-browser pickers) behind a default-collapsed "Advanced" toggle, since those are power-user controls most users never touch. Session Info and Quick Actions panels are unchanged.

## [3.3.0] - 2026-05-27

### Changed
- **Record page: one recorder, two capture options.** Removed the redundant "Record from this browser" card (`DesktopBrowserRecorder`) — it duplicated the always-on recorder but uploaded straight to the server to transcribe, bypassing the browser-first / privacy path and the free-tier gate (an un-gated upload hole, now closed). `AlwaysOnControl` is the single recording surface. Collapsed the meeting-type selector from three (In-person / Online / Mixed) to two: **Just me** (microphone only) and **Me + system audio** (mic + screen / window / browser-tab). Dropped the now-redundant sub-toggles; the raw Mic / Tab / Mic+Tab modes remain in the Advanced expander for power users.

## [3.2.0] - 2026-05-27

### Added
- **Consumer self-serve signup backend (Option B), code-complete but INERT until activated.** Email/password signup for the free tier, coexisting with Keycloak enterprise SSO (the backend already dual-trusts Keycloak headers + its own JWT).
  - `AuthService.create_user(personal_org=True)` provisions a PRIVATE per-user org (`{username}-personal`, user = admin) so consumers never share a workspace; new users are `tier="free"` + `is_verified=False`.
  - Self-serve `POST /api/auth/register` uses the personal-org path and sends a verification email (best-effort — a mail failure never fails signup).
  - `GET /api/auth/verify-email?token=…` (flips `is_verified`, redirects to the app) + `POST /api/auth/resend-verification` (generic 200, no account enumeration).
  - `auth/email.py` — transactional email via `auth_config` SMTP; logs the link + returns False when SMTP is unconfigured (never 500s a signup). Email-verification tokens are type-isolated from password-reset tokens.
  - Reuses the existing account lockout (`authenticate_user`) and free-tier default; not rebuilt.
- Tests: `tests/test_consumer_signup.py` (11) — token helpers + type isolation, `create_user(personal_org)` (private org / free / unverified) + legacy default-org path + duplicate rejection, the register glue (personal org + verification email), and the verify-email / resend endpoints.

### Notes
- **Inert until activated**: with `ALLOW_REGISTRATION=false` (default) `/register` still requires an admin and the new endpoints sit behind oauth2-proxy. Deploying changes nothing for current users. Activation (real `SECRET_KEY`, `ALLOW_REGISTRATION=true`, SMTP, oauth2-proxy skip-routes, Traefik rate-limiting) + the frontend `/signup`+`/login`+`/pricing` pages are documented in `docs/consumer-signup.md` and gated on an explicit launch decision.

## [3.1.0] - 2026-05-27

### Added
- **Free-tier wiring: free users now record on-device by default.** The Record / always-on flow (`AlwaysOnContext`) forces local-only mode for users without the `canonical_reprocess` capability (free tier), so a free user records entirely in the browser (on-device STT + LLM + IndexedDB) with zero server-processing calls instead of hitting 403s mid-recording. A free user on a non-WebGPU browser is cleanly blocked with a "use Chrome/Edge" message rather than falling through to server calls. Every server-processing call (chunks / text / finalize / finalize-audio / resume) is guarded by a capability check plus a 403 backstop that surfaces a dismissible upgrade prompt (links to `/pricing` and Local Sessions). The Local Sessions page is now always reachable from the nav.

### Changed
- Privacy Mode + no-WebGPU now blocks recording with a clear message instead of silently falling back to server recording. Previously a paid user with Privacy Mode ON but no WebGPU would record server-side anyway, contrary to their stated privacy intent.

### Notes
- Inert for current enterprise/superuser users — the free-path code only triggers when `canonical_reprocess` is absent. Frontend-only. tsc build clean; 93 frontend vitest tests pass. Two stale frontend tests (config api-subdomain expectation, Sessions fixture) were corrected. The `/pricing` link is a placeholder pending the pricing page. On-device transcript-quality validation (a real browser-only recording) is still a pre-launch gate.

## [3.0.0] - 2026-05-27

### Added
- **Free-tier enforcement: free tier is browser-only, server processing is paid-tier.** Four new `TIER_FEATURES` capabilities (free=False, pro/enterprise=True), mirrored in the frontend `TierFeatures` type + `DEFAULT_TIER_FEATURES`:
  - `canonical_reprocess` — the server audio-ingest + reprocess pipeline.
  - `brigade_integration` — Brigade graph writes (distinct from the enterprise-only `brigade_byok`).
  - `cross_device_sync` — server-backed cross-device sync (capability flag).
  - `bulk_import` — the server batch `/import` pipeline.
- Two gate primitives in `auth/tier.py`: `require_feature(feature)` (FastAPI dependency, 403s users lacking the capability; validates the feature name at boot) and `gate_feature_for_caller(caller, feature)` (inline gate for `get_internal_or_user` endpoints — internal-service callers bypass, real users are 403'd; duck-types on the `tier` attribute so it's robust to the test suite's `auth.models` reload).

### Changed
- **Server-processing endpoints now require a paid tier.** Gated (free → 403): `/sessions/{id}/chunks`, `/sessions/{id}/chunks-text`, `/sessions/{id}/audio-chunks`, `/sessions/{id}/full-audio`, `/sessions/{id}/finalize-audio`, `/sessions/{id}/finalize` (all `canonical_reprocess`); `/summarize` + `/summarize-slice` (`qwen36_summary`); `/import/jobs` + `/import/jobs/{id}/files` (`bulk_import`). The streaming WS `/ws/sessions/{id}/live` was already gated on `server_live` (Phase B.4). Session CRUD and browser-side capture stay open — free tier records locally (on-device STT + LLM + IndexedDB, i.e. Privacy Mode) and never touches the server. Brigade writes + the reprocess pipeline are downstream of the gated finalize/chunks entry points, so free users never reach them.
- **Wire contract widens (the reason for the major bump):** free-tier users now receive explicit `403` on tier-locked endpoints. Internal-service loopback callers (room_recorder) are unaffected — they bypass tier gating.

### Tests
- New `test_free_tier_enforcement.py` (13): the two gate primitives (free 403 / pro+ pass / superuser pass / internal-caller bypass / unknown-feature ValueError) plus integration tests hitting real gated endpoints free-vs-pro. `test_tier.py` key-consistency updated for the 4 new capabilities. Affected functional tests (audio-chunks, bulk-import, chunks-text, cross-org, internal-auth) updated to seed paid-tier users. Full suite minus the bulk-import *worker* test files: 0 failed; the 3 bulk-import files pass in isolation (7 + 7 + 15). Known test-infra issue (pre-existing, orthogonal to enforcement): the bulk-import worker tests share async event-loop/queue state and hang when run after other files in a single process — tracked as a separate follow-up.

## [2.3.0] - 2026-05-27

### Changed
- **PWA updates no longer apply mid-recording.** The service worker moved from `registerType: "autoUpdate"` + workbox `skipWaiting: true` to `"prompt"` + `skipWaiting: false`, so a freshly-deployed SW parks in the *waiting* state and only activates when the user clicks "Reload now" (which sends `SKIP_WAITING` via `updateSW(true)`). The `PWAUpdate` banner is now suppressed while a recording is in progress — live (`RecordingContext.isRecording`) OR always-on capture (`AlwaysOnContext.state` in starting/recording/paused/stopping) — and reappears the moment recording stops with tailored copy ("we held an update while you were recording"). When no recording is active it behaves as before: prompt as soon as the update is detected. Removes the footgun where a deploy could swap cached chunks out from under an active recording.

## [2.2.0] - 2026-05-27

### Added
- **Opt-in Sortformer canonical-hybrid diarization for `/finalize-audio`** (default OFF). A new path where NVIDIA Sortformer draws the speaker boundaries and wespeaker (still via `meet-speaker-svc`) supplies the per-turn voice embeddings used by `identify_speakers`. Selected per-org (`OrgProviderSettings.provider_name = "sortformer-hybrid"`) or globally via `SPEAKER_PROVIDER_PREFERENCE=sortformer-hybrid`. **Default stays `pyannote` — production is unchanged.**
  - `meet-sortformer-svc`: new `POST /diarize-file-upload` — multipart WAV upload (works cross-host; the backend on bigboy and the svc on midboy2 don't share a filesystem), runs Sortformer segmentation, then asks `meet-speaker-svc` for a per-turn wespeaker embedding over the midboy2-local network, and returns the **same response shape** `meet-speaker-svc /diarize` returns (`segments[{start,end,speaker,embedding}]`, `num_speakers`, `backend`, `duration_seconds`). Turns under 0.5 s skip embedding; an unreachable speaker-svc degrades to labels-only and never raises.
  - Backend `SortformerSpeakerSvcProvider`: a drop-in for `LocalSpeakerSvcProvider.diarize`; `embed`/`identify`/`health` delegate to a wrapped wespeaker provider (wespeaker stays canonical for speaker identity — only the segmentation changes). `registry.get_diarization` gates on the preference, per-org override winning over the env default.
  - Tests: 9 backend (registry selection, response parsing, delegation, graceful failures) + 6 sortformer-svc (endpoint shape, `SPEAKER_NN` label mapping, embed crop/skip, unreachable-svc degradation).

### Known limitations
- **The hybrid is NOT viable as the canonical diarizer for real-length meetings yet, and is shipped opt-in/parked.** Sortformer v1 is trained on ~90 s sessions and its one-shot `diarize()` allocates memory roughly quadratically in audio length: a 38-minute meeting needs ~25 GiB and OOMs the 12 GB RTX 3060 (a 24 GB card would not fit it either). It works fine on short clips (validated: synthetic 2-speaker fixture → 2 speakers + 256-d embeddings end-to-end). For comparison, the canonical pyannote path diarized the same 38-min meeting in ~76 s (2 speakers, 694 segments, 577 embedded turns).
- Making it canonical requires either (a) chunked diarization with cross-chunk speaker stitching via the wespeaker embeddings, or (b) Sortformer v1's `forward_streaming_step()` + speaker-cache API (the spike report's promotion path), or (c) NeMo >= 2.5 streaming-v2 models. Deferred by decision 2026-05-27 — pyannote remains canonical; the hybrid stays as opt-in short-audio infrastructure.
- When the hybrid is selected and the diarize call fails (e.g. OOM on a long meeting), `diarize()` returns `[]` and the reprocess pipeline keeps the live transcript with no speaker overlay. There is intentionally no automatic pyannote fallback in this release — keep the flag off for long-meeting orgs.

## [2.1.0] - 2026-05-26

### Added
- **Per-word streaming UI in `ServerLiveTranscript`**: v2.0.0 wired the backend to consume `/transcribe-stream-v2` and surfaced `tokens_finalized` / `tokens_draft` / `eou_detected` on each WS frame, but the frontend kept the old "one transcript entry per 2.5s flush" cadence. v2.1.0 adds an utterance-grouped accumulator (`Utterance[]`) that appends newly-finalized tokens to the trailing utterance as they arrive — closer to how a real-time captioner displays. Each utterance is a paragraph block: speaker badges + per-word render (one `<span>` per token with `title` showing the timestamp + confidence) + faint italic draft suffix on the active utterance + gray EOU chip when the model sealed end-of-utterance. New utterance opens on the next frame after EOU. Capped at 50 utterances in the DOM to keep long sessions responsive; older utterances drop off the top of the rolling pane.
- **Activation is automatic**: as soon as ANY partial frame carries `tokens_finalized` (i.e. STREAMING_USE_V2_PARAKEET=1 and the v2 endpoint is producing per-word stream), the new utterance view replaces the legacy per-frame view. Legacy clients hitting backends without v2 endpoint keep their old rendering (the transcript[] array still populates as a fallback) — no break in either direction.
- New `Utterance` interface + `UtteranceView` component co-located with `ServerLiveTranscript`. Per-word `<span>` carries `title={t.start.toFixed(2)}s-{t.end.toFixed(2)}s conf={t.confidence.toFixed(2)}` so users can mouse-over any word and see its timing without cluttering the visible UI.
- The active utterance shows the in-flight `text_draft` faint italic at the trailing edge so users see the leading edge of what the model is *thinking* before it commits — this is the per-word streaming UX Phase B.3 chunk C originally envisioned.

### Notes
- The latest speakers-array from each frame "wins" for the currently-active utterance. Past sealed utterances keep their speakers from when they were sealed, so historical attribution is stable. If sortformer re-segments mid-utterance (e.g. detects a second speaker entering), the active utterance's badges update; on EOU + next utterance the prior speakers stick.
- DOM diffing is small per frame because most rendered word spans don't change frame-to-frame — only the trailing draft + the new finalized words update. React's reconciliation handles this efficiently for the 50-utterance cap.
- The legacy per-frame transcript view (each partial = its own entry) stays as a fallback for v1-endpoint sessions and is the rendering path before any tokens arrive (e.g. while WS is connecting). When the first tokens-bearing frame arrives, the view automatically switches.

## [2.0.0] - 2026-05-26

### Added
- **True cache-aware streaming WS path is now the production default**: backend `_flush_to_stt` now POSTs to `services/parakeet-stream-svc/main.py`'s `/transcribe-stream-v2` endpoint (built by Agent C in v1.2.0 as a stepping stone) instead of `/transcribe-stream`. Combined with the v1.5.0 model swap to `parakeet_realtime_eou_120m-v1`, this is the realization of Phase B.3 chunk C's original vision — Agent C's spike found the v3 checkpoint blocked cache-aware streaming, so they built the v2 endpoint as a stepping stone; v1.5.0 swapped to a checkpoint that actually supports it; v2.0.0 wires the endpoint up live. Gated by `STREAMING_USE_V2_PARAKEET=1` in `.env.bigboy` + the explicit forward in the backend service env block of `docker-compose.bigboy.yml`. Rollback is a single env flip back to 0 + backend restart.
- **Partial/final JSON frames now carry per-word `tokens_finalized` array**: each WS frame from the live endpoint includes `tokens_finalized: [{word, start, end, confidence}, ...]` (delta of words newly promoted from draft → finalized in THIS frame) plus `tokens_draft`, `text_draft`, and `eou_detected: bool`. The legacy `text` field stays populated (built from the joined finalized words) so v1.4.x clients keep working. New fields ride alongside the existing `segments` / `confidence` / `model` / `rtf` shape — additive, non-breaking.
- **End-of-utterance (EOU) detection surfaced in the live UI**: the streaming-trained model emits an `<EOU>` token when the speaker stops talking. The backend strips the literal token from `text` (so the UI doesn't render it as a word) and surfaces it as `eou_detected: bool` on the outbound WS frame. The frontend `ServerLiveTranscript` renders a small gray "EOU" chip next to entries where the model detected end-of-utterance — visible feedback that the model understands speaker pauses. Works on both v2-endpoint and v1-endpoint paths (the new model emits `<EOU>` either way).
- **In-flight draft tokens visualized**: when `tokens_draft` is non-empty (model emitted speculative words it may revise), the frontend renders `text_draft` in faint italic next to the finalized text. Gives users a sense of the leading edge of the transcript stream without committing them to the un-stable suffix.

### Changed
- **Wire-contract bump for the live WS endpoint**: partial/final frames may now contain `tokens_finalized` + `tokens_draft` + `text_draft` + `eou_detected`. Clients that ignored unknown fields (the v1.x compat path) keep working; clients that want per-word streaming UX should consume the new fields. This is the rationale for the 2.0.0 major bump — wire-format addition, not removal, but a semantic widening of what live WS frames carry.

### Notes
- The v1.3.0 `consumed_through_ms` cursor + `audioop.rms` VAD silence-gate workarounds STAY in place. With v1.5.0's EOU-trained checkpoint they should fire much less often (the model itself recognizes silence), but they're cheap insurance against checkpoint regressions or unusual audio. We can remove them in v2.1.0 if production telemetry shows zero firings over a sustained window.
- The v2 endpoint is session-stateful (maintains a per-`X-Session-Id` audio ring). Backend WS forwarder already passes a stable `X-Session-Id` header per WS connection, so the svc reconstructs the ring correctly across the 2.5s flush cadence.
- Per-word streaming UI in v2.0.0 is intentionally minimal — full per-word render-as-they-arrive (the v2.1.0 polish) requires a richer state model than "one transcript entry per partial frame". For now the entries still snap in at 2.5s cadence; the draft + EOU chips are the visible upgrade.

## [1.5.0] - 2026-05-26

### Changed
- **Streaming STT checkpoint swap: parakeet-tdt-0.6b-v3 → parakeet_realtime_eou_120m-v1**: replaces the live-streaming model on midboy2 GPU 0 with a checkpoint that was actually *trained* for cache-aware streaming. Per Agent C's v1.2.0 spike (`docs/phase-b3-nemo-streaming-spike.md`), the previous 0.6B v3 checkpoint shipped with `att_context_size=[-1,-1]` (full-context attention) which made true streaming impossible — necessitating v1.3.0's `consumed_through_ms` cursor + audioop VAD silence-gate workarounds. The new 120M EOU model has `att_context_size=[70,1]` + `att_context_style=chunked_limited` + `model.conformer_stream_step` working, AND emits an `<EOU>` (end-of-utterance) token in transcripts when the speaker stops talking — directly addressing the v1.3.0 silence-hallucination root cause at the model level rather than at the WS forwarder level. Eval results on the synthetic_2speaker fixture: 5x smaller (114.9M vs 600M params), VRAM at fp16 drops from ~1.7 GiB to **629 MiB** on the RTX 3060, load time 12.85 s warm (was ~25 s), transcribe 5 s audio in 1.58 s cold / sub-second warm. Transcript quality looks clean (`"welcome everyone to today's test meeting i am the first speaker..."`). The v2 endpoint code (`/transcribe-stream-v2`) shipped in v1.2.0 now also works against this checkpoint and returns `tokens_finalized: [{word, start, end, confidence}, ...]` — Agent C's spike vision realized. The backend still routes through `/transcribe-stream` (v1 endpoint) with `STREAMING_USE_V2_PARAKEET=0`; flipping the flag + consuming the per-word stream shape on the backend + frontend is the v2.0.0 follow-up. Fallback model stays `nvidia/parakeet-tdt-0.6b-v2` (multilingual, full-context — unaffected by this swap). Tradeoff: 120M may have lower absolute accuracy than 600M on hard audio, but the streaming-trained behavior + EOU detection are decisively better for the live UX. The canonical /finalize-audio pipeline still uses the 1.1B v3 model on bigboy for the final transcript, so live-mode quality limits don't affect canonical quality.
  - midboy2 compose: `PARAKEET_STREAM_MODEL` default changed.
  - Image: `meet-parakeet-stream-svc:local` rebuilt from current source (includes Agent C's `/transcribe-stream-v2` endpoint code) and shipped bigboy → midboy2 via `docker save | docker load` (~4.5 min over Tailscale).
  - Multilingual note: the EOU model card lists English-focused training data (AMI, Fisher, librispeech). For multilingual sessions, fall back is the v2 model. A future eval should test the v3 multilingual model on non-English audio if we ship that as a runtime option.
  - The v1.3.0 `consumed_through_ms` cursor + VAD silence gate workarounds STAY in place. With the EOU model they should fire less often (the model itself recognizes silence and stops emitting), but they're cheap insurance. We can remove them in v2.0.0 if production telemetry shows they never fire.

## [1.4.1] - 2026-05-26

### Fixed
- **Settings > In-browser AI: clarify what the "Summary model" dropdown actually controls** (Aaron observed selecting Gemma 4 E2B but seeing Qwen 3.6 in the live summary display). The dropdown previously labeled "Summary model" sets the WebGPU/wasm in-browser LLM used only in Privacy Mode or as a browser-only fallback; normal-mode recordings send audio to the server, and the server-side summarizer (env-configured via `MEETING_OPS_LLM_MODEL`, defaults to `Qwen3.6-35B-A3B-Vision` on midboy1 P40) drives the live progressive summaries the user sees. The label now reads "In-browser summary model (privacy mode + browser-only fallback)" with a paragraph explanation directly below. New read-only "Server-side summarizer" panel below the dropdown fetches the actual model from `/api/system/pipeline` and surfaces it as `Currently {Qwen3.6-35B-A3B-Vision} on backend GPU` so users see both sides at a glance. No behavior change — pure UX clarity. Per-org server-side overrides (admin only) still live in Settings > AI Providers and the dropdown will continue to honor /finalize-audio overrides per `transcription_options.llm_model`.

## [1.4.0] - 2026-05-26

### Added
- **Server-live transcript with Sortformer speaker labels now visible inside the production Record page**: refactored the Phase B.2 streaming UX out of the admin-only `/streaming-test` diagnostic and into the actual `/record` page (`LiveRecording.tsx`). New reusable component `frontend/src/components/ServerLiveTranscript.tsx` (~270 lines) owns the WebSocket lifecycle for `/ws/sessions/{sessionId}/live`, runs its own AudioWorklet mic capture via the existing `startPcm16Capture` helper, and renders a transcript pane with the v1.2.1 `<SpeakerBadges>` color palette inline. Drop-in component takes `sessionId` + `enabled` props; teardown / re-init is automatic on prop changes. Tier-gated at the call site via `useTierFeatures().hasFeature('server_live')` — free tier sees no change, enterprise / pro / superuser see a second transcript pane fed by Phase B.2 streaming + Sortformer parallel dispatch (per v1.2.0 / v1.3.0 / v1.3.1). Both pipelines run in parallel during a recording — the existing `/ws/transcription-auto` path keeps providing live captions + auto-summaries + audio-levels, the new `/ws/sessions/{id}/live` path adds the speaker-labeled near-streaming view. Browsers happily share one OS-level mic across multiple `getUserMedia` calls, so the dual-pipeline architecture works without coordination. The admin `/streaming-test` page stays as the diagnostic; this is the production view. Frontend Docker build (tsc -b strict per v1.1.0) succeeds; 5 baseline vite warnings unchanged.

## [1.3.1] - 2026-05-26

### Fixed
- **Sortformer min-segment filter for cleaner speaker badges**: drop speaker turns shorter than `SORTFORMER_MIN_SEGMENT_MS` (default 500 ms) before emitting in the partial JSON. Sortformer over-segments on solo / quiet audio — flagging brief background-noise / breath sounds / mic-handling artifacts as a different speaker for ~100-300 ms (Aaron observed `speaker_1` chips appearing alongside his own `speaker_0` text on the v1.3.0 smoke test). Real conversational turns are almost always > 500 ms (people speak for at least a syllable), so the 500 ms floor catches genuine multi-speaker windows while dropping the noise. Filter lives in `_flush_to_stt` right after the sortformer response parses, so the frontend `<SpeakerBadges>` never sees the noise. `sortformer_distinct_speakers` also clears to 0 if the filter drops every turn, so the UI doesn't show stale counts. Configurable via env (`SORTFORMER_MIN_SEGMENT_MS=0` disables).

## [1.3.0] - 2026-05-26

### Fixed
- **WS partial transcripts no longer repeat + no longer hallucinate on silence**: v1.2.x near-streaming pipeline shipped a 25 s rolling-window approach where each 2.5 s flush sent the entire buffer to parakeet, then parakeet returned a fresh transcript of the whole window. With `nvidia/parakeet-tdt-0.6b-v3`'s full-context attention training, this produced two failure modes during the v1.2.0 smoke test: (1) the user spoke a sentence and saw it repeat 5+ times in the live transcript as the window kept resending the same audio, and (2) when the user stopped talking, the trailing silence in the window degenerated into repeating-token hallucination ("a little bit of a little bit of a little bit of..."). Per Agent C's spike report (`docs/phase-b3-nemo-streaming-spike.md`), the model architecture itself can't be fixed without a checkpoint swap — but the buffer-management half can.
  - **Cursor-based windowing**: added `_SessionState.consumed_through_ms`, advanced after every successful partial / final emission. `take_pcm()` now returns audio from `(consumed_through_ms − STREAM_LOOKBACK_SECONDS)` forward instead of the last 25 s of buffer. Default lookback 1.0 s keeps a small overlap for word-boundary continuity at the seam. Each flush now sees ~2.5 s of NEW audio + ~1 s of overlap, not 25 s of mostly-rehashed audio.
  - **VAD silence gate** (audioop.rms): added `_is_silent()` helper using Python stdlib `audioop.rms(pcm, 2)`. Default threshold `STREAM_VAD_RMS_THRESHOLD=200` catches background-noise-level windows; full-scale PCM16 sine peaks RMS ~23170, typical speech is 1000-5000 RMS, true silence is < 50. When a window is below threshold, parakeet is skipped entirely (no GPU waste, no hallucinated tokens) but the consumed cursor still advances so silence doesn't accumulate as a backlog of re-transcribe targets. Configurable via `STREAM_VAD_ENABLED=0` for diagnostics.
  - **Empty-text / identical-text de-dup paths** also now advance the consumed cursor (previously they only `return`ed, leaving the buffer to grow). This catches the case where parakeet declined to commit tokens on a low-confidence window — we trust its decision and move on rather than retry with the same audio.
  - Recovery safety net: the 25 s max window cap stays as a recovery guard for the case where N consecutive flushes failed (cursor stalled) — prevents shipping 5×N seconds of audio on the next try.
  - Smoke-tested by Aaron on `meetingops.magicunicorn.dev/#/streaming-test` immediately after deploy.

## [1.2.2] - 2026-05-26

### Fixed
- **WS streaming endpoint crashed on every Connect with `code=1006` due to DetachedInstanceError in `_resolve_org_bucket`**: latent Phase B.5 bug surfaced during the v1.2.0 smoke test. `_resolve_ws_user` (in `backend/api/streaming.py`) closes its DB `SessionLocal()` before returning the User object — necessary because Starlette WebSocket handlers don't compose with `Depends(get_db)` yield-style sessions — which leaves the User detached. Phase B.5's `_resolve_org_bucket` then called `getattr(user, "organizations", None)` on that detached User, which triggers a SQLAlchemy lazy-load and raises `DetachedInstanceError`. The exception propagated up the ASGI stack, the upgrade handshake never completed, and the client saw the worst-case `code=1006` close (abnormal). Every Connect attempt looped through `useReconnectingWebSocket`'s 500ms / 1s / 2s / 4s / 8s backoff and gave up. **Fix**: wrap the `getattr` in `try/except DetachedInstanceError`, falling back to the existing email-based bucket key. Added `DetachedInstanceError` to the `IndexError, TypeError, AttributeError` set the inner `try/except` already catches when walking the relationship. The B.5 per-org rate limit still works for eagerly-loaded callers (e.g. unit tests with a fresh session); the production WS path now degrades gracefully to per-user rate limit, which is a softer bound but still bounded. Backend rebuilt + redeployed; Connect succeeds, `<- {"type":"ready",...}` frame arrives, mic capture path is now reachable end-to-end. Smoke-tested on `meetingops.magicunicorn.dev` by Aaron immediately after deploy.

## [1.2.1] - 2026-05-26

### Added
- **Frontend speaker label badges in StreamingTest**: rendered the `speakers` array shipped on partial/final WS frames in v1.2.0. Each transcript entry now leads with one colored chip per distinct speaker that spoke during the window (sortformer's 4-speaker max → 4-color palette: red / green / blue / amber). Tooltip on each chip shows the speaker's first-turn start/end timestamps. Empty/undefined `speakers` is handled gracefully — entries without speaker data render identically to pre-v1.2.0. Removes the v1.2.0 deferral; the data was DevTools-observable but invisible in the UI, now it's visible inline. New types `SpeakerTurn` + helper `speakerColor(spk_id)` + presentational `<SpeakerBadges>` component in `frontend/src/pages/StreamingTest.tsx`. Docker frontend build (which enforces `tsc -b` strict per v1.1.0) succeeds; 5 baseline vite warnings unchanged.

## [1.2.0] - 2026-05-26

### Added
- **Phase B.3 chunk D: NVIDIA Sortformer streaming diarization end-to-end**: new `services/sortformer-svc/` container running `nvidia/diar_sortformer_4spk-v1` (123 M params, fp16) on midboy2 GPU 0. ~244 MiB resident / ~580 MiB peak during diarize. 175 ms warm round trip on a 33s window, RTF ~0.005 (~190x realtime). Co-resident with parakeet-svc + parakeet-stream-svc + speaker-svc on the same RTX 3060 with 6.5 GiB headroom; stress-tested 10-way concurrent (5 ASR + 5 diarize) without degradation. Service exposes `POST /diarize-stream` (per-window WAV/PCM body in, speakers JSON out with absolute timeline coords via `X-Window-Start-Ms`) and `POST /diarize-file` (full-meeting one-shot). Image layered on `meet-parakeet-svc:local` so we inherit the entire CUDA 12.4 + NeMo 2.4.1 + torch 2.4.1 stack; bigboy build → midboy2 ship via `docker save | docker load`. midboy2 compose adds `meet-sortformer-svc` service block on port 8896. 20 health tests pass. Why v1 not v2/v2.1: streaming variants need NeMo >= 2.5 and our parakeet base image pins 2.4.1; v1 still exposes `forward_streaming_step()` for the eventual true-streaming upgrade. See `docs/phase-b3-sortformer-spike.md` for the full spike report.
- **Phase B.3 chunk D: backend WS forwarder parallel dispatch**: `backend/api/streaming.py` `_flush_to_stt` now fires `asyncio.create_task` on the sortformer `/diarize-stream` POST BEFORE awaiting parakeet, when `STREAMING_USE_SORTFORMER=1`. Because sortformer is faster than parakeet (175 ms vs 200-600 ms warm), the second await is typically a no-op — true parallel inference, zero added latency. Sortformer failures (timeout / connect / 5xx / bad JSON) are non-blocking: empty `speakers` array on the outbound JSON frame, parakeet transcript still ships. Sortformer tasks are cancelled if parakeet errors out. Partial / final JSON frames gain four new keys (`speakers`, `sortformer_model`, `sortformer_rtf`, `sortformer_distinct_speakers`); existing clients ignore unknown keys. Production env flips `STREAMING_USE_SORTFORMER=1` in `.env.bigboy` and the backend service block in `deploy/bigboy/docker-compose.bigboy.yml` now forwards `STREAMING_USE_SORTFORMER` + `SORTFORMER_URL` + (newly explicit) `PARAKEET_STREAM_URL` into the container env. Live on `meetingops.magicunicorn.dev`.
- **Phase B.3 chunk B: Opus codec utility modules** (utility-only, no capture-path integration): `frontend/src/utils/opusEncoder.ts` (WebCodecs primary + MediaRecorder fallback, default 24 kbps speech, surfaces `createOpusEncoder({sampleRate, bitrate})` returning `{encode, flush, close}`) and `services/parakeet-stream-svc/opus_decoder.py` (libopus binding via `opuslib>=3.0.1,<4`, 20 ms frame default, 48 kHz internal). 12 pytest cases + 21 vitest cases pass. **Not yet wired** into `StreamingTest.tsx` capture path: the MediaRecorder fallback emits Opus-in-WebM (container) not raw Opus packets, so cross-browser integration needs either a WebM demuxer or a WebCodecs-only gate. Decision deferred to v1.3.0. Module reference compiles cleanly; if a future client wants to send Opus-coded audio, the encoder + decoder are available to call.
- **Phase B.3 chunk C: NeMo streaming `/transcribe-stream-v2` endpoint** (shipped as stepping-stone, NOT enabled in production): new endpoint in `services/parakeet-stream-svc/main.py` (now 970 lines, was 503) that uses NeMo's `conformer_stream_step` + `BatchedFrameASRTDT` to emit draft + finalize tokens with a session-stateful rolling audio ring. Spike report at `docs/phase-b3-nemo-streaming-spike.md` (268 lines) documents the architectural finding: `nvidia/parakeet-tdt-0.6b-v3` was trained with `att_context_size=[-1,-1]` (full-context attention), but cache-aware streaming requires `chunked_limited` attention. The streaming forward runs, but the model never learned to use the cache state, so it returns text only for the first chunk then nothing. **The fix is a checkpoint swap to `nvidia/multitalker-parakeet-streaming-0.6b-v1` (likely English-only) — multi-day eval follow-up.** v1 endpoint `/transcribe-stream` untouched and tested for back-compat (RTF=0.24, identical output). Endpoint gated behind `STREAMING_USE_V2_PARAKEET=0` (env default off); the integration scaffolding flag stays dormant until the model eval lands.
- **Phase B.3 integration scaffolding** (committed 2026-05-26 ahead of B.3 chunk landings): three new env vars in `backend/api/streaming.py` defaulting OFF so v1.0.0/v1.1.0 behaviour was unchanged at scaffolding time — `STREAMING_USE_V2_PARAKEET`, `STREAMING_USE_SORTFORMER`, `SORTFORMER_URL`. Design memo at `docs/phase-b3-integration-plan.md` (162 lines) documents the integration target spec for all four B.3 chunks. `STREAMING_USE_SORTFORMER` is now flipped to 1 in this release; the other two remain off.

### Changed
- **Phase B.3 chunk A: AudioWorklet migration for browser audio capture**: replaced the deprecated `ScriptProcessorNode` in `frontend/src/pages/StreamingTest.tsx` (the WS streaming smoke-test page) with `AudioWorkletNode`. ScriptProcessor's `onaudioprocess` runs on the main thread; AudioWorklet's `process()` runs in a dedicated audio render-thread, eliminating jank on long sessions and on devices with main-thread pressure (mobile, low-end laptops). New worklet processor at `frontend/public/audio-worklets/pcm16-encoder.worklet.js` (registered as `pcm16-encoder`, configurable frame size via MessagePort, default 3200 samples = 200 ms at 16 kHz). New helper at `frontend/src/utils/audioWorkletCapture.ts` wraps the AudioWorklet wiring behind a `startPcm16Capture(stream, onFrame, opts)` function; the helper transparently falls back to ScriptProcessorNode when `AudioContext.audioWorklet` is undefined (Safari < 14.1) with a console warning, so the page degrades rather than breaks on the rare legacy browser. The 19-byte big-endian WS frame header contract is preserved exactly — backend (`backend/api/streaming.py`) and `services/parakeet-stream-svc/` are unchanged. Bit-exact PCM16 conversion preserved (asymmetric `s < 0 ? s * 0x8000 : s * 0x7fff` mapping, matching the original ScriptProcessor loop). 5 baseline vite warnings unchanged. `tsc -b` clean. Verified production docker build of the frontend image succeeds with the worklet asset copied through to `dist/audio-worklets/`.

### Known scope deferrals
- **Frontend speaker label rendering**: backend now sends `speakers` array in partial / final WS frames, but `StreamingTest.tsx` does not yet render speaker badges next to transcript text. The data is observable in the WS log pane + browser DevTools network frames. UI polish queued for v1.3.0.
- **Opus uplink** (chunk B): utility modules shipped but capture path not wired (MediaRecorder=WebM caveat). v1.3.0 will either gate on WebCodecs-only or add a WebM demuxer.
- **True cache-aware streaming** (chunk C): blocked by checkpoint architecture per spike. Multi-day model eval cycle queued.

## [1.1.0] - 2026-05-26

### Added
- **Brigade Phase 2: inline 3D graph viewer**: new BrigadeGraphViewer component (lazy-loaded, react-force-graph-3d) embedded on SessionDetails. Shows the current meeting's Brigade nodes + 1-hop neighbors (Speaker, ActionItem, Topic, Decision) with color-coded labels and click-to-inspect tooltips. Backend: new GET /api/sessions/{id}/brigade-graph endpoint queries Brigade's Cypher endpoint and returns {nodes, links, graph_url} shape; returns empty + "not_synced_yet" reason for sessions before Brigade write fires. 30s cache. Cross-org isolated. "Open in Brigade" button below the viewer for the full-screen Brigade UI. The existing "View in Brigade graph" indigo banner from Phase 1 stays as an alternative entry point. The inline 3D viewer is gated behind a collapse/expand toggle so the Three.js footprint only loads when the user wants the graph. 7 new backend tests cover the endpoint shape, not-synced state, cross-org isolation, and cache.

- **Bulk Import B-import.4: admin pause/resume + Arq+Redis worker migration**: replaces the in-process asyncio queue with a durable Arq worker backed by unicorn-redis (db=4). Jobs now survive uvicorn restarts mid-batch. New compose service meet-bulk-import-worker running `arq backend.workers.bulk_import_worker.WorkerSettings`. Concurrency=2 default via Arq max_jobs; BULK_IMPORT_WORKERS env still respected. ARQ_ENABLED=false env flips back to the in-process pattern if needed. New admin endpoints: POST /api/import/admin/jobs/{id}/{pause,resume,cancel} + GET /api/import/admin/jobs (cross-org listing, admin-gated). Frontend AdminBulkImport page at /admin/bulk-import with status filter + per-job action buttons + click-through to file detail. 7 backend tests cover pause/resume/cross-org-visibility/non-admin-403/worker durability. The in-process queue stays in the codebase as ARQ_ENABLED=false fallback for emergency rollback.
### Fixed
- **TypeScript strict warnings cleanup**: `tsc -b` was emitting 17 strict-mode errors across the frontend even though `vite build` (which the Dockerfile uses) skipped tsc and shipped clean. Cleaned up the fixable ones across `frontend/src/components/PWAUpdate.tsx` (added `vite-plugin-pwa/client` type reference in `vite-env.d.ts` so `virtual:pwa-register` resolves), `frontend/src/components/TagChip.tsx` (replaced the dynamic-element `keyof JSX.IntrinsicElements` pattern with a conditional render — fixes JSX-namespace + IntrinsicAttributes errors), `frontend/src/components/ImportFilePickerStage.tsx` (removed always-true truthy check on `DataTransferItem.getAsFile` method reference), `frontend/src/contexts/AlwaysOnContext.tsx` (annotated `.map()` return type so the type predicate matches in `appendTranscriptSegments`; simplified the recovery-path `mimeType` resolution since the recorder ref is always null at that point), `frontend/src/pages/LiveRecording.tsx` (optional-chained `activeAgent` + `progressiveData` accesses; rewrote the nested-ternary `sessionData` narrowing that React 19 + TS 5.8 wasn't propagating through JSX), and `frontend/src/utils/api.ts` (coerced `?.startsWith()` result to a strict boolean). 17 strict errors -> 0. Vite production warnings unchanged at 5 (all upstream-library noise: 3 `"use client"` directives in react-toastify/react-router, 1 `eval` in onnxruntime-web, 1 chunk-size advisory). No behavior changes; pure type hygiene to keep CI output clean and unblock the strict `npm run build` script.
- **Pre-existing pytest failures cleared (21 -> 0)**: 21 long-standing failures across `tests/test_analytics.py`, `tests/test_search_analytics.py`, and `tests/test_parakeet_stt.py` had been carried since the security-hardening commit (ed9e70e) without being addressed. Root-caused and fixed in three buckets. (1) `tests/test_search_analytics.py` (15 fails) + the duplicate `tests/test_analytics.py` (4 fails): every test hit `/api/analytics/*` and `/api/simple/recording-sessions/*` without auth headers, which started 401-ing as of ed9e70e. Fixed by routing every call through `_auth_headers(client)` (login + bearer); deleted `test_analytics.py` outright since all four of its tests duplicated `test_search_analytics.py::TestAnalytics` with thinner asserts. (2) `tests/test_parakeet_stt.py::TestProviderRegistrySTTRouting` (2 fails): the three registry tests didn't depend on the `client` fixture so the session-scoped `app` fixture never ran, leaving SQLite without the `org_provider_settings` table. Added `app` as a method-level fixture param so table creation runs first. The `test_parakeet_resolves_when_provider_name_set` assertion also expected `meet-parakeet-svc:` endpoint but production sets `PARAKEET_SERVER_URL=http://100.66.42.57:8881`; fixed by `monkeypatch.delenv("PARAKEET_SERVER_URL")` so the in-cluster default path is exercised. The `test_default_is_local_whisper` test predates the Phase B.2 flip of `STT_DEFAULT_PROVIDER` default to `parakeet`; pinned the env explicitly via `monkeypatch.setenv("STT_DEFAULT_PROVIDER", "local_whisper")` and added a sibling `test_default_is_parakeet_in_production` that pins the current default. (3) New interaction bug exposed by the cleanup: `tests/test_arq_worker.py::test_worker_respects_max_jobs_concurrency` called `importlib.reload(workers.bulk_import_worker)` which transitively re-imported `database.models`, putting fresh `Table` objects on `Base.metadata` and orphaning every FK relationship bound to the OLD tables. `test_bulk_import.py::test_duplicate_sha256_marked_skipped` (and any downstream test) then failed with `NoReferencedTableError`. Fixed by (a) rewriting the test to drive `services.bulk_import_queue.get_bulk_import_concurrency()` directly with `monkeypatch.setenv` (no reload needed), and (b) extending `tests/conftest.py::app` to reload `services.bulk_import_queue` + `workers.bulk_import_worker` after the model reload so their cached model refs rebind to the fresh `Base`. Final: `318 passed, 0 failed, 3 skipped` (previously `288 passed, 21 failed, 3 skipped`).
- **Docker frontend build now enforces TypeScript strict check**: `frontend/Dockerfile` used `npm run build:docker = vite build` which skipped tsc entirely — that's how 17 strict errors silently rode production for weeks AND how a runtime bug shipped in `frontend/src/pages/AdminBulkImport.tsx` (4 sites calling `showToast('msg', 'error')` as a function, but `showToast` is an object with `.success`/`.error`/`.info`/`.warning` methods — calls would no-op at runtime). Fixed by (a) rewriting `package.json::scripts.build:docker` to `tsc -b && vite build` (parity with `npm run build`), (b) cleaning up the AdminBulkImport.tsx call sites to use `.error(msg)` / `.success(msg)`, and (c) fixing the BrigadeGraphViewer.tsx ref typing for `react-force-graph-3d` (was casting to `MutableRefObject<unknown>`; lib expects the `ForceGraphMethods<...>` shape, cast to `any` since we don't use the imperative API). Docker build now fails fast on TS strict errors instead of shipping them.
- **Bulk-import worker healthcheck**: `meet-bulk-import-worker` shipped without a healthcheck, so when the B-import.4 worker started crash-looping due to the hardcoded Redis auth bug (since-resolved at f3857c0), it was only caught manually via `docker logs`. Added a Docker healthcheck (`docker-compose.bigboy.yml`) that pings the ARQ Redis instance the worker connects to via a Python one-liner; flips the container to unhealthy if Redis auth/DSN/connectivity breaks. 30s interval, 5s timeout, 3 retries, 30s start_period. Verified healthy after rebuild.
- **Dead code cleanup in `services/bulk_import_queue.py`**: removed 4 unused imports (`shutil`, `datetime.date`, `datetime.time`, `sqlalchemy.or_`) flagged by pyflakes. Also dropped the `_get_org_slug` helper + its caller (`org_slug = _get_org_slug(...)` at line 466 was computed but never read — the local-disk path the helper was originally meant to inform doesn't actually use it). Pure tidying; no behavior change.

## [1.0.0] - 2026-05-22

### Added
- **Bulk Import B-import.2: polished /import preview-table UX**: stage-based flow (Pick > Preview > Confirm > Progress > Completion). Folder drop-zone (webkitdirectory) accepts up to 1000 audio files at once with MIME validation; non-audio files rejected with toast. Preview table per-row controls: editable parsed title + meeting date + meeting time + participant hint + confidence indicator (green >=0.9, yellow >=0.5, red <0.5). Bulk-edit toolbar: apply participant to selected rows, set-all dates, deselect-low-confidence one-click. Confirm screen surfaces audio total + expected processing time + Garage bucket + GPU host. Progress stage shows per-file status with linked-session button on complete + per-failure retry button. Completion summary with "Retry failed" + "Go to sessions" deep-link. Backend: new POST /api/import/jobs/{id}/files/{file_id}/retry endpoint + ?bulk_import_job_id query filter on /api/simple/recording-sessions. Polish phase for Aaron's 526-file Mac Notes archive at /Volumes/media/audio-from-notes-voicememos-2026-05-20.
- **Brigade Phase 1.5: write from live/browser-only sessions**: extends the Phase 1 writer to also fire when a browser/live session is finalized via /sessions/{id}/finalize (not just the /finalize-audio reprocess path). write_meeting_to_brigade now gracefully handles missing speakers (no diarization in browser path), missing action items, missing topic/decision extraction; always writes at minimum a Meeting node + summary text. New completion_mode parameter ('reprocess' or 'live') stored on the Meeting node for analytics. Hook fires fire-and-forget at /finalize so user-facing flow is never affected. 5 new tests on top of the existing Phase 1 suite cover the live-completion path, the completion_mode tag, and failure swallowing.
- **Phase B.5: production polish on server-live streaming path**: closes Phase B for paid-tier launch.
  - Frontend `useReconnectingWebSocket` hook with exponential backoff (500ms -> 30s, max 5 attempts). StreamingTest page now uses it; clean closes (1000/1001/4xxx) don't reconnect, abnormal closes (1006) do. Reconnect status surfaced in the log pane.
  - Server-side backpressure in `backend/api/streaming.py`: per-session PCM buffer caps at 60s, oldest dropped if exceeded. Parakeet round-trip >2s triggers skip-next-N backoff. Per-org cap of 5 concurrent live sessions (configurable via `STREAMING_MAX_SESSIONS_PER_ORG`); excess gets close code 4429.
  - Prometheus metrics on `/metrics`: `meeting_ops_ws_connections_total` (labels tier + result), `meeting_ops_ws_audio_frames_forwarded_total`, `meeting_ops_ws_partial_transcripts_emitted_total`, `meeting_ops_ws_close_codes_total` (label code), `meeting_ops_parakeet_stream_request_duration_seconds` (histogram).
  - SIGTERM drain: active WS sessions get a `{"type":"server_shutdown","reconnect_after_ms":3000}` JSON frame + close code 1001 before uvicorn exits. Lets the frontend reconnect cleanly after a deploy.
  - 7 new backend tests cover backpressure, per-org rate limit, metrics increments, parakeet slowdown handling, active_sessions registry, org-count drain, and /metrics endpoint shape.
- Phase B is now production-polished end-to-end. Remaining blockers to paid-tier launch are pricing decision and upgrade flow (operational, not engineering).

## [0.9.1] - 2026-05-22

### Added
- **Bulk Import B-import.3: speaker auto-link from filename pattern**: when a bulk-imported file's parsed title matches the `Call with {Name}` pattern (which the bulk of Aaron's 526-file archive does), the pipeline now extracts the name via `extract_call_with_name()` in `backend/utils/filename_parser.py` (handles parenthetical suffixes like `Doug (Crash)` -> `Doug`) and resolves it via `find_speaker_by_name_hint()` in `backend/services/speaker_service.py` using rapidfuzz token_set_ratio at an 0.85 floor against enrolled speakers in the org. On match, creates a `SpeakerSessionLink` with `source='filename-hint'` and `raw_label='HINT'`. The existing post-reprocess `identify_speakers()` embedding-match (source='auto') runs later and adds its own link; both coexist. Cross-org isolation enforced in the lookup. New `backend/tests/test_bulk_import_speaker_link.py` covers happy path, fuzzy match (e.g., `Khan, Shafen` <-> `Shafen Khan`), parenthetical suffix stripping, cross-org isolation, unknown-name, non-call-pattern titles, and the Step 3.5 hook integration. 15 tests pass. Test harness gained a `RECORDINGS_DIR` env var (in conftest.py) pointing to a tempfile so bulk-import tests don't depend on the Docker-only `/app/recordings` path.
- **Phase B.4: tier gate on server-live WebSocket**: the `/ws/sessions/{session_id}/live` endpoint now enforces `tier_features.server_live` via the User.tier infrastructure shipped in v0.8.2 (alembic 028 + `backend/auth/tier.py`). Free-tier users attempting to connect get a JSON `{"type": "error", "reason": "tier_insufficient"}` frame followed by close code 4003. Pro / Enterprise users (and superusers via `get_user_tier()`'s is_superuser override) proceed to the existing ready / partial / final flow. Frontend `/streaming-test` page reads `useTierFeatures()` and renders an upgrade nudge instead of the connect button when `server_live` is false. 5 backend tests cover free / pro / enterprise / superuser-bypass / unauth-regression. Closes the gate that makes server-live a real paid feature; combined with the existing capture-only fallback for free mobile users in v0.8.0, free tier is now a coherent product.

## [0.9.0] - 2026-05-22

### Added
- **Phase B.2 — real Parakeet 0.6B v3 in meet-parakeet-stream-svc + WS forwarding**: the B.1 stub container is replaced with a real NeMo + CUDA streaming-ASR service. `services/parakeet-stream-svc/Dockerfile` now layers on top of the already-built `meet-parakeet-svc:local` image (saves rebuilding the CUDA 12.4 + NeMo 2.4.1 + torch 2.4.1 + audio-tooling stack from scratch — the new image is just a `pip install` and a couple of file copies). At container start, NeMo loads `nvidia/parakeet-tdt-0.6b-v3` into VRAM at fp16 with `nvidia/parakeet-tdt-0.6b-v2` as fallback; model load takes ~47 s the first time (HF download) and ~10-15 s on warm volumes. `POST /transcribe-stream` accepts a WAV body (or raw PCM16) and returns `{text, segments, words, duration, model, rtf, confidence, sequence, is_final}` with real transcripts. Verified on midboy2 GPU 0 (RTX 3060): model resident ~1.7 GB, total GPU 0 usage ~5.1 GB combined with the existing 1.1B batch + speaker-svc containers (~6.9 GB headroom). 2.5 s window inference at RTF 0.08-0.12 (10x realtime).
- **Phase B.2 — WS handler buffers + forwards to streaming service**: `backend/api/streaming.py` is upgraded from the B.1 ack-only scaffold to a real near-streaming forwarder. Each WS session keeps a 60 s ring buffer of PCM16, fires an upstream `POST /transcribe-stream` every 2.5 s of audio (or on `{"type":"flush"}`), and sends `{"type":"partial", text, sequence, covers_through_ms, ...}` JSON frames back to the client as transcripts arrive. The buffer is windowed to the most recent 25 s on each upstream call so it stays inside the streaming service's 30 s per-call cap regardless of how long the session has been running. `{"type":"end"}` triggers a synchronous final flush + `{"type":"final", ...}` frame before close-1000. Concurrency-safe: one upstream call in flight per session via `state.in_flight`. Connection-scoped `httpx.AsyncClient` with keep-alive limits avoids TCP setup on every flush. End-to-end test with the speaker-svc `synthetic_2speaker.wav` fixture (33.7 s, 2 Kokoro TTS speakers) returns 13 progressive partials + 1 final transcript that matches the ground-truth meta.json word-for-word ("…we need a stronger probe to catch it earlier in the future, before it impacts real user sessions"). True NeMo streaming with draft+finalize tokens is the B.3 enhancement; the wire contract is forward-compatible.
- **Phase B.2 — StreamingTest page with real-mic capture**: `/streaming-test` (admin) now has a Start mic button that captures the user's microphone via `getUserMedia` + `ScriptProcessorNode`, transcodes to 16 kHz mono PCM16, batches into 200 ms WS frames with the canonical 19-byte BE header, and streams to the backend. The page also has a "Live transcript" pane below the controls that aggregates partial / final JSON frames into a readable rolling transcript (green left-border for finals, blue for partials). Backwards-compatible — the Send dummy chunk button still works as a seam test, the 19-byte header layout is unchanged.
- **Phase B.2 — frame header reconciliation (doc-vs-code)**: the original `docs/phase-b-server-live-streaming.md` section 4 drafted a variable-length little-endian header (1-byte version + LE uint64 sequence + LE uint64 timestamp_ms + LE uint16 format + payload). B.1 shipped a fixed 19-byte big-endian header (`>IQ4sHB`: uint32 BE sequence + uint64 BE timestamp_us + 4-char ASCII format + uint16 BE sample_rate/100 + uint8 flags). B.2 reconciles to the **fixed BE form** because it carries identical information, parses with one `struct.unpack` on both Python and TypeScript sides, and avoids the read-version-then-branch overhead of the variable layout. Updated section 4 + Appendix A of the design doc, the streaming.py module docstring, and the StreamingTest comment block. Variable-LE form remains an option if we ever need extension fields, but it's over-engineered for v1.
- **Brigade integration Phase 1**: Meeting-Ops now writes session-completion data to Brigade FalkorDB as graph nodes (Meeting + Speaker + ActionItem + Topic + Decision + corresponding edges). Hooks into the existing post-reprocess pipeline so the write happens automatically after Parakeet 1.1B + pyannote + Qwen 3.6 finishes. Tenancy modes: shared / per_org_graph / per_org_instance via `BRIGADE_TENANCY_MODE` env (default `shared`, graph name `agent_meeting_ops_canonical`; per-org mode picks `agent_meeting_ops_org_<id>`). New `backend/services/brigade_client.py` (HTTP client with 3-attempt exponential backoff retry on connect/timeout/5xx, terminal 4xx, log-only no-op mode when `BRIGADE_API_KEY`/`BRIGADE_ADMIN_KEY` unset, `is_live` flag for callers) and `backend/services/brigade_writer.py` (orchestrates per-session write: Meeting node first, then Speaker nodes via SpeakerSessionLink lookup, then ActionItem nodes with best-effort owner→speaker matching for ASSIGNED_TO edges, then Topic nodes from `final_summary.bullets`, then Decision nodes from `final_summary.decisions` with parenthetical "decided by Name" parsing for DECIDED_BY edges; stamps `recording_sessions.brigade_synced_at` + `brigade_graph_node_id` on success). Brigade write failures NEVER break the user-facing pipeline (top-level try/except in writer + dedicated try/except in `_run_session_reprocess` Stage 6 hook; both log + continue). Frontend `SessionDetails` adds a "View in Brigade graph" link when `brigade_graph_url` is set on the session payload; backend pre-builds the URL via `services.brigade_writer.build_brigade_graph_url` so the client doesn't need to know the active tenancy mode. Alembic 030 adds `brigade_graph_node_id` (VARCHAR(64)) + `brigade_synced_at` (TIMESTAMP) columns to `recording_sessions` plus an index on `brigade_synced_at` for the future reconciliation job. End-to-end live test against Brigade v1.13.0 on bigboy verified entity + edge writes land in `agent_meeting_ops_canonical` graph. 7 backend tests cover writer fires after reprocess, full node+edge call shape (11 entities + 11 edges + 2 ASSIGNED_TO + 1 DECIDED_BY for the seeded session), shared-tenancy single-agent-id contract, per_org_graph isolation (disjoint agent_ids per org), failure-swallowing on Brigade errors, idempotent rerun (same node names + monotonic timestamp), and log-only mode when no API key. Phase 1 of `docs/brigade-integration-design.md`; Phase 2 (read endpoints + in-page 3D mini-widget) and Phase 3 (full `/insights` page with feature parity vs Brigade's KnowledgeGraph.jsx) are subsequent rollouts.

## [0.8.2] - 2026-05-22

### Documentation
- Added `docs/README.md` (58 lines) indexing all 14 design docs in `docs/` grouped by topic (architecture, mobile roadmap, bulk operations, conference rooms, ecosystem integration, deployment) with line counts + shipped/designed status. Includes a "reading order for new developers" section. Hand-maintained alongside design-doc commits.
- Updated `CLAUDE.md` with a Latest release line for v0.8.1, a Design docs section linking to `docs/README.md`, an Active roadmap section reflecting the mobile A -> B -> C-1 -> C-2 -> C-3 commitment.

### Added
- **Bulk audio import — Phase 1 (B-import.1)**: new `/import` page lets users upload multiple audio files at once, with the filename parser pre-extracting title + meeting_date + meeting_time. Backend job queue extends the existing `UploadPipelineQueue` pattern with a configurable concurrency cap (default 2 to protect Parakeet 1.1B reprocess load, override via `BULK_IMPORT_WORKERS` env, hard ceiling of 4). Per-file pipeline: SHA-256 dedup against existing sessions → filename parse → RecordingSession create → audio upload to Garage S3 (`meeting-ops-audio` bucket, `{org_id}/{job_id}/{file_id}` key) → internal reprocess enqueue. New `POST /api/import/jobs`, `POST /api/import/jobs/{id}/files` (multipart streaming, 8 MiB chunks, per-file size cap), `GET /api/import/jobs/{id}` (job + per-file rows + counters), `POST /api/import/jobs/{id}/cancel` (soft-cancel: queued files become skipped, in-flight finish gracefully). Alembic 029 adds `bulk_import_jobs` + `bulk_import_files` tables with FK cascades + `(user_id, status)` / `(job_id, status)` / `(file_sha256)` indexes. Org-scoped throughout; cross-org probes return 404 (no existence leak). 7 backend tests covering create-job, upload + parse, SHA-256 dedup, cross-org 404, concurrency-cap semaphore math, cancel-mid-flight, idempotent cancel. Targets Aaron's 526-file backlog at `/Volumes/media/audio-from-notes-voicememos-2026-05-20`. Polished preview-table UX, speaker auto-link from filename, admin pause/resume, and Arq+Redis migration are subsequent phases (B-import.2/3/4) per `docs/bulk-audio-import-design.md`.
- **Phase B.1 scaffolding (server-live streaming foundation)**: new `meet-parakeet-stream-svc` container on midboy2 (port 8895) with stub `/transcribe-stream` endpoint that returns dummy partial transcripts; real Parakeet 0.6B v3 integration lands in Phase B.2 per `docs/phase-b-server-live-streaming.md` sections 5-7. New `/ws/sessions/{session_id}/live` FastAPI WS endpoint in meet-backend (`backend/api/streaming.py`) implementing the 19-byte binary frame header + JSON control protocol (`>IQ4sHB`: uint32 BE sequence + uint64 BE client_timestamp_us + 4-char ASCII payload_format + uint16 BE sample_rate/100 + uint8 flags); auth-gated via the existing oauth2-proxy forward-auth header flow (same path the production `/ws/audio-levels` endpoint uses); accepts connection, emits a `ready` frame, logs each binary chunk + acks it, replies `pong` to `{"type":"ping"}`, closes cleanly on `{"type":"end"}`, returns close-code 4001 for unauthenticated connects. Admin-only `/streaming-test` frontend page (`frontend/src/pages/StreamingTest.tsx`) lets you Connect, Send dummy chunk (1 KB PCM16-formatted), Send ping, Send end, and watches the round-trip with full frame log. End-to-end seam (Cloudflare -> oauth2-proxy -> Traefik -> FastAPI WS upgrade) verified.
- **User tier infrastructure**: new `users.tier` column (alembic 028) with values free / pro / enterprise. Aaron + Shafen backfilled to `enterprise` + `is_superuser=true`. New `backend/auth/tier.py` module with `TIER_FEATURES` dict, `get_user_tier()`, `get_tier_features()`, and `require_tier(min_tier)` FastAPI dependency. `/api/auth/me` response now includes `tier` and `tier_features` fields (the latter is a nested dict with per-capability booleans + quota numbers). Frontend `useTierFeatures()` hook + TS types added. Foundation for Phase B.4 server-live tier gating.

## [0.8.1] - 2026-05-22


### Changed
- Phase B design doc Q1-Q4 open questions locked (`e6d85f2`): Q1 new `meet-parakeet-stream-svc` container running Parakeet 0.6B v3 on midboy2 GPU 0 (existing 1.1B batch on bigboy stays for post-meeting reprocess); Q2 new users default to `tier=free`, Aaron + Shafen set to `tier=enterprise` + `is_superuser=true` via alembic UPDATE on their email rows (tier and admin orthogonal); Q3 Traefik sticky routing for B.1-B.4, defer Redis pub/sub until we add a second backend replica (existing `/ws/audio-levels` proves the single-worker pattern works); Q4 no new seam to test for oauth2-proxy WS through Cloudflare, the existing `/ws/audio-levels` already routes the exact same way in production.
- TS cleanup: settings components and SettingsEnhanced.tsx now use `import type` for `SectionProps` / `SaveStatus` / `HostCapabilities` / `SettingsState` (`ca3ca01` via Codex). The types existed and were exported; the warnings were value-level imports of type-only exports under `isolatedModules`. Vite production build is now warning-free.

### Documentation
- Added `docs/phase-c1-native-ios-design.md` (~1386 lines) scoping the native iOS app with Core ML + watchOS extension. Stack: Swift + SwiftUI native (because watchOS apps must be Swift extensions of iOS bundles). Core ML conversion: use FluidInference/FluidAudio Swift Package (MIT) which already ships Parakeet 0.6B v3 as `.mlpackage` (110x RTF on M4 Pro, INT8 W8A8 ANE-optimized); LLM via runtime priority cascade (Apple Foundation Models 3B on iOS 26+ via Swift API, fallback to mlx-swift Qwen 3 0.6B / Gemma 4 E2B in 4-bit on iOS 17+, fallback to llama.cpp + Metal, fallback to capture-only). Native UX (AVAudioEngine + URLSession background uploads, MPRemoteCommandCenter lock-screen, INVoiceShortcut Siri, CoreSpotlight indexing, share-extension, widgets, Dynamic Island Live Activities), GRDB local DB, WS auth via Sec-WebSocket-Protocol bearer JWT (no cookie). watchOS extension via WatchConnectivity proxying through paired iPhone (B.1) + cellular direct upload (B.2). 5-phase plan (~8-10 weeks for v1 closed beta + 2-4 weeks App Store review). Phase C-1 in the committed mobile roadmap A->B->C-1->C-2->C-3.
- Added `docs/bulk-audio-import-design.md` (~1054 lines) covering the /import page for bulk audio ingestion: UX flow (drop folder → preview table with parsed metadata + bulk-edit overrides → confirm → progress view → completion), job queue architecture (recommendation: in-process asyncio queue for v1 with Arq + Redis migration in v4, vs Celery rejected as sync-first), per-file pipeline (SHA-256 dedup → filename parse → session create → Garage write → reprocess enqueue), concurrency model (=2 default with per-org rate limit + adaptive throttle when Parakeet p95 climbs above 180s), progress UI with WebSocket primary + SSE/polling fallbacks, error handling + restart recovery + resume-after-cancel semantics, speaker auto-link from `Call with X` filename pattern (new `source='filename-hint'` value, embedding match wins), Garage S3 storage layout (`meeting-ops-audio` bucket, `{org_id}/{session_id}/{filename}` key format), security (per-file/per-job/per-org-per-day caps + MIME validation via ffprobe + filename sanitization), alembic 028 schema for `bulk_import_jobs` + `bulk_import_files` tables, and 4-phase implementation plan (~5 working days). Direct continuation of today's filename parser + meeting_date column work (`e447cf9`), targeting Aaron's 526-file backlog at `/Volumes/media/audio-from-notes-voicememos-2026-05-20`.

### Added
- **Synthetic-WAV diarization probe for speaker-svc**: new `GET /healthz/synthetic` endpoint runs a bundled 2-speaker test WAV through the full pyannote + wespeaker pipeline at each probe and asserts `speaker_count` matches ground truth (2). Returns 503 with `reason` on `speaker_count_mismatch` / `segments_too_few` / `embedding_distance_too_low` / `diarization_threw` / `fixture_missing` / `fixture_unreadable`, 200 otherwise. Docker healthcheck wired to call it every 5 minutes with `start_period: 2m` for cold-start tolerance; midboy1 runtime compose updated to match. Catches the pipeline-state-degradation class of failure that the standard `/health` misses; the threshold-sweep false alarm a few days ago was caused by exactly this (pipeline degraded but threshold was fine, container restart fixed it). Refactored shared diarization path into `_run_diarization_on_wav()` so the probe hits the exact same code path normal sessions hit. Fixture is a 33.7s 16 kHz mono WAV concatenating two Kokoro TTS speakers (`af_bella` female + `am_michael` male, ~1MB) with a sibling `synthetic_2speaker.meta.json` describing ground truth + the verification baseline (observed `num_speakers=2`, observed centroid cosine distance 0.977 against the 0.4 floor). 6 unit tests cover fixture-present / ok / speaker_count_mismatch / diarization_threw / embedding_distance_too_low / segments_too_few. Closes #105.
- **Editable meeting_date + meeting_time columns on recording sessions**: backfilled from started_at / created_at via alembic 027. Inline-editable on SessionDetails with native date + time inputs. Session list now supports sort-by-meeting-date in addition to sort-by-upload-date (persisted in localStorage as a "Uploaded / Meeting date" toggle in the controls bar). Backend list endpoint accepts `?sort=meeting_date_desc|meeting_date_asc|created_at_desc`; null meeting_date falls back to started_at then created_at so a session never disappears from the date column.
- **Filename parser (backend + frontend)**: shared utility that extracts title / date / time / source from filenames. Recognizes the `notes__/downloads__` Mac Notes + Voice Memos export pattern (`YYYY-MM-DD_HHMMSS` prefix, confidence 1.0), plus generic ISO-date-prefix (0.8-0.9), US-date-suffix (0.7), and ISO-date-anywhere (0.5) fallbacks. Used at single-file upload time to pre-fill the new-session form (preview card with confidence + accept/override checkbox); also runs server-side at upload finalize so any user-supplied meeting_date / meeting_time wins over the filename guess. Foundation for the upcoming `/import` bulk-upload page that will backfill Aaron's 526-file audio archive at `/Volumes/media/audio-from-notes-voicememos-2026-05-20`.
- New `POST /api/recordings/parse-filename` endpoint exposing the parser to clients (user-scoped auth; returns `title` / `meeting_date` / `meeting_time` / `source` / `confidence` / `raw_filename`).
- **Privacy mode full-quality local pass (Phase A.6)**: at session stop in privacy mode, the browser now runs Parakeet 0.6B INT8 against the assembled IndexedDB audio blob for a high-quality full transcript, then runs Qwen 3 0.6B INT8 (or Gemma 4 E2B) for the final summary. Previous privacy summaries were live-slice rollups only; now they match server-quality privacy-respecting output. Results stored in new local-sessions IndexedDB store.
- **Local Sessions view**: new /local-sessions page lists privacy-mode sessions persisted in IndexedDB. Sidebar entry appears once you have at least one local session. Detail view supports audio playback (from IDB), inline title/tag edits, and export-as-Markdown / export-as-JSON for moving data out of the browser. Local-only badge on every card. Truly zero-server-bytes architecture across capture, STT, summary, storage, and review.

## [0.8.0] - 2026-05-21

### Added
- **Mobile capture-only mode**: phones and tablets now skip browser-side Parakeet 0.6B STT and Qwen 3 0.6B / Gemma 4 E2B LLM loading entirely. New `frontend/src/utils/deviceDetection.ts` runs one-shot probe (UA + WebGPU + maxTouchPoints for iPadOS disambiguation + SharedArrayBuffer + deviceMemory) and buckets devices into `desktop-capable` / `capture-only` / `desktop-fallback`. `AlwaysOnContext` reads the result at provider mount, gates the Parakeet load effect and `triggerSummarize` browser-LLM path on `shouldRunBrowserInference`, exposes `deviceCapability` + `isCaptureOnlyMode` for the UI. `AlwaysOnControl` swaps the live transcript + live summary panes for a "Capture-only mode" banner on mobile; `MobileLiveRecording` shows the same banner above its scroll area. Audio capture continues via MediaRecorder and uploads as chunks through the always-on path; the server runs the full quality pass (Parakeet 1.1B + pyannote 3.1 + Qwen 3.6 35B) at completion and produces transcript + summary about a minute later. This eliminates the "live captions stall on iOS Safari WebGPU" experience and sets honest expectations. First step in the committed mobile roadmap (Phase A → B → C-1 → C-2 → C-3, where C-2 includes Apple Watch support).
- **Desktop local-first audio persistence (Phase A.5)**: chunks now land in IndexedDB during recording in addition to streaming to the server. New `frontend/src/services/localAudioStore.ts` keyed by `[session_id, sequence_number]` plus a session-metadata store for orphan tracking. On stop, the client computes a SHA-256 + byte total + chunk count across the IDB mirror and POSTs a verification payload to `/finalize-audio`; server reassembles the on-disk chunks, recomputes the SHA-256, and either returns `status=complete` (client wipes local) or `status=incomplete` with `missing_chunks` + `server_chunks` (client falls back to whole-file upload). New `/full-audio` endpoint accepts the assembled IDB blob as a bulletproof recovery path — clears any partial chunk state and queues the same reprocess pipeline. Gated to `capabilityClass='desktop-capable'`; mobile and desktop-fallback stay chunks-straight-to-server.
- **Resume-on-reload banner**: orphan sessions (recordings that started but never finalized) are detected at provider mount via a one-shot IDB scan. `AlwaysOnControl` renders a banner per orphan with started-at relative time, chunk count, MB size, and Resume Upload / Discard actions. Resume runs the same verify-then-fall-back-to-full-audio dance; sessions older than 24 hours prompt for confirmation. A browser crash mid-meeting now loses at most the last partial chunk in the encoder buffer instead of the entire recording.
- **Privacy mode is now truly local**: `localOnly: true` on the recorder skips `/audio-chunks` POSTs entirely while still persisting each chunk to IndexedDB so the local STT (Parakeet 0.6B INT8) and local LLM summary (Qwen 3 0.6B / Gemma 4 E2B) pipelines have source audio. No `/finalize-audio` either. The session ends with `localAudioStore.setSessionFinalized()` (audio + sha256 stay on the device) and the existing local-session store keeps transcript + summary + slices. Local STT/LLM pass against the assembled blob is queued as a follow-up — today the slice rollup at stop() produces the final summary from the live-transcribed slices, same as pre-A.5 privacy mode.
- New Help page subsection "On mobile (phones and tablets)" explaining the capture-only contract, why current mobile browsers can't do the live work reliably, and the roadmap to native iOS+Android with on-device live captions sized for phone silicon.
- meeting-ops.magicunicorn.dev (hyphenated) as alias for canonical meetingops.magicunicorn.dev. Cloudflare CNAME (proxied) + Traefik 308 redirect via redirectregex middleware. Cookies/sessions stay on canonical; URL works either way.
- **Browser always-on full audio capture + server-side reprocess**: parallel `MediaRecorder` track on the same MediaStream as the VAD engine produces continuous WebM/Opus (or MP4 on Safari) chunks every 30s; each chunk POSTs to new `/api/recordings/sessions/{id}/audio-chunks` with exponential-backoff retries (max 5). On session end, `/finalize-audio` reassembles via ffmpeg and kicks a BackgroundTasks pipeline: Parakeet 1.1B fp16 → pyannote diarization (`return_embeddings=true`) → `identify_speakers()` → Qwen 3.6 35B-A3B-Vision final summary. `processing_metadata.reprocess_status` drives a banner on SessionDetails (in_progress → complete). Privacy/local-only mode skips audio upload entirely — nothing leaves the device.
  - 2 new HTTP cross-org leak cases (audio-chunks POST + finalize-audio POST → 404 across orgs).
  - Dedicated unit/HTTP test file `test_audio_chunks_reprocess.py` for the wire contract (5 tests).

### Changed
- `frontend/src/utils/fullAudioRecorder.ts`: new `localPersistence` + `localOnly` options. When `localPersistence` is on, each MediaRecorder `dataavailable` blob is persisted to IDB before being queued for upload (the persistence step lands first so a tab crash mid-network-request preserves the chunk). When `localOnly` is on, the server upload path is completely skipped. New `postFinalizeAudioWithVerification()` and `postFullAudio()` helpers handle the verification dance + whole-file fallback. Recorder handle gains `localBytes()` + `mimeType()` accessors so callers can label the assembled blob and surface a "buffered locally" counter.
- `backend/api/recording.py`: `/finalize-audio` accepts an optional Pydantic `FinalizeAudioVerification` body (`client_chunk_count`, `client_bytes_total`, `client_sha256`). When present, server recomputes the SHA-256 from the chunk files on disk (async via `asyncio.to_thread` so a 60MB session doesn't block the event loop) and compares to the client claim. Match returns `status=complete` and queues the reprocess; mismatch returns `status=incomplete` with the chunk-index delta and does NOT queue the reprocess. Pre-A.5 finalize-audio calls without a body still work — the verification is opt-in.
- New `/api/recordings/sessions/{id}/full-audio` endpoint (dual-auth like `/audio-chunks`) accepts a single multipart `audio` field, clears any existing chunk state for the session, writes the recovery blob as a zero-padded "000000" chunk so ffmpeg's concat step still sees it, and queues the same `_run_session_reprocess` pipeline `/finalize-audio` runs. Returns `status=complete` + `bytes_received` + `source: full_audio_fallback`.
- `frontend/src/contexts/AlwaysOnContext.tsx`: `start()` initialises the local-audio store metadata row on desktop-capable browsers and passes `localPersistence: true` (plus `localOnly` matching privacy mode) to the recorder. `stop()` runs the verify-then-fallback dance for standard sessions and finalizes the IDB session for privacy sessions. New context surface: `orphanSessions`, `resumingOrphan`, `resumeOrphanSession`, `discardOrphanSession`. `discardSession()` also wipes the local IDB mirror.
- `frontend/src/components/AlwaysOnControl.tsx`: orphan-session banner above the recording controls — only renders when state=idle and there are local sessions still pending verification.
- `frontend/src/components/MobileLiveRecording.tsx` no longer holds the recording in memory and uploads as one blob at Stop. It now spins up the same `fullAudioRecorder` desktop has used since v0.7.4: parallel MediaRecorder running at a 30s timeslice, sequential FIFO upload queue with exponential-backoff retries (max 5), idempotent on `chunk_index`. On Stop the recorder flushes its current encoder buffer, drains the queue, then the component POSTs `/finalize` followed by `/finalize-audio` to kick the server-side reprocess (Parakeet 1.1B fp16 + pyannote + Qwen 3.6 35B-A3B-Vision). A crashed Safari mid-meeting now loses at most the last 30 seconds; before this change it lost the entire recording.
- **iOS Safari MIME path verified MP4-first**: `frontend/src/utils/fullAudioRecorder.ts` `pickRecordableMime` now branches on a WebKit-family probe (UA-sniff that also catches iOS Chrome/Firefox/Edge, all of which use WKWebView) and probes `audio/mp4;codecs=mp4a.40.2` → `audio/mp4` → `audio/aac` before falling back to `audio/webm`/Opus. This pins production iOS sessions on the years-stable MP4/AAC path even on Safari 18.4+ which newly advertises WebM/Opus support. Server-side ffmpeg reassembly takes either; the choice is purely about which MediaRecorder code path is best-tested on iPhone hardware right now.
- **Mobile recorder polish**: Screen Wake Lock acquired while recording (Safari 18.4+ PWAs honor this; older versions silently no-op so we never throw); visibilitychange surfaces a "tab is in the background" amber banner because iOS can suspend a hidden MediaRecorder and we want the user to know rather than silently losing audio; a live upload-queue indicator shows `N uploaded, M queued, K dropped` so flaky network is visible instead of silent; a "Done. Server is processing." confirmation card with a deep link to Sessions appears after Stop instead of dumping the user back to idle.
- **Mobile recorder dropped the `useUploads` integration**: the `/api/uploads/start` one-shot path is replaced by `/api/recordings/start-always-on` + `/audio-chunks` + `/finalize` + `/finalize-audio`. Mobile sessions are now `mode=always_on` rows in the recording_sessions table (same as desktop browser always-on) and pick up the same server reprocess banner on SessionDetails. No backend changes.

### Fixed
- **Auth: fall back to user's first org instead of platform default** (`e186779`) — users with org memberships outside `magic-unicorn` (the platform default org slug) were getting 403s on every endpoint requiring `get_current_organization`, because `resolve_active_organization` would default to `ensure_default_organization` and then fail the membership check. Hit GFL + shafen-khan org users hardest. Fix: when `current_user.organizations` is non-empty, pick `current_user.organizations[0].organization` as the implicit active org; only call `ensure_default_organization` for users with literally zero memberships (the auto-provision case). Frontend can still override via X-Organization header or ?org= query param.
- **Live summary repeats early content**: `services/summary_slices.maybe_auto_trigger_slice` previously gated on `session.room_id` so only conference-room sessions got server-rolled slices; browser always-on used Qwen 3 0.6B INT8 in the browser, which couldn't sustain incremental summarization with previous-summary context. Gate removed — browser always-on sessions now share the same Qwen 3.6 35B-A3B-Vision server path with `triggered_by='auto-words'` (rooms keep `triggered_by='room-recorder'`). Frontend `AlwaysOnContext.triggerSummarize` now POSTs the manual slice + polls `GET /summary-slices` every 5s for standard sessions; privacy/local-only mode keeps the browser Qwen 3 0.6B path as the only option that respects the "nothing leaves the device" contract.

### Documentation
- Added `docs/compute-economics.md` (~290 lines) covering the browser-first architecture, unit-economics moat (10-100x lower per-user cost vs Otter / Granola / Fathom / Fireflies / Read.ai), competitor cost comparison with named services (AssemblyAI / Deepgram / OpenAI), proposed Free/Pro/Enterprise tier model (pricing TBD), deployment topology (magicunicorn.dev → unicorncommander.ai → enterprise), watch-outs (mobile, live browser quality, bandwidth), and the guiding principle for future architecture decisions (maximum browser-side compute, server only where quality genuinely requires it, third-party APIs only as a last resort).
- Updated `README.md` with a top-of-file "Architecture: browser-first by design" section: text diagram of browser ↔ server completion flow, the moat framing, the proposed tier shape, and the deployment progression. Links to the full strategy doc.
- Updated `CLAUDE.md` with the browser-first architecture principle near the project overview so future engineers default to browser-side compute when adding features.
- Added in-app Help page at `/help` (`frontend/src/pages/Help.tsx`) with a user-facing explainer: "Your computer does the real-time work" / "Our servers run the quality pass when your meeting ends" / "Privacy mode keeps everything local" / "Why we built it this way." Wired into the sidebar nav and routing.
- Added `docs/phase-b-server-live-streaming.md` (~1400 lines) covering server-live streaming as a paid-tier feature: WebSocket protocol (binary PCM16 framing + JSON control + sequence-replay reconnect), backend Parakeet 0.6B v3 streaming + pyannote-deferred (with Sortformer streaming as the B.3 upgrade path) + Qwen 3.6 35B-A3B rolling summary every 5s/200 words, frontend WS client with AudioWorklet PCM transcoding + 3-attempt exponential backoff + capture-only fallback, tier gating via new `User.tier` field + `tier_features` block on `/api/auth/me`, cost modeling vs Otter / Granola / Fathom / Fireflies (their $0.50-0.80/concurrent-user-hour vs our ~$0.01 on already-paid-for hardware, ~20 concurrent Pro users on current GPU footprint), <500ms first-word latency budget, failure-mode matrix (WS drops / GPU saturation / uvicorn restart / tier revoked mid-session / mid-session org reassignment), privacy-mode mutual-exclusion semantics, and a 5-phase implementation plan (~10-12 days: B.1 WS+Parakeet, B.2 rolling summary, B.3 frontend, B.4 tier gate, B.5 reconnect+backpressure+telemetry+drain). Phase B is the next chunk after the v0.8.0 Phase A bundle (mobile capture-only + desktop local-first + privacy mode end-to-end). Targeted at Pro / Enterprise users on mobile and weak desktops.

## [0.7.4] - 2026-05-21

### Changed
- **LLM consolidation**: all 6 Meeting-Ops LLM consumers now use Qwen 3.6 35B-A3B-Vision on midboy1 P40 (dedicated llama-server, -np 4 --cont-batching, 98K context, vision-capable) — same production endpoint Listing-Ops uses. Previous default gemma-4-26b-moe on bigboy 3090 retired. Frees bigboy 3090 for Parakeet/diarization/embedding workloads.
- Meeting Assistant DB row migrated from provider_type=ollama to provider_type=litellm (model_name unchanged).
- Default model environment variables (LLM_MODEL_QUALITY, LLM_MODEL_CHAT) in docker-compose.bigboy.yml and .env.bigboy* now point to Qwen 3.6.

### Added
- backend/scripts/qwen36_consolidation_bench.py: reproducible benchmark script for future model comparisons.
- Alembic migration 026_qwen36_consolidation (idempotent + reversible).

### Fixed
- Thinking-mode handling: documented that /no_think in user prompt is echoed back literally by Qwen 3.6 on llama.cpp nothink.jinja template. Correct control is chat_template_kwargs.enable_thinking: false. Memory note updated.

### Performance
- Final summary on session 103 transcript: 38.2s → 9.0s (4x faster, also more accurate).
- TTFB latency: 0.74s → 0.25s (3x faster).
- Throughput: 14.8 tok/s → 31.9 tok/s.

## [0.7.3] - 2026-05-21

### Added
- **Session attachments**: file uploads attached to session records (Granola notes, external transcripts, supporting docs, etc.).
  - Alembic 025 session_attachments table with FK cascades.
  - Garage S3 storage (bucket meeting-ops-attachments) + local-disk fallback.
  - Multipart upload, list, download, edit, delete endpoints.
  - Frontend drop-zone, list with metadata editing, paperclip icon + count on Sessions list.
- **Move session between orgs**: POST /move-org endpoint with cascade (transcripts, slices, action items, collaborators, attachments, Qdrant re-tag, audit log). Speaker-link orphan surfacing in response. Frontend modal with org dropdown.
- Design docs: appliance build extraction (~530 lines), image registry decision, Brigade integration (1332 lines).

### Changed
- **Forgejo canonical**: git.unicorncommander.ai is source of truth; git.magicunicorn.dev is backup mirror.

### Fixed
- Stale "Granite 3.3 8B" copy in Meeting Assistant description (both unified_agent.py default and live DB row).
- Clustering threshold investigation found root cause was pipeline-state degradation (not threshold value) — kept at 0.700. Filed follow-up for synthetic-WAV correctness probe.

### Removed
- Dead frontend/src/SessionDetails.tsx (root-level orphan; live route is pages/SessionDetails.tsx).

## [0.7.2] - 2026-05-21

### Fixed
- **Speaker auto-match**: embeddings now preserved end-to-end through always-on completion, file upload, and chunked recording paths. Confirmed with 0.83 similarity on test audio. /rediarize endpoint can backfill historical sessions.
- **Markdown export**: regex now accepts md/markdown, ExportOptions.includeTranscript latent crash patched, per-user filter replaced with org-scoped _get_session_for_export. PDF + DOCX 501 stubs also fixed.
- **Email modal**: renamed "Share via email", added free-form Other recipients chip section, magic-link tokens scoped to single session (cross-org safety test passing).

### Added
- Postgres backup taken pre-feature: /home/muut/backups/meet_db/meet_db_2026-05-21_pre-v072.sql.gz.

## [0.7.1] - 2026-05-20

### Added
- **Internal service token** for room_recorder → /chunks loopback POST (X-Internal-Service-Token, secrets.compare_digest, fail-closed on empty env).
- **Server-side auto-summary slice persistence** for room sessions: RecordingSession.processing_metadata.summary_slices JSONB, bounded 200/session.
- GET/POST /api/recordings/sessions/{id}/summary-slices endpoints.
- WebSocket broadcast of new slices to all room viewers.
- Per-device secret on satellite_devices (bcrypt-hashed, generated at pairing redemption).
- Alembic 024 satellite_device_secret migration.
- DeviceSecretReveal frontend component (UI wiring deferred until hardware exists).

### Security
- Satellite WebSocket /ws/satellite/{device_id}/audio now requires Authorization: Bearer device secret.
- 5 satellite HTTP endpoints gain dual-auth (device OR user).
- In-memory leaky-bucket rate limiter on failed satellite auth (5 fails / 10 min → 30-min lockout).

### Changed
- midboy2 speaker-svc autoheal + healthcheck (~8h restart cadence) prevents VRAM bloat.
- Long-term pyannote leak fix recommendations documented.

## [0.7.0] - 2026-05-20

### Added
- **Conference Room recording mode (Phase 1)**: new /rooms list + 5-step setup wizard + 3-tab detail page.
- backend/api/rooms.py with CRUD, lifecycle, pairing codes (6-digit, 10-min TTL).
- services/room_recorder.py per-room arecord subprocess + WebRTC VAD + chunk POSTs.
- Alembic 023 conference_rooms migration (rooms, audio_sources, pairing_codes, ACL).
- Multi-room concurrent native, chunk-based (no SRT/RTP/Icecast).
- Server-multi-mic as Phase 1 primary deployment.
- Live VU meters (SSE), live transcript + auto-summary panes.
- /dev/snd + audio group passed into meet-backend (USB mics now visible).

### Changed
- **UX overhaul around user intent, not mechanism**: three-card use-case picker on /record/personal (In-person / Online meeting / Mixed). On-the-fly source switching mid-recording.
- Admin section in sidebar with ShieldCheck divider.
- Settings regrouped: Your preferences / Workspace setup / Advanced.
- AdminRoute wrapper protects admin URLs.
- Alembic-first entrypoint (create_all removed — no more migration race).
- Page-flash eliminated across Rooms / Sessions / Dashboard / RoomDetail / SpeakerLibrary via localStorage hydration + matched skeletons.
- midboy2 Parakeet fp16 default pinned in compose.

### Fixed
- **Satellite API cross-org leak (CR-001)**: every endpoint now filters by organization_id.
- Diarization Off toggle plumbed through chunk pipeline.
- webrtcvad-wheels swap (setuptools 82 compatible).
- isAdminRole helper centralized in utils/roles.ts.

### Security
- Cross-org leak test extended to 29 parametrized cases (all passing).

## [0.6.0] - 2026-05-19

### Added
- **Granola-style slice-stack live summary** with auto-trigger thresholds.
- **transformers.js runtime backend** for in-browser LLM (Qwen 3 / Gemma 4 / SmolLM2).
- **Parakeet 0.6B INT8 browser STT**: audio never leaves the device when enabled.
- **Local-only privacy mode**: transcript + summary in IndexedDB, no server sync.
- **Mic UX overhaul**: device picker, USB auto-prefer, hot-swap, VU meter, mic test.
- Qwen 3 0.6B as in-browser default with structured prompt + thinking-mode off.

### Changed
- Parakeet weights served from HuggingFace directly (940 MB image bloat removed).

### Removed
- Whisper retired: STT default now Parakeet (1.95 GB VRAM freed on RTX 6000).
- Dead meet_chunks pipeline deleted (closed cross-org leak risk).
- Orphan MeetingChunkEmbedding table dropped.

## [0.5.0] and prior

See git tag annotations directly: git tag -l v0.5.0 -n100.

## [0.0.1] - 2026-02-26

### Added
- Initial versioned release.

[unreleased]: https://git.unicorncommander.ai/UnicornCommander/UC-Meeting-Ops/compare/v1.0.0...HEAD
[1.0.0]: https://git.unicorncommander.ai/UnicornCommander/UC-Meeting-Ops/releases/tag/v1.0.0
[0.9.1]: https://git.unicorncommander.ai/UnicornCommander/UC-Meeting-Ops/releases/tag/v0.9.1
[0.9.0]: https://git.unicorncommander.ai/UnicornCommander/UC-Meeting-Ops/releases/tag/v0.9.0
[0.8.2]: https://git.unicorncommander.ai/UnicornCommander/UC-Meeting-Ops/releases/tag/v0.8.2
[0.8.1]: https://git.unicorncommander.ai/UnicornCommander/UC-Meeting-Ops/releases/tag/v0.8.1
[0.8.0]: https://git.unicorncommander.ai/UnicornCommander/UC-Meeting-Ops/releases/tag/v0.8.0
[0.7.4]: https://git.unicorncommander.ai/UnicornCommander/UC-Meeting-Ops/releases/tag/v0.7.4
[0.7.3]: https://git.unicorncommander.ai/UnicornCommander/UC-Meeting-Ops/releases/tag/v0.7.3
[0.7.2]: https://git.unicorncommander.ai/UnicornCommander/UC-Meeting-Ops/releases/tag/v0.7.2
[0.7.1]: https://git.unicorncommander.ai/UnicornCommander/UC-Meeting-Ops/releases/tag/v0.7.1
[0.7.0]: https://git.unicorncommander.ai/UnicornCommander/UC-Meeting-Ops/releases/tag/v0.7.0
[0.6.0]: https://git.unicorncommander.ai/UnicornCommander/UC-Meeting-Ops/releases/tag/v0.6.0
[0.0.1]: https://git.unicorncommander.ai/UnicornCommander/UC-Meeting-Ops/releases/tag/v0.0.1
