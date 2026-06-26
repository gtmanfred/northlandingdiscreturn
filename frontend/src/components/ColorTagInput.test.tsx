import { useState } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ColorTagInput } from './ColorTagInput'

function Harness({ initial = [] as string[], suggestions = [] as string[] }) {
  const [value, setValue] = useState<string[]>(initial)
  return (
    <div>
      <ColorTagInput value={value} onChange={setValue} suggestions={suggestions} />
      <output data-testid="value">{JSON.stringify(value)}</output>
    </div>
  )
}

function val() {
  return JSON.parse(screen.getByTestId('value').textContent || '[]')
}

it('commits a tag on space and another on enter, preserving order', async () => {
  const user = userEvent.setup()
  render(<Harness />)
  const input = screen.getByRole('combobox')
  await user.type(input, 'black white')
  await user.keyboard('{Enter}')
  expect(val()).toEqual(['black', 'white'])
})

it('preserves order for white, red, blue', async () => {
  const user = userEvent.setup()
  render(<Harness />)
  const input = screen.getByRole('combobox')
  await user.type(input, 'white red blue ')
  expect(val()).toEqual(['white', 'red', 'blue'])
})

it('removes the last tag on backspace when input empty', async () => {
  const user = userEvent.setup()
  render(<Harness initial={['black', 'white']} />)
  const input = screen.getByRole('combobox')
  await user.click(input)
  await user.keyboard('{Backspace}')
  expect(val()).toEqual(['black'])
})

it('does not add duplicate tags', async () => {
  const user = userEvent.setup()
  render(<Harness initial={['red']} />)
  const input = screen.getByRole('combobox')
  await user.type(input, 'red ')
  expect(val()).toEqual(['red'])
})

it('removes a tag via its remove button', async () => {
  const user = userEvent.setup()
  render(<Harness initial={['black', 'white']} />)
  await user.click(screen.getByLabelText('Remove black'))
  expect(val()).toEqual(['white'])
})
