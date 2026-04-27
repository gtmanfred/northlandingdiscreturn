import { describe, it, expect } from 'vitest'
import { parseOwnerName } from './ownerName'

describe('parseOwnerName', () => {
  const cases: Array<[string, { first_name: string; last_name: string }]> = [
    ['Doe, John', { first_name: 'Doe', last_name: 'John' }],
    ['  Doe ,  John  ', { first_name: 'Doe', last_name: 'John' }],
    ['John Smith', { first_name: 'John', last_name: 'Smith' }],
    ['Mary Jane Watson', { first_name: 'Mary', last_name: 'Jane Watson' }],
    ['Cher', { first_name: 'Cher', last_name: '' }],
    ['', { first_name: '', last_name: '' }],
    ['   ', { first_name: '', last_name: '' }],
    ['a, b, c', { first_name: 'a', last_name: 'b, c' }],
  ]
  for (const [raw, expected] of cases) {
    it(`parses ${JSON.stringify(raw)}`, () => {
      expect(parseOwnerName(raw)).toEqual(expected)
    })
  }
})
