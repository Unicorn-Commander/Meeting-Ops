import React, { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Sparkles, ArrowRight } from 'lucide-react';
import { track } from '../utils/posthog';

/**
 * Pricing lives on the canonical Unicorn Commander storefront (Free + Meeting-Ops
 * $15/mo) — Stripe checkout + entitlement are provisioned there. This in-app
 * route used to render its own 5-tier page and run a second Stripe checkout,
 * which drifted from the storefront ("two prices for one product"). It now
 * redirects to the single commerce surface. Every in-app upgrade CTA funnels
 * through /pricing, so this one redirect routes them all to the storefront.
 */
const STOREFRONT_PRICING_URL = 'https://unicorncommander.ai/pricing';

export const Pricing: React.FC = () => {
  useEffect(() => {
    let fromReferrer = 'direct';
    try {
      if (document.referrer) fromReferrer = new URL(document.referrer).host || 'direct';
    } catch {
      /* malformed referrer — keep 'direct' */
    }
    track('pricing_viewed', { from_referrer: fromReferrer, redirect: 'uc_storefront' });
    // replace() so Back doesn't bounce the user into this redirect again.
    window.location.replace(STOREFRONT_PRICING_URL);
  }, []);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 bg-zinc-950 px-6 text-center text-zinc-100">
      <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-fuchsia-500 to-violet-500 shadow-lg shadow-fuchsia-500/20">
        <Sparkles className="h-6 w-6 text-white" />
      </div>
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight text-white">Taking you to pricing…</h1>
        <p className="max-w-md text-sm text-zinc-400">
          Meeting-Ops pricing — Free or $15/mo — lives on the Unicorn Commander storefront.
        </p>
      </div>
      <a
        href={STOREFRONT_PRICING_URL}
        className="inline-flex items-center gap-2 rounded-xl bg-white px-5 py-3 text-sm font-semibold text-zinc-950 transition hover:bg-zinc-100"
      >
        Continue to pricing
        <ArrowRight className="h-4 w-4" />
      </a>
      <Link to="/login" className="text-sm text-fuchsia-200 underline-offset-4 hover:underline">
        Back to Meeting-Ops
      </Link>
    </div>
  );
};

export default Pricing;
