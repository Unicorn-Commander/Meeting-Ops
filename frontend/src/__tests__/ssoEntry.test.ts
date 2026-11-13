import { describe, it, expect } from 'vitest';
import { hasAppRouteEntry } from '../utils/ssoEntry';

function at(hash: string) {
  Object.defineProperty(window, 'location', {
    value: { pathname: '/', hash, hostname: 'meetingops.example.com', href: '' },
    writable: true,
    configurable: true,
  });
}

describe('hasAppRouteEntry', () => {
  it('is true for an app route', () => { at('#/sessions'); expect(hasAppRouteEntry()).toBe(true); });
  it('is false for the bare root', () => { at('#/'); expect(hasAppRouteEntry()).toBe(false); });
  it('is false where a failed sign-in lands', () => { at('#/login?sso_error=provider_down'); expect(hasAppRouteEntry()).toBe(false); });
  it('is false for the other auth screens', () => {
    for (const h of ['#/login', '#/signup', '#/forgot-password', '#/reset-password?t=x']) { at(h); expect(hasAppRouteEntry()).toBe(false); }
  });
  it('is false for any hash carrying sso_error', () => { at('#/sessions?sso_error=x'); expect(hasAppRouteEntry()).toBe(false); });
});
