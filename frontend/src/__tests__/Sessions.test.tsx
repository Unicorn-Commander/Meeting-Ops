import { render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { Sessions } from '../pages/Sessions';

vi.mock('../components/SessionCreator', () => ({
  SessionCreator: () => <div>Session Creator</div>,
}));

vi.mock('../components/MeetingIntelligenceDashboard', () => ({
  MeetingIntelligenceDashboard: () => <div>Meeting Intelligence</div>,
}));

vi.mock('../contexts/UploadsContext', () => ({
  useUploads: () => ({
    uploads: [],
    startUploads: vi.fn(),
    cancelUpload: vi.fn(),
    openSession: vi.fn(),
  }),
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
    await waitFor(() => expect(screen.getByText('Weekly Sync')).toBeInTheDocument());
  });
});
