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
 */
import { setReconnectingState } from '../components/ReconnectingOverlay';

const OAUTH2_PROXY_LOGIN_PATTERN = /\/oauth2\/(start|sign_out|callback)/i;
const KEYCLOAK_PATTERN = /\/realms\/[^/]+\/protocol\/openid-connect/i;

const _originalFetch = window.fetch.bind(window);

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
  // Preserve current hash route so user lands back where they were
  const rd = encodeURIComponent(window.location.pathname + window.location.hash);
  // Use a small delay so React has a frame to render the overlay
  setTimeout(() => {
    window.location.href = `/oauth2/start?rd=${rd}`;
  }, 50);
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
