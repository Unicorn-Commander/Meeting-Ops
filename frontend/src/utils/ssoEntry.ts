// Bureau CX L6: the SSO bootstrap runs BEFORE the router decides anything.
// A visitor who arrives on an app hash route (for example /#/sessions, the
// route Ops-Center app cards link to) without a Meeting-Ops session must
// start the identity-provider redirect immediately and come back to the
// requested screen. A visitor on the bare root with no session stays on the
// public marketing page. The AuthContext /api/auth/me probe reads this flag
// (via hasAppRouteEntry) to know which of the two to do. Evaluated once at
// module load, before React renders anything.
export function hasAppRouteEntry(): boolean {
  try {
    const hash = window.location.hash || '';
    const path = hash.replace(/^#/, '').split('?')[0] || '/';
    return path !== '/' && path !== '';
  } catch {
    return false;
  }
}
