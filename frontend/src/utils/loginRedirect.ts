/**
 * Single-fire guard for /oauth2/start.
 *
 * The SPA has FIVE+ places that redirect to /oauth2/start on auth failure
 * (fetch interceptor, AuthContext, utils/api wrapper, AppRouterSimplified,
 * Login). On initial page load, several fetches can 401 concurrently;
 * without a guard each one fires its own /oauth2/start which lands a
 * fresh PKCE challenge cookie that immediately overwrites the previous
 * one. When the callback comes back referencing the FIRST state, the
 * CSRF cookie holds the SECOND state's verifier → Keycloak rejects
 * with "Code mismatch" and a 500. Seen 2026-05-18.
 *
 * Module-scope flag is sufficient — once we navigate away the entire
 * module reloads.
 */
let inFlight = false;

export function redirectToLogin(rd?: string): void {
  if (inFlight) return;
  inFlight = true;
  const target =
    rd ?? `${window.location.pathname}${window.location.hash}`;
  window.location.href = `/oauth2/start?rd=${encodeURIComponent(target)}`;
}
