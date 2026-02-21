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

describe('Sessions', () => {
  beforeEach(() => {
    vi.useFakeTimers();
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
    vi.useRealTimers();
    vi.unstubAllGlobals();
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
