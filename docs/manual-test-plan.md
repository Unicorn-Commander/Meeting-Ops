# Meeting-Ops — Manual Test Plan (v3.57.x)

*For a human tester. No special tooling needed — a laptop with Chrome, an iPhone, and about
60–90 minutes. Written 2026-07-17 against v3.57.3.*

**Where to test:** production — https://meeting-ops.unicorncommander.ai
(dogfood https://meetingops.magicunicorn.dev exercises the same code with an oauth2-proxy in
front; use prod unless told otherwise).

**How to report:** for each test mark ✅ / ❌ / ⚠️ (worked but something felt off) and jot one
line. For failures: what you clicked, what you expected, what happened, and a screenshot.
Browser console errors (F12 → Console, red lines) are gold — paste them.

| # | Area | Result | Notes |
|---|---|---|---|
| 1 | Landing page | | |
| 2 | Signup & login | | |
| 3 | Record a meeting (server mode) | | |
| 4 | The session record | | |
| 5 | Speakers | | |
| 6 | Local-only (privacy) mode | | |
| 7 | Sharing / cross-org | | |
| 8 | Session self-heal | | |
| 9 | iPhone — Safari + native app | | |
| 10 | Billing (AARON ONLY) | | |

---

## 1. Landing page (logged out, desktop)

1. Open https://meeting-ops.unicorncommander.ai in a private/incognito window.
   - Browser tab reads **"Meeting-Ops — Meetings become memory, decisions, and work"**.
   - The **officer-unicorn watermark** is faintly visible behind the big headline — present
     but subtle, never making the headline hard to read.
2. Refresh 4–5 times. The **headline changes between refreshes** (random pick from a set).
   It should never change *while* you're reading — only on refresh.
3. Scroll the whole page. Sections fade in as you scroll; nothing stays invisible or blank.
   Every screenshot loads; click 2–3 of them — each opens a **full-size lightbox** (Esc or
   click to close).
4. Click **Pricing** in the nav — Free and Pro ($15/mo launch) cards render. FAQ questions
   expand. The platforms strip links to the **App Store** (opens Apple's page for
   Meeting-Ops).
5. Phone check: open the same URL on your phone — no horizontal scrolling, buttons tappable,
   screenshots readable.

## 2. Signup & login

1. **Fresh Google signup** (use a Google account that has never signed in here):
   click Start free → sign up with Google. *Take your time on Google's screens — a
   past bug 403'd signups that took longer than 15 minutes; it should now be fine.*
   You should land signed in, with no error page.
2. Sign out, then sign back in with the same account — lands on the app, no re-consent loop.
3. Close the tab, reopen the site the **next day** — you should still be signed in
   (session policy is now 3 days idle / 30 days max).

## 3. Record a meeting (server mode, desktop Chrome)

1. Start an always-on recording. Talk (or play a podcast) for **at least 3–4 minutes** with
   two different voices if possible.
2. While recording: live transcript streams; the telemetry tiles (VAD, Elapsed, Chunks,
   Sessions, Current) update, and each shows a **tooltip on hover** explaining what it is.
3. The stuck-recording warning should **not** appear during normal recording or while the
   post-stop processing spinner runs.
4. Stop. The session should move through processing → **completed** (give it ~1–2 min).
5. Open the session: summary, action items, transcript with speaker labels, and a title all
   present. Card headers are readable (no white-on-white).

## 4. The session record

Open a completed session (the one from test 3 is fine):

1. **Audio playback** — the player plays, seeks, and shows the right duration (a past bug
   404'd audio on shared sessions; it should play everywhere now).
2. **Export Summary** (Quick Action) — downloads a PDF; if PDF generation is unavailable it
   downloads Markdown instead and says so. Either way, *something* downloads and a toast
   confirms it.
3. **Copy Action Items** (Quick Action) — pastes a sensible action-item list.
4. **Voice summary (TTS)** — plays audio of the summary. *Also check: does the UI label say
   Kokoro (correct) or VibeVoice (stale label — report it)?*
5. Durations on the session cards read like `93:08`, never `93:7.6932…`.

## 5. Speakers

1. Open a session with 2+ speakers. **Re-detect speakers** with a speaker-count hint of 2 —
   the roster should come back with exactly 2 (a past bug could never *reduce* the count).
2. **Name a speaker** — a toast says the summary will refresh; within ~1 minute the summary
   regenerates using the name. The name also shows on the session card and in every past
   session with that voice.

## 6. Local-only (privacy) mode — desktop Chrome

1. Start a recording with **privacy/local-only ON**. Confirm the UI says audio stays on
   device.
2. **Short meeting:** talk ~1–2 minutes, stop. Even this short session ends with a real
   summary (a past bug left short local meetings with none).
3. **Longer meeting:** record 10–15 min, stop. Watch the status line: after the live-quality
   summary it should say the full-quality pass is running **in short segments** and then show
   live progress — `Transcribing locally — 4 of ~12 min (33%)`. **The page must stay
   responsive the whole time** (switch tabs, scroll — no beachball, no frozen UI). It ends
   with a higher-quality transcript + summary in Local Sessions.
4. If you're on a machine with less than 8 GB RAM and the recording is over ~1 h, the pass
   should *skip* with a clear explanation and keep the live summary — that's correct
   behavior, not a bug.

## 7. Sharing / cross-org

*Needs a session shared to you from another workspace (or switch your active org away from
the one that owns the session).*

1. Open the shared session: transcript, summary, insights, attachments, and **audio
   playback** all work.
2. Open the **Knowledge Graph tab** on that shared session — it renders (this was the last
   tab that 404'd cross-org; fixed in v3.57.0).
3. **Reprocess** the shared session — it queues and completes instead of "Session not found
   in organization".

## 8. Session self-heal

1. Leave the app open and idle for a few hours (lunch works). Come back, click anything that
   loads data.
2. If the session had silently expired you should see a brief **"Reconnecting…"** overlay
   that signs you back in and returns you to the page — **no dead buttons, no
   silently-doing-nothing UI** (the old failure mode). If you never see the overlay, that's
   fine too — it means the session was still alive.
3. Faster variant (optional, technical): DevTools → Application → Cookies → delete all for
   the site → click any button. The overlay should appear and recover.

## 9. iPhone — Safari + native app

**Safari (meeting-ops.unicorncommander.ai):**
1. Start an always-on recording, record ~2 min, stop — session appears and processes.
2. **Lock-screen check:** start a recording, lock the phone for 2 minutes, unlock. Does the
   recording survive, or does a **Resume/Discard banner** appear on reopen? Note exactly
   what you saw — we're verifying how much audio iOS suspend still loses.

**Native app** ([App Store — Meeting-Ops](https://apps.apple.com/us/app/meeting-ops/id6780018348)):
3. Install, sign in with the same account (Unicorn Commander SSO) — your sessions list
   matches the web.
4. Record a short session in the app — it appears on the web too.

## 10. Billing — AARON ONLY (real card)

1. From a test account on the Free tier: Ops-Center storefront → Meeting-Ops Pro with promo
   code `PROJECTOPS-1DOLLAR` ($1/30d) → complete checkout with a real card.
2. Within ~a minute of completing: the MO account shows **Pro**, and server-pass features
   (studio transcript, reprocess) unlock after next login.
3. Sanity: MO's own Pricing page for an **already-subscribed** user routes to the Stripe
   billing portal (manage/cancel), not a second checkout.

---

### Known-fine things (don't report these)

- The full-quality local pass **skipping** on phones, non-WebGPU browsers, or very long
  recordings — by design; the live summary is the record.
- Landing headline being different from a screenshot you saw earlier — it rotates per
  refresh.
- First local recording downloading ~900 MB of models (one-time, cached).
- `?static=1` on the landing URL disables the scroll-fade animation — it's a capture/tooling
  flag, not a bug.
