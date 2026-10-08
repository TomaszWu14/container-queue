import { UploadIcon } from 'lucide-react'
import { useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { useT } from './i18n'

// Wybór pliku w stylu i języku aplikacji (audyt UI B24, UX-028): natywne „Choose File / No file
// chosen” mówiło językiem przeglądarki. Ukryty <input type="file"> (nazwa dla czytnika w aria-label)
// otwiera przycisk „Wybierz plik”; obok nazwa wybranego pliku.
export function FilePicker({ label, caption, accept, disabled, file, onChange }: {
  label: string                 // nazwa pola dla czytnika ekranu
  caption?: ReactNode           // widoczny podpis nad przyciskiem (jak w <Field>)
  accept?: string
  disabled?: boolean
  file?: File | null            // wybrany plik; bez propa — nazwa ostatnio wybranego
  onChange: (file: File | null) => void
}) {
  const t = useT()
  const ref = useRef<HTMLInputElement>(null)
  const [picked, setPicked] = useState('')
  const name = file === undefined ? picked : file?.name ?? ''
  return (
    <div className={caption ? 'file-pick with-caption' : 'file-pick'}>
      {caption && <span className="file-pick-caption">{caption}</span>}
      <span className="file-pick-row">
        <input ref={ref} type="file" hidden accept={accept} disabled={disabled} aria-label={label}
               onChange={e => {
                 const f = e.target.files?.[0] ?? null
                 setPicked(f?.name ?? '')
                 onChange(f)
                 e.target.value = ''   // ten sam plik da się wybrać ponownie (po wyczyszczeniu formularza)
               }} />
        <button type="button" className="btn small secondary" disabled={disabled}
                onClick={() => ref.current?.click()}>
          <UploadIcon size={14} aria-hidden="true" /> {t('filePick')}
        </button>
        <span className={name ? 'file-pick-name' : 'file-pick-name muted'} title={name || undefined}>
          {name || t('fileNone')}
        </span>
      </span>
    </div>
  )
}

// Przycisk wgrywania osiągalny z klawiatury (spec dokumenty-dostaw §4 pkt 49): prawdziwy <button>
// zamiast <label> z ukrytym inputem — Tab / Enter / Spacja działają, czytnik czyta etykietę.
export function FileButton({ children, className = 'btn small secondary', accept, multiple, disabled,
                             title, directory, onFiles }: {
  children: ReactNode
  className?: string
  accept?: string
  multiple?: boolean
  disabled?: boolean
  title?: string
  directory?: boolean             // cały folder (webkitdirectory)
  onFiles: (files: File[]) => void
}) {
  const ref = useRef<HTMLInputElement>(null)
  const dirProps = directory ? { webkitdirectory: '', directory: '' } as Record<string, string> : {}
  return (
    <>
      <input ref={ref} type="file" hidden tabIndex={-1} accept={accept} multiple={multiple || directory}
             disabled={disabled} {...dirProps}
             aria-label={typeof children === 'string' ? children : title}
             onChange={e => { onFiles(Array.from(e.target.files ?? [])); e.target.value = '' }} />
      <button type="button" className={className} disabled={disabled} title={title}
              onClick={() => ref.current?.click()}>{children}</button>
    </>
  )
}
