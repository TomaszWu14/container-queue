import { CameraIcon, ImageIcon, TriangleAlertIcon, XIcon } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, errorMessage } from '../api'
import { useT } from '../i18n'
import { useToast } from '../feedback'
import type { Complaint, Container, ProblemType } from '../types'

export const COMPLAINT_STATUS_BADGE: Record<string, string> = {
  SZKIC: 'st-ZAPOWIEDZIANY',
  NOWA: 'st-ZAPOWIEDZIANY', ZGLOSZONA: 'st-ODPRAWA', WYSLANA: 'st-W_TRANSPORCIE',
  ODPOWIEDZ: 'st-AWIZOWANY', ZAMKNIETA: 'st-ZREALIZOWANY',
}

export function ComplaintsPanel({ container }: { container: Container }) {
  const t = useT()
  const navigate = useNavigate()
  const { showToast } = useToast()
  const [complaints, setComplaints] = useState<Complaint[]>([])
  const [types, setTypes] = useState<ProblemType[]>([])
  const [typesError, setTypesError] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [kind, setKind] = useState<'PROBLEM' | 'REKLAMACJA'>('PROBLEM')
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [description, setDescription] = useState('')
  const [driverNote, setDriverNote] = useState('')
  const [photos, setPhotos] = useState<File[]>([])
  const [thumbs, setThumbs] = useState<string[]>([])
  const [reportToWarehouse, setReportToWarehouse] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const cameraRef = useRef<HTMLInputElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  // podglądy blob tworzymy raz na zmianę listy i zwalniamy przy sprzątaniu (bez wycieku)
  useEffect(() => {
    const urls = photos.map(file => URL.createObjectURL(file))
    setThumbs(urls)
    return () => urls.forEach(URL.revokeObjectURL)
  }, [photos])

  const load = useCallback(() => {
    api.get<Complaint[]>(`/api/complaints?container_id=${container.id}`)
      .then(setComplaints).catch(err => showToast(errorMessage(err)))
  }, [container.id, showToast])
  useEffect(() => {
    load()
    setTypesError(false)
    api.get<ProblemType[]>('/api/problem-types?active_only=true')
      .then(setTypes)
      .catch(err => { setTypesError(true); showToast(errorMessage(err)) })
  }, [load, showToast])

  const toggle = (id: number) =>
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })

  const addPhotos = (list: FileList | null) => {
    if (list) setPhotos(prev => [...prev, ...Array.from(list)])
  }

  const reset = () => {
    setSelected(new Set()); setDescription(''); setDriverNote('')
    setPhotos([]); setKind('PROBLEM'); setShowForm(false)
    createdIdRef.current = null; uploadedRef.current = 0  // porzucona reklamacja startuje od nowa
  }

  const createdIdRef = useRef<number | null>(null)
  const uploadedRef = useRef(0)
  const submit = async () => {
    setBusy(true)
    setError('')
    try {
      // reklamację tworzymy raz — po błędzie uploadu ponowny „Zapisz" tylko dosyła
      // zdjęcia (bez duplikatu zgłoszenia)
      if (createdIdRef.current === null) {
        const created = await api.post<Complaint>('/api/complaints', {
          container_id: container.id, kind,
          description, driver_note: driverNote,
          problem_type_ids: [...selected],
          report_to_warehouse: reportToWarehouse,
        })
        createdIdRef.current = created.id
        uploadedRef.current = 0
      }
      for (let i = uploadedRef.current; i < photos.length; i++) {
        await api.upload(`/api/complaints/${createdIdRef.current}/photos`, photos[i])
        uploadedRef.current = i + 1
      }
      createdIdRef.current = null
      uploadedRef.current = 0
      reset()
      load()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="panel">
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h3 style={{ margin: 0 }}>{t('complaints')}</h3>
        {!showForm && (
          <button className="btn small" onClick={() => setShowForm(true)}>
            <TriangleAlertIcon size={14} /> {t('complaintNew')}
          </button>
        )}
      </div>

      {showForm && (
        <div className="complaint-form">
          <div className="tabs" style={{ marginTop: 10 }}>
            <button className={kind === 'PROBLEM' ? 'active' : ''} onClick={() => setKind('PROBLEM')}>
              {t('complaintKindProblem')}
            </button>
            <button className={kind === 'REKLAMACJA' ? 'active' : ''} onClick={() => setKind('REKLAMACJA')}>
              {t('complaintKindClaim')}
            </button>
          </div>

          <label className="cform-label">{t('complaintProblems')}</label>
          <div className="problem-chips">
            {types.map(type => (
              <button key={type.id} type="button"
                      className={`chip${selected.has(type.id) ? ' on' : ''}`}
                      onClick={() => toggle(type.id)}>
                {type.name}
              </button>
            ))}
            {types.length === 0 && (
              <span className={typesError ? 'error' : 'muted'}>
                {typesError ? t('retry') : t('complaintNoTypes')}
              </span>
            )}
          </div>

          <label className="cform-label">{t('complaintDesc')}
            <textarea rows={3} value={description} onChange={e => setDescription(e.target.value)} />
          </label>
          <label className="cform-label">{t('driverName')} — {t('complaintDriverNote')}
            <input value={driverNote} onChange={e => setDriverNote(e.target.value)} />
          </label>

          <div className="photo-row">
            <button type="button" className="btn secondary" onClick={() => cameraRef.current?.click()}>
              <CameraIcon size={14} /> {t('complaintPhoto')}
            </button>
            <button type="button" className="btn secondary" onClick={() => fileRef.current?.click()}>
              <ImageIcon size={14} /> {t('complaintGallery')}
            </button>
            <input ref={cameraRef} type="file" accept="image/*" capture="environment"
                   style={{ display: 'none' }} onChange={e => addPhotos(e.target.files)} />
            <input ref={fileRef} type="file" accept="image/*" multiple
                   style={{ display: 'none' }} onChange={e => addPhotos(e.target.files)} />
          </div>
          {photos.length > 0 && (
            <div className="photo-thumbs">
              {photos.map((file, index) => (
                <div className="thumb" key={index}>
                  <img src={thumbs[index]} alt={file.name} width={92} height={92} loading="lazy" />
                  <button aria-label={t('delete')} onClick={() => setPhotos(p => p.filter((_, i) => i !== index))}><XIcon size={14} /></button>
                </div>
              ))}
            </div>
          )}

          <label className="row" style={{ fontSize: 14, marginTop: 8 }}>
            <input type="checkbox" checked={reportToWarehouse}
                   onChange={e => setReportToWarehouse(e.target.checked)} />
            {t('complaintReportWarehouse')}
          </label>
          {error && <p className="error">{error}</p>}
          <div className="row" style={{ justifyContent: 'flex-end', marginTop: 8 }}>
            <button className="btn secondary" disabled={busy} onClick={reset}>{t('cancel')}</button>
            <button className="btn" disabled={busy} onClick={submit}>
              {busy ? t('loading') : t('complaintSubmit')}
            </button>
          </div>
        </div>
      )}

      {complaints.length === 0 && !showForm && (
        <p style={{ color: 'var(--muted)' }}>{t('complaintNone')}</p>
      )}
      {complaints.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table className="grid" style={{ minWidth: 720, marginTop: 10 }}>
            <thead>
              <tr><th>{t('complaintNo')}</th><th>{t('status')}</th><th>{t('complaintProblems')}</th>
                  <th><CameraIcon size={14} /></th><th></th></tr>
            </thead>
            <tbody>
              {complaints.map(c => (
                <tr key={c.id} className="clickable" style={{ cursor: 'pointer' }}
                    onClick={() => navigate(`/reklamacje/${c.id}`)}>
                  <td className="mono">{c.number}</td>
                  <td><span className={`badge ${COMPLAINT_STATUS_BADGE[c.status]}`}>
                    {t(`cst_${c.status}`)}</span></td>
                  <td>{c.problems.join(', ') || '—'}</td>
                  <td>{c.photo_count || ''}</td>
                  <td><button className="btn small secondary">{t('details')}</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
