// Bureau CX L6: the SSO bootstrap runs BEFORE the router decides anything.
// A visitor who arrives on an app hash route (for example /#/sessions, the
// route Ops-Center app cards link to) without a Meeting-Ops session must
// start the identity-provider redirect immediately and come back to the
// requested screen. A visitor on the bare root with no session stays on the
// public marketing page. The AuthContext /api/auth/me probe reads this flag
// (via hasAppRouteEntry) to know which of the two to do. Evaluated once at
// module load, before React renders anything.
const AUTH_ROUTES = ['/login', '/signup', '/register', '/verify', '/forgot-password', '/reset-password'];

export function hasAppRouteEntry(): boolean {
  try {
    const hash = window.location.hash || '';
    const path = hash.replace(/^#/, '').split('?')[0] || '/';
    // Auth screens are where a failed start lands (#/login?sso_error=...);
    // treating them as app routes would redirect straight back into the loop.
    if (hash.includes('sso_error=')) return false;
    if (AUTH_ROUTES.some((r) => path === r || path.startsWith(`${r}/`))) return false;
    return path !== '/' && path !== '';
  } catch {
    return false;
  }
}
