import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { SpeakerTimeline } from '../components/SpeakerTimeline';

/**
 * Include-filter semantics (per spec-d7f6f353):
 *   - empty selection => every speaker's bars are shown
 *   - clicking a name => SELECTS that speaker to SHOW; only selected
 *                        speakers' bars render, the rest are hidden
 *   - multi-select    => several speakers can be shown at once
 *   - "All"           => clears the selection, showing everyone again
 *
 * Segment bars are buttons whose title is "<speaker>: <start> → <end>",
 * so their presence/absence is the ground truth for what is shown.
 */
describe('SpeakerTimeline include filter', () => {
  const segments = [
    { start: 0, end: 10, speaker: 'Alice' },
    { start: 10, end: 20, speaker: 'Bob' },
    { start: 20, end: 30, speaker: 'Charlie' },
  ];

  const speakers = ['Alice', 'Bob', 'Charlie'];

  const ALICE_BAR = 'Alice: 0:00 → 0:10';
  const BOB_BAR = 'Bob: 0:10 → 0:20';
  const CHARLIE_BAR = 'Charlie: 0:20 → 0:30';

  const renderTimeline = () =>
    render(
      <SpeakerTimeline duration={30} segments={segments} speakers={speakers} />
    );

  it("shows every speaker's bars initially (empty selection = all)", () => {
    renderTimeline();

    expect(screen.getByTitle(ALICE_BAR)).toBeInTheDocument();
    expect(screen.getByTitle(BOB_BAR)).toBeInTheDocument();
    expect(screen.getByTitle(CHARLIE_BAR)).toBeInTheDocument();

    // No filter active yet, so the "All" reset control is not shown.
    expect(screen.queryByText('All')).not.toBeInTheDocument();
  });

  it("clicking a speaker shows only that speaker's bars", () => {
    renderTimeline();

    fireEvent.click(screen.getByText('Alice'));

    // Only Alice remains; Bob and Charlie are filtered out.
    expect(screen.getByTitle(ALICE_BAR)).toBeInTheDocument();
    expect(screen.queryByTitle(BOB_BAR)).not.toBeInTheDocument();
    expect(screen.queryByTitle(CHARLIE_BAR)).not.toBeInTheDocument();

    // Pressed state tracks the selection; unselected names stay togglable.
    expect(screen.getByText('Alice')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText('Bob')).toHaveAttribute('aria-pressed', 'false');

    // A filter is active, so the "All" reset control appears.
    expect(screen.getByText('All')).toBeInTheDocument();
  });

  it("selecting a second speaker shows both selected speakers' bars", () => {
    renderTimeline();

    fireEvent.click(screen.getByText('Alice'));
    fireEvent.click(screen.getByText('Bob'));

    // Alice and Bob are both shown; Charlie stays hidden.
    expect(screen.getByTitle(ALICE_BAR)).toBeInTheDocument();
    expect(screen.getByTitle(BOB_BAR)).toBeInTheDocument();
    expect(screen.queryByTitle(CHARLIE_BAR)).not.toBeInTheDocument();
  });

  it('the All button resets the filter to show everyone', () => {
    renderTimeline();

    // Narrow to Alice first, proving the filter is engaged.
    fireEvent.click(screen.getByText('Alice'));
    expect(screen.queryByTitle(BOB_BAR)).not.toBeInTheDocument();

    fireEvent.click(screen.getByText('All'));

    // Everyone is back...
    expect(screen.getByTitle(ALICE_BAR)).toBeInTheDocument();
    expect(screen.getByTitle(BOB_BAR)).toBeInTheDocument();
    expect(screen.getByTitle(CHARLIE_BAR)).toBeInTheDocument();

    // ...and, with an empty selection again, the reset control is gone.
    expect(screen.queryByText('All')).not.toBeInTheDocument();
  });
});
