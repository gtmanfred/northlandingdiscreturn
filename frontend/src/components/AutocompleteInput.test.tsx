import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AutocompleteInput } from './AutocompleteInput'

const suggestions = [
  { value: 'Innova' },
  { value: 'Discraft' },
  { value: 'Latitude 64' },
]

function setup(value = '', onValueChange = vi.fn()) {
  render(
    <AutocompleteInput
      suggestions={suggestions}
      onValueChange={onValueChange}
      value={value}
    />
  )
  return { input: screen.getByRole('combobox'), onValueChange }
}

it('renders an input', () => {
  const { input } = setup()
  expect(input).toBeInTheDocument()
})

it('shows matching suggestions on focus', async () => {
  const user = userEvent.setup()
  const { input } = setup()
  await user.click(input)
  expect(screen.getByRole('listbox')).toBeInTheDocument()
  expect(screen.getByText('Innova')).toBeInTheDocument()
  expect(screen.getByText('Discraft')).toBeInTheDocument()
})

it('filters suggestions as user types', async () => {
  const user = userEvent.setup()
  const onValueChange = vi.fn()
  render(
    <AutocompleteInput suggestions={suggestions} onValueChange={onValueChange} value="Inn" />
  )
  const input = screen.getByRole('combobox')
  await user.click(input)
  expect(screen.getByText('Innova')).toBeInTheDocument()
  expect(screen.queryByText('Discraft')).not.toBeInTheDocument()
})

it('calls onValueChange with value when suggestion is clicked', async () => {
  const user = userEvent.setup()
  const { input, onValueChange } = setup()
  await user.click(input)
  await user.click(screen.getByText('Innova'))
  expect(onValueChange).toHaveBeenCalledWith('Innova')
})

it('shows label in dropdown but writes value to input', async () => {
  const user = userEvent.setup()
  const onValueChange = vi.fn()
  render(
    <AutocompleteInput
      suggestions={[{ value: '+15551234567', label: '+15551234567 — Alice (alice@example.com)' }]}
      onValueChange={onValueChange}
      value=""
    />
  )
  const input = screen.getByRole('combobox')
  await user.click(input)
  expect(screen.getByText('+15551234567 — Alice (alice@example.com)')).toBeInTheDocument()
  await user.click(screen.getByText('+15551234567 — Alice (alice@example.com)'))
  expect(onValueChange).toHaveBeenCalledWith('+15551234567')
})

it('selects suggestion with Enter after arrow navigation', async () => {
  const user = userEvent.setup()
  const { input, onValueChange } = setup()
  await user.click(input)
  await user.keyboard('{ArrowDown}')
  await user.keyboard('{Enter}')
  expect(onValueChange).toHaveBeenCalled()
})

it('closes dropdown on Escape', async () => {
  const user = userEvent.setup()
  const { input } = setup()
  await user.click(input)
  expect(screen.getByRole('listbox')).toBeInTheDocument()
  await user.keyboard('{Escape}')
  expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
})
