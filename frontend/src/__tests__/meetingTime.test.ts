import { describe, expect, it } from 'vitest';
import { formatMeetingTime } from '../utils/meetingTime';

describe('formatMeetingTime', () => {
  it('keeps a July Chicago wall clock and labels it CT for an Eastern viewer', () => {
    const display = formatMeetingTime({
      meetingDate: '2026-07-15',
      meetingTime: '14:15:00',
      organizationTimezone: 'America/Chicago',
      browserTimezone: 'America/New_York',
    });

    expect(display.text).toBe('2:15 PM CT');
    expect(display.title).toBe('3:15 PM your time (ET)');
  });

  it('does not add a label when the viewer and org zones match', () => {
    const display = formatMeetingTime({
      meetingDate: '2026-07-15',
      meetingTime: '14:15:00',
      organizationTimezone: 'America/New_York',
      browserTimezone: 'America/New_York',
    });

    expect(display).toEqual({ text: '2:15 PM' });
  });

  it('fails closed for a missing or unknown organization timezone', () => {
    const input = {
      meetingDate: '2026-07-15',
      meetingTime: '14:15:00',
      browserTimezone: 'America/New_York',
    };

    expect(formatMeetingTime(input)).toEqual({ text: '2:15 PM' });
    expect(formatMeetingTime({ ...input, organizationTimezone: 'Not/AZone' })).toEqual({
      text: '2:15 PM',
    });
  });
});
