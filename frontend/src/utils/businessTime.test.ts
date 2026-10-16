import { describe, expect, it } from 'vitest';
import { businessDateString, dateOnlyParts } from './businessTime';

describe('business calendar helpers', () => {
  it('uses the New York calendar date rather than the UTC date', () => {
    expect(businessDateString(new Date('2026-10-17T00:30:00Z'))).toBe('2026-10-16');
  });

  it('keeps date-only values as their own calendar parts', () => {
    expect(dateOnlyParts('2026-10-16')).toEqual({ year: 2026, month: 10, day: 16 });
  });
});
