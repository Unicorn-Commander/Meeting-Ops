# Changelog

All notable changes to UC-Meeting-Ops are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- meeting-ops.magicunicorn.dev (hyphenated) as alias for canonical meetingops.magicunicorn.dev. Cloudflare CNAME (proxied) + Traefik 308 redirect via redirectregex middleware. Cookies/sessions stay on canonical; URL works either way.
- **Browser always-on full audio capture + server-side reprocess**: parallel `MediaRecorder` track on the same MediaStream as the VAD engine produces continuous WebM/Opus (or MP4 on Safari) chunks every 30s; each chunk POSTs to new `/api/recordings/sessions/{id}/audio-chunks` with exponential-backoff retries (max 5). On session end, `/finalize-audio` reassembles via ffmpeg and kicks a BackgroundTasks pipeline: Parakeet 1.1B fp16 → pyannote diarization (`return_embeddings=true`) → `identify_speakers()` → Qwen 3.6 35B-A3B-Vision final summary. `processing_metadata.reprocess_status` drives a banner on SessionDetails (in_progress → complete). Privacy/local-only mode skips audio upload entirely — nothing leaves the device.
  - 2 new HTTP cross-org leak cases (audio-chunks POST + finalize-audio POST → 404 across orgs).
  - Dedicated unit/HTTP test file `test_audio_chunks_reprocess.py` for the wire contract (5 tests).

### Fixed
- **Live summary repeats early content**: `services/summary_slices.maybe_auto_trigger_slice` previously gated on `session.room_id` so only conference-room sessions got server-rolled slices; browser always-on used Qwen 3 0.6B INT8 in the browser, which couldn't sustain incremental summarization with previous-summary context. Gate removed — browser always-on sessions now share the same Qwen 3.6 35B-A3B-Vision server path with `triggered_by='auto-words'` (rooms keep `triggered_by='room-recorder'`). Frontend `AlwaysOnContext.triggerSummarize` now POSTs the manual slice + polls `GET /summary-slices` every 5s for standard sessions; privacy/local-only mode keeps the browser Qwen 3 0.6B path as the only option that respects the "nothing leaves the device" contract.

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

[unreleased]: https://git.unicorncommander.ai/UnicornCommander/UC-Meeting-Ops/compare/v0.7.4...HEAD
[0.7.4]: https://git.unicorncommander.ai/UnicornCommander/UC-Meeting-Ops/releases/tag/v0.7.4
[0.7.3]: https://git.unicorncommander.ai/UnicornCommander/UC-Meeting-Ops/releases/tag/v0.7.3
[0.7.2]: https://git.unicorncommander.ai/UnicornCommander/UC-Meeting-Ops/releases/tag/v0.7.2
[0.7.1]: https://git.unicorncommander.ai/UnicornCommander/UC-Meeting-Ops/releases/tag/v0.7.1
[0.7.0]: https://git.unicorncommander.ai/UnicornCommander/UC-Meeting-Ops/releases/tag/v0.7.0
[0.6.0]: https://git.unicorncommander.ai/UnicornCommander/UC-Meeting-Ops/releases/tag/v0.6.0
[0.0.1]: https://git.unicorncommander.ai/UnicornCommander/UC-Meeting-Ops/releases/tag/v0.0.1
