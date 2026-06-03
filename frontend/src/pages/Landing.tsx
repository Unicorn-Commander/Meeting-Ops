/**
 * Public, invite-only landing page for the v3.19 polished launch at
 * `meeting-ops.unicorncommander.ai`. Rendered at `/` when
 * `VITE_LANDING_PAGE_ENABLED` is `"true"` at build time AND the visitor
 * is not authenticated. Bigboy keeps the historical `/` → `/dashboard`
 * redirect via `VITE_LANDING_PAGE_ENABLED=false` (compose default).
 *
 * Intentionally:
 * - No API calls on mount (no /me probe, no analytics beacon).
 * - No external JS — no third-party fonts, no GA, no Segment.
 * - No moat-revealing copy. Three product points, hero, invite form.
 * - The invite form POSTs to `/api/landing/invite-request` which is
 *   public + rate-limited + idempotent on dupes (backend/api/landing.py).
 */
import React, { useState } from 'react';
import { Lock, Sparkles, Plug, ArrowRight } from 'lucide-react';
import { config } from '../config';
import LegalFooter from '../components/LegalFooter';
import { track } from '../utils/posthog';

type SubmitState = 'idle' | 'submitting' | 'success' | 'error';

export const Landing: React.FC = () => {
  const [email, setEmail] = useState('');
  const [state, setState] = useState<SubmitState>('idle');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setErrorMsg(null);

    const trimmed = email.trim();
    if (!trimmed || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmed)) {
      setErrorMsg('Please enter a valid email address.');
      setState('error');
      return;
    }

    setState('submitting');
    // v3.21.0 full-path CTA: always fire-and-forget the invite-request
    // log (so manual follow-up still has the email captured + the
    // existing rate-limit + Postmark notify path keeps working), then
    // immediately redirect to /signup?email=. The Signup page detects
    // the 403 "registration closed" reply gracefully and shows the
    // friendly invite-confirmation copy when self-serve isn't open.
    try {
      const apiBase = config.apiBaseUrl.replace(/\/$/, '');
      const url = `${apiBase}/api/landing/invite-request`;
      // Fire-and-forget — we don't await success. Even a 429 doesn't
      // block the user from trying to sign up. Failures are silent on
      // the UI; the invite-only flow logs server-side.
      void fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: trimmed }),
      }).catch(() => {
        /* intentional: the redirect below is the user-facing path */
      });
      // Fired at submit (the request is fire-and-forget, so there's no
      // 200 to await). No-op unless PostHog initialized (key present,
      // not DNT/opted-out). No email/PII in the event.
      track('landing_invite_requested', {});
      const encoded = encodeURIComponent(trimmed);
      // Hash router — setting location.hash to `/signup?email=...` makes
      // the URL `<origin>/#/signup?email=...`, which is what HashRouter
      // reads. (Setting it with a leading `#` would double-up.)
      window.location.hash = `/signup?email=${encoded}`;
      setState('success');
      setEmail('');
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Network error.');
      setState('error');
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-zinc-950 to-black text-zinc-100">
      <div className="mx-auto flex min-h-screen max-w-5xl flex-col px-6 py-12 sm:px-10">
        {/* Header strip */}
        <header className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-fuchsia-500 to-indigo-500">
              <span className="text-xl text-white">✨</span>
            </div>
            <div>
              <div className="text-base font-semibold text-white">Meeting-Ops</div>
              <div className="text-xs text-zinc-500">Private beta</div>
            </div>
          </div>
          <a
            href="#/login"
            className="text-sm text-zinc-400 transition-colors hover:text-white"
          >
            I have an account → Sign in
          </a>
        </header>

        {/* Hero */}
        <section className="mt-20">
          <div className="inline-flex items-center gap-2 rounded-full border border-zinc-800 bg-zinc-900/60 px-3 py-1 text-xs text-zinc-400">
            <span className="h-1.5 w-1.5 rounded-full bg-fuchsia-400" />
            Private beta — request an invite
          </div>
          <h1 className="mt-6 text-4xl font-semibold leading-tight text-white sm:text-5xl">
            Meeting and conversation intelligence that stays private.
          </h1>
          <p className="mt-6 max-w-2xl text-lg text-zinc-400">
            The browser-first meeting and conversation intelligence
            platform. Your audio never leaves your device unless you
            decide it should. Optional server pass for higher-accuracy
            transcription, speaker recognition, and AI chat across your
            entire meeting library.
          </p>

          {/* Primary CTA */}
          <div className="mt-10">
            <a
              href="#invite"
              className="inline-flex items-center gap-2 rounded-lg bg-fuchsia-500 px-5 py-3 text-sm font-medium text-white shadow-lg shadow-fuchsia-500/20 transition-colors hover:bg-fuchsia-400"
            >
              Get started
              <ArrowRight className="h-4 w-4" />
            </a>
          </div>
        </section>

        {/* 3 product points */}
        <section className="mt-24 grid gap-6 sm:grid-cols-3">
          <article className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5">
            <Lock className="h-6 w-6 text-fuchsia-300" aria-hidden="true" />
            <h2 className="mt-4 text-base font-semibold text-white">
              Browser-only by default
            </h2>
            <p className="mt-2 text-sm text-zinc-400">
              Transcription, summaries, and storage run on your device.
              No server pass unless you opt in.
            </p>
          </article>
          <article className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5">
            <Sparkles className="h-6 w-6 text-fuchsia-300" aria-hidden="true" />
            <h2 className="mt-4 text-base font-semibold text-white">
              Optional Pro server pass
            </h2>
            <p className="mt-2 text-sm text-zinc-400">
              Higher-accuracy completion, speaker diarization, and AI
              chat across meetings — available on demand, per session.
            </p>
          </article>
          <article className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5">
            <Plug className="h-6 w-6 text-fuchsia-300" aria-hidden="true" />
            <h2 className="mt-4 text-base font-semibold text-white">
              Bring-your-own ecosystem
            </h2>
            <p className="mt-2 text-sm text-zinc-400">
              Integrations with Brigade knowledge graph, Project-Ops,
              and Contact-Ops. Per-workspace toggles, encrypted at rest.
            </p>
          </article>
        </section>

        {/* Invite form */}
        <section id="invite" className="mt-24">
          <div className="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-6 sm:p-8">
            <h3 className="text-xl font-semibold text-white">
              Get started
            </h3>
            <p className="mt-2 text-sm text-zinc-400">
              Drop your email and we'll take you to account setup. If
              self-serve signup isn't open yet, we'll log your interest
              and get back to you as slots open.
            </p>

            {state === 'success' ? (
              <div
                role="status"
                aria-live="polite"
                className="mt-6 rounded-lg border border-emerald-700/40 bg-emerald-900/20 px-4 py-3 text-sm text-emerald-300"
              >
                Taking you to account setup…
              </div>
            ) : (
              <form
                onSubmit={handleSubmit}
                className="mt-6 flex flex-col gap-3 sm:flex-row"
                noValidate
              >
                <label htmlFor="invite-email" className="sr-only">
                  Email address
                </label>
                <input
                  id="invite-email"
                  type="email"
                  required
                  autoComplete="email"
                  placeholder="you@example.com"
                  value={email}
                  onChange={(e) => {
                    setEmail(e.target.value);
                    if (state === 'error') setState('idle');
                  }}
                  disabled={state === 'submitting'}
                  className="flex-1 rounded-lg border border-zinc-700 bg-zinc-950 px-4 py-3 text-sm text-zinc-100 outline-none transition focus:border-fuchsia-400 disabled:opacity-60"
                />
                <button
                  type="submit"
                  disabled={state === 'submitting'}
                  className="rounded-lg bg-fuchsia-500 px-5 py-3 text-sm font-medium text-white transition-colors hover:bg-fuchsia-400 disabled:opacity-60"
                >
                  {state === 'submitting' ? 'Submitting…' : 'Continue'}
                </button>
              </form>
            )}

            {state === 'error' && errorMsg && (
              <div
                role="alert"
                className="mt-4 rounded-lg border border-rose-700/40 bg-rose-900/20 px-4 py-3 text-sm text-rose-300"
              >
                {errorMsg}
              </div>
            )}
          </div>
        </section>

        {/* Footer */}
        <footer className="mt-auto pt-24 text-xs text-zinc-500">
          <div className="border-t border-zinc-800 pt-6">
            <p>
              Built by Magic Unicorn Unconventional Technology &amp; Stuff Inc.
            </p>
            <p className="mt-2">
              Made for makers, not for ad networks. Self-hosted
              Enterprise available — contact{' '}
              <a
                className="text-zinc-400 underline-offset-4 hover:text-fuchsia-300 hover:underline"
                href="mailto:enterprise@meeting-ops.unicorncommander.ai"
              >
                enterprise@meeting-ops.unicorncommander.ai
              </a>
              .
            </p>
            <p className="mt-2">
              Questions?{' '}
              <a
                className="text-zinc-400 underline-offset-4 hover:text-fuchsia-300 hover:underline"
                href="#/contact"
              >
                Contact Support
              </a>
              .
            </p>
          </div>
        </footer>

        {/* v3.22.5 unified legal footer (Terms / Privacy / Acceptable
            Use / Contact Support / copyright). Mirrors the authed
            AppLayout footer so every public surface exposes the same
            legal nav. */}
        <LegalFooter />
      </div>
    </div>
  );
};

export default Landing;
