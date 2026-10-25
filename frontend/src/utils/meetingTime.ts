export interface MeetingTimeDisplay {
  /** The meeting's organization wall-clock time, optionally zone-labelled. */
  text: string;
  /** Viewer-local equivalent for the time's title/hover, when zones differ. */
  title?: string;
}

export interface MeetingTimeInput {
  meetingDate?: string | null;
  meetingTime?: string | null;
  organizationTimezone?: string | null;
  /** Injectable for deterministic tests; defaults to the browser's zone. */
  browserTimezone?: string | null;
}

export interface MeetingTimestampInput {
  /** An API timestamp; legacy zone-less values are persisted UTC. */
  timestamp?: string | null;
  organizationTimezone?: string | null;
  /** Injectable for deterministic tests; defaults to the browser's zone. */
  browserTimezone?: string | null;
}

const US_TIMEZONE_LABELS: Record<string, string> = {
  'America/New_York': 'ET',
  'America/Chicago': 'CT',
  'America/Denver': 'MT',
  'America/Los_Angeles': 'PT',
};

interface WallClockParts {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
  second: number;
  nominalUtc: Date;
}

function parseWallClockParts(
  meetingDate: string | null | undefined,
  meetingTime: string | null | undefined,
): WallClockParts | null {
  const dateMatch = typeof meetingDate === 'string'
    ? /^(\d{4})-(\d{2})-(\d{2})$/.exec(meetingDate.trim())
    : null;
  const timeMatch = typeof meetingTime === 'string'
    ? /^(\d{2}):(\d{2})(?::(\d{2}))?$/.exec(meetingTime.trim())
    : null;
  if (!dateMatch || !timeMatch) return null;

  const year = Number(dateMatch[1]);
  const month = Number(dateMatch[2]);
  const day = Number(dateMatch[3]);
  const hour = Number(timeMatch[1]);
  const minute = Number(timeMatch[2]);
  const second = Number(timeMatch[3] || 0);
  if (
    month < 1 || month > 12 || day < 1 || day > 31
    || hour > 23 || minute > 59 || second > 59
  ) {
    return null;
  }

  const nominalUtc = new Date(Date.UTC(year, month - 1, day, hour, minute, second));
  if (
    Number.isNaN(nominalUtc.getTime())
    || nominalUtc.getUTCFullYear() !== year
    || nominalUtc.getUTCMonth() !== month - 1
    || nominalUtc.getUTCDate() !== day
  ) {
    return null;
  }
  return { year, month, day, hour, minute, second, nominalUtc };
}

function canonicalTimezone(timezone: string | null | undefined): string | null {
  if (!timezone) return null;
  try {
    return new Intl.DateTimeFormat('en-US', { timeZone: timezone })
      .resolvedOptions().timeZone || timezone;
  } catch {
    return null;
  }
}

/** Parse a timestamp from the API without allowing a zone-less value to mean
 * browser-local time. Legacy DateTime columns are stored as UTC. */
export function parseApiTimestamp(value: string | null | undefined): Date | null {
  const raw = typeof value === 'string' ? value.trim() : '';
  if (!raw) return null;
  const hasOffset = /(?:[zZ]|[+-]\d{2}:?\d{2})$/.test(raw);
  const parsed = new Date(hasOffset ? raw : `${raw}Z`);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function timeZoneParts(value: Date, timezone: string): Record<string, string> | null {
  try {
    return new Intl.DateTimeFormat('en-US', {
      timeZone: timezone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hourCycle: 'h23',
    }).formatToParts(value).reduce<Record<string, string>>((parts, part) => {
      if (part.type !== 'literal') parts[part.type] = part.value;
      return parts;
    }, {});
  } catch {
    return null;
  }
}

function timezoneOffsetMinutes(value: Date, timezone: string): number | null {
  const parts = timeZoneParts(value, timezone);
  if (!parts) return null;
  const year = Number(parts.year);
  const month = Number(parts.month);
  const day = Number(parts.day);
  const hour = Number(parts.hour);
  const minute = Number(parts.minute);
  const second = Number(parts.second);
  if ([year, month, day, hour, minute, second].some(Number.isNaN)) return null;
  // Intl can represent midnight as 24 in some runtimes despite hourCycle h23.
  const normalizedHour = hour === 24 ? 0 : hour;
  const localAsUtc = Date.UTC(year, month - 1, day, normalizedHour, minute, second);
  return Math.round((localAsUtc - value.getTime()) / 60000);
}

function wallClockToInstant(parts: WallClockParts, timezone: string): Date | null {
  let offset = timezoneOffsetMinutes(parts.nominalUtc, timezone);
  if (offset === null) return null;

  // First-pass offset gets the nominal wall clock into the zone. Re-read the
  // offset at that instant so a DST boundary is resolved with the actual date.
  let instant = new Date(parts.nominalUtc.getTime() - offset * 60_000);
  const correctedOffset = timezoneOffsetMinutes(instant, timezone);
  if (correctedOffset !== null && correctedOffset !== offset) {
    offset = correctedOffset;
    instant = new Date(parts.nominalUtc.getTime() - offset * 60_000);
  }
  return instant;
}

function formatTime(value: Date, timezone: string): string {
  return new Intl.DateTimeFormat(undefined, {
    timeZone: timezone,
    hour: 'numeric',
    minute: '2-digit',
  }).format(value);
}

function shortTimezoneLabel(timezone: string, instant: Date): string | null {
  const canonical = canonicalTimezone(timezone) || timezone;
  const mapped = US_TIMEZONE_LABELS[canonical];
  if (mapped) return mapped;
  try {
    const shortName = new Intl.DateTimeFormat(undefined, {
      timeZone: canonical,
      timeZoneName: 'short',
    }).formatToParts(instant).find((part) => part.type === 'timeZoneName')?.value;
    return shortName || null;
  } catch {
    return null;
  }
}

function browserTimezone(): string | null {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || null;
  } catch {
    return null;
  }
}

/**
 * Format an org-wall-clock meeting time without converting the displayed
 * meeting time. A zone label and viewer-local title are added only when the
 * org and browser have different offsets at this meeting's instant.
 */
export function formatMeetingTime(input: MeetingTimeInput): MeetingTimeDisplay {
  const parts = parseWallClockParts(input.meetingDate, input.meetingTime);
  if (!parts) return { text: '' };

  const wallClockText = formatTime(parts.nominalUtc, 'UTC');
  const orgTimezone = canonicalTimezone(input.organizationTimezone);
  const viewerTimezone = canonicalTimezone(
    input.browserTimezone === undefined ? browserTimezone() : input.browserTimezone,
  );
  if (!orgTimezone || !viewerTimezone) return { text: wallClockText };

  const instant = wallClockToInstant(parts, orgTimezone);
  if (!instant) return { text: wallClockText };
  const orgOffset = timezoneOffsetMinutes(instant, orgTimezone);
  const viewerOffset = timezoneOffsetMinutes(instant, viewerTimezone);
  if (
    orgTimezone === viewerTimezone
    || orgOffset === null
    || viewerOffset === null
    || orgOffset === viewerOffset
  ) {
    return { text: wallClockText };
  }

  const orgLabel = shortTimezoneLabel(orgTimezone, instant);
  const viewerLabel = shortTimezoneLabel(viewerTimezone, instant);
  if (!orgLabel) return { text: wallClockText };

  const viewerText = formatTime(instant, viewerTimezone);
  return {
    text: `${wallClockText} ${orgLabel}`,
    title: viewerLabel
      ? `${viewerText} your time (${viewerLabel})`
      : `${viewerText} your time`,
  };
}

/**
 * Format an absolute session timestamp in the organization's wall-clock
 * timezone. The time portion delegates to formatMeetingTime so its zone-label
 * and viewer-local hover behavior stay identical to explicit meeting times.
 */
export function formatMeetingTimestamp(
  input: MeetingTimestampInput,
): MeetingTimeDisplay {
  const instant = parseApiTimestamp(input.timestamp);
  if (!instant) return { text: '' };

  const orgTimezone = canonicalTimezone(input.organizationTimezone);
  const viewerTimezone = input.browserTimezone === undefined
    ? browserTimezone()
    : input.browserTimezone;
  if (!orgTimezone) {
    try {
      return {
        text: new Intl.DateTimeFormat(undefined, {
          timeZone: canonicalTimezone(viewerTimezone) || undefined,
          dateStyle: 'short',
          timeStyle: 'medium',
        }).format(instant),
      };
    } catch {
      return { text: instant.toLocaleString() };
    }
  }

  const parts = timeZoneParts(instant, orgTimezone);
  if (!parts) return { text: instant.toLocaleString() };
  const hour = parts.hour === '24' ? '00' : parts.hour;
  const wallDate = `${parts.year}-${parts.month}-${parts.day}`;
  const wallTime = `${hour}:${parts.minute}:${parts.second}`;
  const timeDisplay = formatMeetingTime({
    meetingDate: wallDate,
    meetingTime: wallTime,
    organizationTimezone: orgTimezone,
    browserTimezone: viewerTimezone,
  });
  const dateText = new Intl.DateTimeFormat(undefined, {
    timeZone: orgTimezone,
    year: 'numeric',
    month: 'numeric',
    day: 'numeric',
  }).format(instant);
  return {
    text: `${dateText}, ${timeDisplay.text}`,
    title: timeDisplay.title,
  };
}

/** Return the calendar date represented by an API timestamp in a display
 * timezone. Falls back to the browser's calendar when no org timezone exists. */
export function calendarDateForTimestamp(
  value: string | null | undefined,
  timezone?: string | null,
): string | null {
  const instant = parseApiTimestamp(value);
  if (!instant) return null;
  const zone = canonicalTimezone(timezone);
  const parts = zone ? timeZoneParts(instant, zone) : null;
  if (parts) return `${parts.year}-${parts.month}-${parts.day}`;
  const pad = (part: number) => String(part).padStart(2, '0');
  return `${instant.getFullYear()}-${pad(instant.getMonth() + 1)}-${pad(instant.getDate())}`;
}
