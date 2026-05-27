import React from 'react';
import {
  Cpu,
  Server,
  Shield,
  Globe,
  Zap,
  Clock,
  ArrowRight,
  Mic,
  Brain,
  Lock,
  Smartphone,
  Users,
  Radio,
  Circle,
  FolderTree,
  FileText,
  MessageSquare,
  Download,
  Search,
  Building2,
  Database,
  Tag,
} from 'lucide-react';

/**
 * Help page — user-facing explainer for how Meeting-Ops actually
 * works under the hood. Not for engineers or investors; this is for
 * the user who hits Record and wonders "what is this thing doing
 * with my audio."
 *
 * The substance: live work runs in your browser, the polish pass
 * runs on our servers when the meeting ends, privacy mode keeps
 * everything local. Plain language. The full strategy doc lives at
 * docs/compute-economics.md for anyone who wants the deep version.
 */
export default function Help() {
  return (
    <div className="h-full overflow-y-auto bg-zinc-950 px-4 py-6 md:px-8 md:py-8">
      <div className="mx-auto max-w-3xl space-y-10">
        <header>
          <h1 className="text-2xl font-semibold text-zinc-100 md:text-3xl">
            How Meeting-Ops works
          </h1>
          <p className="mt-3 text-zinc-400">
            How to use it, where your audio goes, and why we built it this way.
            Jump to <span className="text-zinc-300">Using Meeting-Ops</span> for
            the practical guide, or <span className="text-zinc-300">How it
            works</span> for what's happening under the hood.
          </p>
        </header>

        {/* ----------------------------- Using ----------------------------- */}
        <div className="space-y-10">
          <h2 className="text-xl font-semibold text-fuchsia-300 border-b border-zinc-800 pb-2">
            Using Meeting-Ops
          </h2>

          <section className="space-y-4">
            <div className="flex items-center gap-3">
              <Mic className="h-5 w-5 text-fuchsia-400" />
              <h3 className="text-lg font-semibold text-zinc-100">
                Recording a meeting
              </h3>
            </div>
            <p className="text-zinc-300">
              Go to <span className="text-zinc-100">Record</span> and pick how
              you want to capture audio, then hit record. The live transcript
              and a rolling summary build as you talk; tap Stop when you're
              done and the finished transcript + summary land in your sessions.
            </p>
            <ul className="space-y-2 text-zinc-300">
              <li className="flex items-start gap-3">
                <Circle className="mt-1 h-3 w-3 flex-shrink-0 text-zinc-500" />
                <span>
                  <span className="text-zinc-100">Just me</span> — captures your
                  microphone only. Good for in-person meetings and dictation.
                </span>
              </li>
              <li className="flex items-start gap-3">
                <Circle className="mt-1 h-3 w-3 flex-shrink-0 text-zinc-500" />
                <span>
                  <span className="text-zinc-100">Me + system audio</span> —
                  also captures what's playing on your computer (the other
                  people on a video call, a webinar). Your browser will ask you
                  to share a tab or screen <em>with audio</em> — keep that box
                  checked.
                </span>
              </li>
            </ul>
          </section>

          <section className="space-y-4">
            <div className="flex items-center gap-3">
              <FolderTree className="h-5 w-5 text-fuchsia-400" />
              <h3 className="text-lg font-semibold text-zinc-100">
                Finding meetings: Sessions &amp; Folders
              </h3>
            </div>
            <p className="text-zinc-300">
              The <span className="text-zinc-100">Sessions</span> page lists
              every meeting with full-text search and filters. Switch to the{' '}
              <span className="text-zinc-100">Folders</span> view to group them.
            </p>
            <ul className="space-y-2 text-zinc-300">
              <li className="flex items-start gap-3">
                <Tag className="mt-0.5 h-4 w-4 flex-shrink-0 text-zinc-500" />
                <span>
                  Folders <span className="text-zinc-100">are tags</span> — so a
                  single meeting can live in several folders at once (e.g. a
                  client folder <em>and</em> a project folder). The rail shows
                  each folder with a session count, plus "All sessions" and
                  "Ungrouped".
                </span>
              </li>
              <li className="flex items-start gap-3">
                <Search className="mt-0.5 h-4 w-4 flex-shrink-0 text-zinc-500" />
                <span>
                  Make a folder with <span className="text-zinc-100">New
                  folder</span>, then select one or more sessions and{' '}
                  <span className="text-zinc-100">Add to folder</span>. Remove
                  them the same way. The flat list, search, and filters are
                  always still there.
                </span>
              </li>
            </ul>
          </section>

          <section className="space-y-4">
            <div className="flex items-center gap-3">
              <Building2 className="h-5 w-5 text-fuchsia-400" />
              <h3 className="text-lg font-semibold text-zinc-100">
                Conference rooms &amp; microphones
              </h3>
            </div>
            <p className="text-zinc-300">
              A <span className="text-zinc-100">Conference Room</span> is a
              fixed recording space backed by one or more server-attached mics.
              In a room's <span className="text-zinc-100">Settings</span> tab you
              can add <span className="text-zinc-100">one or several mics</span>{' '}
              in a single step, give each a friendly label ("Podium",
              "Audience", "Speaker phone"), and run a 3-second{' '}
              <span className="text-zinc-100">Test mic</span> probe to check the
              levels before you add it. Each source shows a live status badge
              (idle / recording / error / disabled) and a remove button.
            </p>
          </section>

          <section className="space-y-4">
            <div className="flex items-center gap-3">
              <FileText className="h-5 w-5 text-fuchsia-400" />
              <h3 className="text-lg font-semibold text-zinc-100">
                Reading a meeting
              </h3>
            </div>
            <p className="text-zinc-300">
              Open any session to get the playback + everything the meeting
              produced:
            </p>
            <ul className="space-y-2 text-zinc-300">
              <li className="flex items-start gap-3">
                <FileText className="mt-0.5 h-4 w-4 flex-shrink-0 text-zinc-500" />
                <span>
                  <span className="text-zinc-100">Transcript</span> with speaker
                  labels, searchable and filterable by speaker, synced to the
                  audio player.
                </span>
              </li>
              <li className="flex items-start gap-3">
                <Brain className="mt-0.5 h-4 w-4 flex-shrink-0 text-zinc-500" />
                <span>
                  <span className="text-zinc-100">Summary, key points, and
                  action items</span> generated from the full transcript.
                </span>
              </li>
              <li className="flex items-start gap-3">
                <MessageSquare className="mt-0.5 h-4 w-4 flex-shrink-0 text-zinc-500" />
                <span>
                  <span className="text-zinc-100">Ask about this meeting</span> —
                  a chat panel that answers questions using the meeting's
                  transcript as context ("what did we decide about pricing?").
                </span>
              </li>
              <li className="flex items-start gap-3">
                <Download className="mt-0.5 h-4 w-4 flex-shrink-0 text-zinc-500" />
                <span>
                  <span className="text-zinc-100">Export</span> the transcript
                  or summary as PDF, DOCX, TXT, or SRT, and download the audio.
                </span>
              </li>
            </ul>
          </section>

          <section className="space-y-4">
            <div className="flex items-center gap-3">
              <Database className="h-5 w-5 text-emerald-400" />
              <h3 className="text-lg font-semibold text-zinc-100">
                Where your recordings are stored
              </h3>
            </div>
            <p className="text-zinc-300">
              Finished recordings are kept in <span className="text-zinc-100">our
              own object storage, on our own hardware</span> — not a third-party
              cloud. Nothing is shipped to AWS, Google, or any external
              transcription service. When you <span className="text-zinc-100">delete
              a session</span>, its audio is purged from storage too, so delete
              means delete.
            </p>
            <p className="text-zinc-300">
              On the free tier, your audio never leaves your browser at all (see
              Privacy mode below). On paid tiers, the finished audio is stored
              durably so it survives and stays available across devices — but it
              still lives only inside our infrastructure.
            </p>
          </section>

          <section className="space-y-4">
            <div className="flex items-center gap-3">
              <Users className="h-5 w-5 text-fuchsia-400" />
              <h3 className="text-lg font-semibold text-zinc-100">
                Plans at a glance
              </h3>
            </div>
            <div className="grid gap-3 md:grid-cols-3">
              <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
                <div className="text-sm font-medium text-zinc-100">Free</div>
                <div className="mt-1 text-sm text-zinc-400">
                  Fully on-device in your browser. Live transcript + summary,
                  recordings stay local. Nothing uploaded.
                </div>
              </div>
              <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
                <div className="text-sm font-medium text-zinc-100">Pro</div>
                <div className="mt-1 text-sm text-zinc-400">
                  Adds the server quality pass (better transcript + diarization
                  + summary), the live server transcript, durable cross-device
                  storage, and bulk import.
                </div>
              </div>
              <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
                <div className="text-sm font-medium text-zinc-100">Enterprise</div>
                <div className="mt-1 text-sm text-zinc-400">
                  On-prem / private deployment, Privacy mode on by default, and
                  HIPAA-suitable handling for regulated environments.
                </div>
              </div>
            </div>
          </section>
        </div>

        {/* -------------------------- How it works ------------------------- */}
        <h2 className="text-xl font-semibold text-fuchsia-300 border-b border-zinc-800 pb-2">
          How it works
        </h2>

        <section className="space-y-4">
          <div className="flex items-center gap-3">
            <Cpu className="h-5 w-5 text-fuchsia-400" />
            <h2 className="text-lg font-semibold text-zinc-100">
              Your computer does the real-time work
            </h2>
          </div>
          <p className="text-zinc-300">
            While you're recording, the live transcript and the rolling summary
            you see on screen are running on your own computer, in this browser
            tab. Nothing is being streamed to a server for transcription. There
            is no third-party API in the loop. The first time you open the
            recorder, we download a couple of small AI models (a speech model
            and a small language model) and cache them in your browser, so
            future meetings start instantly.
          </p>
          <ul className="space-y-2 text-zinc-300">
            <li className="flex items-start gap-3">
              <Mic className="mt-0.5 h-4 w-4 flex-shrink-0 text-zinc-500" />
              <span>
                <span className="text-zinc-100">Live transcript</span> is
                produced by Parakeet 0.6B, a compact speech recognition model
                that runs locally on your CPU (or GPU if your browser supports
                WebGPU).
              </span>
            </li>
            <li className="flex items-start gap-3">
              <Brain className="mt-0.5 h-4 w-4 flex-shrink-0 text-zinc-500" />
              <span>
                <span className="text-zinc-100">Live summary</span> is produced
                by a small language model (Qwen 3 0.6B by default, Gemma 4 E2B
                as an alternative) that refreshes every few hundred words while
                you record.
              </span>
            </li>
            <li className="flex items-start gap-3">
              <Zap className="mt-0.5 h-4 w-4 flex-shrink-0 text-zinc-500" />
              <span>
                <span className="text-zinc-100">First load</span> can take 30-60
                seconds on a slow connection. After that, everything is cached
                and starts instantly.
              </span>
            </li>
          </ul>
        </section>

        <section className="space-y-4">
          <div className="flex items-center gap-3">
            <Radio className="h-5 w-5 text-fuchsia-400" />
            <h2 className="text-lg font-semibold text-zinc-100">
              Server live transcript (paid tier only)
            </h2>
          </div>
          <p className="text-zinc-300">
            On enterprise / pro tier, you'll see a second transcript pane in
            the Record page below the browser-side Live transcript. This is
            the <span className="text-zinc-100">Server live transcript</span> —
            a separate pipeline that sends your audio to our GPU and runs a
            different family of models specifically built for live streaming.
          </p>
          <ul className="space-y-2 text-zinc-300">
            <li className="flex items-start gap-3">
              <Mic className="mt-0.5 h-4 w-4 flex-shrink-0 text-zinc-500" />
              <span>
                <span className="text-zinc-100">Per-word streaming</span> via
                NVIDIA Parakeet realtime EOU 120M — a streaming-trained
                checkpoint that emits words as the model commits them rather
                than at a fixed 2-3 second cadence. Each word shows its
                timestamp + confidence on mouse-over.
              </span>
            </li>
            <li className="flex items-start gap-3">
              <Users className="mt-0.5 h-4 w-4 flex-shrink-0 text-zinc-500" />
              <span>
                <span className="text-zinc-100">Live speaker labels</span> via
                NVIDIA Sortformer 4-speaker streaming diarization, running in
                parallel with the transcript. Each utterance gets a colored
                speaker chip (red / green / blue / amber) so you can see who
                said what while you record.
              </span>
            </li>
            <li className="flex items-start gap-3">
              <Brain className="mt-0.5 h-4 w-4 flex-shrink-0 text-zinc-500" />
              <span>
                <span className="text-zinc-100">EOU detection</span> — when
                the model recognizes you've stopped talking, it emits an
                end-of-utterance marker and starts a new paragraph. No more
                hallucinated tokens during quiet stretches.
              </span>
            </li>
            <li className="flex items-start gap-3">
              <Zap className="mt-0.5 h-4 w-4 flex-shrink-0 text-zinc-500" />
              <span>
                <span className="text-zinc-100">Latency</span> — about 175ms
                round trip per window on our RTX 3060. Smaller, faster, and
                lower-VRAM than the original full-context checkpoint, while
                staying close enough to your audio that it feels real-time.
              </span>
            </li>
          </ul>
          <p className="text-zinc-400 text-sm">
            <Clock className="inline h-3.5 w-3.5 mr-1 -mt-0.5" />
            Both transcripts run side-by-side during recording — the browser
            one stays as your privacy-respecting baseline, the server one is
            the higher-fidelity live view. Each utterance is a paragraph; an
            italic suffix shows what the model is "thinking" before it commits.
          </p>
        </section>

        <section className="space-y-4">
          <div className="flex items-center gap-3">
            <Server className="h-5 w-5 text-fuchsia-400" />
            <h2 className="text-lg font-semibold text-zinc-100">
              Our servers run the quality pass when your meeting ends
            </h2>
          </div>
          <p className="text-zinc-300">
            When you stop recording, you'll see a banner at the top of the
            session that says something like "Reprocessing..." for about 30 to
            90 seconds. That's our servers doing the polish pass on your audio:
          </p>
          <ul className="space-y-2 text-zinc-300">
            <li className="flex items-start gap-3">
              <ArrowRight className="mt-0.5 h-4 w-4 flex-shrink-0 text-zinc-500" />
              <span>
                <span className="text-zinc-100">High-quality transcript</span>{' '}
                from Parakeet 1.1B (a larger version of the model your browser
                ran) with word-level timestamps.
              </span>
            </li>
            <li className="flex items-start gap-3">
              <ArrowRight className="mt-0.5 h-4 w-4 flex-shrink-0 text-zinc-500" />
              <span>
                <span className="text-zinc-100">Speaker diarization</span> —
                figures out who was talking when, and matches voices against
                your speaker library if you've enrolled people.
              </span>
            </li>
            <li className="flex items-start gap-3">
              <ArrowRight className="mt-0.5 h-4 w-4 flex-shrink-0 text-zinc-500" />
              <span>
                <span className="text-zinc-100">Polished summary</span> from
                Qwen 3.6 (a much larger model than the one in your browser),
                with action items and attendee notes.
              </span>
            </li>
          </ul>
          <p className="text-zinc-400 text-sm">
            <Clock className="inline h-3.5 w-3.5 mr-1 -mt-0.5" />
            The wait is intentional. We could stream every word through a big
            cloud model in real time, but that would make every meeting cost
            real money to run and would mean your audio leaves your machine
            constantly. Instead, we do it once at the end. The output is
            higher quality and the architecture stays sustainable.
          </p>
        </section>

        <section className="space-y-4">
          <div className="flex items-center gap-3">
            <Smartphone className="h-5 w-5 text-sky-400" />
            <h2 className="text-lg font-semibold text-zinc-100">
              On mobile (phones and tablets)
            </h2>
          </div>
          <p className="text-zinc-300">
            On mobile devices, Meeting-Ops runs in capture-only mode. Your
            phone records the audio and uploads it as you talk. About a
            minute after the meeting ends, the server produces a full
            transcript and AI summary that lands in your sessions list,
            ready to read.
          </p>
          <p className="text-zinc-300">
            We don't do the live transcript and live summary in mobile
            browsers right now. Today's phone browsers don't reliably have
            the compute or memory headroom for the on-device speech and
            language models the laptop version uses, and pretending
            otherwise would give you stalled captions and a hot phone. So
            we skip the live work and let the server polish pass do it
            once, well, at the end.
          </p>
          <p className="text-zinc-300">
            Native iOS and Android apps are on the roadmap, with on-device
            live captions sized for phone silicon. Server-side live
            captions for mobile browsers will arrive as part of a paid
            tier later. For now, mobile is a great way to capture
            meetings, the quality output happens after you tap Stop.
          </p>
        </section>

        <section className="space-y-4">
          <div className="flex items-center gap-3">
            <Shield className="h-5 w-5 text-emerald-400" />
            <h2 className="text-lg font-semibold text-zinc-100">
              Privacy mode keeps everything local
            </h2>
          </div>
          <p className="text-zinc-300">
            If you toggle Privacy mode on for a session (look for the lock icon
            in the recorder), the server pass is skipped entirely. Your audio
            bytes never leave your device. The live transcript and live summary
            your browser produced are what you get. Nothing else.
          </p>
          <p className="text-zinc-300">
            Privacy mode is per-session — you can turn it on for sensitive
            meetings and leave it off for everything else. The audio bytes
            simply aren't uploaded, which is exact and verifiable. When you
            tap Stop, your browser runs a full-quality transcription and
            summary pass over the recorded audio so what you get matches the
            server-side pipeline in shape, just without the audio ever
            leaving the device.
          </p>
          <div className="rounded-lg border border-purple-500/20 bg-purple-500/5 p-4 text-sm text-zinc-300">
            <div className="flex items-start gap-3">
              <Lock className="mt-0.5 h-4 w-4 flex-shrink-0 text-purple-300" />
              <div>
                <div className="font-medium text-purple-200">
                  What runs after you tap Stop in privacy mode
                </div>
                <ul className="mt-2 space-y-1.5 text-zinc-400">
                  <li>
                    <span className="text-zinc-200">Full-audio transcription</span> with
                    Parakeet 0.6B INT8 against the recording your browser
                    held in IndexedDB during the session. Catches everything,
                    not just what the live captions caught.
                  </li>
                  <li>
                    <span className="text-zinc-200">Final summary</span> from Qwen 3 0.6B
                    (or Gemma 4 E2B) over that full transcript. Same prompt
                    shape as the server pipeline — Decisions, Action Items,
                    Metrics, Risks.
                  </li>
                  <li>
                    <span className="text-zinc-200">Local Sessions view</span> at{' '}
                    <code className="rounded bg-zinc-900 px-1 py-0.5 text-zinc-300">/local-sessions</code>{' '}
                    lists every privacy-mode session you've recorded on this
                    device. The sidebar entry shows up after your first one.
                  </li>
                  <li>
                    <span className="text-zinc-200">Export</span> as Markdown or JSON.
                    Markdown is the readable artefact; JSON optionally
                    includes the audio as base64 if you need to move the
                    session between machines.
                  </li>
                </ul>
              </div>
            </div>
          </div>
          <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-4 text-sm text-zinc-300">
            <div className="flex items-start gap-3">
              <Lock className="mt-0.5 h-4 w-4 flex-shrink-0 text-emerald-400" />
              <div>
                <div className="font-medium text-emerald-300">
                  HIPAA / clinical deployments
                </div>
                <div className="mt-1 text-zinc-400">
                  Enterprise deployments (medical, legal, regulated
                  environments) default Privacy mode on. Talk to your admin if
                  you're not sure which mode your organization is using.
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="space-y-4">
          <div className="flex items-center gap-3">
            <Globe className="h-5 w-5 text-fuchsia-400" />
            <h2 className="text-lg font-semibold text-zinc-100">
              Why we built it this way
            </h2>
          </div>
          <p className="text-zinc-300">
            Most meeting-AI products run everything on cloud GPUs and pay a
            big bill per minute, per user. That cost gets passed to you, and
            your audio is constantly being shipped off to third-party
            transcription services and big cloud LLMs.
          </p>
          <p className="text-zinc-300">
            We push the live work to your browser because your computer is
            already doing the meeting anyway. We only spin up real server
            compute when there's something the browser genuinely can't do well
            — like diarization across an hour-long meeting, or a polished
            summary from a much larger model. That keeps the product:
          </p>
          <div className="grid gap-3 md:grid-cols-2">
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
              <div className="text-sm font-medium text-zinc-100">Faster</div>
              <div className="mt-1 text-sm text-zinc-400">
                Live transcript and summary appear without round-trips to a
                server. They run as fast as your machine can run them.
              </div>
            </div>
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
              <div className="text-sm font-medium text-zinc-100">
                Cheaper to run
              </div>
              <div className="mt-1 text-sm text-zinc-400">
                We don't pay per-minute for every meeting. That keeps the
                product sustainable without aggressive pricing.
              </div>
            </div>
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
              <div className="text-sm font-medium text-zinc-100">
                More private
              </div>
              <div className="mt-1 text-sm text-zinc-400">
                Your audio mostly stays on your device. Privacy mode keeps it
                fully local. Nothing goes to OpenAI or Anthropic by default.
              </div>
            </div>
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
              <div className="text-sm font-medium text-zinc-100">
                Fewer dependencies
              </div>
              <div className="mt-1 text-sm text-zinc-400">
                No third-party transcription API. No big LLM vendor lock-in.
                If an external service has an outage, your meetings still work.
              </div>
            </div>
          </div>
        </section>

        <section className="space-y-3 border-t border-zinc-800 pt-6">
          <h2 className="text-lg font-semibold text-zinc-100">Want more detail?</h2>
          <p className="text-zinc-400 text-sm">
            The full strategy doc lives at{' '}
            <code className="rounded bg-zinc-900 px-1.5 py-0.5 text-zinc-300">
              docs/compute-economics.md
            </code>{' '}
            in the source tree. It covers the architecture in depth, the
            numbers behind the unit economics, and the principles we use for
            future architecture decisions.
          </p>
          <p className="text-zinc-400 text-sm">
            If you want to switch the in-browser models (Qwen 3 0.6B vs Gemma 4
            E2B vs others), head to Settings → In-browser AI.
          </p>
        </section>
      </div>
    </div>
  );
}
