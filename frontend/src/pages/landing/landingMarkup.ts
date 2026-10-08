// Statyczny markup landingu (materiał projektowy, nie dane użytkownika) — wstawiany
// przez dangerouslySetInnerHTML; id `kl-*` ożywia useEffect w LandingPage.
export const MARKUP = `
<nav>
  <div class="brand">
    <span class="logo"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#04121f" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="8" width="13" height="9" rx="1"></rect><path d="M15 11h4l3 3v3h-7z"></path><circle cx="6" cy="19" r="1.6"></circle><circle cx="17" cy="19" r="1.6"></circle></svg></span>
    <span>Kolejka<small>Container Flow</small></span>
  </div>
  <div class="navlinks">
    <a href="#features">Funkcje</a><a href="#how">Jak to działa</a><a href="#tenant">Multi-tenant</a><a href="#features">Tracking</a>
  </div>
  <div class="navcta">
    <button class="btn btn-ghost" data-cta="demo">Zobacz demo</button>
    <button class="btn btn-primary" data-cta="login">Zaloguj się</button>
  </div>
</nav>

<header class="hero"><div class="wrap"><div class="hero-top">
  <div>
    <span class="badge"><span class="live"></span> Multi-tenant · role · audyt zmian</span>
    <h1>Zarządzaj kontenerami <span class="grad">od awizacji po dostawę</span></h1>
    <p class="subtitle"><span id="kl-typed"></span><span class="cursor"></span></p>
    <div class="stats">
      <div class="stat"><div class="num"><span data-count="1428">0</span></div><div class="lbl">Kontenery w kolejce</div></div>
      <div class="stat"><div class="num"><span data-count="18">0</span><span class="u">min</span></div><div class="lbl">Śr. czas oczekiwania</div></div>
      <div class="stat"><div class="num"><span class="u">ETA</span> <span data-count="42">0</span><span class="u">min</span></div><div class="lbl">Najbliższa dostawa</div></div>
    </div>
    <div class="hero-cta">
      <button class="btn btn-primary" data-cta="login">Zaloguj się</button>
      <button class="btn btn-ghost" data-cta="demo">Poznaj funkcje</button>
    </div>
  </div>

  <div class="panel dash">
    <div class="dash-head">
      <span class="t">Cykl życia kontenera — na żywo</span>
      <div class="bell-wrap">
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M6 16V10.5a6 6 0 0 1 12 0V16l1.6 2.2H4.4Z"></path><path d="M10 20.5a2 2 0 0 0 4 0"></path></svg>
        <span class="bdg">3</span>
      </div>
    </div>

    <svg viewBox="0 0 660 190" width="100%" style="display:block">
      <defs><linearGradient id="kl-fg" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#3b82f6"/><stop offset="1" stop-color="#06b6d4"/></linearGradient></defs>
      <path id="kl-fpath" class="flowline" d="M56 60 H604"></path>
      <path id="kl-fpathlit" class="flowline-dlt" d="M56 60 H604"></path>
      <g id="kl-stages"></g>
      <g id="kl-gps" style="display:none"><circle class="gps-ring" cx="0" cy="0" r="4"></circle><circle class="gps" cx="0" cy="0" r="4"></circle></g>
      <g id="kl-ctr" class="ctr"></g>
    </svg>

    <div class="drow">
      <div class="w">
        <div class="wl">Kalendarz awizacji — limity dzienne</div>
        <div class="cal" id="kl-cal"></div>
      </div>
      <div class="w">
        <div class="wl">Wskaźniki operacyjne</div>
        <div class="kpis" style="margin-top:9px">
          <div class="kpi"><span style="color:var(--muted);font-size:13px">Kontenery w kolejce</span><span class="v" style="color:var(--blue)" id="kl-k1">128</span></div>
          <div class="kpi"><span style="color:var(--muted);font-size:13px">Śr. oczekiwanie</span><span class="v" style="color:var(--cyan)" id="kl-k2">18 min</span></div>
          <div class="kpi"><span style="color:var(--muted);font-size:13px">Alerty demurrage</span><span class="v" style="color:var(--amber)" id="kl-k3">4</span></div>
        </div>
      </div>
    </div>

    <div class="tl" id="kl-tl">
      <div class="ev"><i style="background:var(--blue)"></i> Status zmieniony → W_PORCIE <time>12:04</time></div>
      <div class="ev"><i style="background:var(--cyan)"></i> ETA zaktualizowane · −22 min <time>12:07</time></div>
      <div class="ev"><i style="background:var(--amber)"></i> Alert demurrage · MSKU4471 <time>12:09</time></div>
    </div>
  </div>
</div></div></header>

<section class="sec" id="features"><div class="wrap">
  <div class="sec-head"><span class="eyebrow">Możliwości systemu</span><h2>Pełny cykl życia kontenera w jednym systemie</h2>
    <p>Pięć zrealizowanych modułów — od awizacji i kolejki, przez śledzenie statków AIS i moduł spedytora, po powiadomienia i raporty.</p></div>
  <div class="cards">
    <div class="card">
      <div class="ico">
        <svg class="slot-anim" viewBox="0 0 24 24" fill="none" stroke="var(--blue)" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">
          <rect x="3" y="4.5" width="18" height="16" rx="2"></rect><path d="M3 9h18M8 2.5v4M16 2.5v4"></path>
          <rect class="s" x="6" y="12" width="3.5" height="2.4" rx=".6" fill="var(--blue)" stroke="none"></rect>
          <rect class="s" x="10.5" y="12" width="3.5" height="2.4" rx=".6" fill="var(--amber)" stroke="none"></rect>
          <rect class="s" x="15" y="16" width="3.5" height="2.4" rx=".6" fill="var(--red)" stroke="none"></rect>
        </svg>
      </div>
      <h3>Kolejka i awizacje</h3>
      <p>Zarządzanie kolejką kontenerów z dziennymi limitami rozładunku i kalendarzem świąt PL/PT.</p>
      <div class="tags"><span class="tag">Limity dzienne</span><span class="tag">Kalendarz PL/PT</span><span class="tag">Import z Excela</span></div>
    </div>
    <div class="card">
      <div class="ico" style="background:rgba(6,182,212,.10);border-color:rgba(6,182,212,.22)">
        <svg viewBox="0 0 24 24" fill="none" stroke="var(--cyan)" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">
          <path d="M9 3 3 5v16l6-2 6 2 6-2V3l-6 2-6-2Z"></path><path d="M9 3v16M15 5v16"></path>
          <circle class="gpsdot" cx="12" cy="11" r="2.2" fill="var(--cyan)" stroke="none"></circle>
        </svg>
      </div>
      <h3>Tracking w czasie rzeczywistym</h3>
      <p>Pozycje statków z AIS na mapie i globusie, oś zdarzeń kontenera i alerty opóźnień.</p>
      <div class="tags"><span class="tag">AIS</span><span class="tag">Alerty opóźnień</span><span class="tag">Oś zdarzeń</span></div>
    </div>
    <div class="card">
      <div class="ico" style="background:rgba(59,130,246,.10);border-color:rgba(59,130,246,.22)">
        <svg viewBox="0 0 24 24" fill="none" stroke="var(--blue)" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">
          <rect x="4" y="3" width="12" height="16" rx="2"></rect><path d="M8 7h4M8 11h4M8 15h2"></path>
          <g class="orbit"><path d="M19 8a7 7 0 0 1 0 8" stroke="var(--cyan)"></path><path d="M19 16l1.6-1.2M19 16l-1.2-1.6" stroke="var(--cyan)"></path></g>
        </svg>
      </div>
      <h3>Moduł spedytora</h3>
      <p>Zlecenia transportowe, wymiana plików, wiadomości i dane agenta celnego w jednym obiegu.</p>
      <div class="tags"><span class="tag">Zlecenia</span><span class="tag">Wymiana plików</span><span class="tag">Agent celny</span></div>
    </div>
    <div class="card">
      <div class="ico" style="background:rgba(245,158,11,.10);border-color:rgba(245,158,11,.22)">
        <svg viewBox="0 0 24 24" fill="none" stroke="var(--amber)" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">
          <path class="bell" d="M6 16V10.5a6 6 0 0 1 12 0V16l1.6 2.2H4.4Z"></path><path d="M10 20.5a2 2 0 0 0 4 0"></path>
        </svg>
      </div>
      <h3>Powiadomienia i alerty</h3>
      <p>Powiadomienia in-app, e-mail i Teams, alerty demurrage oraz eksport zestawień do XLSX.</p>
      <div class="tags"><span class="tag">In-app</span><span class="tag">E-mail</span><span class="tag">Teams</span><span class="tag">Demurrage</span></div>
    </div>
    <div class="card">
      <div class="ico" style="background:rgba(16,185,129,.10);border-color:rgba(16,185,129,.22)">
        <svg class="barsvg" viewBox="0 0 24 24" fill="none" stroke="var(--green)" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">
          <path d="M4 20V4M4 20h16"></path>
          <rect x="7" y="12" width="2.6" height="6" fill="var(--green)" stroke="none"></rect>
          <rect x="11" y="9" width="2.6" height="9" fill="var(--green)" stroke="none"></rect>
          <rect x="15" y="6" width="2.6" height="12" fill="var(--green)" stroke="none"></rect>
        </svg>
      </div>
      <h3>Dashboard i raporty</h3>
      <p>Statystyki operacyjne, kalendarz awizacji z limitami i eksportowalne raporty na żądanie.</p>
      <div class="tags"><span class="tag">Statystyki</span><span class="tag">Kalendarz limitów</span><span class="tag">Eksport</span></div>
    </div>
    <div class="card" style="display:flex;flex-direction:column;justify-content:center;background:linear-gradient(135deg,rgba(59,130,246,.14),rgba(6,182,212,.10));border-color:rgba(6,182,212,.28)">
      <h3 style="font-size:19px">Gotowy na Twój terminal?</h3>
      <p style="margin-bottom:16px">Uruchom system dla swojej firmy w kilka minut.</p>
      <button class="btn btn-primary" data-cta="login" style="align-self:flex-start">Zaloguj się</button>
    </div>
  </div>
</div></section>

<section class="sec" id="how"><div class="wrap">
  <div class="sec-head"><span class="eyebrow">Jak to działa</span><h2>Od rejestracji do pełnego dashboardu w 3 krokach</h2></div>
  <div class="steps">
    <div class="step"><div class="n"></div><h4>Rejestracja firmy</h4><p>Zakładasz konto organizacji i przydzielasz role zespołowi.</p>
      <div class="chips"><span class="chip b">Operator</span><span class="chip c">Spedytor</span><span class="chip g">Agent celny</span></div></div>
    <div class="step"><div class="n"></div><h4>Kontener wchodzi do systemu</h4><p>Awizacja, wejście do kolejki terminalu i start trackingu.</p>
      <div class="chips"><span class="chip b">Awizacja</span><span class="chip c">Kolejka</span><span class="chip g">Tracking</span></div></div>
    <div class="step"><div class="n"></div><h4>Dashboard wypełnia się danymi</h4><p>Metryki, powiadomienia i raporty aktualizują się na bieżąco.</p>
      <div class="chips"><span class="chip b">Metryki</span><span class="chip c">Powiadomienia</span><span class="chip g">Raporty</span></div></div>
  </div>
</div></section>

<section class="sec" id="tenant"><div class="wrap">
  <div class="sec-head"><span class="eyebrow">Multi-tenant</span><h2>Wiele firm, jeden system — pełna izolacja danych</h2>
    <p>Każda organizacja ma własny dashboard, role i dane. Przełącz się i zobacz, jak działa separacja.</p></div>
  <div class="tenant">
    <div class="tenant-tabs" id="kl-ttabs"></div>
    <div class="tenant-body" id="kl-tbody"></div>
  </div>
</div></section>

<footer>
  <div class="fl">Zaufaj systemowi, który śledzi każdy kontener i każdy termin.</div>
  <div class="fs">© 2026 Kolejka · Container Flow — kolejkowanie · tracking · spedycja · powiadomienia · raporty.</div>
</footer>

<div class="tooltip" id="kl-tt"><div class="id"></div><div class="st"><i></i><span></span></div></div>
`
