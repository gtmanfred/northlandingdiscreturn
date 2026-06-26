export function normalizePhone(value: string): string {
  const digits = value.replace(/\D/g, '')
  if (digits.length === 10) return `+1${digits}`
  if (digits.length === 11 && digits[0] === '1') return `+${digits}`
  throw new Error('Enter a 10-digit US number, e.g. (555) 123-4567 or +15551234567.')
}

/** Format a stored phone (E.164 +1XXXXXXXXXX or raw digits) as xxx-xxx-xxxx. */
export function formatPhone(value: string): string {
  let digits = value.replace(/\D/g, '')
  if (digits.length === 11 && digits[0] === '1') digits = digits.slice(1)
  if (digits.length !== 10) return value
  return `${digits.slice(0, 3)}-${digits.slice(3, 6)}-${digits.slice(6)}`
}
