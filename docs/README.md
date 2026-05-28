# UC-Meeting-Ops Design Documents

Design and architecture documents for UC-Meeting-Ops.

Last updated: 2026-05-27.

This directory contains design notes, architecture decisions, operational
references, and roadmap documents. Status labels describe the document's
relationship to the product as of the last updated date.

## Architecture and economics

- [`compute-economics.md`](compute-economics.md) (294 lines). Status: live. Browser-first compute model, unit-economics moat at 10-100x vs Otter, Granola, Fathom, and Fireflies, proposed Free, Pro, and Enterprise tiers, and deployment topology from `magicunicorn.dev` to `unicorncommander.ai` to enterprise. Reflects shipped v0.7.4, v0.8.0, and v0.8.1 architecture.

## Storage, protocols, and capture devices

- [`audio-storage-garage.md`](audio-storage-garage.md). Status: live (cutover complete, v3.9.0). Canonical meeting audio in the Garage `meeting-ops-audio` bucket: the `media_storage` / `session_media` modules, the `audio_storage_backend` / `audio_object_key` columns (alembic 031), read/write/delete flow, the backfill + eviction scripts, bucket provisioning, and the Garage HEAD-400 gotcha.
- [`POSTGRESQL_QDRANT_SETUP.md`](POSTGRESQL_QDRANT_SETUP.md) (333 lines). Status: live guide. PostgreSQL and Qdrant setup, SQLite migration, semantic search endpoints, and vector-search operating notes.
- [`WYOMING_PROTOCOL.md`](WYOMING_PROTOCOL.md) (336 lines). Status: designed reference. Wyoming Protocol integration for Home Assistant satellite microphones, wake words, gesture controls, and remote activation devices.
- [`always-on-recording-design.md`](always-on-recording-design.md) (183 lines). Status: designed, partly superseded by browser always-on work. Continuous recording and silence-gap segmentation design for server-side always-on capture.
- [`companion-app-design.md`](companion-app-design.md) (396 lines). Status: designed. Lightweight desktop companion app for microphone and system-audio capture, with macOS Swift native as the primary path and Electron as a cross-platform fallback.
- [`satellite-devices-design.md`](satellite-devices-design.md) (379 lines). Status: designed, with supporting backend infrastructure already present. ESP32-S3 and Raspberry Pi satellite-device architecture for multi-room recording, store-and-forward upload, and optional local STT.

## Mobile roadmap (A → B → C-1 → C-2 → C-3)

Phased plan to bring Meeting-Ops to mobile, watch, and native devices. Phase A complete in v0.8.0 and v0.8.1. Subsequent phases are designed and queued.

- **Phase A, mobile PWA capture-only.** Status: shipped v0.8.0. See [`../CHANGELOG.md`](../CHANGELOG.md).
- [`phase-b-server-live-streaming.md`](phase-b-server-live-streaming.md) (1410 lines). Status: designed. Server-live streaming as a paid-tier feature: WebSocket protocol, Parakeet 0.6B v3 streaming on midboy2, Qwen 3.6 35B rolling summary, tier gating, cost modeling, and a 5-phase implementation plan. All 4 open questions are locked.
- [`phase-c1-native-ios-design.md`](phase-c1-native-ios-design.md) (1386 lines). Status: designed. Native iOS plus Core ML plus watchOS extension. Swift and SwiftUI are required for Watch. FluidInference and FluidAudio Swift Package provide Parakeet 0.6B at 110x RTF on M4 Pro. Apple Foundation Models 3B, available on iOS 26+, provide the on-device LLM. The doc contains a 5-phase, 8-10 week plan for a v1 closed beta.
- **Phase C-2, watchOS extension on top of C-1.** Status: future.
- **Phase C-3, native Android plus NNAPI.** Status: future.

## Bulk operations

- [`bulk-audio-import-design.md`](bulk-audio-import-design.md) (1054 lines). Status: designed. `/import` page for the 526-file audio backlog. Covers the job queue, in-process asyncio for v1, Arq plus Redis migration in v4, per-file pipeline, speaker auto-linking from the `Call with X` filename pattern, and a 4-phase plan estimated at about 5 working days.

## Conference rooms

- [`conference-room-design.md`](conference-room-design.md) (1136 lines). Status: Phase 1 shipped, Phases 2-5 designed. Multi-room native model, USB mic primary path, chunk-based recording, room abstraction, satellite integration, and future administrative lifecycle.

## Agent platform (planning)

- [`agent-platform-roadmap.md`](agent-platform-roadmap.md). Status: planning. The next arc — conversational + app-driving + voice agent. Inventories the existing foundation (per-meeting + cross-meeting RAG in `ai_chat.py` + Qdrant, the Brigade FalkorDB graph, the 8 read-only MCP tools, the `agents.py`/`agent_tools.py` framework, TTS/STT building blocks), names the gaps, and lays out a 4-phase plan (solidify RAG + graph → safe app-control MCP write tools → agent runtime → voice) plus the key design decisions and operational context.

## Ecosystem integration

- [`brigade-integration-design.md`](brigade-integration-design.md) (1332 lines). Status: designed. Meeting-Ops to Brigade graph writer and 3D viewer. Writes Meeting, Speaker, ActionItem, Topic, and Decision nodes to Brigade FalkorDB on session completion. Tenancy modes are `shared`, `per_org_graph`, and `per_org_instance` via environment variable. Includes the HIPAA path for Legacy1.

## Deployment and distribution

- [`appliance-extraction-design.md`](appliance-extraction-design.md) (530 lines). Status: designed. Extract appliance build to `UC-Meeting-Ops-Appliance` via git submodule for enterprise on-prem packaging.
- [`screen-recording-design.md`](screen-recording-design.md) (1268 lines). Status: Phase 1 designed. Personal screen plus audio MVP, capture paths, browser constraints, and implementation plan.
- [`image-registry-decision.md`](image-registry-decision.md) (143 lines). Status: decision recorded, implementation deferred. Recommends the Forgejo container registry at `git.unicorncommander.ai` as canonical image distribution.

## Reading order for new developers

1. Read [`compute-economics.md`](compute-economics.md) first. It explains why the architecture is browser-first and why server compute is rationed.
2. Read [`phase-b-server-live-streaming.md`](phase-b-server-live-streaming.md) and [`phase-c1-native-ios-design.md`](phase-c1-native-ios-design.md) in either order. Together they explain the forward mobile and native roadmap.
3. Read [`bulk-audio-import-design.md`](bulk-audio-import-design.md). It is concrete near-term implementation work.
4. Skim the conference-room, Brigade, appliance, and screen-recording documents as needed for the feature area being changed.

This file is hand-maintained alongside design-document commits. It can lag behind the directory. If exact counts matter, verify them with `wc -l docs/*.md`.
