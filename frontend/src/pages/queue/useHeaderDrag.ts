// Przestawianie kolumn kolejki przeciąganiem nagłówka (HTML5 drag & drop). Wskaźnik miejsca
// upuszczenia = pionowa kreska po lewej/prawej stronie nagłówka pod kursorem. Klawiatura: ↑/↓ w menu „Widok".
import { useState } from 'react'
import type { DragEvent } from 'react'

type Move = (key: string, target: string, after: boolean) => void
const afterMid = (e: DragEvent<HTMLElement>) => {
  const r = e.currentTarget.getBoundingClientRect()
  return e.clientX > r.left + r.width / 2
}

export function useHeaderDrag(move: Move | undefined) {
  const [drag, setDrag] = useState<string | null>(null)
  const [over, setOver] = useState<{ key: string; after: boolean } | null>(null)
  const end = () => { setDrag(null); setOver(null) }
  /** Atrybuty <th>: pusty obiekt dla kolumny nieruchomej (Nr, spółka) albo bez zapisu kolejności. */
  const thProps = (key: string, movable: boolean) => (!move || !movable ? {} : {
    draggable: true,
    onDragStart: (e: DragEvent<HTMLElement>) => {
      // przeciąganie tekstu w panelu lejka (portal — zdarzenia bąbelkują drzewem Reacta) to nie przestawianie
      if (e.target !== e.currentTarget) return
      e.dataTransfer?.setData('text/plain', key)
      if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move'
      setDrag(key)
    },
    onDragOver: (e: DragEvent<HTMLElement>) => {
      if (!drag || drag === key) return
      e.preventDefault()   // bez tego przeglądarka nie pozwala upuścić
      const after = afterMid(e)
      if (over?.key !== key || over.after !== after) setOver({ key, after })
    },
    onDrop: (e: DragEvent<HTMLElement>) => {
      e.preventDefault()
      if (drag && drag !== key) move(drag, key, afterMid(e))
      end()
    },
    onDragEnd: end,
  })
  /** Klasa wskaźnika dla nagłówka `key`. */
  const dropClass = (key: string) =>
    (drag === key ? ' kq-dragging' : '') + (over?.key === key ? (over.after ? ' kq-drop-after' : ' kq-drop-before') : '')
  return { thProps, dropClass }
}
