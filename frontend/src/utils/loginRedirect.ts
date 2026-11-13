/**
 * Single-fire guard for the SSO sign-in start (/oauth2/start or
 * /api/auth/sso/uc/start).
 *
 * The SPA has FIVE+ places that redirect to the SSO start on auth failure
 * (fetch interceptor, AuthContext, utils/api wrapper, AppRouterSimplified,
 * Login). On initial page load, several fetches can 401 concurrently;
 * without a guard each one fires its own /oauth2/start which lands a
 * fresh PKCE challenge cookie that immediately overwrites the previous
 * one. When the callback comes back referencing the FIRST state, the
 * CSRF cookie holds the SECOND state's verifier, and Keycloak rejects
 * with "Code mismatch" and a 500. Seen 2026-05-18.
 *
 * Module-scope flag is sufficient: once we navigate away the entire
 * module reloads, so the flag resets naturally.
 *
 * L6 one-attempt guard (Bureau CX): the SSO start can itself be unreachable
 * (the identity provider is down, the backend is not). Without a guard the
 * app would bounce the visitor through the provider on every reload of the
 * same app route (the ProtectedRoute render effect re-fires after each
 * failed redirect returns). The marker below records that one attempt was
 * already made for THIS requested screen; a second redirect within the same
 * page life is suppressed so the visitor stays on the plain "sign-in
 * unavailable, retry" screen instead of looping.
 */
let inFlight = false;

const SSO_DOWN_KEY = 'mo-sso-start-attempted';
// The marker must survive the full-page round trip through the provider (a
// failed start comes back as a NEW document), so it is a timestamp in
// sessionStorage, not cleared at load. Within this window a second redirect is
// suppressed; after it a manual retry works again.
export const SSO_RETRY_WINDOW_MS = 2 * 60 * 1000;

export function ssoStartUrl(target: string): string {
  return ssoStartUrlFor(target, isNativeOidcHost());
}

export function ssoStartUrlFor(target: string, nativeOidc: boolean): string {
  const encoded = encodeURIComponent(target);
  return nativeOidc
    ? `/api/auth/sso/uc/start?returnTo=${encoded}`
    : `/oauth2/start?rd=${encoded}`;
}

export function isNativeOidcHost(): boolean {
  return (
    typeof window !== 'undefined' &&
    /(?:^|\.)unicorncommander\.ai$/i.test(window.location.hostname)
  );
}

export function redirectToLogin(rd?: string): void {
  if (inFlight) return;
  if (readSsoDown()) return;
  inFlight = true;
  writeSsoDown();
  const target =
    rd ?? `${window.location.pathname}${window.location.hash}`;
  window.location.href = ssoStartUrl(target);
}

function readSsoDown(): boolean {
  try {
    const at = Number(sessionStorage.getItem(SSO_DOWN_KEY));
    return Number.isFinite(at) && at > 0 && Date.now() - at < SSO_RETRY_WINDOW_MS;
  } catch {
    return false;
  }
}

function writeSsoDown(): void {
  try {
    sessionStorage.setItem(SSO_DOWN_KEY, String(Date.now()));
  } catch {
    /* storage unavailable: the in-flight flag still prevents double-fire */
  }
}

/**
 * Drop the one-attempt marker. Called by AuthContext when the SSO probe
 * finds a live session, and by an explicit user retry. Never at page load:
 * that would defeat the guard on the provider round trip.
 */
export function resetSsoAttemptGuard(): void {
  inFlight = false;
  try {
    sessionStorage.removeItem(SSO_DOWN_KEY);
  } catch {
    /* ignore */
  }
}
