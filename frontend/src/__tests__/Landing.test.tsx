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
  });

  afterEach(() => {
    vi.unstubAllGlobals();
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

    // Form
    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /request invite/i }),
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

  it('submits the invite request and shows the success state', async () => {
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
    fireEvent.click(screen.getByRole('button', { name: /request invite/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain('/api/landing/invite-request');
    expect(init?.method).toBe('POST');
    expect(JSON.parse(init?.body as string)).toEqual({
      email: 'aaron@example.com',
    });

    // Success message replaces the form
    await waitFor(() => {
      expect(
        screen.getByText(/thanks — your request is in/i),
      ).toBeInTheDocument();
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
    fireEvent.click(screen.getByRole('button', { name: /request invite/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/please enter a valid email address/i),
      ).toBeInTheDocument();
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('shows the rate-limit message when the server returns 429', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 429,
      json: async () => ({ detail: 'Too many requests.' }),
    });
    vi.stubGlobal('fetch', fetchMock);

    render(
      <MemoryRouter>
        <Landing />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText(/email address/i), {
      target: { value: 'flood@example.com' },
    });
    fireEvent.click(screen.getByRole('button', { name: /request invite/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/too many requests from this network/i),
      ).toBeInTheDocument();
    });
  });
});
