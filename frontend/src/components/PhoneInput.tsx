import { useRef, useState } from 'react'

interface PhoneInputProps {
  value: string
  onChange: (value: string) => void
  className?: string
}

export function PhoneInput({ value, onChange, className = '' }: PhoneInputProps) {
  const [area, setArea] = useState(() => extractPart(value, 0, 3))
  const [exchange, setExchange] = useState(() => extractPart(value, 3, 6))
  const [line, setLine] = useState(() => extractPart(value, 6, 10))

  const exchangeRef = useRef<HTMLInputElement>(null)
  const lineRef = useRef<HTMLInputElement>(null)

  function extractPart(digits: string, start: number, end: number) {
    const d = digits.replace(/\D/g, '')
    return d.slice(start, end)
  }

  function emit(a: string, e: string, l: string) {
    onChange(`${a}${e}${l}`)
  }

  function handleArea(v: string) {
    const d = v.replace(/\D/g, '').slice(0, 3)
    setArea(d)
    emit(d, exchange, line)
    if (d.length === 3) exchangeRef.current?.focus()
  }

  function handleExchange(v: string) {
    const d = v.replace(/\D/g, '').slice(0, 3)
    setExchange(d)
    emit(area, d, line)
    if (d.length === 3) lineRef.current?.focus()
  }

  function handleLine(v: string) {
    const d = v.replace(/\D/g, '').slice(0, 4)
    setLine(d)
    emit(area, exchange, d)
  }

  function handleExchangeKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Backspace' && exchange === '') {
      exchangeRef.current?.blur()
      // focus area code and move cursor to end
      const el = document.querySelector<HTMLInputElement>('[data-phone-area]')
      el?.focus()
    }
  }

  function handleLineKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Backspace' && line === '') {
      lineRef.current?.blur()
      exchangeRef.current?.focus()
    }
  }

  const segmentClass = `border border-gray-300 rounded px-2 py-2 text-center tabular-nums ${className}`

  return (
    <div className="flex items-center gap-1">
      <span className="text-gray-400 text-sm">+1</span>
      <input
        data-phone-area
        type="tel"
        inputMode="numeric"
        placeholder="555"
        maxLength={3}
        value={area}
        onChange={(e) => handleArea(e.target.value)}
        className={`${segmentClass} w-14`}
        aria-label="Area code"
      />
      <span className="text-gray-400">-</span>
      <input
        ref={exchangeRef}
        type="tel"
        inputMode="numeric"
        placeholder="123"
        maxLength={3}
        value={exchange}
        onChange={(e) => handleExchange(e.target.value)}
        onKeyDown={handleExchangeKey}
        className={`${segmentClass} w-14`}
        aria-label="Exchange"
      />
      <span className="text-gray-400">-</span>
      <input
        ref={lineRef}
        type="tel"
        inputMode="numeric"
        placeholder="4567"
        maxLength={4}
        value={line}
        onChange={(e) => handleLine(e.target.value)}
        onKeyDown={handleLineKey}
        className={`${segmentClass} w-16`}
        aria-label="Line number"
      />
    </div>
  )
}
