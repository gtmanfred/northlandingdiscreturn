export function normalizePhone(value: string): string {
  const digits = value.replace(/\D/g, '')
  if (digits.length === 10) return `+1${digits}`
  if (digits.length === 11 && digits[0] === '1') return `+${digits}`
  throw new Error('Enter a 10-digit US number, e.g. (555) 123-4567 or +15551234567.')
}
