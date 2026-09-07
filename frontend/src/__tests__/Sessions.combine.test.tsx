import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { Sessions } from '../pages/Sessions';

// Page-level flow for "Combine selected": select two recordings → Combine
// → dialog (earliest first, default name) → POST /api/sessions/combine →
// navigate to the new combined meeting. Mocks mirror Sessions.test.tsx.

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => mockNavigate };
});

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
    activeOrganization: { id: 'org-1', slug: 'test-org', name: 'Test Org', role: 'admin' },
    organizations: [],
    getOrgQueryUrl: (url: string) => url,
  }),
}));

vi.mock('../contexts/AuthContext', () => {
  const TEST_TIER_FEATURES = {
    server_live: true, diarization: true, qwen36_summary: true, speaker_library: true,
    retention_controls: true, brigade_byok: false, hipaa: false, canonical_reprocess: true,
    brigade_integration: true, cross_device_sync: true, bulk_import: true,
    max_sessions_per_month: null, max_session_minutes: null, audio_upload: true,
    server_text_storage: true, ai_chat_over_corpus: true, cross_meeting_search: true,
    uc_suite_entitlement: false, byok_models: false,
  };
  return {
    DEFAULT_TIER_FEATURES: TEST_TIER_FEATURES,
    useAuth: () => ({
      user: { id: 1, email: 'test@example.com', tier: 'pro', tier_features: TEST_TIER_FEATURES, is_founding_member: false },
      isAuthenticated: true,
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
    }),
  };
});

vi.mock('../services/localSessionStore', () => ({
  listLocalSessions: vi.fn().mockResolvedValue([]),
  isLocalSessionId: (id: string) => id.startsWith('local-'),
  deleteLocalSession: vi.fn(),
  updateLocalSessionMeta: vi.fn(),
}));

vi.mock('../components/Toast', () => ({
  showToast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

const LIST = [
  {
    id: 'uuid-kim2', name: 'Call with Tom Kim2',
    created_at: '2026-09-07T18:00:00Z', updated_at: '2026-09-07T18:00:00Z',
    meeting_date: '2026-08-13', meeting_time: '21:30:42', duration: 1193.5,
    status: 'completed', has_transcript: true, has_audio: true,
    is_combined: false, parts_count: 0, part_of: [],
  },
  {
    id: 'uuid-kim1', name: 'Call with Tom Kim1',
    created_at: '2026-09-07T18:01:00Z', updated_at: '2026-09-07T18:01:00Z',
    meeting_date: '2026-08-13', meeting_time: '21:05:49', duration: 1228.1,
    status: 'completed', has_transcript: true, has_audio: true,
    is_combined: false, parts_count: 0, part_of: [],
  },
];

describe('Sessions — Combine selected', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    mockNavigate.mockReset();
    const store: Record<string, string> = {};
    vi.stubGlobal('localStorage', {
      getItem: vi.fn((key: string) => store[key] || null),
      setItem: vi.fn((key: string, value: string) => { store[key] = value; }),
      removeItem: vi.fn((key: string) => { delete store[key]; }),
      clear: vi.fn(() => { Object.keys(store).forEach((k) => delete store[k]); }),
    });

    fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes('/api/sessions/combine')) {
        return {
          ok: true,
          status: 202,
          json: async () => ({
            id: 941,
            name: 'Call with Tom Kim1 (combined, 2 parts)',
            status: 'processing',
            is_combined: true,
            parts: [],
            _body: init?.body,
          }),
        } as unknown as Response;
      }
      if (url.includes('/recording-sessions?')) {
        return { ok: true, status: 200, json: async () => ({ items: LIST, next_cursor: null, has_more: false }) } as unknown as Response;
      }
      return { ok: true, status: 200, json: async () => ({}) } as unknown as Response;
    });
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('combines two selected recordings in start order and navigates to the new meeting', async () => {
    render(
      <MemoryRouter>
        <Sessions />
      </MemoryRouter>,
    );

    const boxes = await screen.findAllByLabelText('Select session');
    expect(boxes.length).toBeGreaterThanOrEqual(2);
    fireEvent.click(boxes[0]);
    fireEvent.click(boxes[1]);

    const combineButton = await screen.findByRole('button', { name: /Combine 2 selected/i });
    expect(combineButton).toBeEnabled();
    fireEvent.click(combineButton);

    // Dialog: earliest first, default name from the earliest part.
    const rows = await screen.findAllByTestId('combine-part');
    expect(rows[0]).toHaveTextContent('Call with Tom Kim1');
    expect(rows[1]).toHaveTextContent('Call with Tom Kim2');
    const input = screen.getByLabelText(/Combined meeting name/i) as HTMLInputElement;
    expect(input.value).toBe('Call with Tom Kim1 (combined, 2 parts)');

    fireEvent.click(screen.getByRole('button', { name: /Combine 2 recordings/i }));

    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/sessions/941'));

    const combineCall = fetchMock.mock.calls.find(([u]) => String(u).includes('/api/sessions/combine'));
    expect(combineCall).toBeTruthy();
    const [, init] = combineCall as [string, RequestInit];
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toEqual({
      session_ids: ['uuid-kim1', 'uuid-kim2'],
      name: 'Call with Tom Kim1 (combined, 2 parts)',
    });
  });

  it('disables Combine with an explanation when only one recording is selected', async () => {
    render(
      <MemoryRouter>
        <Sessions />
      </MemoryRouter>,
    );
    const boxes = await screen.findAllByLabelText('Select session');
    fireEvent.click(boxes[0]);
    const combineButton = await screen.findByRole('button', { name: /Combine 1 selected/i });
    expect(combineButton).toBeDisabled();
    expect(combineButton).toHaveAttribute('title', expect.stringMatching(/at least 2/i));
  });
});
