import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { SpeakerTimeline } from '../components/SpeakerTimeline';

describe('SpeakerTimeline filter', () => {
  const segments = [
    { start: 0, end: 10, speaker: 'Alice' },
    { start: 10, end: 20, speaker: 'Bob' },
    { start: 20, end: 30, speaker: 'Charlie' },
  ];

  const speakers = ['Alice', 'Bob', 'Charlie'];

  it('toggles a speaker and hides their bars', () => {
    render(
      <SpeakerTimeline
        duration={30}
        segments={segments}
        speakers={speakers}
      />
    );

    // Initially all bars are visible
    expect(screen.getByTitle('Alice: 0:00 → 0:10')).toBeInTheDocument();
    expect(screen.getByTitle('Bob: 0:10 → 0:20')).toBeInTheDocument();
    expect(screen.getByTitle('Charlie: 0:20 → 0:30')).toBeInTheDocument();

    // Click Alice to toggle
    fireEvent.click(screen.getByText('Alice'));

    // Alice's bar should be hidden, others visible
    expect(screen.queryByTitle('Alice: 0:00 → 0:10')).not.toBeInTheDocument();
    expect(screen.getByTitle('Bob: 0:10 → 0:20')).toBeInTheDocument();
    expect(screen.getByTitle('Charlie: 0:20 → 0:30')).toBeInTheDocument();
    
    // Alice's button should be dimmed
    const aliceButton = screen.getByText('Alice');
    expect(aliceButton).toHaveClass('opacity-40');
  });

  it('shows bars for multiple selected speakers', () => {
    render(
      <SpeakerTimeline
        duration={30}
        segments={segments}
        speakers={speakers}
      />
    );

    // Toggle Alice and Bob
    fireEvent.click(screen.getByText('Alice'));
    fireEvent.click(screen.getByText('Bob'));

    // Alice and Bob bars hidden, Charlie visible
    expect(screen.queryByTitle('Alice: 0:00 → 0:10')).not.toBeInTheDocument();
    expect(screen.queryByTitle('Bob: 0:10 → 0:20')).not.toBeInTheDocument();
    expect(screen.getByTitle('Charlie: 0:20 → 0:30')).toBeInTheDocument();
  });

  it('resets filter with All button', () => {
    render(
      <SpeakerTimeline
        duration={30}
        segments={segments}
        speakers={speakers}
      />
    );

    // Toggle Alice
    fireEvent.click(screen.getByText('Alice'));
    expect(screen.queryByTitle('Alice: 0:00 → 0:10')).not.toBeInTheDocument();

    // Click All
    fireEvent.click(screen.getByText('All'));

    // All bars visible again
    expect(screen.getByTitle('Alice: 0:00 → 0:10')).toBeInTheDocument();
    expect(screen.getByTitle('Bob: 0:10 → 0:20')).toBeInTheDocument();
    expect(screen.getByTitle('Charlie: 0:20 → 0:30')).toBeInTheDocument();
    
    // All button should be gone
    expect(screen.queryByText('All')).not.toBeInTheDocument();
  });
});
