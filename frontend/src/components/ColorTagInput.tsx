import { useEffect, useId, useRef, useState } from 'react'
import { X } from 'lucide-react'

interface ColorTagInputProps {
  id?: string
  /** Ordered list of color tags. Order is significant (rim/dominant first). */
  value: string[]
  onChange: (value: string[]) => void
  /** Existing color tags to autocomplete against. */
  suggestions?: string[]
  className?: string
  placeholder?: string
}

/**
 * Tag input that maintains order. Typing a token and pressing Space or Enter
 * commits it as a chip; Backspace on an empty input removes the last chip.
 * Autocomplete suggests existing single-color tags.
 */
export function ColorTagInput({
  id,
  value,
  onChange,
  suggestions = [],
  className,
  placeholder,
}: ColorTagInputProps) {
  const [draft, setDraft] = useState('')
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)
  const containerRef = useRef<HTMLDivElement>(null)
  const listId = useId()

  const draftStr = draft.trim().toLowerCase()
  const filtered = suggestions.filter(
    (s) => s.toLowerCase().includes(draftStr) && !value.includes(s),
  )
  const safeActiveIndex = activeIndex < filtered.length ? activeIndex : filtered.length - 1
  const isOpen = open && draft.length > 0 && filtered.length > 0

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

  const addTag = (raw: string) => {
    const tag = raw.trim()
    if (!tag) return
    if (!value.includes(tag)) onChange([...value, tag])
    setDraft('')
    setOpen(false)
    setActiveIndex(-1)
  }

  const removeTag = (index: number) => {
    onChange(value.filter((_, i) => i !== index))
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setOpen(true)
      setActiveIndex((i) => Math.min(i + 1, filtered.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIndex((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Enter' || e.key === ' ') {
      // Space and Enter both commit a chip.
      e.preventDefault()
      if (isOpen && safeActiveIndex >= 0) addTag(filtered[safeActiveIndex])
      else addTag(draft)
    } else if (e.key === 'Escape') {
      setOpen(false)
      setActiveIndex(-1)
    } else if (e.key === 'Backspace' && draft === '' && value.length > 0) {
      e.preventDefault()
      removeTag(value.length - 1)
    }
  }

  return (
    <div ref={containerRef} className="relative">
      <div className={className ?? 'flex flex-wrap items-center gap-1.5 rounded-md border border-input bg-background px-2 py-1.5'}>
        {value.map((tag, i) => (
          <span
            key={`${tag}-${i}`}
            className="inline-flex items-center gap-1 rounded bg-muted px-2 py-0.5 text-sm"
          >
            <span
              className="inline-block h-3 w-3 rounded-full border border-border"
              style={{ backgroundColor: tag.toLowerCase() }}
            />
            {tag}
            <button
              type="button"
              onClick={() => removeTag(i)}
              className="text-muted-foreground hover:text-foreground"
              aria-label={`Remove ${tag}`}
            >
              <X className="h-3 w-3" />
            </button>
          </span>
        ))}
        <input
          id={id}
          value={draft}
          onChange={(e) => {
            setDraft(e.target.value)
            setOpen(true)
            setActiveIndex(-1)
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => addTag(draft)}
          onKeyDown={handleKeyDown}
          role="combobox"
          aria-haspopup="listbox"
          aria-autocomplete="list"
          aria-expanded={isOpen}
          aria-controls={listId}
          aria-activedescendant={isOpen && safeActiveIndex >= 0 ? `${listId}-${safeActiveIndex}` : undefined}
          autoComplete="off"
          placeholder={value.length === 0 ? placeholder : undefined}
          className="min-w-24 flex-1 bg-transparent text-sm outline-none"
        />
      </div>
      {isOpen && (
        <ul
          id={listId}
          role="listbox"
          className="absolute z-10 mt-1 max-h-48 w-full overflow-y-auto rounded border border-gray-300 bg-white shadow-md"
        >
          {filtered.map((s, i) => (
            <li
              key={s}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === safeActiveIndex}
              onMouseDown={(e) => {
                e.preventDefault()
                addTag(s)
              }}
              className={`cursor-pointer px-3 py-2 text-sm ${
                i === safeActiveIndex ? 'bg-green-50 text-green-800' : 'hover:bg-gray-50'
              }`}
            >
              {s}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
