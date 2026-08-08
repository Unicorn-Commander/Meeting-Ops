// Pricing display constants — single source of truth for the Pro price.
// -----------------------------------------------------------------------------
// This is the ONLY place the Pro price is written for display. Every in-app
// surface that shows it (Landing card + FAQ, the /pricing page, the
// UpgradeBanner, the Settings → Plan & billing panel) imports from here, so the
// hub can change the shown price by editing this one file.
//
// IMPORTANT: this is DISPLAY ONLY. The amount actually charged is resolved
// server-side — the backend maps the `pro` plan to its Stripe price ID in
// `startCheckout('pro')`. Changing the number here does NOT change what a
// customer is billed; it only changes the copy. Keep the two in sync manually.
//
// LADDER (locked 2026-08-08). Pro is $15/mo standing — not a launch rate, not a
// discount off anything. The live Stripe prices behind it are:
//   $15/mo  price_1TonlODzk9HqAZnHqA8Y7d7L  (STRIPE_PRO_PRICE_ID)
//   $150/yr price_1TonlODzk9HqAZnHPmVQGCGO  (STRIPE_PRO_ANNUAL_PRICE_ID)
// Annual has no UI yet, so it is deliberately NOT displayed here — an
// advertised price a customer cannot buy is the same defect as a wrong one.
//
// WHY THERE IS NO "$20 LIST" ANCHOR ANYMORE
// A struck-through $20 with "25% off" shipped in v3.50.0 on the reasoning that
// $20 was a bona-fide prior standing price. It was not. $20/mo existed only as
// a Stripe price object (created v3.23.0, 2026-06-02); no UI ever called
// checkout until v3.50.0 (2026-07-07), and that release shipped AT $15. Nobody
// was ever offered Pro at $20, and the account has never had a single
// subscription at any price. A reference price nobody was ever charged is a
// fabricated discount, so it is gone. If a real increase is wanted later, raise
// PRO_MONTHLY_PRICE_USD — do not re-add an anchor.
// -----------------------------------------------------------------------------

/** Pro monthly price in whole US dollars (display only). */
export const PRO_MONTHLY_PRICE_USD = 15;

/** Formatted price without a period, e.g. "$15". */
export const PRO_MONTHLY_PRICE_DISPLAY = `$${PRO_MONTHLY_PRICE_USD}`;

/** Formatted price with a short period, e.g. "$15/mo". */
export const PRO_MONTHLY_PRICE_WITH_PERIOD = `${PRO_MONTHLY_PRICE_DISPLAY}/mo`;
