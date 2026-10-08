// Limit pliku = backend max_upload_mb (domyślnie 25 MB; po zalogowaniu App podmienia go
// wartością z /api/ui-config). Za duży plik odrzucamy PRZED wysłaniem (api.upload,
// downloadFile z formularzem) — zamiast minut uploadu zakończonych 413.
// Osobny moduł: testy mockujące './api' nie muszą go powielać.
let uploadLimitMb = 25

export function setUploadLimitMb(mb: unknown): void {
  if (typeof mb === 'number' && mb > 0) uploadLimitMb = mb
}

export function assertUploadSize(files: Iterable<unknown>): void {
  for (const f of files) {
    if (f instanceof File && f.size > uploadLimitMb * 1024 * 1024)
      throw new Error(`Plik „${f.name}” jest za duży — limit ${uploadLimitMb} MB.`)
  }
}
