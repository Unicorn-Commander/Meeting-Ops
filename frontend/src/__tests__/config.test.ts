import { describe, it, expect, vi, afterEach } from 'vitest';
import { config } from '../config';

const setLocation = (url: string) => {
  const parsed = new URL(url);
  const locationMock = {
    href: parsed.href,
    hostname: parsed.hostname,
    protocol: parsed.protocol,
  };

  vi.stubGlobal('location', locationMock);

  try {
    Object.defineProperty(window, 'location', {
      value: locationMock,
      writable: true,
    });
  } catch (error) {
    // Ignore if jsdom prevents redefining window.location
  }
};

describe('config api urls', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('uses localhost backend for local development', () => {
    setLocation('http://localhost:7777');
    expect(config.apiUrl).toBe('http://localhost:9050');
  });

  it('uses api subdomain for SSO deployments', () => {
    setLocation('https://app.example.com');
    expect(config.apiUrl).toBe('https://api.example.com');
  });
});
