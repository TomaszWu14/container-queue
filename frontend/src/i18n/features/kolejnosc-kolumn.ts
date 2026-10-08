// Kolejność kolumn kolejki: przyciski ↑/↓ i przywracanie w menu „Widok" (ViewControls.tsx)
import { defineFeature } from '../feature'

export default defineFeature({
  pl: {
    kqColMoveUp: 'Przesuń w lewo', kqColMoveDown: 'Przesuń w prawo',
    kqColOrderReset: 'Przywróć domyślną kolejność', kqColDragHint: 'Przeciągnij nagłówek, aby zmienić kolejność kolumn',
  },
  en: {
    kqColMoveUp: 'Move left', kqColMoveDown: 'Move right',
    kqColOrderReset: 'Restore default order', kqColDragHint: 'Drag the header to reorder columns',
  },
  pt: {
    kqColMoveUp: 'Mover para a esquerda', kqColMoveDown: 'Mover para a direita',
    kqColOrderReset: 'Repor ordem predefinida', kqColDragHint: 'Arraste o cabeçalho para reordenar as colunas',
  },
})
