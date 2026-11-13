import { describe, it, expect, beforeEach } from 'vitest';
import {
  isNativeOidcHost,
  redirectToLogin,
  resetSsoAttemptGuard,
  ssoStartUrlFor,
} from '../utils/loginRedirect';

// jsdom: `window.location.href = ...` cannot navigate, so the module's
// in-flight flag would latch after the first test. resetSsoAttemptGuard()
// clears both the flag and the marker between tests.

function stubLocation(hash: string, pathname = '/', hostname = 'meetingops.example.com') {
  Object.defineProperty(window, 'location', {
    value: { pathname, hash, hostname, href: '' },
    writable: true,
    configurable: true,
  });
}

function stubStorage(store: Record<string, string>) {
  Object.defineProperty(window, 'sessionStorage', {
    value: {
      getItem: (key: string) => store[key] ?? null,
      setItem: (key: string, value: string) => { store[key] = value; },
      removeItem: (key: string) => { delete store[key]; },
      clear: () => { Object.keys(store).forEach((k) => delete store[k]); },
    },
    writable: true,
    configurable: true,
  });
}

function href(): string {
  return (window as unknown as { location: { href: string } }).location.href;
}

beforeEach(() => {
  stubLocation('');
  stubStorage({});
  resetSsoAttemptGuard();
});

describe('ssoStartUrl', () => {
  it('targets the native OIDC start with the encoded returnTo', () => {
    const url = ssoStartUrlFor('/#/sessions?tab=open', true);
    expect(url).toBe(`/api/auth/sso/uc/start?returnTo=${encodeURIComponent('/#/sessions?tab=open')}`);
  });

  it('targets the oauth2-proxy start with the encoded rd', () => {
    const url = ssoStartUrlFor('/index.html#/record/personal', false);
    expect(url).toBe(`/oauth2/start?rd=${encodeURIComponent('/index.html#/record/personal')}`);
  });

  it('preserves the requested app route in the redirect target', () => {
    stubLocation('#/sessions/abc?tab=transcript', '/index.html');
    redirectToLogin();
    expect(href()).toBe(
      `/oauth2/start?rd=${encodeURIComponent('/index.html#/sessions/abc?tab=transcript')}`,
    );
  });

  it('detects the native OIDC host from the hostname', () => {
    stubLocation('', '/', 'meeting-ops.unicorncommander.ai');
    expect(isNativeOidcHost()).toBe(true);
    stubLocation('', '/', 'meetingops.magicunicorn.dev');
    expect(isNativeOidcHost()).toBe(false);
  });
});

describe('redirectToLogin one-attempt guard', () => {
  it('suppresses a second redirect when the provider is down', () => {
    stubLocation('#/sessions');
    redirectToLogin();
    const first = href();
    expect(first).toBe(`/oauth2/start?rd=${encodeURIComponent('/#/sessions')}`);

    // The failed redirect bounced the visitor back to the same app route;
    // the render effect fires again. Must NOT start a second attempt.
    redirectToLogin();
    expect(href()).toBe(first);
  });

  it('a pre-set down marker blocks the very first redirect', () => {
    stubLocation('#/sessions');
    const store = (window as unknown as { sessionStorage: Storage }).sessionStorage;
    store.setItem('mo-sso-start-attempted', '1');

    redirectToLogin();
    expect(href()).toBe('');
  });

  it('resetSsoAttemptGuard lets a manual retry fire again', () => {
    stubLocation('#/sessions');
    const store = (window as unknown as { sessionStorage: Storage }).sessionStorage;
    store.setItem('mo-sso-start-attempted', '1');

    redirectToLogin();
    expect(href()).toBe('');

    resetSsoAttemptGuard();

    redirectToLogin();
    expect(href()).toBe(`/oauth2/start?rd=${encodeURIComponent('/#/sessions')}`);
  });

  it('explicit returnTo targets are honored', () => {
    stubLocation('#/');
    redirectToLogin('/#/sessions');
    expect(href()).toBe(`/oauth2/start?rd=${encodeURIComponent('/#/sessions')}`);
  });
});
