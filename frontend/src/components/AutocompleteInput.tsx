import { useEffect, useId, useRef, useState } from 'react'

export interface Suggestion {
  value: string
  label?: string
}

interface AutocompleteInputProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'onChange'> {
  suggestions: Suggestion[]
  onValueChange: (value: string) => void
}

export function AutocompleteInput({
  suggestions,
  onValueChange,
  value = '',
  className,
  ...props
}: AutocompleteInputProps) {
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)
  const containerRef = useRef<HTMLDivElement>(null)
  const listId = useId()

  const inputStr = String(value)
  const filtered = suggestions.filter((s) =>
    s.value.toLowerCase().includes(inputStr.toLowerCase()),
  )
  // Clamp to last valid index; yields -1 when list is empty (safe — Enter guard checks >= 0)
  const safeActiveIndex = activeIndex < filtered.length ? activeIndex : filtered.length - 1
  const isOpen = open && filtered.length > 0

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
        setActiveIndex(-1)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const select = (s: Suggestion) => {
    onValueChange(s.value)
    setOpen(false)
    setActiveIndex(-1)
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setOpen(true)
      setActiveIndex((i) => Math.min(i + 1, filtered.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIndex((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Enter' && safeActiveIndex >= 0) {
      e.preventDefault()
      select(filtered[safeActiveIndex])
    } else if (e.key === 'Escape') {
      setOpen(false)
      setActiveIndex(-1)
    }
  }

  return (
    <div ref={containerRef} className="relative">
      <input
        {...props}
        value={value}
        onChange={(e) => {
          onValueChange(e.target.value)
          setOpen(true)
          setActiveIndex(-1)
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={handleKeyDown}
        role="combobox"
        aria-expanded={isOpen}
        aria-controls={listId}
        aria-activedescendant={isOpen && safeActiveIndex >= 0 ? `${listId}-${safeActiveIndex}` : undefined}
        autoComplete="off"
        className={className ?? 'w-full border border-gray-300 rounded px-3 py-2'}
      />
      {isOpen && (
        <ul
          id={listId}
          role="listbox"
          className="absolute z-10 w-full bg-white border border-gray-300 rounded shadow-md mt-1 max-h-48 overflow-y-auto"
        >
          {filtered.map((s, i) => (
            <li
              key={s.value}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === safeActiveIndex}
              onMouseDown={() => select(s)}
              className={`px-3 py-2 cursor-pointer text-sm ${
                i === safeActiveIndex ? 'bg-green-50 text-green-800' : 'hover:bg-gray-50'
              }`}
            >
              {s.label ?? s.value}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
