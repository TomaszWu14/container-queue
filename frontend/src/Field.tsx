import { cloneElement, isValidElement, useId } from 'react'
import type { ReactElement, ReactNode } from 'react'

// Pole formularza z etykietą nad kontrolką (audyt UI S1): <label> owija pole, więc czytnik
// ekranu zna jego nazwę; podpowiedź i błąd są podpięte przez aria-describedby.
export function Field({ label, hint, error, className, children }: {
  label: ReactNode
  hint?: ReactNode
  error?: ReactNode
  className?: string
  children: ReactNode
}) {
  const id = useId()
  const describedBy = [hint && `${id}-h`, error && `${id}-e`].filter(Boolean).join(' ') || undefined
  const control = isValidElement(children)
    ? cloneElement(children as ReactElement<Record<string, unknown>>,
        { 'aria-describedby': describedBy, 'aria-invalid': error ? true : undefined })
    : children
  return (
    <label className={className ? `field ${className}` : 'field'}>
      <span className="field-label">{label}</span>
      {control}
      {hint && <span id={`${id}-h`} className="field-hint">{hint}</span>}
      {error && <span id={`${id}-e`} className="field-error" role="alert">{error}</span>}
    </label>
  )
}
