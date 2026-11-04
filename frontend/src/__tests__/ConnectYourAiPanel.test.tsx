import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';

import ConnectYourAiPanel from '../components/settings/ConnectYourAiPanel';

describe('ConnectYourAiPanel', () => {
  beforeEach(() => {
    vi.stubGlobal('navigator', {
      clipboard: {
        writeText: vi.fn(async () => undefined),
      },
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it('uses the configured public MCP URL for the current ring', () => {
    const configuredUrl = 'https://meetingops.example.test/mcp';
    vi.stubEnv('VITE_HOSTED_MCP_URL', configuredUrl);

    render(<ConnectYourAiPanel />);

    expect(screen.getAllByText(configuredUrl).length).toBeGreaterThan(0);
  });

  it('offers the four client tabs and placeholder-only copy forms', async () => {
    render(<ConnectYourAiPanel />);

    expect(screen.getAllByRole('tab').map((tab) => tab.textContent)).toEqual([
      'Claude Code',
      'Claude Desktop / claude.ai',
      'ChatGPT',
      'Cursor / Codex',
    ]);
    expect(screen.getAllByRole('tab')).toHaveLength(4);
    expect(screen.getAllByText(/claude mcp add --transport http meeting-ops/).length).toBe(2);
    expect(screen.getByText(/Your AI gets your permissions and nothing more; revoke any time below/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: 'Claude Desktop / claude.ai' }));
    expect(screen.getByText(/Settings → Connectors → Add custom connector → URL/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: 'ChatGPT' }));
    expect(screen.getByText(/Settings → Connectors → Developer mode → New connector → URL/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: 'Cursor / Codex' }));
    expect(screen.getAllByText(/"type": "http"/).length).toBe(2);
    expect(screen.getAllByText(/mops_pat_…/u).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole('button', { name: 'Copy mcp.json with token header' }));
    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
        expect.stringContaining('mops_pat_…'),
      );
    });
    expect(navigator.clipboard.writeText).not.toHaveBeenCalledWith(
      expect.stringContaining('fixture-only-plaintext'),
    );
  });
});
