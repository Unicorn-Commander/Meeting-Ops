# Phase B.3 integration plan

Pre-written 2026-05-26 while the 4 B.3 spike/impl agents run in parallel.

This memo documents the integration target after the four B.3 chunks land:
A (AudioWorklet), B (Opus codec utilities), C (true NeMo streaming),
D (Sortformer streaming diarization).

The actual integration code waits for the agent branches to return. This
memo + a small env-var scaffold are the only changes landed up-front; they
default OFF so v1 production behavior is unchanged.

## Scope of integration (what I do after agents return)

The four B.3 agents produce independent feature branches. Integration =
merging them onto `main` with the wiring layer they intentionally left out.

### A. AudioWorklet (branch `b3-audioworklet`)

**What agent ships**: `frontend/src/pages/StreamingTest.tsx` migrated from
`ScriptProcessorNode` → `AudioWorklet`. New worklet processor JS file. New
`audioWorkletCapture` helper. Wire format unchanged — 19-byte BE header +
PCM16 payload at 16 kHz mono, 200ms frames. Production behavior unchanged
when the browser supports AudioWorklet (Chrome 66+, Firefox 76+, Safari 14.1+).

**Integration work**: none. Self-contained client-side change. Just merge.

**Risk**: medium — browser audio thread changes can have subtle behavior
differences (sample-accurate timing, buffer sizes). Manual mic-test
verification before merging to main.

### B. Opus codec utilities (branch `b3-opus-codec`)

**What agent ships**: `frontend/src/utils/opusEncoder.ts` (WebCodecs primary
+ MediaRecorder fallback) and `services/parakeet-stream-svc/opus_decoder.py`
(libopus binding). Standalone modules with unit tests. NOT integrated into
the capture path.

**Integration work** (after both A and B land):
1. In `StreamingTest.tsx` (A's owned file), add a format toggle: "PCM16
   (default)" vs "Opus (smaller payload)". Wire the toggle to swap between
   sending PCM16 frames vs encoding via `opusEncoder.encode()` and sending
   Opus frames. Set the format byte in the 19-byte header accordingly
   (`"PC16"` vs `"OPUS"`).
2. In `services/parakeet-stream-svc/main.py`, detect the format byte on
   incoming chunks. For `"OPUS"`, decode via `OpusDecoder` from B before
   running through Parakeet (Parakeet wants PCM16). For `"PC16"`, current
   path unchanged.
3. In `backend/api/streaming.py`, no change needed — the backend passes
   the audio through to parakeet-stream-svc as a WAV body; format
   conversion can happen either at the backend or at the svc. Cleanest
   is at the svc since it owns the model interface.

**Risk**: medium. MediaRecorder produces Opus-in-WebM (not raw Opus
packets); the encoder needs to demux. Per agent B's brief, the agent will
document this. May require additional wrapping.

### C. True NeMo streaming with draft+finalize tokens (branch `b3-nemo-streaming-spike`)

**What agent ships** (spike, may not be fully shipping):
- New endpoint `/transcribe-stream-v2` in `services/parakeet-stream-svc/main.py`
  that uses NeMo's streaming API and emits `tokens_finalized` + `tokens_draft`
- Spike report at `docs/phase-b3-nemo-streaming-spike.md`
- Old `/transcribe-stream` endpoint preserved for back-compat
- Possible: new requirements.txt entries (e.g. `nemo_toolkit[asr-streaming]`)

**Integration work** (depends on C's spike outcome):
- If C ships v2 as production-ready: flip `STREAMING_USE_V2_PARAKEET=1` in
  `.env.bigboy`, update `backend/api/streaming.py` to:
  - POST to `/transcribe-stream-v2` instead of `/transcribe-stream`
  - Pass through `tokens_finalized` + `tokens_draft` arrays in the partial
    JSON frame back to the WS client
  - Update the partial frame schema in `StreamingTest.tsx` to render
    draft tokens distinctly (e.g. grey italic) and finalize tokens as
    confirmed text (green left border, replacing the matching draft)
- If C ships v2 as needs-more-work: keep v1 path, schedule follow-up

**Risk**: high. NeMo streaming API for parakeet-tdt-0.6b-v3 may not be
fully exposed; agent C's brief explicitly asks for honest "this is what
the model supports" answer.

### D. Sortformer streaming diarization (branch `b3-sortformer-spike`)

**What agent ships** (spike, may not be fully shipping):
- New service directory `services/sortformer-svc/` with Dockerfile, main.py,
  requirements.txt, README
- `POST /diarize-stream` endpoint returning speaker labels
- Spike report at `docs/phase-b3-sortformer-spike.md`
- VRAM co-residency findings on midboy2 GPU 0

**Integration work** (depends on D's spike outcome + VRAM verdict):
- If D ships as production-ready and GPU 0 has headroom: add
  - `meet-sortformer-svc` to `/home/muut/uc-meeting-ops-deploy/midboy2/docker-compose.midboy2.yml`
  - `SORTFORMER_URL` env var to `.env.bigboy`
  - Backend WS forwarder: parallel `httpx.post` to sortformer in addition to
    parakeet (via `asyncio.gather`); merge `speakers: [...]` array into the
    partial JSON
  - Frontend: render speaker label badges next to transcript text
- If D ships as needs-more-work or VRAM-blocked: document the GPU-eviction
  decision needed (move speaker-svc to midboy1 P40? upgrade midboy2 GPU?)

**Risk**: high. Streaming Sortformer on a 12GB consumer GPU shared with
parakeet-batch + parakeet-stream + post-hoc speaker-svc may not fit. The
spike answers this.

## Env-var scaffolding shipped up-front

Adding three flags to `backend/api/streaming.py`, all default OFF:

```python
# Phase B.3 integration flags - all default OFF so v1 behavior is unchanged.
# Flip per env after the corresponding B.3 chunk lands + is verified.
STREAMING_USE_V2_PARAKEET = os.getenv("STREAMING_USE_V2_PARAKEET", "0") not in ("0", "false", "no")
STREAMING_USE_SORTFORMER = os.getenv("STREAMING_USE_SORTFORMER", "0") not in ("0", "false", "no")
SORTFORMER_URL = os.getenv("SORTFORMER_URL", "http://100.66.42.57:8896").rstrip("/")
```

These are read but not yet referenced by code paths. They exist so the
integration PR (post-B.3-agent-completion) can land with config-only
toggles instead of also adding env support in the same commit.

## Wire-format extensions reserved

The 19-byte BE frame header has 4 ASCII chars for format. Currently used:
- `"PC16"` — 16 kHz mono PCM16 (only format supported in production)

Reserved by B.3:
- `"OPUS"` — Opus packets (chunk B)
- `"AACL"` — AAC-LC (mobile-native, no current implementation)

Partial JSON frame extensions reserved by B.3:
- `tokens_finalized: [{text, start_ms, end_ms, confidence}, ...]` (chunk C)
- `tokens_draft: [{text, start_ms, end_ms}, ...]` (chunk C)
- `speakers: [{spk_id, start_ms, end_ms}, ...]` (chunk D)

Clients render these only when present; v1 clients ignore unknown keys.

## Verification plan for the final integrated PR

1. v1 path regression: with all flags OFF, current StreamingTest behavior
   unchanged. Existing tests (`test_streaming_*`) pass.
2. AudioWorklet (A): mic-test in Chrome + Firefox + Safari. Confirm partial
   transcripts still arrive at parity with the ScriptProcessorNode path.
3. Opus (A+B): toggle format selector, verify smaller bandwidth (Network
   tab in DevTools) and same transcript quality.
4. v2 streaming (C): `STREAMING_USE_V2_PARAKEET=1` on staging, mic-test,
   confirm draft tokens appear + are replaced by finalize.
5. Sortformer (D): `STREAMING_USE_SORTFORMER=1` on staging, mic-test with
   2 speakers, confirm speaker labels appear in real-time.

## Sequencing

1. A (low risk, must ship) → merge first, manual browser smoke
2. B (utility only, no integration) → merge second after own tests pass
3. C spike-or-ship → merge third (or queue if not shipping)
4. D spike-or-ship → merge fourth (or queue if not shipping)
5. Integration PR with full wiring → after 1-4 are decided, ships as a single
   PR with all flags + new partial-JSON renderers + sortformer compose
   addition + UI polish

After all of B.3 ships, cut v1.2.0.
