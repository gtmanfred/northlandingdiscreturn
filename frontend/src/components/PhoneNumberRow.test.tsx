import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { PhoneNumberRow } from './PhoneNumberRow'

vi.mock('../api/northlanding', () => ({
  useVerifyPhone: vi.fn(),
  useAddPhone: vi.fn(),
}))

import { useVerifyPhone, useAddPhone } from '../api/northlanding'

const verifyMutate = vi.fn()
const addMutate = vi.fn()

beforeEach(() => {
  verifyMutate.mockReset().mockResolvedValue({})
  addMutate.mockReset().mockResolvedValue({})
  vi.mocked(useVerifyPhone).mockReturnValue({ mutateAsync: verifyMutate, isPending: false } as any)
  vi.mocked(useAddPhone).mockReturnValue({ mutateAsync: addMutate, isPending: false } as any)
  baseProps.onRemove.mockReset()
  baseProps.onVerified.mockReset()
})

const baseProps = {
  number: '+15551234567',
  onRemove: vi.fn(),
  onVerified: vi.fn(),
}

describe('PhoneNumberRow', () => {
  it('verified row shows no code field', () => {
    render(<PhoneNumberRow {...baseProps} verified />)
    expect(screen.getByText('Verified')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /verify/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /remove/i })).toBeInTheDocument()
  })

  it('unverified row shows code field, Verify and Resend', () => {
    render(<PhoneNumberRow {...baseProps} verified={false} />)
    expect(screen.getByText('Unverified')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^verify$/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /resend code/i })).toBeInTheDocument()
  })

  it('Verify is disabled until 6 digits entered', async () => {
    const user = userEvent.setup()
    render(<PhoneNumberRow {...baseProps} verified={false} />)
    const verifyBtn = screen.getByRole('button', { name: /^verify$/i })
    expect(verifyBtn).toBeDisabled()
    await user.type(screen.getByLabelText(/verification code/i), '123456')
    expect(verifyBtn).toBeEnabled()
  })

  it('submitting the code calls verifyPhone and onVerified on success', async () => {
    const user = userEvent.setup()
    const onVerified = vi.fn()
    render(<PhoneNumberRow {...baseProps} verified={false} onVerified={onVerified} />)
    await user.type(screen.getByLabelText(/verification code/i), '123456')
    await user.click(screen.getByRole('button', { name: /^verify$/i }))
    expect(verifyMutate).toHaveBeenCalledWith({ data: { number: '+15551234567', code: '123456' } })
    expect(onVerified).toHaveBeenCalled()
  })

  it('shows an error when verify fails', async () => {
    const user = userEvent.setup()
    verifyMutate.mockRejectedValue(new Error('bad'))
    render(<PhoneNumberRow {...baseProps} verified={false} />)
    await user.type(screen.getByLabelText(/verification code/i), '000000')
    await user.click(screen.getByRole('button', { name: /^verify$/i }))
    expect(await screen.findByText(/invalid or expired verification code/i)).toBeInTheDocument()
  })

  it('Resend calls addPhone and shows a success message', async () => {
    const user = userEvent.setup()
    render(<PhoneNumberRow {...baseProps} verified={false} />)
    await user.click(screen.getByRole('button', { name: /resend code/i }))
    expect(addMutate).toHaveBeenCalledWith({ data: { number: '+15551234567' } })
    expect(await screen.findByText(/new code sent/i)).toBeInTheDocument()
  })

  it('Remove button calls onRemove with the phone number', async () => {
    const user = userEvent.setup()
    const onRemove = vi.fn()
    render(<PhoneNumberRow {...baseProps} verified onRemove={onRemove} />)
    await user.click(screen.getByRole('button', { name: /remove/i }))
    expect(onRemove).toHaveBeenCalledWith('+15551234567')
  })

  it('shows an error when resend fails', async () => {
    const user = userEvent.setup()
    addMutate.mockRejectedValue(new Error('network'))
    render(<PhoneNumberRow {...baseProps} verified={false} />)
    await user.click(screen.getByRole('button', { name: /resend code/i }))
    expect(await screen.findByText(/failed to send code/i)).toBeInTheDocument()
  })
})
