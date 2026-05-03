import { render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import { Login } from '../components/Login';

describe('Login', () => {
  const mockReplace = vi.fn();

  beforeEach(() => {
    mockReplace.mockClear();
    vi.stubGlobal('location', {
      ...window.location,
      replace: mockReplace,
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders the SSO redirect state', () => {
    render(<Login />);

    expect(screen.getByText(/redirecting to unicorn commander sign-in/i)).toBeInTheDocument();
  });

  it('redirects to oauth2-proxy sign-in', async () => {
    render(<Login />);

    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith('/oauth2/start?rd=%2F');
    });
  });
});
