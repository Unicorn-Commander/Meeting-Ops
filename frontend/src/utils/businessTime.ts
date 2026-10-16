import { BUSINESS_TIME_ZONE } from '../config';

type DateOnlyParts = { year: number; month: number; day: number };

/** Return the New York calendar date for a real instant. */
export function businessDateString(value: Date = new Date()): string {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: BUSINESS_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(value);
  const byType = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${byType.year}-${byType.month}-${byType.day}`;
}

/** Parse a date-only string without turning it into a UTC midnight instant. */
export function dateOnlyParts(value: string): DateOnlyParts | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return null;
  const parts = {
    year: Number(match[1]),
    month: Number(match[2]),
    day: Number(match[3]),
  };
  const check = new Date(Date.UTC(parts.year, parts.month - 1, parts.day, 12));
  if (
    check.getUTCFullYear() !== parts.year ||
    check.getUTCMonth() !== parts.month - 1 ||
    check.getUTCDate() !== parts.day
  ) return null;
  return parts;
}

/** Format the date-only value's own calendar parts for the viewer's locale. */
export function formatDateOnly(value: string): string | null {
  const parts = dateOnlyParts(value);
  if (!parts) return null;
  return new Intl.DateTimeFormat(undefined, {
    timeZone: 'UTC',
    year: 'numeric',
    month: 'numeric',
    day: 'numeric',
  }).format(new Date(Date.UTC(parts.year, parts.month - 1, parts.day, 12)));
}
