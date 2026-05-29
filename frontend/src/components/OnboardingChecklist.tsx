// First-run onboarding checklist for the Dashboard.
//
// Audit context (2026-05-29 Codex UX audit): new free-tier signups land on
// the Dashboard with `0 sessions` and no signposts. The dashboard's existing
// HeroActions/StatsRow tell them what they have, not what to do first.
// This component shows four dismissible cards aimed at the four moves a
// first-run user needs to make (mic check, record a short sample, learn
// about privacy mode, see the upgrade path).
//
// Visibility rule: only when the user has zero sessions, AND at least one
// card hasn't been dismissed. Dismissals persist per-card in localStorage
// so the user never has to dismiss the same card twice.

import { useMemo, useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Mic, Radio, ShieldCheck, Sparkles, X } from 'lucide-react';

const STORAGE_KEY_PREFIX = 'meet:onboarding:dismissed:';

interface ChecklistItem {
  id: string;
  title: string;
  body: string;
  to: string;
  cta: string;
  icon: React.ComponentType<{ className?: string }>;
  iconBg: string;
  iconColor: string;
}

const ITEMS: ChecklistItem[] = [
  {
    id: 'mic-test',
    title: 'Test your microphone',
    body: 'Pick the right input and confirm levels before your first recording.',
    to: '/settings#audio-devices',
    cta: 'Open audio settings',
    icon: Mic,
    iconBg: 'bg-purple-100',
    iconColor: 'text-purple-600',
  },
  {
    id: 'first-recording',
    title: 'Record a 60-second sample',
    body: 'Capture a quick personal recording to see live transcription in action.',
    to: '/record/personal',
    cta: 'Start recording',
    icon: Radio,
    iconBg: 'bg-fuchsia-100',
    iconColor: 'text-fuchsia-600',
  },
  {
    id: 'privacy-mode',
    title: 'Privacy mode keeps audio on your device',
    body: 'Local-only sessions never leave your browser. See where they live.',
    to: '/local-sessions',
    cta: 'View local sessions',
    icon: ShieldCheck,
    iconBg: 'bg-emerald-100',
    iconColor: 'text-emerald-600',
  },
  {
    id: 'pro-upgrade',
    title: 'Optional: upgrade to Pro for server completion',
    body: 'Server-side summaries, action items, and cross-meeting search.',
    to: '/pricing',
    cta: 'See plans',
    icon: Sparkles,
    iconBg: 'bg-amber-100',
    iconColor: 'text-amber-600',
  },
];

function readDismissed(id: string): boolean {
  try {
    return window.localStorage.getItem(STORAGE_KEY_PREFIX + id) === '1';
  } catch {
    return false;
  }
}

function writeDismissed(id: string) {
  try {
    window.localStorage.setItem(STORAGE_KEY_PREFIX + id, '1');
  } catch {
    /* ignore quota / disabled storage */
  }
}

interface Props {
  sessionCount: number;
}

export default function OnboardingChecklist({ sessionCount }: Props) {
  // Initialize from localStorage so the dismissals are persistent across
  // tab reloads. We can't put this in useMemo because we need to flip
  // state on user action.
  const [dismissed, setDismissed] = useState<Record<string, boolean>>(() => {
    const out: Record<string, boolean> = {};
    for (const item of ITEMS) out[item.id] = readDismissed(item.id);
    return out;
  });

  // Re-read on mount in case the dashboard hot-mounts and localStorage
  // changed in another tab.
  useEffect(() => {
    const next: Record<string, boolean> = {};
    let changed = false;
    for (const item of ITEMS) {
      const v = readDismissed(item.id);
      next[item.id] = v;
      if (v !== dismissed[item.id]) changed = true;
    }
    if (changed) setDismissed(next);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const visibleItems = useMemo(
    () => ITEMS.filter((item) => !dismissed[item.id]),
    [dismissed],
  );

  const dismiss = (id: string) => {
    writeDismissed(id);
    setDismissed((prev) => ({ ...prev, [id]: true }));
  };

  // Audit-defined visibility rule: show whenever the user has zero
  // sessions OR they still have at least one undismissed card. (The first
  // half catches the brand-new user; the second keeps the checklist
  // visible on subsequent loads until they actively dismiss each card.)
  const hasUndismissed = visibleItems.length > 0;
  if (sessionCount > 0 && !hasUndismissed) return null;
  if (!hasUndismissed) return null;

  return (
    <section
      aria-label="Getting started"
      className="mt-6 rounded-2xl border border-zinc-800 bg-zinc-900/40 p-4"
    >
      <header className="mb-3 flex items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-zinc-100">Get set up in 4 quick steps</h2>
          <p className="text-xs text-zinc-500">
            Dismiss any card you've already handled — they won't come back.
          </p>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {visibleItems.map((item) => {
          const Icon = item.icon;
          return (
            <div
              key={item.id}
              className="relative flex flex-col gap-2 rounded-xl border border-zinc-800 bg-zinc-950 p-3 text-left"
            >
              <button
                type="button"
                onClick={() => dismiss(item.id)}
                aria-label={`Dismiss ${item.title}`}
                className="absolute right-2 top-2 rounded p-1 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200"
              >
                <X className="h-3.5 w-3.5" />
              </button>
              <div className={`inline-flex h-8 w-8 items-center justify-center rounded-lg ${item.iconBg}`}>
                <Icon className={`h-4 w-4 ${item.iconColor}`} />
              </div>
              <h3 className="text-sm font-semibold text-zinc-100 pr-6">{item.title}</h3>
              <p className="text-xs leading-5 text-zinc-400">{item.body}</p>
              <Link
                to={item.to}
                className="mt-auto inline-flex w-fit items-center gap-1 rounded-md border border-zinc-700 bg-zinc-900 px-2.5 py-1 text-xs font-medium text-zinc-200 hover:bg-zinc-800"
              >
                {item.cta}
              </Link>
            </div>
          );
        })}
      </div>
    </section>
  );
}
