import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

import RAGChat from '../pages/RAGChat';
import { AuthProvider } from '../contexts/AuthContext';
import { OrgProvider } from '../contexts/OrgContext';

const ORG_FIXTURE = {
  id: 1,
  name: 'Magic Unicorn',
  slug: 'magic-unicorn',
  role: 'admin',
  is_active: true,
};

const ME_PAYLOAD = {
  id: 1,
  email: 'test@example.com',
  username: 'tester',
  is_active: true,
  is_verified: true,
  created_at: '2026-05-03T00:00:00Z',
  organizations: [ORG_FIXTURE],
  active_organization: ORG_FIXTURE,
};

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

function streamingResponse(events: string[], status = 200) {
  const encoder = new TextEncoder();
  let i = 0;
  const reader = {
    read: vi.fn(async () => {
      if (i >= events.length) {
        return { done: true, value: undefined };
      }
      const chunk = encoder.encode(events[i]);
      i += 1;
      return { done: false, value: chunk };
    }),
  };
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: {
      get: (name: string) => (name.toLowerCase() === 'content-type' ? 'text/event-stream' : null),
    },
    body: { getReader: () => reader },
  } as unknown as Response;
}

interface FetchCall {
  url: string;
  init?: RequestInit;
}

let fetchMock: ReturnType<typeof vi.fn>;
let fetchCalls: FetchCall[];

function installFetch(streamEvents: string[] | null = null, historyPayload: unknown[] = []) {
  fetchCalls = [];
  fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString();
    fetchCalls.push({ url, init });

    if (url.endsWith('/api/auth/me')) {
      return jsonResponse(ME_PAYLOAD);
    }
    if (url.includes('/api/rag/chat/history')) {
      if (init?.method === 'DELETE') {
        return jsonResponse({ ok: true });
      }
      return jsonResponse(historyPayload);
    }
    if (url.includes('/api/rag/chat')) {
      if (streamEvents === null) {
        return jsonResponse({ detail: 'no embeddings yet' }, 503);
      }
      return streamingResponse(streamEvents);
    }
    return jsonResponse({}, 404);
  });
  vi.stubGlobal('fetch', fetchMock);
}

function installLocalStorage() {
  const store: Record<string, string> = { access_token: 'test-token' };
  vi.stubGlobal('localStorage', {
    getItem: vi.fn((key: string) => store[key] ?? null),
    setItem: vi.fn((key: string, value: string) => {
      store[key] = value;
    }),
    removeItem: vi.fn((key: string) => {
      delete store[key];
    }),
    clear: vi.fn(() => {
      Object.keys(store).forEach((key) => delete store[key]);
    }),
  });
}

async function renderRAGChat() {
  await act(async () => {
    render(
      <MemoryRouter>
        <AuthProvider>
          <OrgProvider>
            <RAGChat />
          </OrgProvider>
        </AuthProvider>
      </MemoryRouter>
    );
  });
  await waitFor(() =>
    expect(screen.getByPlaceholderText(/ask a question about your meetings/i)).toBeInTheDocument()
  );
}

describe('RAGChat', () => {
  beforeEach(() => {
    installLocalStorage();
    // jsdom does not implement scrollIntoView, but the component invokes it via a ref.
    Element.prototype.scrollIntoView = vi.fn();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('renders the chat input and at least one action button', async () => {
    installFetch([]);
    await renderRAGChat();

    expect(screen.getByPlaceholderText(/ask a question about your meetings/i)).toBeInTheDocument();
    // Send button (icon-only) plus the Clear-history button = at least 2 buttons.
    const buttons = screen.getAllByRole('button');
    expect(buttons.length).toBeGreaterThanOrEqual(2);
  });

  it('shows the empty state when no messages exist yet', async () => {
    installFetch([]);
    await renderRAGChat();

    expect(
      await screen.findByText(/Ask questions about your meetings across time/i)
    ).toBeInTheDocument();
  });

  it('posts the question to /api/rag/chat with the X-MeetingOps-Org header', async () => {
    installFetch(['data: {"done": true}\n\n']);
    await renderRAGChat();

    const input = screen.getByPlaceholderText(/ask a question about your meetings/i);
    fireEvent.change(input, { target: { value: 'What happened last week?' } });
    fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });

    await waitFor(() => {
      const ragPost = fetchCalls.find(
        (call) => call.url.includes('/api/rag/chat') && !call.url.includes('history')
      );
      expect(ragPost).toBeTruthy();
      expect(ragPost?.init?.method).toBe('POST');
      const headers = new Headers(ragPost?.init?.headers as HeadersInit);
      expect(headers.get('X-MeetingOps-Org')).toBe('magic-unicorn');
      expect(headers.get('Content-Type')).toBe('application/json');
    });
  });

  it('renders streamed answer chunks back to the user', async () => {
    installFetch([
      'data: {"token": "Hello "}\n\n',
      'data: {"token": "world"}\n\n',
      'data: {"done": true, "sources": []}\n\n',
    ]);
    await renderRAGChat();

    const input = screen.getByPlaceholderText(/ask a question about your meetings/i);
    fireEvent.change(input, { target: { value: 'Summarize this.' } });
    fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });

    expect(await screen.findByText(/Hello world/)).toBeInTheDocument();
  });

  it('renders citations as clickable session links after streaming completes', async () => {
    installFetch([
      'data: {"token": "Per the meeting"}\n\n',
      'data: {"done": true, "sources": [{"meeting_id": "abc-123", "chunk_idx": 4, "snippet": "key decision recorded here"}]}\n\n',
    ]);
    await renderRAGChat();

    const input = screen.getByPlaceholderText(/ask a question about your meetings/i);
    fireEvent.change(input, { target: { value: 'Cite something.' } });
    fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });

    const link = await screen.findByRole('link', { name: /Meeting abc-123 chunk 4/ });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute('href', '#/sessions/abc-123');
  });

  it('shows an error message when the RAG endpoint is unreachable', async () => {
    installFetch(null);
    await renderRAGChat();

    const input = screen.getByPlaceholderText(/ask a question about your meetings/i);
    fireEvent.change(input, { target: { value: 'Will this work?' } });
    fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });

    expect(
      await screen.findByText(/Error: Unable to reach RAG service\./i)
    ).toBeInTheDocument();
  });
});
