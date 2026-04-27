export function parseOwnerName(raw: string): {
  first_name: string
  last_name: string
} {
  const s = (raw ?? '').trim()
  if (!s) return { first_name: '', last_name: '' }
  const commaIdx = s.indexOf(',')
  if (commaIdx >= 0) {
    return {
      first_name: s.slice(0, commaIdx).trim(),
      last_name: s.slice(commaIdx + 1).trim(),
    }
  }
  const match = s.match(/^(\S+)\s+(.+)$/)
  if (!match) return { first_name: s, last_name: '' }
  return { first_name: match[1], last_name: match[2].trim() }
}
