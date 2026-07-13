/** Date and number formatting shared across screens. */

const DAY_FORMAT = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  day: 'numeric',
  timeZone: 'UTC',
});

const DAY_YEAR_FORMAT = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  day: 'numeric',
  year: 'numeric',
  timeZone: 'UTC',
});

/** "Jun 5" — tick labels and tooltips. */
export function formatDay(timestamp: number): string {
  return DAY_FORMAT.format(new Date(timestamp));
}

/** "Jun 5, 2026" — accessible summaries and detail rows. */
export function formatDayYear(timestamp: number): string {
  return DAY_YEAR_FORMAT.format(new Date(timestamp));
}

/** Trim float noise: up to 2 decimals, no trailing zeros. */
export function formatValue(value: number): string {
  return String(Math.round(value * 100) / 100);
}
