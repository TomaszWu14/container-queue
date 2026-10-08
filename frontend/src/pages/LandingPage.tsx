import { useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { STYLE } from './landing/landingStyle'
import { MARKUP } from './landing/landingMarkup'
import { prefersReducedMotion, scrollBehavior } from '../motion'

/*
 * Publiczna strona wejściowa (landing) — port projektu „Kolejka Landing v2" z Claude Design.
 * CSS jest zescopowany pod `.kolejka-landing`, bo aplikacja definiuje globalnie m.in. `.btn`
 * i `.card` (styles.css). Fonty Google celowo NIE są ładowane linkiem — CSP (`style-src 'self'
 * 'unsafe-inline'`, `font-src` z default-src 'self') zablokowałoby zewnętrzne CSS/fonty; używamy
 * fallbacku systemowego. Markup wstawiony przez dangerouslySetInnerHTML (statyczny materiał
 * projektowy, nie dane użytkownika); logika animacji przeniesiona do useEffect z czyszczeniem.
 */

export default function LandingPage() {
  const navigate = useNavigate()
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const root = rootRef.current
    if (!root) return
    const NS = 'http://www.w3.org/2000/svg'
    const q = (sel: string) => root.querySelector(sel) as any
    const timers: number[] = []
    const rafs: number[] = []
    const setI = (fn: () => void, ms: number) => { const id = window.setInterval(fn, ms); timers.push(id); return id }
    const setT = (fn: () => void, ms: number) => { const id = window.setTimeout(fn, ms); timers.push(id); return id }
    const raf = (fn: FrameRequestCallback) => { const id = requestAnimationFrame(fn); rafs.push(id); return id }
    const still = prefersReducedMotion() // UX-040: bez pętli — jedna klatka / wartość końcowa

    // typewriter
    const full = 'Kolejkowanie · Tracking · Spedycja · Powiadomienia · Raporty — wszystko w jednym systemie.'
    const typed = q('#kl-typed'); let ti = 0
    const type = () => { if (typed && ti <= full.length) { typed.textContent = full.slice(0, ti); ti++; setT(type, 30) } }
    type()

    // counters
    root.querySelectorAll('[data-count]').forEach((el: any) => {
      const target = +el.dataset.count; let t0: number | null = null
      const step = (ts: number) => {
        if (!t0) t0 = ts
        const p = still ? 1 : Math.min(1, (ts - t0) / 1500), e = 1 - Math.pow(1 - p, 3)
        el.textContent = Math.round(target * e).toLocaleString('pl-PL')
        if (p < 1) raf(step)
      }
      raf(step)
    })

    // hero flow: 5 stages + moving container + highlight + GPS pulse
    const STAGES = [{ label: 'Awizacja' }, { label: 'Kolejka' }, { label: 'Tracking' }, { label: 'Odprawa' }, { label: 'Dostarczony' }]
    const sg = q('#kl-stages'); if (sg) sg.innerHTML = ''
    const X0 = 56, X1 = 604, Y = 60, STEP = (X1 - X0) / (STAGES.length - 1)
    const stageEls: Element[] = []
    STAGES.forEach((s, ix) => {
      const x = X0 + STEP * ix
      const g = document.createElementNS(NS, 'g'); g.setAttribute('class', 'stage'); g.setAttribute('transform', `translate(${x},${Y})`)
      const box = document.createElementNS(NS, 'rect'); box.setAttribute('class', 'stagebox')
      box.setAttribute('x', '-15'); box.setAttribute('y', '-15'); box.setAttribute('width', '30'); box.setAttribute('height', '30'); box.setAttribute('rx', '8')
      const ic = document.createElementNS(NS, 'path'); ic.setAttribute('class', 'si'); ic.setAttribute('d',
        ix === 0 ? 'M-7 -3h14M-7 1h14M-7 5h9' : ix === 1 ? 'M-6 6v-9h4v9M0 6v-6h4v6' : ix === 2 ? 'M0 -7c3.5 0 6 2.5 6 6 0 4-6 9-6 9s-6-5-6-9c0-3.5 2.5-6 6-6z' : 'M-6 0l4 4 8-9')
      ic.setAttribute('fill', 'none'); ic.setAttribute('stroke-width', '1.9'); ic.setAttribute('stroke-linecap', 'round'); ic.setAttribute('stroke-linejoin', 'round')
      const lb = document.createElementNS(NS, 'text'); lb.setAttribute('class', 'sl'); lb.setAttribute('text-anchor', 'middle'); lb.setAttribute('y', '30'); lb.textContent = s.label
      g.appendChild(box); g.appendChild(ic); g.appendChild(lb); sg.appendChild(g); stageEls.push(g)
    })

    const dltPath = q('#kl-fpathlit'), dltLen = dltPath ? dltPath.getTotalLength() : 0
    if (dltPath) { dltPath.setAttribute('stroke-dasharray', String(dltLen)); dltPath.setAttribute('stroke-dashoffset', String(dltLen)) }
    const gpsG = q('#kl-gps')
    const ctrG = q('#kl-ctr'); if (ctrG) ctrG.innerHTML = ''
    const body = document.createElementNS(NS, 'rect'); body.setAttribute('class', 'body')
    body.setAttribute('x', '-15'); body.setAttribute('y', '-10'); body.setAttribute('width', '30'); body.setAttribute('height', '20'); body.setAttribute('rx', '2.5'); body.setAttribute('fill', '#3b82f6')
    const ctxt = document.createElementNS(NS, 'text'); ctxt.setAttribute('text-anchor', 'middle'); ctxt.setAttribute('y', '3'); ctxt.textContent = '4471'
    if (ctrG) { ctrG.appendChild(body); ctrG.appendChild(ctxt) }

    const LOOP = 13000, DWELL = 0.06
    const heroFrame = (ts: number) => {
      const t = (ts % LOOP) / LOOP
      const segs = STAGES.length - 1, seg = Math.min(segs - 1, Math.floor(t * segs)), local = (t * segs) - seg
      let e: number
      if (local < DWELL) { e = 0 } else { const l = (local - DWELL) / (1 - DWELL); e = l < .5 ? 2 * l * l : 1 - Math.pow(-2 * l + 2, 2) / 2 }
      const globalFrac = (seg + e) / segs
      const x = X0 + (X1 - X0) * globalFrac
      if (ctrG) ctrG.setAttribute('transform', `translate(${x},${Y})`)
      if (dltPath) dltPath.setAttribute('stroke-dashoffset', String(dltLen * (1 - globalFrac)))
      const activeIdx = Math.round(globalFrac * segs)
      stageEls.forEach((g, i) => g.classList.toggle('active', i <= activeIdx))
      const col = activeIdx >= 4 ? '#10b981' : activeIdx === 2 ? '#06b6d4' : activeIdx === 3 ? '#f59e0b' : '#3b82f6'
      body.setAttribute('fill', col)
      if (gpsG) {
        if (activeIdx === 2) { gpsG.style.display = ''; gpsG.setAttribute('transform', `translate(${x},${Y})`) }
        else gpsG.style.display = 'none'
      }
      if (!still) raf(heroFrame)
    }
    raf(heroFrame)

    // container tooltip
    const tt = q('#kl-tt'), ttId = tt?.querySelector('.id'), ttI = tt?.querySelector('.st i'), ttS = tt?.querySelector('.st span')
    if (ctrG && tt) {
      ctrG.style.cursor = 'pointer'
      const onEnter = () => { ttId.textContent = 'MSKU4471'; ttI.style.background = body.getAttribute('fill'); ttS.textContent = 'W obiegu — cykl życia'; tt.classList.add('on') }
      const onMove = (ev: MouseEvent) => { tt.style.left = (ev.clientX + 16) + 'px'; tt.style.top = (ev.clientY + 16) + 'px' }
      const onLeave = () => tt.classList.remove('on')
      ctrG.addEventListener('mouseenter', onEnter); ctrG.addEventListener('mousemove', onMove); ctrG.addEventListener('mouseleave', onLeave)
    }

    // mini calendar
    const cal = q('#kl-cal'); if (cal) cal.innerHTML = ''
    const pattern = ['', 'has', 'has', 'full', 'has', 'over', '', 'has', 'has', 'has', 'full', 'over', 'has', '', 'has', 'full', 'has', 'has', 'over', 'has', '']
    for (let d = 0; d < 21; d++) { const c = document.createElement('div'); c.className = 'd'; cal.appendChild(c) }
    const cells = cal.children
    const fillCal = () => {
      Array.prototype.forEach.call(cells, (c: any) => { c.className = 'd' })
      const order: number[] = []; for (let i = 0; i < 21; i++) if (pattern[i]) order.push(i)
      order.forEach((i, ix) => setT(() => { cells[i].className = 'd ' + pattern[i] }, ix * 90))
    }

    // timeline reveal + KPI drift
    const evs = root.querySelectorAll('#kl-tl .ev')
    const playTL = () => evs.forEach((e, i) => { e.classList.remove('show'); setT(() => e.classList.add('show'), 400 + i * 550) })
    const k1 = q('#kl-k1'), k2 = q('#kl-k2'), k3 = q('#kl-k3')
    const drift = () => {
      k1.textContent = String(110 + Math.round(Math.random() * 40))
      k2.textContent = (12 + Math.round(Math.random() * 12)) + ' min'
      k3.textContent = String(Math.round(Math.random() * 7))
    }
    const dash = q('.dash')
    const heroObs = new IntersectionObserver((en) => {
      if (en[0].isIntersecting) { fillCal(); playTL(); drift(); setI(() => { fillCal(); playTL(); drift() }, 6500) }
    }, { threshold: .2 })
    if (dash) heroObs.observe(dash)

    // scroll reveal: cards + steps
    const io = new IntersectionObserver((entries) => {
      entries.forEach((en) => { if (en.isIntersecting) { (en.target as HTMLElement).style.transitionDelay = ((en.target as HTMLElement).dataset.d || 0) + 'ms'; en.target.classList.add('in'); io.unobserve(en.target) } })
    }, { threshold: .2 })
    root.querySelectorAll('.card').forEach((c, i) => { (c as HTMLElement).dataset.d = String((i % 3) * 100); io.observe(c) })
    root.querySelectorAll('.step').forEach((s, i) => { (s as HTMLElement).dataset.d = String(i * 140); io.observe(s) })

    // multi-tenant switcher (nazwy generyczne — to strona publiczna)
    const TENANTS = [
      { id: 'c1', name: 'Company-1', color: '#3b82f6', role: 'Operator logistyczny', m: [['W kolejce', '214'], ['Dostarczone /dz', '86'], ['Alerty', '2'], ['Terminale', '5']] },
      { id: 'c2', name: 'Company-2', color: '#06b6d4', role: 'Operator + spedytor', m: [['W kolejce', '132'], ['Dostarczone /dz', '54'], ['Alerty', '1'], ['Terminale', '3']] },
      { id: 'c3', name: 'Company-3', color: '#f59e0b', role: 'Spedytor', m: [['W kolejce', '78'], ['Dostarczone /dz', '31'], ['Alerty', '4'], ['Terminale', '2']] },
      { id: 'c4', name: 'Company-4', color: '#e0396b', role: 'Operator (PT)', m: [['W kolejce', '96'], ['Dostarczone /dz', '40'], ['Alerty', '0'], ['Terminale', '2']] },
    ]
    const ttabs = q('#kl-ttabs'), tbody = q('#kl-tbody')
    if (ttabs) ttabs.innerHTML = ''; if (tbody) tbody.innerHTML = ''
    const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c] as string))
    const select = (id: string) => {
      ttabs.querySelectorAll('.ttab').forEach((x: any) => x.classList.toggle('active', x.dataset.id === id))
      tbody.querySelectorAll('.tpane').forEach((x: any) => x.classList.toggle('active', x.dataset.id === id))
    }
    TENANTS.forEach((t, ix) => {
      const tab = document.createElement('div'); tab.className = 'ttab' + (ix === 0 ? ' active' : ''); tab.dataset.id = t.id
      tab.innerHTML = `<span class="avatar" style="background:${t.color}">${esc(t.name[0])}</span><span>${esc(t.name)}<div class="role">${esc(t.role)}</div></span>`
      tab.addEventListener('click', () => { userTouched = true; select(t.id) })
      ttabs.appendChild(tab)
      const pane = document.createElement('div'); pane.className = 'tpane' + (ix === 0 ? ' active' : ''); pane.dataset.id = t.id
      const metrics = t.m.map((m) => `<div class="tm"><div class="l">${esc(m[0])}</div><div class="v" style="color:${t.color}">${esc(m[1])}</div></div>`).join('')
      pane.innerHTML =
        `<div class="tpane-head"><span class="lg" style="background:${t.color}">${esc(t.name[0])}</span>` +
        `<div><div style="font-weight:700">${esc(t.name)}</div><div style="font-size:12px;color:var(--muted)">${esc(t.role)}</div></div>` +
        `<span class="role-badge">Rola: ${esc(t.role.split(' ')[0])}</span></div>` +
        `<div class="tmetrics">${metrics}</div>` +
        `<div class="iso-note"><svg viewBox="0 0 24 24" fill="none" stroke="${t.color}" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="11" width="14" height="9" rx="2"></rect><path d="M8 11V8a4 4 0 0 1 8 0v3"></path></svg> Dane firmy <b style="color:var(--text);margin:0 4px">${esc(t.name)}</b> są w pełni odizolowane od pozostałych organizacji.</div>`
      tbody.appendChild(pane)
    })
    let auto = 0, userTouched = false
    if (!still) setI(() => { if (userTouched) return; auto = (auto + 1) % TENANTS.length; select(TENANTS[auto].id) }, 3800)

    // CTA + kotwice: przyciski logowania → /login, „demo" → sekcja funkcji
    const onClick = (ev: Event) => {
      const el = (ev.target as HTMLElement).closest('[data-cta], a[href^="#"]') as HTMLElement | null
      if (!el) return
      const cta = el.getAttribute('data-cta')
      if (cta === 'login') { ev.preventDefault(); navigate('/login'); return }
      const href = el.getAttribute('href')
      if (cta === 'demo') { ev.preventDefault(); root.querySelector('#features')?.scrollIntoView({ behavior: scrollBehavior() }); return }
      if (href && href.startsWith('#')) { ev.preventDefault(); root.querySelector(href)?.scrollIntoView({ behavior: scrollBehavior() }) }
    }
    root.addEventListener('click', onClick)

    return () => {
      timers.forEach(clearTimeout); timers.forEach(clearInterval)
      rafs.forEach(cancelAnimationFrame)
      heroObs.disconnect(); io.disconnect()
      root.removeEventListener('click', onClick)
    }
  }, [navigate])

  return (
    <div className="kolejka-landing" ref={rootRef}>
      <style>{STYLE}</style>
      <div dangerouslySetInnerHTML={{ __html: MARKUP }} />
    </div>
  )
}
