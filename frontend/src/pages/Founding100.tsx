import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight,
  CalendarCheck2,
  Crown,
  Gift,
  Headphones,
  Lock,
  MessageSquare,
  Sparkles,
  Vote,
} from 'lucide-react';
import { config } from '../config';

// Public Founding 100 page (v3.21.0).
//
// Fetches GET /api/founding/status?cohort=meeting_ops_v1 (no auth, cached
// 60s) and renders:
//   - "X / 100 seats filled" headline
//   - progress bar
//   - perks list (lifetime price-lock, Discord, advisory council seat,
//     quarterly roadmap vote, annual founders summit, cross-app early
//     access)
//   - CTA → /pricing when is_open, "Cohort closed" message otherwise
//
// The Founding 100 cohort is grant-on-annual-upfront only. The /pricing
// page owns the actual purchase flow; we just send people there.

interface FoundingStatus {
  cohort: string;
  seats_taken: number;
  seats_total: number;
  is_open: boolean;
}

interface Perk {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  body: string;
}

const PERKS: Perk[] = [
  {
    icon: Lock,
    title: 'Lifetime price-lock',
    body: 'Your annual rate is fixed for as long as you stay subscribed. No surprise hikes when we re-price.',
  },
  {
    icon: MessageSquare,
    title: 'Private Discord',
    body: 'Direct line to the team in a small, focused room. Bug reports, roadmap pushback, build threads.',
  },
  {
    icon: Crown,
    title: 'Advisory council seat',
    body: 'Quarterly call with the founder. Steer what gets built next.',
  },
  {
    icon: Vote,
    title: 'Quarterly roadmap vote',
    body: 'Weighted ballot on the next quarter\'s product surface — you pick the work, we ship it.',
  },
  {
    icon: CalendarCheck2,
    title: 'Annual founders summit',
    body: 'One day a year, in person. Talks, demos, working sessions. Travel on you, room and meals on us.',
  },
  {
    icon: Sparkles,
    title: 'Cross-app early access',
    body: 'Project-Ops, Contact-Ops, Accounting-Ops, Brigade — you see new ecosystem apps before public release.',
  },
];

export const Founding100: React.FC = () => {
  const [status, setStatus] = useState<FoundingStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const r = await fetch(
          `${config.apiBaseUrl}/api/founding/status?cohort=meeting_ops_v1`,
        );
        if (!r.ok) {
          throw new Error(`status ${r.status}`);
        }
        const body = (await r.json()) as FoundingStatus;
        if (!cancelled) setStatus(body);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Could not load cohort status.');
        }
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const seatsTaken = status?.seats_taken ?? 0;
  const seatsTotal = status?.seats_total ?? 100;
  const pct = Math.min(100, Math.round((seatsTaken / Math.max(1, seatsTotal)) * 100));
  const isOpen = status?.is_open ?? true;

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <div className="mx-auto flex min-h-screen w-full max-w-5xl flex-col px-4 py-8 lg:px-8">
        <header className="flex items-center justify-between border-b border-white/10 pb-5">
          <Link to="/" className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-fuchsia-500 to-violet-500 shadow-lg shadow-fuchsia-500/20">
              <Sparkles className="h-5 w-5 text-white" />
            </div>
            <div>
              <div className="text-sm font-semibold tracking-tight text-white">Meeting-Ops</div>
              <div className="text-xs text-zinc-400">Founding 100</div>
            </div>
          </Link>
          <div className="flex items-center gap-3 text-sm text-zinc-300">
            <Link to="/pricing" className="rounded-full border border-white/10 px-3 py-2 hover:border-fuchsia-400/40 hover:text-white">
              Pricing
            </Link>
            <Link to="/login" className="rounded-full border border-white/10 px-3 py-2 hover:border-fuchsia-400/40 hover:text-white">
              Sign in
            </Link>
          </div>
        </header>

        <main className="flex-1 py-10">
          <section className="space-y-6">
            <div className="inline-flex items-center gap-2 rounded-full border border-fuchsia-500/30 bg-fuchsia-500/10 px-3 py-1 text-xs font-medium text-fuchsia-200">
              <Crown className="h-3.5 w-3.5" />
              Meeting-Ops v1 cohort
            </div>
            <div className="space-y-4">
              <h1 className="text-4xl font-semibold tracking-tight text-white sm:text-5xl">
                The first 100 annual customers shape what gets built.
              </h1>
              <p className="max-w-2xl text-base leading-7 text-zinc-300">
                We are running Meeting-Ops as a private-and-fast platform first. The
                Founding 100 keep us honest — direct access, a real vote on the
                roadmap, and the same price forever. No discount; just a seat at
                the table.
              </p>
            </div>

            <div className="rounded-3xl border border-white/10 bg-zinc-900/80 p-6 shadow-2xl shadow-black/30 backdrop-blur">
              {error && (
                <div className="mb-4 rounded-2xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
                  We could not reach the seat counter ({error}). Try again in a minute.
                </div>
              )}
              <div className="flex items-end justify-between gap-4">
                <div>
                  <div className="text-sm font-medium text-zinc-300">Seats filled</div>
                  <div className="mt-1 text-4xl font-semibold tracking-tight text-white">
                    {seatsTaken} <span className="text-zinc-500">/ {seatsTotal}</span>
                  </div>
                </div>
                <div className="text-right text-sm text-zinc-400">
                  Cohort:&nbsp;
                  <span className="font-mono text-zinc-200">meeting_ops_v1</span>
                </div>
              </div>
              <div
                className="mt-5 h-3 w-full overflow-hidden rounded-full bg-white/5"
                role="progressbar"
                aria-valuenow={seatsTaken}
                aria-valuemin={0}
                aria-valuemax={seatsTotal}
              >
                <div
                  className="h-full bg-gradient-to-r from-fuchsia-500 to-violet-500 transition-all"
                  style={{ width: `${pct}%` }}
                />
              </div>

              <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                {isOpen ? (
                  <>
                    <div className="text-sm text-zinc-300">
                      The cohort is open. Annual plans only — monthly plans are not part of Founding 100.
                    </div>
                    <Link
                      to="/pricing"
                      className="inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-fuchsia-500 to-violet-500 px-4 py-3 text-sm font-semibold text-white shadow-lg shadow-fuchsia-500/20 transition hover:from-fuchsia-400 hover:to-violet-400"
                    >
                      <ArrowRight className="h-4 w-4" />
                      Become a Founding member
                    </Link>
                  </>
                ) : (
                  <div className="rounded-2xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-100">
                    <strong className="font-semibold">Cohort closed — thank you.</strong>{' '}
                    The Meeting-Ops v1 Founding 100 is now full. Annual customers
                    can still join Pro, but cohort perks are reserved for the
                    first 100.
                  </div>
                )}
              </div>
            </div>
          </section>

          <section className="mt-12 space-y-6">
            <div className="space-y-2">
              <div className="inline-flex items-center gap-2 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs font-medium text-emerald-200">
                <Gift className="h-3.5 w-3.5" />
                What you get
              </div>
              <h2 className="text-2xl font-semibold tracking-tight text-white">
                Six perks as part of the first 100.
              </h2>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              {PERKS.map((perk) => {
                const Icon = perk.icon;
                return (
                  <div
                    key={perk.title}
                    className="rounded-2xl border border-white/10 bg-white/5 p-5 transition hover:border-fuchsia-400/30"
                  >
                    <div className="flex items-center gap-2 text-white">
                      <Icon className="h-5 w-5 text-fuchsia-300" />
                      <span className="font-medium">{perk.title}</span>
                    </div>
                    <p className="mt-2 text-sm leading-6 text-zinc-300">{perk.body}</p>
                  </div>
                );
              })}
            </div>
          </section>

          <section className="mt-12 rounded-3xl border border-white/10 bg-zinc-900/60 p-6">
            <div className="flex items-start gap-3">
              <Headphones className="mt-0.5 h-5 w-5 text-fuchsia-300" />
              <div>
                <div className="font-medium text-white">Questions before you commit?</div>
                <p className="mt-1 text-sm text-zinc-300">
                  Email{' '}
                  <a
                    className="text-fuchsia-200 hover:text-fuchsia-100"
                    href="mailto:hello@magicunicorn.dev?subject=Founding%20100"
                  >
                    hello@magicunicorn.dev
                  </a>
                  . We answer every message from a real person.
                </p>
              </div>
            </div>
          </section>
        </main>
      </div>
    </div>
  );
};

export default Founding100;
