import { fromZonedTime, formatInTimeZone } from 'date-fns-tz'

export const COURSE_TIMEZONE = 'America/New_York'

/** Combine a yyyy-mm-dd date + HH:mm time (course-local) into a UTC ISO string. */
export function combineDateAndTime(date: string, time: string): string {
  const local = `${date}T${time}:00`
  return fromZonedTime(local, COURSE_TIMEZONE).toISOString()
}

/** Split a UTC ISO string into {date, time} strings in course-local TZ. */
export function splitIsoToLocal(iso: string): { date: string; time: string } {
  return {
    date: formatInTimeZone(iso, COURSE_TIMEZONE, 'yyyy-MM-dd'),
    time: formatInTimeZone(iso, COURSE_TIMEZONE, 'HH:mm'),
  }
}

/** Human-friendly window display, e.g. "May 1, 2026 · 4:00–6:00 PM ET". */
export function formatWindow(startIso: string, endIso: string): string {
  const day = formatInTimeZone(startIso, COURSE_TIMEZONE, 'MMM d, yyyy')
  const start = formatInTimeZone(startIso, COURSE_TIMEZONE, 'h:mm')
  const end = formatInTimeZone(endIso, COURSE_TIMEZONE, 'h:mm a')
  const tz = formatInTimeZone(startIso, COURSE_TIMEZONE, 'zzz')
  return `${day} · ${start}–${end} ${tz}`
}
