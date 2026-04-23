import { describe, it, expect } from 'vitest'
import { combineDateAndTime, formatWindow, COURSE_TIMEZONE } from './courseTime'

describe('courseTime', () => {
  it('exposes the America/New_York timezone', () => {
    expect(COURSE_TIMEZONE).toBe('America/New_York')
  })

  it('combines a yyyy-mm-dd date and HH:mm time in course TZ into a UTC ISO string', () => {
    // 2026-05-01 16:00 America/New_York (EDT, UTC-4) = 2026-05-01T20:00:00Z
    const iso = combineDateAndTime('2026-05-01', '16:00')
    expect(iso).toBe('2026-05-01T20:00:00.000Z')
  })

  it('formats a UTC ISO window into course-local display', () => {
    const text = formatWindow(
      '2026-05-01T20:00:00.000Z',
      '2026-05-01T22:00:00.000Z',
    )
    expect(text).toMatch(/May 1, 2026/)
    expect(text).toMatch(/4:00/)
    expect(text).toMatch(/6:00/)
    expect(text).toMatch(/ET|EDT|EST/)
  })
})
