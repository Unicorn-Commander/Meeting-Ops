/**
 * Global fetch interceptor — installs at module load time.
 *
 * Wraps window.fetch so every request to /api/* gets stale-session
 * detection without per-page migration. Detects:
 *   - 302 redirects to oauth2-proxy / Keycloak (stale session cookie)
 *   - HTML responses when JSON was expected (oauth2-proxy 401 page)
 *
 * On detection: shows the ReconnectingOverlay and redirects through
 * /oauth2/start so the SPA gets a fresh KC session and lands back
 * on the same hash route.
 *
 * Active-recording guard
 * -----------------------
 * Long-running captures regularly outlive the oauth2-proxy cookie_refresh
 * window (60 min on bigboy). The first audio-chunk save after refresh
 * fails would otherwise force `window.location.href = /oauth2/start`,
 * killing the recording mid-meeting. Instead, when the recording
 * contexts have marked the session as live via `setRecordingActive(true)`
 * we DEFER the redirect: the overlay surfaces with a "session expired —
 * tap to resume" prompt, the failing fetch still returns 401 so the
 * caller can buffer/retry locally, and the redirect only fires once
 * recording actually stops (or the user explicitly opts in).
 */
import { setReconnectingState } from '../components/ReconnectingOverlay';
import { redirectToLogin } from './loginRedirect';

const _originalFetch = window.fetch.bind(window);

// Module-level claim set the recording contexts flip — see AlwaysOnContext +
// RecordingContext. Each context owns a distinct key (`alwaysOn`,
// `recordingContext`) so neither one's stop-handler ever clears the
// other's claim by mistake.
const activeRecordingClaims = new Set<string>();
let redirectDeferred = false;

export function setRecordingActive(key: string, active: boolean): void {
  const wasActive = activeRecordingClaims.size > 0;
  if (active) activeRecordingClaims.add(key);
  else activeRecordingClaims.delete(key);
  const isActive = activeRecordingClaims.size > 0;
  // Recording just stopped (no claims remaining) AND we had previously
  // deferred a redirect → surface it now so the user re-auths instead of
  // staring at a dead overlay.
  if (wasActive && !isActive && redirectDeferred) {
    redirectDeferred = false;
    setTimeout(() => { redirectToLogin(); }, 50);
  }
}

function isApiUrl(urlStr: string): boolean {
  // Same-origin /api/* OR absolute https://meetingops.../api/*
  if (urlStr.startsWith('/api/') || urlStr.startsWith('/ws/')) return true;
  try {
    const u = new URL(urlStr, window.location.origin);
    return (u.pathname.startsWith('/api/') || u.pathname.startsWith('/ws/')) &&
           u.origin === window.location.origin;
  } catch {
    return false;
  }
}

function triggerReconnect() {
  try { setReconnectingState(true); } catch { /* component may not be mounted yet */ }
  if (activeRecordingClaims.size > 0) {
    // Hold the redirect — recording is live and we'd lose the capture if
    // we kicked the user to /oauth2/start. The overlay stays up; the
    // setRecordingActive(false) callback runs the redirect once recording
    // actually stops. The failing fetch still returns 401, so any
    // caller-side retry/buffer logic kicks in normally.
    redirectDeferred = true;
    return;
  }
  // Use a small delay so React has a frame to render the overlay
  setTimeout(() => { redirectToLogin(); }, 50);
}

const interceptedFetch: typeof fetch = async (input, init) => {
  const urlStr = typeof input === 'string'
    ? input
    : input instanceof URL
      ? input.toString()
      : input.url;

  if (!isApiUrl(urlStr)) {
    // Pass through non-API calls untouched
    return _originalFetch(input as RequestInfo, init);
  }

  // Force JSON Accept header so oauth2-proxy is more likely to return
  // a 401/JSON instead of an HTML login page if it can't find a session.
  const headers = new Headers(init?.headers || {});
  if (!headers.has('Accept')) headers.set('Accept', 'application/json');

  // redirect: 'manual' so we can detect the 302 to Keycloak ourselves;
  // letting the browser follow the redirect would CORS-fail at auth.<domain>.
  const finalInit: RequestInit = {
    ...init,
    headers,
    redirect: init?.redirect || 'manual',
  };

  let response: Response;
  try {
    response = await _originalFetch(input as RequestInfo, finalInit);
  } catch (err) {
    // A network error on an API call almost always means the browser
    // tried to follow a cross-origin redirect (oauth2-proxy → Keycloak)
    // and CORS-blocked. Treat as stale session.
    triggerReconnect();
    throw err;
  }

  // Manual-mode opaque redirect → status 0, type === 'opaqueredirect'
  if (response.type === 'opaqueredirect' || response.status === 0 || response.status === 302) {
    triggerReconnect();
    return new Response(JSON.stringify({ detail: 'Reconnecting…' }), {
      status: 401,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  // HTML body when JSON was expected → oauth2-proxy unauth page or similar
  const ct = response.headers.get('content-type') || '';
  if (ct.startsWith('text/html')) {
    triggerReconnect();
    return new Response(JSON.stringify({ detail: 'Reconnecting…' }), {
      status: 401,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  return response;
};

// Install once at module load. Idempotent — won't double-wrap on HMR.
if (!(window as unknown as { __meetOpsFetchInterceptor?: boolean }).__meetOpsFetchInterceptor) {
  window.fetch = interceptedFetch;
  (window as unknown as { __meetOpsFetchInterceptor?: boolean }).__meetOpsFetchInterceptor = true;
}

export {};
