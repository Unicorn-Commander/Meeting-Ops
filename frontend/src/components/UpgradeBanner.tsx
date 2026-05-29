// UpgradeBanner — small dismissible banner for free-tier users.
//
// Renders at the top of Sessions / SessionDetails. Single CTA → /pricing.
// Dismiss persists for 7 days in localStorage (so we don't nag), then it
// comes back on its own.
//
// Aaron's locked copy + price ($12/mo, individual, cancel anytime).
// Browser-first moat language: this is the upsell for SERVER-side
// features. Free is on-device by design — see compute-economics.md.

import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Sparkles, X } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';

const DISMISS_KEY = 'meet:upgrade-banner:dismissed';
const DISMISS_TTL_MS = 7 * 24 * 60 * 60 * 1000; // 7 days

function isDismissedRecently(): boolean {
  try {
    const raw = localStorage.getItem(DISMISS_KEY);
    if (!raw) return false;
    const ts = parseInt(raw, 10);
    if (!Number.isFinite(ts)) return false;
    return Date.now() - ts < DISMISS_TTL_MS;
  } catch {
    return false;
  }
}

function markDismissed(): void {
  try {
    localStorage.setItem(DISMISS_KEY, String(Date.now()));
  } catch {
    /* ignore storage failures */
  }
}

export const UpgradeBanner: React.FC = () => {
  const { user } = useAuth();
  const [dismissed, setDismissed] = useState<boolean>(true);

  // Read storage on mount only — avoids the SSR-style flash on each render.
  useEffect(() => {
    setDismissed(isDismissedRecently());
  }, []);

  // Gate: only render for free-tier users. Superuser overrides to
  // enterprise via the tier resolution, so admins never see this. Anon
  // (no user) doesn't see it either — they have their own /signup flow.
  if (!user) return null;
  const tier = (user as { tier?: string }).tier;
  if (tier && tier !== 'free') return null;
  if (dismissed) return null;

  const handleDismiss = () => {
    markDismissed();
    setDismissed(true);
  };

  return (
    <div
      className="relative mb-4 flex flex-col gap-2 rounded-xl border border-fuchsia-400/30 bg-gradient-to-r from-fuchsia-500/10 via-violet-500/10 to-fuchsia-500/10 p-3 text-sm text-zinc-100 sm:flex-row sm:items-center sm:justify-between sm:gap-4 sm:p-4"
      role="region"
      aria-label="Upgrade to Pro"
    >
      <div className="flex items-start gap-3 sm:items-center">
        <Sparkles className="mt-0.5 h-5 w-5 shrink-0 text-fuchsia-300 sm:mt-0" />
        <p className="leading-6">
          <strong className="font-semibold text-white">Upgrade to Pro — $12/mo.</strong>{' '}
          Higher-accuracy transcription, speaker diarization, AI chat, cross-device sync. Cancel anytime.
        </p>
      </div>
      <div className="flex items-center gap-2">
        <Link
          to="/pricing"
          className="inline-flex items-center justify-center rounded-lg bg-white px-3 py-2 text-sm font-semibold text-zinc-950 transition hover:bg-zinc-100"
        >
          Upgrade to Pro
        </Link>
        <button
          type="button"
          aria-label="Dismiss upgrade banner"
          onClick={handleDismiss}
          className="rounded-md p-1 text-zinc-400 transition hover:bg-white/10 hover:text-white"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
};

export default UpgradeBanner;
