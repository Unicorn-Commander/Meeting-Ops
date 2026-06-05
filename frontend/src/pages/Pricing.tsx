import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  ArrowRight,
  Check,
  X,
  Sparkles,
  Users,
  Building2,
  Layers,
  BrainCircuit,
  Zap,
} from 'lucide-react';
import {
  startCheckout,
  startPortal,
  BillingUnavailableError,
  type BillingCycle,
  type CheckoutPlan,
} from '../services/billingApi';
import LegalFooter from '../components/LegalFooter';
// PENDING_CHECKOUT_KEY: the sessionStorage key we stash {plan, cycle} into
// before redirecting to Stripe so App.tsx can fire `subscription_started`
// on the success redirect. Defined in utils/posthog so App can read it
// without eagerly importing this lazy-loaded page.
import { track, PENDING_CHECKOUT_KEY } from '../utils/posthog';

/**
 * v3.23.0 — 5-tier Pricing rebuild.
 *
 * Free → Basic → Pro → Suite → Enterprise. Single Monthly/Annual toggle
 * at the top; Free and Enterprise ignore it. Pro is the highlighted
 * card ("Most popular" monthly, "Best value" annual). Each paid annual
 * tier saves 2 months vs the monthly rate.
 *
 * Suite checkout works end-to-end; "Project-Ops + Contact-Ops Pro
 * included" is documentation-only until Brigade federation lands —
 * Suite buyers still get Meeting-Ops Pro features immediately and the
 * cross-app benefit lights up automatically when federation deploys.
 *
 * Per-seat language is intentionally absent — each subscription = 1
 * user for now; we add seat language in v3.24+ when invites ship.
 */

type IncludedFeature = { included: true; label: string };
type ExcludedFeature = { included: false; label: string };
type Feature = IncludedFeature | ExcludedFeature;

interface TierCard {
  key: 'free' | 'basic' | 'pro' | 'suite' | 'enterprise';
  name: string;
  tagline: string;
  monthly: string; // displayed price for monthly toggle
  annual: string | null; // displayed price for annual toggle; null = no toggle
  monthlySuffix: string;
  annualSuffix: string;
  /** Sub-line under annual price, e.g. "$6.58/mo billed annually". */
  annualSubcopy: string | null;
  /** Savings badge text on annual (e.g. "Save 2 mo"). */
  annualSavingsBadge: string | null;
  /** True for tiers with a Monthly/Annual toggle (Basic / Pro / Suite). */
  hasToggle: boolean;
  features: Feature[];
  ctaLabel: string;
  /** When set, CTA wires up to billingApi.startCheckout(checkoutPlan, cycle). */
  checkoutPlan?: CheckoutPlan;
  /** When set, CTA renders as an <a href> (mailto / external) instead. */
  ctaHref?: string;
  /** When set, CTA renders as a <Link to>. Used by Free → /signup. */
  ctaTo?: string;
  /** Highlights the card with the fuchsia border + popularity badge. */
  highlight?: boolean;
  /** Suite-specific footnote rendered in the card. */
  footnote?: string;
}

const ENTERPRISE_MAILTO =
  'mailto:enterprise@unicorncommander.ai?subject=Meeting-Ops%20Enterprise%20inquiry';

function isLoggedIn(): boolean {
  try {
    return !!localStorage.getItem('access_token');
  } catch {
    return false;
  }
}

const tiers: TierCard[] = [
  {
    key: 'free',
    name: 'Free',
    tagline: 'Forever on your device',
    monthly: '$0',
    annual: null,
    monthlySuffix: 'forever',
    annualSuffix: '',
    annualSubcopy: null,
    annualSavingsBadge: null,
    hasToggle: false,
    features: [
      { included: true, label: 'Browser-only recording + transcription' },
      { included: true, label: 'Live summary slices (Qwen 3 0.6B / Gemma 4 E2B on WebGPU)' },
      { included: true, label: '50 sessions per month' },
      { included: true, label: 'No sync, no server processing of audio' },
      { included: false, label: 'Cross-meeting search' },
      { included: false, label: 'AI Chat over your library' },
    ],
    ctaLabel: 'Get started free',
    ctaTo: '/signup',
  },
  {
    key: 'basic',
    name: 'Basic',
    tagline: 'Sync your notes everywhere',
    monthly: '$7.99',
    annual: '$79',
    monthlySuffix: '/ month',
    annualSuffix: '/ year',
    annualSubcopy: '$6.58/mo billed annually',
    annualSavingsBadge: 'Save 2 mo',
    hasToggle: true,
    features: [
      { included: true, label: 'Everything in Free' },
      { included: true, label: 'Cross-device sync (text artifacts)' },
      { included: true, label: 'AI Chat over your entire meeting library' },
      { included: true, label: 'Semantic + keyword search across all meetings' },
      { included: true, label: 'Action item dashboard + tracking' },
      { included: true, label: 'Calendar export (.ics) of action items' },
      { included: true, label: 'Weekly email digest' },
      { included: true, label: 'Custom vocabulary' },
      { included: true, label: 'Unlimited sessions' },
      { included: false, label: 'Audio uploads to our server (still browser-only audio)' },
      { included: false, label: 'Server-grade 35B summary' },
      { included: false, label: 'Speaker library (needs server audio processing)' },
    ],
    ctaLabel: 'Subscribe to Basic',
    checkoutPlan: 'basic',
  },
  {
    key: 'pro',
    name: 'Pro',
    tagline: 'The full conversation intelligence stack',
    monthly: '$20',
    annual: '$200',
    monthlySuffix: '/ month',
    annualSuffix: '/ year',
    annualSubcopy: '$16.67/mo billed annually',
    annualSavingsBadge: 'Save 2 mo',
    hasToggle: true,
    features: [
      { included: true, label: 'Everything in Basic' },
      {
        included: true,
        label:
          'Full server completion pass (Parakeet 1.1B fp16 + pyannote 3.1 + Qwen 3.6 35B-A3B-Vision summary)',
      },
      { included: true, label: 'Audio upload + 90-day compressed retention' },
      { included: true, label: 'Full speaker library + speaker recognition' },
      { included: true, label: 'Brigade knowledge graph integration' },
      {
        included: true,
        label: 'All cross-app handles in MCP results (Contact-Ops, Project-Ops, Crisis-Ops)',
      },
      { included: true, label: 'Bulk import (526+ historical meetings in one shot)' },
      { included: false, label: 'Cross-app subscription on other UC apps' },
      { included: false, label: 'Live server diarization (Enterprise / Founding 100 only)' },
    ],
    ctaLabel: 'Subscribe to Pro',
    checkoutPlan: 'pro',
    highlight: true,
  },
  {
    key: 'suite',
    name: 'Suite',
    tagline: 'The full UC ecosystem under one subscription',
    monthly: '$35',
    annual: '$350',
    monthlySuffix: '/ month',
    annualSuffix: '/ year',
    annualSubcopy: '$29.17/mo billed annually',
    annualSavingsBadge: 'Save 2 mo',
    hasToggle: true,
    features: [
      { included: true, label: 'Everything in Pro on Meeting-Ops' },
      { included: true, label: 'Project-Ops Pro included' },
      { included: true, label: 'Contact-Ops Pro included' },
      { included: true, label: 'Brigade graph + federation (cross-app KG)' },
      { included: true, label: 'Future UC apps included as they ship' },
      { included: true, label: 'One subscription, one login (via Brigade federation when it lands)' },
    ],
    ctaLabel: 'Subscribe to Suite',
    checkoutPlan: 'suite',
    footnote:
      'Suite cross-app sync is rolling out — Pro benefits on Project-Ops and Contact-Ops light up as soon as our federation gateway deploys. Subscribe now to lock in the price.',
  },
  {
    key: 'enterprise',
    name: 'Enterprise',
    tagline: 'For teams that need compliance and control',
    monthly: 'Custom',
    annual: null,
    monthlySuffix: '',
    annualSuffix: '',
    annualSubcopy: null,
    annualSavingsBadge: null,
    hasToggle: false,
    features: [
      { included: true, label: 'Everything in Suite' },
      { included: true, label: 'Multi-seat with admin controls (10+ seats)' },
      { included: true, label: 'SSO / SCIM provisioning' },
      { included: true, label: 'BAA available (HIPAA)' },
      { included: true, label: 'BYOK model selection (Claude, GPT-4, Llama, your own fine-tunes)' },
      { included: true, label: 'On-prem / VPC deployment available' },
      { included: true, label: 'Custom retention policies' },
      { included: true, label: 'Priority support + SLA' },
      { included: true, label: 'Live server diarization (Sortformer streaming)' },
    ],
    ctaLabel: 'Contact sales',
    ctaHref: ENTERPRISE_MAILTO,
  },
];

const iconByPlan: Record<TierCard['key'], React.ReactNode> = {
  free: <Sparkles className="h-5 w-5 text-fuchsia-300" />,
  basic: <Zap className="h-5 w-5 text-fuchsia-300" />,
  pro: <BrainCircuit className="h-5 w-5 text-fuchsia-300" />,
  suite: <Layers className="h-5 w-5 text-fuchsia-300" />,
  enterprise: <Building2 className="h-5 w-5 text-fuchsia-300" />,
};

export const Pricing: React.FC = () => {
  const navigate = useNavigate();
  const [checkoutBusy, setCheckoutBusy] = useState<string | null>(null);
  const [checkoutError, setCheckoutError] = useState<string | null>(null);
  /**
   * Single global Monthly/Annual toggle (session-scoped, no localStorage).
   * Free + Enterprise ignore this; Basic / Pro / Suite swap their displayed
   * price and pass the chosen cycle through to /api/billing/checkout.
   */
  const [cycle, setCycle] = useState<BillingCycle>('monthly');
  const loggedIn = isLoggedIn();

  useEffect(() => {
    // `from_referrer` is the document referrer host (or 'direct'). We
    // deliberately don't send the full URL — just where the visit came
    // from at a coarse grain.
    let fromReferrer = 'direct';
    try {
      if (document.referrer) fromReferrer = new URL(document.referrer).host || 'direct';
    } catch {
      /* malformed referrer — keep 'direct' */
    }
    track('pricing_viewed', { from_referrer: fromReferrer });
  }, []);

  const handleSubscribe = async (plan: CheckoutPlan) => {
    setCheckoutError(null);
    if (plan === 'enterprise') {
      // Defensive: shouldn't reach here (Enterprise CTA is a mailto), but
      // keep behaviour explicit if a future card flips this.
      window.location.href = ENTERPRISE_MAILTO;
      return;
    }
    if (!loggedIn) {
      // Carry intent + cycle through signup so the user lands back here
      // with the same toggle position they picked.
      const returnTo = `/pricing?cycle=${cycle}&plan=${plan}`;
      navigate(`/signup?return_to=${encodeURIComponent(returnTo)}`);
      return;
    }
    setCheckoutBusy(plan);
    try {
      // Stash intent so App.tsx can fire `subscription_started` on the
      // post-Stripe success redirect with the plan + cycle attached.
      try {
        window.sessionStorage.setItem(
          PENDING_CHECKOUT_KEY,
          JSON.stringify({ plan, billing_cycle: cycle }),
        );
      } catch {
        /* sessionStorage unavailable — the conversion event just won't fire */
      }
      await startCheckout(plan, cycle);
      // startCheckout redirects on success; still here = failed.
    } catch (err) {
      const msg =
        err instanceof BillingUnavailableError
          ? 'Stripe Checkout is not enabled yet on this instance. Email hello@magicunicorn.dev to upgrade.'
          : err instanceof Error
            ? err.message
            : 'Could not start checkout. Try again in a moment.';
      setCheckoutError(msg);
      setCheckoutBusy(null);
    }
  };

  const handleManageSubscription = async () => {
    setCheckoutError(null);
    try {
      await startPortal();
    } catch (err) {
      const msg =
        err instanceof BillingUnavailableError
          ? 'Billing portal is not enabled on this instance.'
          : err instanceof Error
            ? err.message
            : 'Could not open billing portal.';
      setCheckoutError(msg);
    }
  };

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <div className="mx-auto w-full max-w-7xl px-4 py-6 lg:px-8">
        <header className="flex items-center justify-between border-b border-white/10 pb-4">
          <Link to="/login" className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-fuchsia-500 to-violet-500 shadow-lg shadow-fuchsia-500/20">
              <Sparkles className="h-5 w-5 text-white" />
            </div>
            <div>
              <div className="text-sm font-semibold tracking-tight text-white">Meeting-Ops</div>
              <div className="text-xs text-zinc-400">Pricing</div>
            </div>
          </Link>
          <div className="flex items-center gap-2">
            <Link
              to="/login"
              className="rounded-full border border-white/10 px-3 py-2 text-sm text-zinc-300 transition hover:border-fuchsia-400/40 hover:text-white"
            >
              Sign in
            </Link>
            <Link
              to="/signup"
              className="inline-flex items-center gap-2 rounded-full bg-white/5 px-3 py-2 text-sm text-zinc-100 transition hover:bg-white/10"
            >
              <ArrowRight className="h-4 w-4" />
              Sign up
            </Link>
          </div>
        </header>

        <main className="py-10">
          <div className="max-w-3xl space-y-4">
            <div className="inline-flex items-center gap-2 rounded-full border border-fuchsia-500/30 bg-fuchsia-500/10 px-3 py-1 text-xs font-medium text-fuchsia-200">
              <Users className="h-3.5 w-3.5" />
              Free, Pro, Suite, and Enterprise
            </div>
            <h1 className="text-4xl font-semibold tracking-tight text-white sm:text-5xl">
              Choose the tier that matches how you work.
            </h1>
            <p className="max-w-2xl text-base leading-7 text-zinc-300">
              Meeting and conversation intelligence — the platform for teams that take
              their calls seriously. Browser-first by default, server-grade when you
              want it, and one subscription for the whole UC ecosystem when you grow
              into it.
            </p>
          </div>

          {loggedIn && (
            <div className="mt-6">
              <button
                type="button"
                onClick={handleManageSubscription}
                className="text-sm text-fuchsia-200 underline-offset-4 hover:underline"
              >
                View existing subscription
              </button>
            </div>
          )}

          {checkoutError && (
            <div
              role="alert"
              className="mt-6 rounded-2xl border border-amber-400/30 bg-amber-500/10 p-4 text-sm text-amber-100"
            >
              {checkoutError}
            </div>
          )}

          {/* Global Monthly / Annual toggle. Applies to Basic / Pro / Suite. */}
          <div className="mt-10 flex items-center justify-center">
            <div
              className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-zinc-900/60 p-1 text-xs"
              role="tablist"
              aria-label="Billing cycle"
            >
              <button
                type="button"
                role="tab"
                aria-selected={cycle === 'monthly'}
                onClick={() => setCycle('monthly')}
                className={`rounded-full px-4 py-2 transition ${
                  cycle === 'monthly'
                    ? 'bg-white text-zinc-950'
                    : 'text-zinc-300 hover:text-white'
                }`}
              >
                Monthly
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={cycle === 'annual'}
                onClick={() => setCycle('annual')}
                className={`inline-flex items-center gap-2 rounded-full px-4 py-2 transition ${
                  cycle === 'annual'
                    ? 'bg-white text-zinc-950'
                    : 'text-zinc-300 hover:text-white'
                }`}
              >
                Annual
                <span
                  className={`rounded-full px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${
                    cycle === 'annual'
                      ? 'bg-emerald-500/15 text-emerald-700'
                      : 'bg-emerald-500/20 text-emerald-200'
                  }`}
                >
                  Save 2 mo
                </span>
              </button>
            </div>
          </div>

          {/* 5-column tier grid at xl; stacks below. */}
          <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
            {tiers.filter((tier) => tier.key !== 'basic').map((tier) => {
              const showAnnual = tier.hasToggle && cycle === 'annual' && tier.annual !== null;
              const displayPrice = showAnnual ? tier.annual! : tier.monthly;
              const displaySuffix = showAnnual ? tier.annualSuffix : tier.monthlySuffix;
              const isHighlighted = !!tier.highlight;
              const popularityLabel = showAnnual ? 'Best value' : 'Most popular';

              return (
                <article
                  key={tier.key}
                  className={`flex flex-col rounded-3xl border p-6 shadow-xl shadow-black/20 ${
                    isHighlighted
                      ? 'border-fuchsia-400/40 bg-fuchsia-500/10'
                      : 'border-white/10 bg-zinc-900/70'
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-2">
                      {iconByPlan[tier.key]}
                      <h2 className="text-xl font-semibold text-white">{tier.name}</h2>
                    </div>
                    {isHighlighted && (
                      <span className="rounded-full border border-fuchsia-400/40 bg-fuchsia-400/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-fuchsia-100">
                        {popularityLabel}
                      </span>
                    )}
                  </div>

                  <div className="mt-3 text-sm text-zinc-400">{tier.tagline}</div>

                  <div className="mt-4 flex items-baseline gap-2">
                    <div className="text-3xl font-semibold tracking-tight text-white">
                      {displayPrice}
                    </div>
                    {displaySuffix && (
                      <div className="text-sm text-zinc-400">{displaySuffix}</div>
                    )}
                  </div>

                  {showAnnual && tier.annualSubcopy && (
                    <div className="mt-1 text-xs text-emerald-200">{tier.annualSubcopy}</div>
                  )}
                  {showAnnual && tier.annualSavingsBadge && (
                    <div className="mt-1">
                      <span className="inline-flex items-center rounded-full border border-emerald-400/30 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-emerald-200">
                        {tier.annualSavingsBadge}
                      </span>
                    </div>
                  )}

                  <ul className="mt-6 flex-1 space-y-2.5 text-sm text-zinc-300">
                    {tier.features.map((feature) => (
                      <li key={feature.label} className="flex items-start gap-2">
                        {feature.included ? (
                          <Check
                            className="mt-0.5 h-4 w-4 shrink-0 text-fuchsia-300"
                            aria-hidden="true"
                          />
                        ) : (
                          <X
                            className="mt-0.5 h-4 w-4 shrink-0 text-zinc-600"
                            aria-hidden="true"
                          />
                        )}
                        <span
                          className={`leading-6 ${
                            feature.included ? '' : 'text-zinc-500 line-through decoration-zinc-700'
                          }`}
                        >
                          {feature.label}
                        </span>
                      </li>
                    ))}
                  </ul>

                  {tier.footnote && (
                    <div className="mt-4 rounded-2xl border border-fuchsia-400/20 bg-fuchsia-500/5 p-3 text-xs leading-5 text-fuchsia-100">
                      {tier.footnote}
                    </div>
                  )}

                  <div className="mt-6">
                    {tier.checkoutPlan ? (
                      <button
                        type="button"
                        disabled={checkoutBusy === tier.checkoutPlan}
                        onClick={() => handleSubscribe(tier.checkoutPlan!)}
                        className={`inline-flex w-full items-center justify-center gap-2 rounded-xl px-4 py-3 text-sm font-semibold transition disabled:cursor-wait disabled:opacity-70 ${
                          isHighlighted
                            ? 'bg-white text-zinc-950 hover:bg-zinc-100'
                            : 'border border-white/10 bg-white/5 text-zinc-100 hover:bg-white/10'
                        }`}
                      >
                        {checkoutBusy === tier.checkoutPlan ? 'Redirecting…' : tier.ctaLabel}
                        <ArrowRight className="h-4 w-4" />
                      </button>
                    ) : tier.ctaHref ? (
                      <a
                        href={tier.ctaHref}
                        className={`inline-flex w-full items-center justify-center gap-2 rounded-xl px-4 py-3 text-sm font-semibold transition ${
                          isHighlighted
                            ? 'bg-white text-zinc-950 hover:bg-zinc-100'
                            : 'border border-white/10 bg-white/5 text-zinc-100 hover:bg-white/10'
                        }`}
                      >
                        {tier.ctaLabel}
                        <ArrowRight className="h-4 w-4" />
                      </a>
                    ) : tier.ctaTo ? (
                      <Link
                        to={tier.ctaTo}
                        className={`inline-flex w-full items-center justify-center gap-2 rounded-xl px-4 py-3 text-sm font-semibold transition ${
                          isHighlighted
                            ? 'bg-white text-zinc-950 hover:bg-zinc-100'
                            : 'border border-white/10 bg-white/5 text-zinc-100 hover:bg-white/10'
                        }`}
                      >
                        {tier.ctaLabel}
                        <ArrowRight className="h-4 w-4" />
                      </Link>
                    ) : null}
                  </div>
                </article>
              );
            })}
          </div>

          <p className="mt-8 max-w-3xl text-xs text-zinc-500">
            Every paid annual tier saves 2 months vs the monthly rate. Each subscription
            today includes one user — multi-seat invites and per-seat pricing arrive in a
            future release. Suite buyers get all Meeting-Ops Pro features immediately;
            Project-Ops and Contact-Ops Pro entitlements activate automatically as the
            Brigade federation gateway rolls out.
          </p>
        </main>

        {/* v3.22.5 legal footer for unauthenticated marketing pages. */}
        <LegalFooter />
      </div>
    </div>
  );
};

export default Pricing;
