import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import AuthoredSpeakerLabels from '../components/AuthoredSpeakerLabels';

describe('authored speaker labels', () => {
  it('shows supplied names as text with an explicit absence of voice verification', () => {
    const { container } = render(<AuthoredSpeakerLabels speakers={['Dana Moreau', '<img src=x onerror=alert(1)>']} />);
    expect(screen.getByRole('heading', { name: 'Authored speaker labels' })).toBeInTheDocument();
    expect(screen.getByText(/No audio samples or verified voice identities are available/)).toBeInTheDocument();
    expect(screen.getByText('Dana Moreau')).toBeInTheDocument();
    expect(screen.getByText('<img src=x onerror=alert(1)>')).toBeInTheDocument();
    expect(container.querySelector('img')).toBeNull();
    expect(screen.queryByRole('button')).toBeNull();
  });
});
