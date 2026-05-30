import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';
import Landing from '../pages/Landing';

describe('Landing', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn(),
    );
    // Reset hash between tests so the redirect assertion is reliable.
    window.location.hash = '';
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    window.location.hash = '';
  });

  it('renders hero copy, three product points, and the invite form', () => {
    render(
      <MemoryRouter>
        <Landing />
      </MemoryRouter>,
    );

    // Hero
    expect(
      screen.getByRole('heading', {
        level: 1,
        name: /meeting transcription that actually stays private\./i,
      }),
    ).toBeInTheDocument();

    // Three product points
    expect(screen.getByText(/browser-only by default/i)).toBeInTheDocument();
    expect(screen.getByText(/optional pro server pass/i)).toBeInTheDocument();
    expect(screen.getByText(/bring-your-own ecosystem/i)).toBeInTheDocument();

    // Form — v3.21.0: CTA button is now "Continue" (full-path to /signup).
    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /continue/i }),
    ).toBeInTheDocument();

    // Sign-in escape hatch
    expect(
      screen.getByRole('link', { name: /i have an account → sign in/i }),
    ).toBeInTheDocument();

    // Footer attribution
    expect(
      screen.getByText(
        /built by magic unicorn unconventional technology & stuff inc\./i,
      ),
    ).toBeInTheDocument();
  });

  it('submits the invite request (fire-and-forget) and redirects to /signup with the email', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ok: true }),
    });
    vi.stubGlobal('fetch', fetchMock);

    render(
      <MemoryRouter>
        <Landing />
      </MemoryRouter>,
    );

    const input = screen.getByLabelText(/email address/i);
    fireEvent.change(input, { target: { value: 'aaron@example.com' } });
    fireEvent.click(screen.getByRole('button', { name: /continue/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain('/api/landing/invite-request');
    expect(init?.method).toBe('POST');
    expect(JSON.parse(init?.body as string)).toEqual({
      email: 'aaron@example.com',
    });

    // Full-path CTA: hash router navigates to /signup?email=...
    await waitFor(() => {
      expect(window.location.hash).toMatch(/^#\/signup\?email=aaron%40example\.com$/);
    });
  });

  it('rejects an invalid email before hitting the network', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    render(
      <MemoryRouter>
        <Landing />
      </MemoryRouter>,
    );

    const input = screen.getByLabelText(/email address/i);
    fireEvent.change(input, { target: { value: 'not-an-email' } });
    fireEvent.click(screen.getByRole('button', { name: /continue/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/please enter a valid email address/i),
      ).toBeInTheDocument();
    });
    expect(fetchMock).not.toHaveBeenCalled();
    // No redirect on validation failure.
    expect(window.location.hash).toBe('');
  });

  it('redirects to /signup even when the invite-request POST fails (fire-and-forget)', async () => {
    // Server is down / rate-limited / 500'd — the redirect still
    // happens because v3.21.0 makes the invite log fire-and-forget.
    const fetchMock = vi.fn().mockRejectedValue(new Error('network down'));
    vi.stubGlobal('fetch', fetchMock);

    render(
      <MemoryRouter>
        <Landing />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText(/email address/i), {
      target: { value: 'flood@example.com' },
    });
    fireEvent.click(screen.getByRole('button', { name: /continue/i }));

    await waitFor(() => {
      expect(window.location.hash).toMatch(/^#\/signup\?email=flood%40example\.com$/);
    });
  });
});
