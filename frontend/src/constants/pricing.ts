// Pricing display constants — single source of truth for the Pro price.
// -----------------------------------------------------------------------------
// This is the ONLY place the Pro price is written for display. Every in-app
// surface that shows it (Landing card + FAQ, the /pricing page, the
// UpgradeBanner, the Settings → Plan & billing panel) imports from here, so the
// hub can change the shown price by editing this one file.
//
// IMPORTANT: this is DISPLAY ONLY. The amount actually charged is resolved
// server-side — the backend maps the `pro` plan + billing cycle to a Stripe
// price ID in `startCheckout('pro', cycle)`. Changing a number here does NOT
// change what a customer is billed; it only changes the copy. Keep the two in
// sync manually.
//
// LADDER (repriced 2026-08-08, Aaron: "Shouldn't meeting-ops be more? We didn't
// want a race to the bottom."). Pro is $22/mo standing, or $216/yr. Both are
// standing prices, not launch rates and not a discount off anything. The live
// Stripe prices behind them are:
//   $22/mo   price_1U2LVNDzk9HqAZnHVvaNigJ0  (STRIPE_PRO_PRICE_ID)
//   $216/yr  price_1U2LVrDzk9HqAZnH4dL6Oypc  (STRIPE_PRO_ANNUAL_PRICE_ID)
// Both are livemode, active, and on prod_UborP589krk3ur — the same product the
// live checkout already used. The previous $15/$150 pair
// (price_1TonlO…qA8Y7d7L / price_1TonlO…PmVQGCGO) is ARCHIVED in Stripe.
//
// WHERE $22 / $216 COME FROM
// Aaron's own written decision, ~/Documents/Site-Refresh-2026-08-06/
// DECISIONS-2026-08-07.txt: "$18/seat/mo annual, $22 monthly". $18 × 12 = $216.
// It sits at the top of the sourced competitor band (Granola $14, Otter $16.99,
// Fireflies $18–19, Fathom $20–34) rather than under it.
//
// THE ANNUAL SAVING IS COMPUTED, NOT CLAIMED
// Do not hand-write a "save X%" string. Both savings constants below are
// derived from the two real prices ($22 × 12 = $264; $264 − $216 = $48; $216 ÷
// 12 = $18). If either price changes, the saving follows automatically and
// cannot drift into a lie.
//
// THERE IS NO LIST-PRICE ANCHOR, AND THERE MUST NEVER BE ONE
// A struck-through $20 with "25% off" shipped in v3.50.0 on the reasoning that
// $20 was a bona-fide prior standing price. It was not. $20/mo existed only as
// a Stripe price object (created v3.23.0, 2026-06-02); no UI ever called
// checkout against it, and that release shipped AT $15. Nobody was ever offered
// Pro at $20. Likewise: $15 WAS a real standing price until today, but the
// account has never had a single subscription at any price, so nobody ever paid
// it either — striking through $15 to make $22 look like a deal would be the
// same fabricated discount in a new costume. Show the price. Do not anchor it.
// -----------------------------------------------------------------------------

/** Pro monthly price in whole US dollars (display only). */
export const PRO_MONTHLY_PRICE_USD = 22;

/** Pro annual price in whole US dollars, billed once a year (display only). */
export const PRO_ANNUAL_PRICE_USD = 216;

/** Formatted price without a period, e.g. "$22". */
export const PRO_MONTHLY_PRICE_DISPLAY = `$${PRO_MONTHLY_PRICE_USD}`;

/** Formatted price with a short period, e.g. "$22/mo". */
export const PRO_MONTHLY_PRICE_WITH_PERIOD = `${PRO_MONTHLY_PRICE_DISPLAY}/mo`;

/** Formatted annual price without a period, e.g. "$216". */
export const PRO_ANNUAL_PRICE_DISPLAY = `$${PRO_ANNUAL_PRICE_USD}`;

/** Formatted annual price with a short period, e.g. "$216/yr". */
export const PRO_ANNUAL_PRICE_WITH_PERIOD = `${PRO_ANNUAL_PRICE_DISPLAY}/yr`;

/**
 * What the annual plan works out to per month ($18), rounded to whole dollars
 * only because $216 / 12 is exact. Derived, never typed.
 */
export const PRO_ANNUAL_PRICE_PER_MONTH_USD = PRO_ANNUAL_PRICE_USD / 12;

/** e.g. "$18/mo" — the annual plan expressed as a monthly equivalent. */
export const PRO_ANNUAL_PRICE_PER_MONTH_WITH_PERIOD = `$${
  Number.isInteger(PRO_ANNUAL_PRICE_PER_MONTH_USD)
    ? PRO_ANNUAL_PRICE_PER_MONTH_USD
    : PRO_ANNUAL_PRICE_PER_MONTH_USD.toFixed(2)
}/mo`;

/** Dollars saved in a year by paying annually instead of monthly ($48). */
export const PRO_ANNUAL_SAVING_USD =
  PRO_MONTHLY_PRICE_USD * 12 - PRO_ANNUAL_PRICE_USD;

/** e.g. "$48" — the real annual saving, computed from the two real prices. */
export const PRO_ANNUAL_SAVING_DISPLAY = `$${PRO_ANNUAL_SAVING_USD}`;
