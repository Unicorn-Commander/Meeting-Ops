// Billing API client — wraps /api/billing/{checkout,portal,subscription}.
//
// All three endpoints require the JWT token. If they 503, billing is
// not configured on this instance (test sandbox, on-prem appliance
// without Stripe) — callers should fall back to the mailto: CTA the
// Pricing page already has, not show a broken-flow toast.
//
// The Checkout + Portal flows are window.location redirects (we don't
// open them in a popup). Stripe's hosted Checkout handles the rest:
// success_url and cancel_url are configured server-side.

import { config } from '../config';

export interface CheckoutResponse {
  url: string;
}

export interface PortalResponse {
  url: string;
}

export interface SubscriptionState {
  tier: string;
  is_founding_member: boolean;
  founding_cohort?: string | null;
  has_subscription: boolean;
  subscription_id?: string | null;
  status?: string | null;
  price_id?: string | null;
  current_period_end?: string | null;
  cancel_at_period_end: boolean;
}

export class BillingUnavailableError extends Error {
  constructor(message = 'Billing is not configured on this instance.') {
    super(message);
    this.name = 'BillingUnavailableError';
  }
}

function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  try {
    const token = localStorage.getItem('access_token');
    if (token) headers['Authorization'] = `Bearer ${token}`;
  } catch {
    /* ignore storage failures */
  }
  return headers;
}

async function postBilling<T>(path: string, body?: object): Promise<T> {
  const r = await fetch(`${config.apiBaseUrl}${path}`, {
    method: 'POST',
    headers: authHeaders(),
    body: body ? JSON.stringify(body) : undefined,
  });
  if (r.status === 503) {
    throw new BillingUnavailableError();
  }
  if (!r.ok) {
    let detail = `${r.status} ${r.statusText}`;
    try {
      const data = await r.json();
      if (data?.detail) detail = data.detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return (await r.json()) as T;
}

/**
 * Start a Stripe Checkout session for the given plan and redirect the
 * browser to the hosted Checkout URL.
 *
 * `plan` is "pro" (Aaron's only Checkout-able tier in v1).
 *
 * Returns void — the redirect happens synchronously. Callers wanting
 * to handle errors should `await startCheckout(...)` inside a try/catch
 * and toast on the rethrown error.
 */
export async function startCheckout(plan: string): Promise<void> {
  const data = await postBilling<CheckoutResponse>('/api/billing/checkout', { plan });
  if (data.url) {
    window.location.href = data.url;
  } else {
    throw new Error('Checkout URL not returned');
  }
}

/**
 * Start a Stripe Billing Portal session and redirect the browser to it.
 * Used for the "View existing subscription" link on /pricing.
 */
export async function startPortal(): Promise<void> {
  const data = await postBilling<PortalResponse>('/api/billing/portal');
  if (data.url) {
    window.location.href = data.url;
  } else {
    throw new Error('Portal URL not returned');
  }
}

/**
 * Read the current user's subscription state. Returns `has_subscription:
 * false` if billing is unconfigured or the user has no Stripe customer.
 * Throws only on real network/auth errors.
 */
export async function fetchSubscription(): Promise<SubscriptionState> {
  const r = await fetch(`${config.apiBaseUrl}/api/billing/subscription`, {
    headers: authHeaders(),
  });
  if (!r.ok) {
    throw new Error(`${r.status} ${r.statusText}`);
  }
  return (await r.json()) as SubscriptionState;
}
