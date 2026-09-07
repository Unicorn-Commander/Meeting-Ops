import { fireEvent, render, screen } from '@testing-library/react';
import { vi } from 'vitest';
import CombineSessionsDialog, {
  defaultCombinedName,
  orderParts,
  type CombinePart,
} from '../components/CombineSessionsDialog';

// Selection order is deliberately reversed / mixed so the tests prove the
// dialog re-orders by start time (earliest first) and derives the default
// name from the EARLIEST part, not the first selected one.
const PARTS: CombinePart[] = [
  { id: '730', name: 'Call with Tom Kim2', startedAt: '2026-08-13T21:30:42', duration: 1193.5 },
  { id: '731', name: 'Call with Tom Kim1', startedAt: '2026-08-13T21:05:49', duration: 1228.1 },
];

describe('CombineSessionsDialog', () => {
  it('orders parts by start time and derives the default name from the earliest', () => {
    const ordered = orderParts(PARTS);
    expect(ordered.map((p) => p.id)).toEqual(['731', '730']);
    expect(defaultCombinedName(ordered)).toBe('Call with Tom Kim1 (combined, 2 parts)');
  });

  it('puts parts with an unknown start last and breaks ties by numeric id', () => {
    const ordered = orderParts([
      { id: '12', name: 'b', startedAt: null },
      { id: '9', name: 'a', startedAt: '2026-09-05T00:55:00' },
      { id: '10', name: 'c', startedAt: '2026-09-05T00:55:00' },
    ]);
    expect(ordered.map((p) => p.id)).toEqual(['9', '10', '12']);
  });

  it('renders the ordered list, prefills the name, and confirms with the edited name + ordered ids', () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(
      <CombineSessionsDialog open parts={PARTS} onConfirm={onConfirm} onCancel={onCancel} />,
    );

    const rows = screen.getAllByTestId('combine-part');
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent('Call with Tom Kim1');
    expect(rows[1]).toHaveTextContent('Call with Tom Kim2');

    const input = screen.getByLabelText(/Combined meeting name/i) as HTMLInputElement;
    expect(input.value).toBe('Call with Tom Kim1 (combined, 2 parts)');

    fireEvent.change(input, { target: { value: 'Tom Reyes — Aug 13 call' } });
    fireEvent.click(screen.getByRole('button', { name: /Combine 2 recordings/i }));

    expect(onConfirm).toHaveBeenCalledWith('Tom Reyes — Aug 13 call', ['731', '730']);
    expect(onCancel).not.toHaveBeenCalled();
  });

  it('shows the server error and disables confirm while busy', () => {
    render(
      <CombineSessionsDialog
        open
        parts={PARTS}
        busy
        error="A combined meeting can’t be a part of another one"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('can’t be a part');
    expect(screen.getByRole('button', { name: /Combining…/i })).toBeDisabled();
  });
});
