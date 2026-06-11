import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { PhoneInput } from './PhoneInput'

function segments() {
  return {
    area: screen.getByLabelText('Area code') as HTMLInputElement,
    exchange: screen.getByLabelText('Exchange') as HTMLInputElement,
    line: screen.getByLabelText('Line number') as HTMLInputElement,
  }
}

it('splits a 10-digit national number into segments', () => {
  render(<PhoneInput value="5551234567" onChange={vi.fn()} />)
  const { area, exchange, line } = segments()
  expect(area.value).toBe('555')
  expect(exchange.value).toBe('123')
  expect(line.value).toBe('4567')
})

it('strips the leading country code from an 11-digit E.164 number', () => {
  render(<PhoneInput value="+15551234567" onChange={vi.fn()} />)
  const { area, exchange, line } = segments()
  expect(area.value).toBe('555')
  expect(exchange.value).toBe('123')
  expect(line.value).toBe('4567')
})

it('emits a 10-digit national number as segments are typed', async () => {
  const user = userEvent.setup()
  const onChange = vi.fn()
  render(<PhoneInput value="" onChange={onChange} />)
  const { area } = segments()
  await user.type(area, '555')
  expect(onChange).toHaveBeenLastCalledWith('555')
})
