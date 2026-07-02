// Pricing display constants — single source of truth for the Pro price.
// -----------------------------------------------------------------------------
// This is the ONLY place the Pro monthly price is written for display. Every
// in-app surface that shows the Pro price (Landing card + FAQ, the /pricing
// page, the UpgradeBanner, the Settings → Plan & billing panel) imports from
// here, so the hub can change the shown price by editing this one file.
//
// IMPORTANT: this is DISPLAY ONLY. The amount actually charged is resolved
// server-side — the backend maps the `pro` plan to its Stripe price ID in
// `startCheckout('pro')`. Changing the number here does NOT change what a
// customer is billed; it only changes the copy. Keep the two in sync manually.
// -----------------------------------------------------------------------------

/** Pro monthly price in whole US dollars (display only). */
export const PRO_MONTHLY_PRICE_USD = 15;

/** Formatted price without a period, e.g. "$15". */
export const PRO_MONTHLY_PRICE_DISPLAY = `$${PRO_MONTHLY_PRICE_USD}`;

/** Formatted price with a short period, e.g. "$15/mo". */
export const PRO_MONTHLY_PRICE_WITH_PERIOD = `${PRO_MONTHLY_PRICE_DISPLAY}/mo`;
