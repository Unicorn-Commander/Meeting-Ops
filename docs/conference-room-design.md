# Conference Room Recording: Architecture Design

Status: Draft for approval. Implementation tickets at the end of this doc.
Owner: Meeting-Ops team.
Authoring date: 2026-05-20.

## 1. Purpose and Framing

Today UC-Meeting-Ops has exactly one recording surface that users interact with:
the browser. A user opens `/record`, clicks Always-On / Desktop Browser /
Mobile, and the laptop's mic does all the capture. The server only sees
finished audio chunks uploaded over HTTPS.

That surface is great for "I'm a person who wants to record a meeting I'm
attending right now." It's the wrong surface for "this room records itself,
forever, with hardware that nobody owns personally."

This doc designs the second surface — **Conference Room mode** — without
disturbing the first one. The two coexist:

| Mode | Who initiates | Where the mic is | Lifetime | Auth boundary |
|---|---|---|---|---|
| Personal / Browser | A user, per-meeting | Their device | Minutes-hours | The user |
| Conference Room | The room itself, on schedule / event / button | Physical hardware bound to the room | Indefinite | The room + room ACL |

Aaron's verbatim framing: *"for rooms where the server has a physical mic or
a satellite device that sends audio to the server or whatever, like for
permanent or semi-permanent conference recording type thing."*

The design goals are:

1. **Rooms are first-class.** A Conference Room is a database entity with
   admin lifecycle, ACL, retention policy, and a hardware binding — not a
   user with a fake browser.
2. **Multiple hardware paths converge to one pipeline.** Server-attached
   USB, network audio stream, ESP32 / RPi / Mac Mini satellite, and
   companion-app room hosts all land in the same Whisper / diarization /
   summary path.
3. **Don't break what works.** AlwaysOnContext, DesktopBrowserRecorder, the
   `/api/recordings/start-always-on` chunk pipeline, and the mobile shell
   stay exactly as they are. Conference Room is additive.
4. **Reuse the existing satellite infrastructure.** `SatelliteDevice`
   table, `/api/satellites/*` endpoints, `/ws/satellite/.../audio`, and the
   `source_type='satellite_*'` extensions on `recording_sessions` already
   exist. This design wraps them in a "Room" abstraction rather than
   replacing them.

## 2. What Already Exists (Survey Result)

Before designing anything new, a survey of the codebase on `magicunicorn`
shows the following already in place:

### Backend

- `database/models.py::SatelliteDevice` — device registry table with
  `device_id`, `name`, `room_name`, `device_type`, `capabilities`,
  `ip_address`, `last_heartbeat`, `status`, `firmware_version`,
  `config`, `api_key`, `current_session_id`, `organization_id`
  (nullable today).
- `database/models.py::RecordingSession` extensions — `source_device_id`,
  `source_type` (with values `local_mic`, `satellite_stream`,
  `satellite_upload`, `satellite_transcript`, `companion_app`,
  `browser_always_on`), `room_name`.
- `api/satellite_api.py` (719 lines) — CRUD + heartbeat + audio-upload +
  transcript-upload + start/stop-recording. **Scoped by user only, NOT by
  organization** (see Section 12).
- `api/websocket_satellite.py` (409 lines) — `/ws/satellite/{device_id}/audio`
  WebSocket receiver that handles raw PCM streaming, WAV finalization,
  resumes within a 60-second reconnect window, and triggers
  `process_recording()` on disconnect.
- `api/websocket_remote_audio.py` (706 lines) — the companion-app
  equivalent for `/ws/remote-audio/{session_id}`.
- `services/always_on_recorder.py` — host-mic, single-server state machine
  with VAD-based segmentation. This is the closest thing to "room mode"
  today, but it's bound to *the server's* microphone, not a generic Room.
- `services/live_transcription_service.py` — host-mic continuous
  transcription with a 60-minute circular buffer + retroactive session
  creation.
- `audio_level_direct_usb.py` — direct `arecord` subprocess capture from
  `hw:0,0`. The current "server-attached USB mic" path, but hard-coded.
- `docs/satellite-devices-design.md` — full ESP32 + RPi protocol spec.
  Reusable; this doc references it rather than restating it.
- `docs/WYOMING_PROTOCOL.md` (336 lines) — alternate ESP32 path via
  Home Assistant's Wyoming protocol on port 10700, including wake words.
- `docs/companion-app-design.md` — the Mac/PC companion app spec; relevant
  for room-host machines but a separate user story.
- `docs/always-on-recording-design.md` — silence-gap segmentation spec,
  which this doc reuses for unattended room recording.

### Frontend

- `pages/LiveRecording.tsx` — wraps `AlwaysOnControl`, `DesktopBrowserRecorder`,
  the legacy host-mic UI (hidden behind `false &&`), and the mobile shell.
- `contexts/AlwaysOnContext.tsx` (1542 lines) — VAD, chunk upload, browser
  STT, browser LLM live-summary, device picker, source-mode picker
  (mic/tab/mic+tab).
- `components/AlwaysOnControl.tsx`, `components/DesktopBrowserRecorder.tsx`,
  `components/MobileLiveRecording.tsx` — the three current per-user
  recording surfaces.
- **No frontend code touches `satellite_api`, no `/rooms` page, no
  Conference Room UI exists.** This is the gap.

### Migrations

Through `022_stt_default_parakeet.py` plus the
`b18939734458_drop_orphan_meeting_chunk_embeddings_` revision. Next
migration this design touches: `023_conference_rooms`.

## 3. Mental Model: Three Layers

```
+--------------------------------------------------------------------+
|  Layer 3:  Room                                                    |
|   - Persistent admin-owned entity                                  |
|   - Owns retention policy, ACL, scheduling, naming                 |
|   - Binds to >=1 audio source                                      |
+--------------------------------------------------------------------+
                              |  has many
                              v
+--------------------------------------------------------------------+
|  Layer 2:  Audio Source                                            |
|   - Server-attached mic (ALSA / PipeWire)                          |
|   - Network audio stream (RTP/SRT/Icecast)                         |
|   - Satellite device (ESP32-S3, RPi, Mac Mini)                     |
|   - Companion app on a room-host machine                           |
+--------------------------------------------------------------------+
                              |  produces
                              v
+--------------------------------------------------------------------+
|  Layer 1:  Recording Session                                       |
|   - The thing you watch / read / search                            |
|   - source_type tells you which path it came from                  |
|   - room_id tells you which room (NULL for personal/browser)       |
+--------------------------------------------------------------------+
```

The browser/personal path lives entirely in Layer 1 — it has no Layer 2
device and no Layer 3 room. The new mode adds Layer 3 and formalizes the
Layer 2 abstraction.

## 4. User Journey

### 4.1 Initial setup (admin)

1. Admin navigates to `/rooms` in the org dashboard. Empty state with
   "Add Conference Room" CTA.
2. Wizard at `/rooms/new`:
   - Step 1: Name ("Conference Room A") + location ("HQ, 2nd floor").
   - Step 2: Pick an audio source:
     - **Server-attached USB mic** — picker shows the
       `arecord -L` enumeration on the host (PipeWire / ALSA devices).
     - **Network audio stream** — admin pastes an RTP / SRT / Icecast URL
       and we validate by probing for 5s of audio.
     - **Satellite device** — admin gets a 6-digit pairing code; an
       ESP32 / RPi / Mac Mini on the same Tailnet enters it during
       firmware first-boot.
   - Step 3: Recording mode:
     - **Manual only** — admin / member presses Start / Stop in the UI.
     - **Scheduled** — cron-like schedule ("Weekdays 09:00-17:00 ET").
     - **Always-on** — silence-gap segmentation runs 24/7 (reuses
       `services/always_on_recorder.py`).
     - **Wake-word triggered** — Wyoming wake word starts recording.
       Out of scope for Phase 1.
   - Step 4: Retention policy ("90 days" default; admin can pick 7 / 30
     / 90 / 365 / forever / legal-hold).
   - Step 5: ACL ("org members can view recordings from this room" /
     "only these users / groups").
3. After submit: room appears in `/rooms`, status `idle`, hardware
   `healthy` (or `unbound` if no device has paired yet).

### 4.2 Daily use

- **Scheduled** room: cron triggers `room.start_session()` automatically
  at the scheduled time. Session ends on schedule or on silence-gap
  threshold.
- **Always-on** room: device streams continuously; the silence-gap state
  machine in `always_on_recorder.py` opens / closes sessions
  automatically.
- **Manual** room: any org member with `room.record` permission can press
  Start in `/rooms/{id}`. Anyone with `room.record` can press Stop.
- All sessions are visible at `/sessions?room_id={id}` and on the room's
  detail page.

### 4.3 Multi-room

An org can register N rooms. Each room is independent: its own hardware
binding, schedule, retention, ACL. The org's sidebar gets a "Rooms"
section listing all rooms with live status (idle / recording / offline /
error) and a green/red dot.

## 5. Hardware Sources, Ranked

Ordered simplest -> most flexible. Phase numbers refer to Section 16.

### 5.1 Server-attached USB mic [Phase 1]

The server has a physical USB mic plugged into it. Already half-implemented
via `audio_level_direct_usb.py` and `services/working_audio_service.py`
(both currently hard-code `hw:0,0`).

- Discovery: `arecord -L` enumerates devices on boot. Admin picks one in
  the wizard. We persist `pipewire_node_name` (preferred) or
  `alsa_device_string` (fallback) in `audio_sources.config`.
- Capture: long-lived `arecord -D <device> -f S16_LE -r 16000 -c 1 -t raw`
  subprocess managed by a new `services/room_recorder.py`. One process
  per active room.
- Failure mode: if the device disappears (USB unplug), state goes to
  `error`; we don't auto-create empty sessions during this window.

Pros: simplest possible. Zero firmware. No network involved.
Cons: physically tethers the room to wherever the server is. Doesn't
scale past 1-2 rooms before the server becomes the cable nightmare.

### 5.2 Network audio stream [Phase 2]

A dedicated PC / Mac / IP audio interface in the room runs a small agent
(or off-the-shelf software like OBS, Icecast, or `srt-live-transmit`)
that pushes audio to a server endpoint over the LAN.

- Protocol options (we accept all three):
  - **RTP** — `udp://0.0.0.0:5004`; server runs ffmpeg listener.
  - **SRT** — `srt://server:9000?streamid=room-A&latency=200`;
    SRT is firewall-friendlier than RTP, has FEC, recommended.
  - **Icecast / HTTP** — `http://server:9001/room-A.opus`; admin pushes
    via `darkice` or similar.
- Capture: ffmpeg listener subprocess managed by `room_recorder.py`,
  one process per active source.
- Discovery: admin supplies the listen URL; the room polls / heartbeats
  via a sidecar status endpoint.

Pros: decouples the mic from the server. Works for any room with a PC
already in it (most do). Lower-cost than satellites for buildings with
existing equipment.
Cons: requires SOMETHING in the room to push audio. Not zero-touch.

### 5.3 Satellite device (ESP32, RPi, Mac Mini) [Phase 3]

The full satellite story is already specced in `satellite-devices-design.md`.
This doc reuses that spec verbatim — see Section 6 for protocol details
— and only adds the new "Room" wrapper.

Pros: dedicated hardware per room, cheap (ESP32 = ~$15, RPi = ~$130),
zero-touch with mDNS + pairing code, supports store-and-forward for
WiFi-flaky rooms.
Cons: real hardware to deploy and maintain. Firmware updates over OTA
are a real engineering item.

### 5.4 Companion app on a room-host Mac / PC [Phase 4]

A Mac Mini or sub-NUC in the room runs the companion app from
`companion-app-design.md` permanently. The room-host machine is treated
as a Room device of type `companion-app`. Same WebSocket protocol as the
satellite path. This is the high-end / studio-grade tier for rooms that
want system audio capture too (e.g. share a Zoom mix into the recording).

## 6. Satellite Device Protocol

The protocol is **already specified** in `satellite-devices-design.md`.
Quick summary so this doc stands on its own; the source-of-truth is that
file:

- **Auth**: device sends `device_id` + `API key` over WebSocket (`X-API-Key`
  header or query param). API key is generated at pairing and stored
  hashed in `satellite_devices.api_key`.
- **Streaming**: WS to `/ws/satellite/{device_id}/audio`. Server sends
  back `{ "session_id": "..." }`. Device sends binary PCM frames
  (16 kHz / 16-bit / mono / little-endian) every ~100 ms.
- **Heartbeat**: `POST /api/satellites/{device_id}/heartbeat` every
  30 s with `{ status, battery_pct?, wifi_rssi?, free_sd_mb? }`.
  Server flips device to `offline` after 90 s of silence.
- **Reconnection**: server holds the session open for 60 s after WS
  disconnect; if the device reconnects within that window, it appends to
  the same WAV file. Beyond 60 s, a new session begins on next connect.
- **Store-and-forward**: device records to SD card if WiFi is down,
  uploads via `POST /api/satellites/{device_id}/upload-audio` when
  network returns, deletes local file on 200 OK.
- **Local STT (RPi only)**: optional whisper.cpp on the device; sends
  transcript via `POST /api/satellites/{device_id}/transcript`.
- **mDNS discovery**: device looks up `_meetingops-server._tcp.local`;
  server advertises `_meetingops-satellite._tcp.local` for inverse
  discovery. Tailscale MagicDNS works for cross-VLAN.

What this design adds on top of the existing protocol:

- **Pairing code**: today `POST /api/satellites/register` is open to any
  authenticated user. We add a 6-digit one-shot pairing code that the
  admin generates from `/rooms/{id}/setup`. The code maps to a
  `room_id`, expires after 10 minutes, and pre-fills the device's
  organization + room. This solves "who owns this device" cleanly.
- **Room binding**: registration must include a valid pairing code OR
  an existing API key from a previous pairing. Bare registrations
  without a code go to `room_id=NULL` and require admin assignment.
- **Re-pairing**: a device whose API key is revoked can re-pair via a
  new code. Old recordings stay attributed to the same `device_id`.

## 7. Data Model Additions

Migration: `023_conference_rooms`.

### 7.1 New table: `conference_rooms`

```sql
CREATE TABLE conference_rooms (
    id                  SERIAL PRIMARY KEY,
    organization_id     INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name                VARCHAR(200) NOT NULL,
    location            VARCHAR(200),
    description         TEXT,
    -- Recording behavior
    recording_mode      VARCHAR(20) NOT NULL DEFAULT 'manual',
        -- 'manual' | 'scheduled' | 'always_on' | 'wake_word'
    schedule_cron       VARCHAR(100),       -- nullable; e.g. '0 9-17 * * 1-5'
    schedule_timezone   VARCHAR(50),        -- e.g. 'America/New_York'
    silence_gap_minutes INTEGER DEFAULT 5,  -- for always_on mode
    -- Retention
    retention_days      INTEGER,            -- NULL = forever; legal hold sets to NULL too
    legal_hold          BOOLEAN NOT NULL DEFAULT FALSE,
    -- ACL (denormalized for fast filtering; details in room_acl below)
    default_visibility  VARCHAR(20) NOT NULL DEFAULT 'org_members',
        -- 'org_members' | 'restricted' | 'public_link'
    -- Lifecycle
    status              VARCHAR(20) NOT NULL DEFAULT 'idle',
        -- 'idle' | 'recording' | 'offline' | 'error' | 'paused'
    current_session_id  VARCHAR(100),       -- pointer to active recording_sessions.session_id
    last_recording_at   TIMESTAMPTZ,
    -- Timestamps
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by_user_id  INTEGER REFERENCES users(id) ON DELETE SET NULL,
    UNIQUE (organization_id, name)
);
CREATE INDEX ix_conference_rooms_org ON conference_rooms (organization_id);
CREATE INDEX ix_conference_rooms_status ON conference_rooms (status);
```

### 7.2 New table: `room_audio_sources`

A room can bind to one *active* source but keep N configured (for
hot-swap during maintenance).

```sql
CREATE TABLE room_audio_sources (
    id              SERIAL PRIMARY KEY,
    room_id         INTEGER NOT NULL REFERENCES conference_rooms(id) ON DELETE CASCADE,
    source_type     VARCHAR(30) NOT NULL,
        -- 'host_mic' | 'network_stream' | 'satellite' | 'companion_app'
    is_active       BOOLEAN NOT NULL DEFAULT FALSE,
    config          JSONB NOT NULL DEFAULT '{}',
        -- host_mic:        {"pipewire_node": "alsa_input...", "alsa_device": "hw:0,0"}
        -- network_stream:  {"protocol": "srt", "listen_url": "srt://0.0.0.0:9000?...", "stream_id": "room-A"}
        -- satellite:       {"device_id": "esp32-room-a-001"}   -- FK-by-string into satellite_devices
        -- companion_app:   {"device_id": "macmini-room-a"}
    last_audio_at   TIMESTAMPTZ,
    health_status   VARCHAR(20) DEFAULT 'unknown',
        -- 'healthy' | 'degraded' | 'offline' | 'unbound' | 'error'
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ix_room_audio_sources_room ON room_audio_sources (room_id);
CREATE UNIQUE INDEX ix_room_audio_sources_active
    ON room_audio_sources (room_id) WHERE is_active = TRUE;
```

### 7.3 New table: `room_pairing_codes`

```sql
CREATE TABLE room_pairing_codes (
    id              SERIAL PRIMARY KEY,
    room_id         INTEGER NOT NULL REFERENCES conference_rooms(id) ON DELETE CASCADE,
    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    code            VARCHAR(8) NOT NULL UNIQUE,   -- 6-digit numeric; UNIQUE globally for cross-org safety
    expires_at      TIMESTAMPTZ NOT NULL,         -- now() + 10 min
    consumed_at     TIMESTAMPTZ,                  -- nullable; set on successful pair
    consumed_by_device_id VARCHAR(100),           -- nullable; the satellite_devices.device_id that consumed it
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL
);
CREATE INDEX ix_room_pairing_codes_active
    ON room_pairing_codes (code) WHERE consumed_at IS NULL;
```

### 7.4 New table: `room_acl`

Per-room access overrides on top of org membership.

```sql
CREATE TABLE room_acl (
    id              SERIAL PRIMARY KEY,
    room_id         INTEGER NOT NULL REFERENCES conference_rooms(id) ON DELETE CASCADE,
    user_id         INTEGER REFERENCES users(id) ON DELETE CASCADE,
    email           CITEXT,        -- for external invitees, future
    access_level    VARCHAR(20) NOT NULL,
        -- 'view' | 'record' | 'manage'
    granted_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (user_id IS NOT NULL OR email IS NOT NULL)
);
CREATE INDEX ix_room_acl_room_user ON room_acl (room_id, user_id);
```

### 7.5 Extend `satellite_devices`

```sql
ALTER TABLE satellite_devices
    ADD COLUMN IF NOT EXISTS room_id INTEGER REFERENCES conference_rooms(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS pairing_code_id INTEGER REFERENCES room_pairing_codes(id) ON DELETE SET NULL;
-- organization_id is already nullable; backfill from room_id and tighten to NOT NULL once backfilled.
CREATE INDEX ix_satellite_devices_room ON satellite_devices (room_id);
```

### 7.6 Extend `recording_sessions`

```sql
ALTER TABLE recording_sessions
    ADD COLUMN IF NOT EXISTS room_id INTEGER REFERENCES conference_rooms(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS legal_hold BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS retention_expires_at TIMESTAMPTZ;  -- null = inherit room policy / forever
CREATE INDEX ix_recording_sessions_room ON recording_sessions (room_id);
CREATE INDEX ix_recording_sessions_retention
    ON recording_sessions (retention_expires_at)
    WHERE retention_expires_at IS NOT NULL AND legal_hold = FALSE;
```

`source_type` already accepts the satellite values. We add one more
constant: `room_host_mic` for Phase 1 server-attached-USB sessions, so
that auditors can tell host-mic sessions apart from the legacy
`local_mic` value used by the silence-gap recorder. We do NOT rename the
existing `local_mic` — that would migration-thrash analytics queries.

## 8. API Surface

### 8.1 New endpoints — Room CRUD + lifecycle

| Method | Endpoint | Purpose | Auth |
|---|---|---|---|
| `POST` | `/api/rooms` | Admin creates a room | `org_admin` |
| `GET` | `/api/rooms` | List rooms in active org | `org_member` |
| `GET` | `/api/rooms/{id}` | Room detail (live status + sources + recent sessions) | `room.view` |
| `PATCH` | `/api/rooms/{id}` | Update room (name/schedule/retention/ACL) | `org_admin` |
| `DELETE` | `/api/rooms/{id}` | Soft-delete; recordings keep attribution | `org_admin` |
| `POST` | `/api/rooms/{id}/sources` | Bind a new audio source | `org_admin` |
| `PATCH` | `/api/rooms/{id}/sources/{src_id}` | Update source / mark active | `org_admin` |
| `DELETE` | `/api/rooms/{id}/sources/{src_id}` | Remove a source | `org_admin` |
| `POST` | `/api/rooms/{id}/pairing-codes` | Generate a 6-digit pairing code | `org_admin` |
| `GET` | `/api/rooms/{id}/pairing-codes` | List active codes (for debugging) | `org_admin` |
| `POST` | `/api/rooms/{id}/recordings/start` | Manual start | `room.record` |
| `POST` | `/api/rooms/{id}/recordings/stop` | Manual stop | `room.record` |
| `GET` | `/api/rooms/{id}/recordings` | Sessions for this room (filterable) | `room.view` |
| `POST` | `/api/rooms/{id}/probe-source` | Capture 5 s of audio to validate a binding | `org_admin` |
| `GET` | `/api/rooms/host-devices` | Enumerate USB / ALSA / PipeWire devices on the server | `org_admin` |
| `POST` | `/api/rooms/{id}/legal-hold` | Set / clear legal hold (blocks retention purge) | `org_admin` |

### 8.2 Modified endpoints — satellite registration

`POST /api/satellites/register` gains an optional `pairing_code` field.
When supplied:

- Validate code is unused and not expired.
- Set `room_id` and `organization_id` from the code's room.
- Generate API key, return to device.
- Mark code consumed.

When omitted: legacy behavior (creates a device with `room_id=NULL` that
an admin must assign manually via `PATCH /api/satellites/{device_id}`).

### 8.3 WebSocket endpoints — unchanged

`/ws/satellite/{device_id}/audio` keeps its current contract. The server
looks up `device.room_id` once at session-create time and sets
`recording_sessions.room_id` accordingly. No new WS endpoint needed for
satellites.

### 8.4 New WebSocket — host-mic + network-stream

For Phase-1 server-attached USB and Phase-2 network audio, we don't need
a new WS endpoint — there's no remote party. Capture happens
server-locally inside `services/room_recorder.py`. The room admin UI
subscribes to live transcripts via the existing
`/api/live-transcription/ws` channel, scoped by `room_id` (a new query
parameter).

## 9. Frontend Routes & Components

### 9.1 New routes

```
/rooms                          List of rooms, live status grid
/rooms/new                      Setup wizard (Step 1-5)
/rooms/:id                      Detail: live transcript, sources, sessions, settings
/rooms/:id/setup                Re-run the wizard for an existing room
/rooms/:id/pair                 Pairing code display (auto-refreshes every 5 s)
/rooms/:id/sessions             Sessions filtered to this room
```

### 9.2 Renamed / clarified routes

- `/record` -> stays as a redirect alias for backward compatibility, but
  the canonical name becomes **`/record/personal`** to disambiguate from
  `/record/conference/{room_id}` (rare manual-trigger UI).
- Add a redirect: `/record` -> `/record/personal`.
- `LiveRecording.tsx` stays; we add a tiny `<RoomRecordingPanel
  roomId={...} />` for the conference path that wraps the same VAD-free
  transcript stream.

### 9.3 New components

- `pages/Rooms.tsx` — list + live status (red/green/yellow dot, current
  session pill).
- `pages/RoomDetail.tsx` — three tabs: Live (transcript ticker, audio
  level meter, Stop button if `room.record`), Sessions (table filtered
  by `room_id`), Settings (sources, schedule, retention, ACL).
- `pages/RoomSetupWizard.tsx` — 5-step wizard (Section 4.1).
- `components/RoomCard.tsx` — used on `/rooms` list.
- `components/RoomStatusDot.tsx` — pulsing red when recording.
- `components/AudioSourcePicker.tsx` — server-mic dropdown,
  network-stream URL field, satellite pairing-code generator.
- `components/RoomLiveTranscript.tsx` — WS subscription on
  `/api/live-transcription/ws?room_id={id}`.
- `components/RoomScheduleEditor.tsx` — cron expression builder UI.
- `components/RoomRetentionPanel.tsx` — retention picker + legal-hold
  toggle.
- `services/roomsApi.ts` — typed REST client for `/api/rooms/*`.

The sidebar (`SimplifiedNavigation`) adds a "Rooms" entry between
"Sessions" and "Speakers", visible to all org members (rooms list is
read-visible to all; mutation is admin-only).

## 10. Multi-Mic / Multi-Speaker Handling

Conference rooms often have multiple mics. Three configurations to
support, in order of complexity:

### 10.1 Mic-shared (one channel, everyone on it)

The simplest and most common. Single I2S mic, ceiling mic, or
omnidirectional mic. We diarize with our existing pyannote / ONNX path.
This works today. Phase 1 ships this only.

### 10.2 Mic-per-speaker (N channels, one speaker each)

A boardroom with personal lavaliers or a table-mic array that exposes
per-mic channels. Two sub-cases:

- **Channels arrive at the server already separated** (multi-channel WAV
  or multiple synchronized RTP streams). We extend `RecordingSession`
  with a `channels` JSON field that records `[{"channel_index": 0,
  "speaker_id": 17, "label": "Aaron"}]`. Diarization becomes trivial —
  the channel IS the speaker. Each channel runs Whisper separately, then
  we time-merge.
- **Channels need separation server-side** — beamforming, voice
  separation. Out of scope until Phase 4.

### 10.3 Pre-registered speaker roster

Every Conference Room can have a roster of expected attendees
(`room_speaker_roster` table — out of scope for this doc but trivially
addable). Diarization quality is dramatically better with a known-N
prior. Phase 4.

### 10.4 Beamforming / source localization

Out of scope for v1-v3. Flagged for Phase 5 as the "appliance" tier
when we own the hardware.

## 11. STT / LLM Routing for Rooms

Rooms always use **server-side STT**. There is no browser involved when
the source is hardware — pushing a hardware audio stream into WebGPU
makes no sense.

- STT path: same Parakeet-on-midboy2 + Whisper-server-on-bigboy chain
  the rest of the app uses. The router in
  `services/stt_model_manager.py` already picks per-org defaults.
- LLM live-summary path: server-side via `unified_agent_service`. Rooms
  do not need browser-LLM rolling summary; they're not bandwidth-bound.
  Final summary uses the org's configured LLM provider, same as today.
- Privacy mode: **N/A** for rooms (privacy mode is a per-user
  on-device-only flag; rooms are by definition shared / off-device).
  The privacy mode UI should hide itself when viewing room sessions.

## 12. Access Control & Multi-Tenancy

### 12.1 The bug we found in the survey

`api/satellite_api.py` today scopes by `current_user` only. There is no
`organization_id` check on list / get / update / delete. A user in Org A
can see and mutate satellites belonging to Org B. The
`SatelliteDevice.organization_id` column exists but is `nullable=True`
and is NOT filtered in the API queries.

**This must be fixed before Conference Room ships**, otherwise the new
room ACL is meaningless. Ticket included in Section 17.

### 12.2 New permission strings

| Permission | Granted to | Effect |
|---|---|---|
| `room.view` | Anyone in `room_acl` with level `view`+ OR org member when `default_visibility='org_members'` | Read room + sessions |
| `room.record` | `room_acl` level `record`+ OR org `member` role | Manual start / stop |
| `room.manage` | `room_acl` level `manage` OR org `admin` role | Edit settings, ACL, retention |

ACL resolves in this order: explicit `room_acl` row > `default_visibility` > deny.

### 12.3 Federation

Cross-UC-instance rooms (e.g. a `magicunicorn.dev` room visible from
`brightwaterlabs.example`) are **out of scope for v1**. The schema is
federation-ready: `room_id` is opaque, devices auth with API keys, all
endpoints accept tokens minted by the Unicorn Commander federation
layer.

## 13. Retention Policy

- Default: 90 days. Configurable per room: 7 / 30 / 90 / 365 / forever
  / legal-hold.
- `retention_expires_at` is set at session-finalize time as
  `session.ended_at + room.retention_days`.
- Legal hold sets `legal_hold=TRUE` on every session and clears
  `retention_expires_at` on those sessions; the room itself flips
  `legal_hold=TRUE` so new sessions inherit.
- A nightly cron (`services/retention_sweeper.py`, new) deletes audio +
  transcripts where `retention_expires_at < now()` AND `legal_hold = FALSE`.
- Soft-delete first (mark `status='archived'`, move WAV to cold
  storage), then hard-delete after 30 days in archived state. Audit-log
  every deletion.
- Compliance hook: webhook `room.retention_expiring_soon` fires 7 days
  before purge so legal can intervene.

## 14. Comparison Matrix: Personal vs Conference Room

| Dimension | Personal / Browser | Conference Room |
|---|---|---|
| Audio source | The user's device mic | Hardware bound to a room |
| Who starts / stops | The user | Schedule / event / authorized user |
| Who can access | Owner + collaborators they invite | Org members (by default) + room ACL |
| Default retention | None enforced (manual delete) | 90 days, per-room override |
| Compute path | Browser STT + browser LLM live-summary; server STT for final | Server STT throughout |
| Recording lifetime | Minutes-hours | Indefinite, often 24/7 |
| Bandwidth / storage | Bounded by user device | Bounded by room schedule + retention |
| Multi-mic | No | Yes (Phase 4+) |
| Privacy mode | Available (on-device-only) | N/A |
| Auth boundary | User JWT | User JWT for control plane + device API key for data plane |
| Legal hold | No | Yes |
| Scheduling | No | Yes (cron) |
| Setup cost | Open `/record` | Admin wizard + optional hardware install |
| Failure mode if server down | User can still record locally (privacy mode) | Satellites store-and-forward; host-mic loses audio |
| Cancellation cost | Close tab | Stop schedule, decommission hardware |

## 15. Phased Rollout

### Phase 1 — Host-Mic MVP (target: 1-2 weeks)

Goal: validate end-to-end Conference Room without any new hardware.

- Migration `023_conference_rooms` (rooms / sources / acl / pairing
  codes; satellite_devices.room_id; recording_sessions.room_id).
- `api/rooms.py` — CRUD + start/stop + host-device enumeration.
- `services/room_recorder.py` — one-arecord-subprocess-per-room.
- `services/retention_sweeper.py` — basic cron deleter (no archive).
- Frontend: `/rooms` list, setup wizard (host-mic step only),
  `/rooms/:id` detail with live transcript + Start / Stop.
- Bug fix: scope `api/satellite_api.py` by `organization_id`.

What's deliberately not in Phase 1: scheduled mode, satellite devices,
network audio, legal hold, multi-mic. **One room per server in Phase 1**
(constrained by `room_recorder` not yet supporting multiple concurrent
ALSA subprocesses on the same host).

### Phase 2 — Scheduled + multi-room (target: 1 week)

- Cron-driven start/stop in `room_recorder.py`.
- Per-org concurrency limit (configurable, default 4 concurrent rooms).
- `RoomScheduleEditor.tsx` UI.
- Cron sweeper (`services/room_scheduler.py`).
- Retention configuration UI + legal-hold flag.

### Phase 3 — Satellite Device Integration (target: 2-3 weeks)

Reuse the existing satellite infra:

- Pairing code system (`room_pairing_codes` table + `/api/rooms/{id}/pairing-codes`).
- Modify `satellite_api.register` to honor codes.
- Frontend: `/rooms/:id/pair` page with auto-refresh code display.
- ESP32 firmware skeleton (`firmware/esp32-satellite/` in the repo) —
  reads pairing code from BLE Provisioning or a captive portal, calls
  `/api/satellites/register`.
- RPi reference image — Ansible playbook in `deploy/rpi-satellite/`
  that installs the Python streaming agent + systemd unit.

### Phase 4 — Multi-mic + Network Stream (target: 2-3 weeks)

- Network audio source (RTP / SRT / Icecast) via ffmpeg listener.
- Multi-channel WAV ingestion with per-channel speaker labeling.
- Pre-registered speaker roster (`room_speaker_roster`).
- Diarization pipeline branch for "channels are speakers".

### Phase 5 — Appliance / SDVOSB SMB Product (target: TBD)

- Custom hardware (RPi 5 + beamforming mic array + PoE), pre-imaged.
- Beamforming + source localization (likely Respeaker XVF3800 +
  on-device WebRTC AEC).
- Wake-word activation (reuse Wyoming Protocol path; integrate with
  the existing wake-word doc).
- Federation support so SMBs on different UC tenants can deploy.
- This is the "buy a box, plug it in, recordings appear in your UC"
  product. Phase 5 unlocks the SDVOSB hardware play CJ Williams flagged.

## 16. Open Questions for Aaron

1. **Phase 1 single-room limit**: is shipping with one-room-per-server
   acceptable for MVP, or does Phase 1 need to handle 2-4 concurrent
   host-mic rooms day one? (Multiplexing one USB device into N sessions
   is doable but adds complexity.)
2. **Storage tiering**: Section 13 proposes soft-delete -> cold-storage
   archive -> hard-delete. Do you want a Garage bucket pre-allocated
   for cold storage now, or punt to Phase 2 when retention is enforced?
3. **Mac Mini as room host (companion-app)**: should that ship inside
   Phase 3 alongside satellites, or wait until the companion app itself
   has shipped Phase 2 (mic + system audio on macOS)? They're coupled.
4. **Network audio protocol default**: SRT is the recommended choice
   (FEC, firewall-friendly). Are you okay with making RTP / Icecast
   optional / advanced-tab settings, or do you want all three at parity
   in the UI?
5. **Pairing-code length**: 6-digit numeric balances usability vs. brute
   force (1M codes, 10-min TTL, rate-limited). Want longer / alphanum
   for production?
6. **Cron vs. native scheduler**: should the schedule run inside the
   FastAPI process (APScheduler) or as a separate systemd timer? The
   FastAPI process is simpler but adds restart-sensitivity. Recommend
   APScheduler with a Postgres job store.
7. **Legal hold UX**: only org admins, or do we need a dedicated "legal
   officer" role? (Not introducing a new role unless asked.)
8. **Beamforming hardware**: Respeaker XVF3800 vs. a custom MEMS array
   for Phase 5 — partner decision involving CJ Williams / SDVOSB
   roadmap. Out of scope here but worth flagging.

## 17. Ticket Breakdown

Each ticket is sized S (~1 day), M (~2-4 days), L (1-2 weeks). All file
paths are absolute under `/home/muut/Production/UC-Meeting-Ops/src/`.

### CR-001 [S] Fix multi-tenancy bug in satellite_api.py
- **Scope**: scope every query in `backend/api/satellite_api.py` by
  `organization_id`; require `get_current_organization` dep alongside
  `get_current_user`; backfill `satellite_devices.organization_id`
  from the inviter; flip column to `NOT NULL`.
- **Deps**: none. Blocker for CR-005 onward.
- **Files**: `backend/api/satellite_api.py`,
  `backend/alembic/versions/022_*.py` (new migration to backfill +
  tighten).

### CR-002 [M] Migration `023_conference_rooms`
- **Scope**: create `conference_rooms`, `room_audio_sources`,
  `room_pairing_codes`, `room_acl`; extend `satellite_devices` +
  `recording_sessions` per Section 7.
- **Deps**: CR-001.
- **Files**: `backend/alembic/versions/023_conference_rooms.py`,
  `backend/database/models.py`.

### CR-003 [L] Backend: `api/rooms.py` (CRUD + lifecycle)
- **Scope**: all endpoints in Section 8.1 (room CRUD, source binding,
  pairing-code generation, manual start / stop, recordings filter,
  host-device enumeration, source probe). Pydantic models + permission
  checks against `room_acl`.
- **Deps**: CR-002.
- **Files**: `backend/api/rooms.py` (new), `backend/main.py`
  (router registration), `backend/auth/permissions.py` (new
  permission strings).

### CR-004 [M] Backend: `services/room_recorder.py`
- **Scope**: one-arecord-subprocess-per-room service. Manages
  PipeWire/ALSA capture, writes WAV progressively (reuse helpers from
  `websocket_satellite.py`), creates `RecordingSession` rows with
  `room_id` set, feeds Whisper pipeline. Handles process restart on
  device-disappear with backoff.
- **Deps**: CR-002.
- **Files**: `backend/services/room_recorder.py` (new),
  `backend/services/working_audio_service.py` (extract reusable
  host-device enumeration), small refactor of
  `audio_level_direct_usb.py`.

### CR-005 [M] Pairing code system
- **Scope**: code generation endpoint, validation in
  `satellite_api.register`, expiry / consumption logic, frontend
  `/rooms/:id/pair` page.
- **Deps**: CR-001, CR-002, CR-003.
- **Files**: `backend/api/rooms.py` (`/pairing-codes` endpoints),
  `backend/api/satellite_api.py` (consume codes in register),
  `frontend/src/pages/RoomPair.tsx` (new).

### CR-006 [L] Frontend: `/rooms` + setup wizard
- **Scope**: list page, detail page (Live / Sessions / Settings tabs),
  5-step wizard, audio-source picker, sidebar entry, redirect
  `/record` -> `/record/personal`, room status dot, room card.
- **Deps**: CR-003.
- **Files**: `frontend/src/pages/Rooms.tsx`,
  `frontend/src/pages/RoomDetail.tsx`,
  `frontend/src/pages/RoomSetupWizard.tsx`,
  `frontend/src/components/RoomCard.tsx`,
  `frontend/src/components/RoomStatusDot.tsx`,
  `frontend/src/components/AudioSourcePicker.tsx`,
  `frontend/src/components/RoomLiveTranscript.tsx`,
  `frontend/src/services/roomsApi.ts`,
  `frontend/src/AppRouterSimplified.tsx`.

### CR-007 [M] Live transcript WS room scoping
- **Scope**: add `?room_id={id}` query parameter to
  `/api/live-transcription/ws`; broadcast room-tagged segments;
  frontend subscribes per-room on `RoomDetail`.
- **Deps**: CR-003, CR-004.
- **Files**: `backend/api/live_transcription.py`,
  `backend/services/live_transcription_service.py`,
  `frontend/src/components/RoomLiveTranscript.tsx`.

### CR-008 [M] Retention sweeper
- **Scope**: nightly job that purges sessions where
  `retention_expires_at < now()` AND `legal_hold = FALSE`. Two-stage:
  soft-delete (status='archived') first, hard-delete after 30 days.
  Audit log on every deletion. APScheduler with Postgres job store.
- **Deps**: CR-002.
- **Files**: `backend/services/retention_sweeper.py` (new),
  `backend/services/scheduler.py` (new APScheduler bootstrap),
  `backend/main.py` (start scheduler).

### CR-009 [M] Scheduled-mode recording
- **Scope**: cron expression on `conference_rooms.schedule_cron`;
  APScheduler triggers start / stop. Time-zone-aware. UI:
  `RoomScheduleEditor.tsx` with cron presets ("Weekdays 9-5", "Custom...").
- **Deps**: CR-003, CR-004, CR-008 (shares APScheduler).
- **Files**: `backend/services/room_scheduler.py` (new),
  `backend/api/rooms.py` (cron validation),
  `frontend/src/components/RoomScheduleEditor.tsx`.

### CR-010 [M] Always-on mode wiring
- **Scope**: connect `services/always_on_recorder.py` to a Room.
  Today it's a singleton; refactor to per-room instances keyed by
  `room_id`. Silence-gap threshold from `conference_rooms.silence_gap_minutes`.
- **Deps**: CR-002, CR-004.
- **Files**: `backend/services/always_on_recorder.py`,
  `backend/api/rooms.py` (mode='always_on' handler).

### CR-011 [L] Satellite device frontend
- **Scope**: surface paired devices in `/rooms/:id` detail (Sources
  tab), show device telemetry (battery, RSSI, free SD), allow
  re-pair / decommission. Hook up the existing `satellite_api.py`
  endpoints (now org-scoped after CR-001).
- **Deps**: CR-001, CR-005, CR-006.
- **Files**: `frontend/src/components/SatelliteDevicePanel.tsx` (new),
  `frontend/src/services/satellitesApi.ts` (new),
  `frontend/src/pages/RoomDetail.tsx`.

### CR-012 [L] ESP32 firmware skeleton
- **Scope**: minimal Arduino / ESP-IDF project that pairs via captive
  portal, streams I2S audio to
  `/ws/satellite/{device_id}/audio`. mDNS server discovery. Heartbeat
  every 30 s. Status LED. No SD card / store-and-forward in this
  ticket (separate ticket later).
- **Deps**: CR-005.
- **Files**: `firmware/esp32-satellite/` (new repo subdir),
  `firmware/esp32-satellite/README.md` (assembly + flash steps).

### CR-013 [L] RPi reference satellite image
- **Scope**: Ansible playbook that installs a Python streaming agent
  + systemd unit. Pairs via QR code shown on first boot (HDMI). Same
  WebSocket streaming as ESP32, optional local Whisper via
  `whisper.cpp`.
- **Deps**: CR-005.
- **Files**: `deploy/rpi-satellite/playbook.yml` (new),
  `deploy/rpi-satellite/agent.py` (new),
  `deploy/rpi-satellite/README.md`.

### CR-014 [M] Network audio source (SRT / RTP / Icecast)
- **Scope**: ffmpeg-based listener in `room_recorder.py`. SRT default;
  RTP + Icecast behind an "advanced" tab. Probe endpoint
  (`/api/rooms/{id}/probe-source`) captures 5 s and returns RMS +
  spectrogram thumbnail for the admin to verify.
- **Deps**: CR-003, CR-004.
- **Files**: `backend/services/room_recorder.py`,
  `backend/api/rooms.py`,
  `frontend/src/components/AudioSourcePicker.tsx`.

### CR-015 [M] Legal hold + audit log
- **Scope**: `/api/rooms/{id}/legal-hold` endpoint; admin UI to set
  / clear; audit-log table entry on every change; retention sweeper
  skips legal-hold sessions; UI shows a lock badge on held sessions.
- **Deps**: CR-002, CR-008.
- **Files**: `backend/api/rooms.py`, `backend/services/retention_sweeper.py`,
  `frontend/src/components/RoomRetentionPanel.tsx`.

### CR-016 [S] Documentation + sample configs
- **Scope**: update `README.md` + `INSTALL.md` with a Conference Room
  section; ship two sample configs (`rooms/example-host-mic.json`,
  `rooms/example-srt.json`); add to the CHANGELOG.
- **Deps**: CR-006 (so the UI is real).
- **Files**: `README.md`, `INSTALL.md`, `docs/rooms-quickstart.md`
  (new).

## 18. Out of Scope (Explicit)

- Real-time multi-room audio mixing (e.g. "Room A and Room B as a single
  session"). Sessions are per-room.
- Cross-tenant federation of rooms (covered in `FEDERATION_TRUST_MODES.md`
  separately).
- Live broadcast of room audio to external clients. Rooms are recording
  surfaces, not streaming surfaces.
- AEC / echo cancellation for satellites — defer to hardware that
  ships with on-device AEC (Respeaker, MEMS arrays with DSPs).
- Per-channel speaker re-identification across sessions (Phase 4+
  enhancement on top of the speaker library).
- Mobile satellite clients (e.g. a phone in a coat pocket). Use the
  existing personal/browser path.

## 19. Compatibility Notes

- The new mode adds tables and columns. **No existing data is
  modified.** All current `recording_sessions` rows keep `room_id =
  NULL` and are classified as personal sessions.
- `source_type` accepts a new value (`room_host_mic`) but the existing
  values are unchanged.
- All new API endpoints are namespaced under `/api/rooms/*`. The
  existing `/api/satellites/*` endpoints continue to work; the only
  observable change is that registration starts honoring a new optional
  `pairing_code` field and queries now filter by org.
- Frontend: `/record` keeps working (redirects to `/record/personal`).
  No existing user-facing URL breaks.

## 20. Success Criteria

Phase 1 is "done" when an admin can:

1. Plug a USB mic into bigboy.
2. Open `/rooms`, click "Add Conference Room", pick the USB mic in the
   wizard.
3. Click Start. The room status flips to red / "Recording". The live
   transcript appears in the room detail page.
4. Click Stop. A new session appears in `/sessions` with
   `room_id=<id>`, the WAV is on disk, the summary is generated.
5. Open the session, listen back, read the transcript. Looks like any
   other session except it's tagged with the room.

If all of that works without touching the existing browser-recording
flow, Phase 1 is shipped.
