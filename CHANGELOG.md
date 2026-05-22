# Changelog

All notable changes to UC-Meeting-Ops are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[unreleased]: https://git.unicorncommander.ai/UnicornCommander/UC-Meeting-Ops/compare/v0.8.0...HEAD
[0.8.0]: https://git.unicorncommander.ai/UnicornCommander/UC-Meeting-Ops/releases/tag/v0.8.0
[0.7.4]: https://git.unicorncommander.ai/UnicornCommander/UC-Meeting-Ops/releases/tag/v0.7.4
[0.7.3]: https://git.unicorncommander.ai/UnicornCommander/UC-Meeting-Ops/releases/tag/v0.7.3
[0.7.2]: https://git.unicorncommander.ai/UnicornCommander/UC-Meeting-Ops/releases/tag/v0.7.2
[0.7.1]: https://git.unicorncommander.ai/UnicornCommander/UC-Meeting-Ops/releases/tag/v0.7.1
[0.7.0]: https://git.unicorncommander.ai/UnicornCommander/UC-Meeting-Ops/releases/tag/v0.7.0
[0.6.0]: https://git.unicorncommander.ai/UnicornCommander/UC-Meeting-Ops/releases/tag/v0.6.0
[0.0.1]: https://git.unicorncommander.ai/UnicornCommander/UC-Meeting-Ops/releases/tag/v0.0.1
