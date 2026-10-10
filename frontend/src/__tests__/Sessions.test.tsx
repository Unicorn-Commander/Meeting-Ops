import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { Sessions } from '../pages/Sessions';

vi.mock('../components/SessionCreator', () => ({
  SessionCreator: () => <div>Session Creator</div>,
}));

vi.mock('../contexts/UploadsContext', () => ({
  useUploads: () => ({
    uploads: [],
    startUploads: vi.fn(),
    cancelUpload: vi.fn(),
    openSession: vi.fn(),
  }),
}));

vi.mock('../contexts/OrgContext', () => ({
  useOrg: () => ({
    activeOrganization: {
      id: 'org-1',
      slug: 'test-org',
      name: 'Test Org',
      role: 'admin',
    },
    getOrgQueryUrl: (url: string) => url,
  }),
}));

// Stripe UpgradeBanner uses useAuth — stub the context so Sessions tests
// don't need a full AuthProvider tree. Mirrors the pro-tier path so the
// banner short-circuits invisibly during rendering. v3.23.0: also exports
// DEFAULT_TIER_FEATURES so useTierFeatures() resolves without importing
// the real context, and supplies a pro-tier `tier_features` payload so
// the Upload Audio/Video button still renders for these tests.
vi.mock('../contexts/AuthContext', () => {
  const TEST_TIER_FEATURES = {
    server_live: true,
    diarization: true,
    qwen36_summary: true,
    speaker_library: true,
    retention_controls: true,
    brigade_byok: false,
    hipaa: false,
    canonical_reprocess: true,
    brigade_integration: true,
    cross_device_sync: true,
    bulk_import: true,
    max_sessions_per_month: null,
    max_session_minutes: null,
    audio_upload: true,
    server_text_storage: true,
    ai_chat_over_corpus: true,
    cross_meeting_search: true,
    uc_suite_entitlement: false,
    byok_models: false,
  };
  return {
    DEFAULT_TIER_FEATURES: TEST_TIER_FEATURES,
    useAuth: () => ({
      user: {
        id: 1,
        email: 'test@example.com',
        tier: 'pro',
        tier_features: TEST_TIER_FEATURES,
        is_founding_member: false,
      },
      isAuthenticated: true,
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
    }),
  };
});

vi.mock('../services/localSessionStore', () => ({
  listLocalSessions: vi.fn().mockResolvedValue([]),
}));

vi.mock('../components/Toast', () => ({
  showToast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  },
}));

describe('Sessions', () => {
  beforeEach(() => {
    const store: Record<string, string> = {};
    vi.stubGlobal('localStorage', {
      getItem: vi.fn((key: string) => store[key] || null),
      setItem: vi.fn((key: string, value: string) => { store[key] = value; }),
      removeItem: vi.fn((key: string) => { delete store[key]; }),
      clear: vi.fn(() => { Object.keys(store).forEach(k => delete store[k]); }),
    });

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ([
        {
          id: 'session-1',
          name: 'Weekly Sync',
          created_at: '2025-01-01T10:00:00Z',
          updated_at: '2025-01-01T10:00:00Z',
          status: 'completed',
          has_transcript: false,
          has_audio: false,
        },
      ]),
    }));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders sessions page', async () => {
    render(
      <MemoryRouter>
        <Sessions />
      </MemoryRouter>
    );

    await waitFor(() => expect(screen.getByText('Sessions')).toBeInTheDocument());
  });

  it('shows "New Session" button', async () => {
    render(
      <MemoryRouter>
        <Sessions />
      </MemoryRouter>
    );

    await waitFor(() => expect(screen.getByText('Sessions')).toBeInTheDocument());
    expect(screen.getByText('New Session')).toBeInTheDocument();
  });

  it('renders sessions list after fetching', async () => {
    render(
      <MemoryRouter>
        <Sessions />
      </MemoryRouter>
    );

    await waitFor(() => expect(screen.getByText('Sessions')).toBeInTheDocument());
    await waitFor(() => expect(screen.getAllByText('Weekly Sync').length).toBeGreaterThan(0));
  });

  it('loads the next cursor page', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('recording-sessions?')) {
        const secondPage = url.includes('cursor=next-page');
        return {
          ok: true,
          json: async () => ({
            items: [{
              id: secondPage ? 'session-2' : 'session-1',
              name: secondPage ? 'Older Meeting' : 'Weekly Sync',
              created_at: secondPage ? '2024-12-01T10:00:00Z' : '2025-01-01T10:00:00Z',
              updated_at: '2025-01-01T10:00:00Z',
              status: 'completed',
              has_transcript: false,
              has_audio: false,
            }],
            next_cursor: secondPage ? null : 'next-page',
          }),
        };
      }
      return { ok: true, json: async () => ({}) };
    });
    vi.stubGlobal('fetch', fetchMock);
    render(<MemoryRouter><Sessions /></MemoryRouter>);

    const loadMore = await screen.findByRole('button', { name: 'Load more sessions' });
    fireEvent.click(loadMore);
    await waitFor(() => expect(screen.getAllByText('Older Meeting').length).toBeGreaterThan(0));
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('cursor=next-page'))).toBe(true);
  });

  it('keeps pages loaded with "Load more" when the list refreshes', async () => {
    // A server that honours limit + cursor over 120 sessions, newest first.
    const rows = Array.from({ length: 120 }, (_, i) => ({
      id: `session-${i + 1}`,
      name: `Meeting ${i + 1}`,
      created_at: new Date(Date.UTC(2025, 0, 31) - i * 3_600_000).toISOString(),
      updated_at: '2025-01-01T10:00:00Z',
      status: 'completed',
      has_transcript: false,
      has_audio: false,
    }));
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), 'http://localhost');
      if (url.pathname.endsWith('/recording-sessions')) {
        const start = Number(url.searchParams.get('cursor') ?? 0);
        const end = Math.min(rows.length, start + Number(url.searchParams.get('limit')));
        return {
          ok: true,
          json: async () => ({ items: rows.slice(start, end), next_cursor: end < rows.length ? String(end) : null }),
        };
      }
      return { ok: true, json: async () => ({}) };
    });
    vi.stubGlobal('fetch', fetchMock);
    render(<MemoryRouter><Sessions /></MemoryRouter>);

    // 25 cards per page: the first click shows cards 26–50 from the first
    // server page; the second needs rows 51–75, so it fetches the next page.
    fireEvent.click(await screen.findByRole('button', { name: 'Load more sessions' }, { timeout: 5000 }));
    await waitFor(() => expect(screen.getAllByText('Meeting 50').length).toBeGreaterThan(0), { timeout: 5000 });
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('cursor='))).toBe(false);
    fireEvent.click(screen.getByRole('button', { name: 'Load more sessions' }));
    await waitFor(() => expect(screen.getAllByText('Meeting 75').length).toBeGreaterThan(0), { timeout: 5000 });
    expect(screen.queryAllByText('Meeting 76')).toHaveLength(0);

    // The 10-second poll and the invalidation event both refetch without a cursor.
    fetchMock.mockClear();
    window.dispatchEvent(new Event('meetingops:sessions-invalidated'));
    await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => {
      const u = new URL(String(url), 'http://localhost');
      return u.pathname.endsWith('/recording-sessions') && u.searchParams.get('limit') === '100' && !u.searchParams.has('cursor');
    })).toBe(true), { timeout: 5000 });
    await waitFor(() => expect(screen.getAllByText('Meeting 75').length).toBeGreaterThan(0), { timeout: 5000 });
    expect(screen.queryAllByText('Meeting 76')).toHaveLength(0);
    expect(screen.getByRole('button', { name: 'Load more sessions' })).toBeInTheDocument();
  }, 20000);
});
