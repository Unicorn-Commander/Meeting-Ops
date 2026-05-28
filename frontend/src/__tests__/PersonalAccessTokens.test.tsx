import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';

import PersonalAccessTokens from '../components/settings/PersonalAccessTokens';

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: {
      get: (name: string) => (name.toLowerCase() === 'content-type' ? 'application/json' : null),
    },
    json: async () => body,
  } as Response;
}

describe('PersonalAccessTokens', () => {
  let tokens: any[];
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    tokens = [
      {
        id: 1,
        name: 'Claude Desktop',
        token_prefix: 'mops_pat_ABC',
        last_used_at: null,
        created_at: '2026-05-28T00:00:00Z',
        revoked_at: null,
      },
    ];
    fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString();
      if (url.includes('/api/auth/pats') && init?.method === 'POST') {
        const created = {
          id: 2,
          name: 'Cursor',
          token_prefix: 'mops_pat_DEF',
          plaintext: 'mops_pat_DEFGHIJKLMNOPQRSTUVWXYZ234567',
          last_used_at: null,
          created_at: '2026-05-28T00:01:00Z',
          revoked_at: null,
        };
        tokens = [created, ...tokens];
        return jsonResponse(created, 201);
      }
      if (url.includes('/api/auth/pats/1') && init?.method === 'DELETE') {
        tokens = tokens.map((token) =>
          token.id === 1 ? { ...token, revoked_at: '2026-05-28T00:02:00Z' } : token
        );
        return jsonResponse({}, 204);
      }
      if (url.includes('/api/auth/pats')) {
        return jsonResponse(tokens.map(({ plaintext, ...token }) => token));
      }
      return jsonResponse({}, 404);
    });
    vi.stubGlobal('fetch', fetchMock);
    vi.stubGlobal('navigator', {
      clipboard: {
        writeText: vi.fn(async () => undefined),
      },
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('renders existing tokens without plaintext', async () => {
    render(<PersonalAccessTokens />);

    expect(await screen.findByText('Claude Desktop')).toBeInTheDocument();
    expect(screen.getByText('mops_pat_ABC...')).toBeInTheDocument();
    expect(screen.queryByText(/DEFGHIJKLMNOP/)).not.toBeInTheDocument();
  });

  it('creates a token and shows the plaintext once modal', async () => {
    render(<PersonalAccessTokens />);
    await screen.findByText('Claude Desktop');

    fireEvent.click(screen.getByRole('button', { name: /New Token/i }));
    fireEvent.change(screen.getByLabelText(/Token name/i), {
      target: { value: 'Cursor' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^Create$/i }));

    expect(await screen.findByText(/Copy this token now/i)).toBeInTheDocument();
    expect(screen.getByText('mops_pat_DEFGHIJKLMNOPQRSTUVWXYZ234567')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /^Copy$/i }));
    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
        'mops_pat_DEFGHIJKLMNOPQRSTUVWXYZ234567'
      );
    });
  });

  it('revokes a token', async () => {
    render(<PersonalAccessTokens />);
    await screen.findByText('Claude Desktop');

    fireEvent.click(screen.getByRole('button', { name: /Revoke Claude Desktop/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/auth/pats/1'),
        expect.objectContaining({ method: 'DELETE' })
      );
    });
    expect(await screen.findByText('Revoked')).toBeInTheDocument();
  });
});
