import { defineFeature } from '../feature'

// paczka faktur w kolejce tła: stan niepociętego zestawu zamiast „0 pozycji” (InvoiceBatchesPanel)
export default defineFeature({
  pl: {
    invQueued: 'w kolejce do przetworzenia',
    invProcessingSince: 'przetwarzanie od {n} min',
    invProcessingStale: 'przetwarzanie od {n} min — wygląda na zawieszone; odśwież za chwilę albo usuń paczkę i wgraj ponownie',
  },
  en: {
    invQueued: 'queued for processing',
    invProcessingSince: 'processing for {n} min',
    invProcessingStale: 'processing for {n} min — looks stuck; refresh shortly or delete the batch and upload again',
  },
  pt: {
    invQueued: 'na fila para processamento',
    invProcessingSince: 'em processamento há {n} min',
    invProcessingStale: 'em processamento há {n} min — parece bloqueado; atualize daqui a pouco ou elimine o lote e carregue de novo',
  },
})
