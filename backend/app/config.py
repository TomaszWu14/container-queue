from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8",
                                      extra="ignore")

    app_name: str = "TIMPORYE — kolejka kontenerów"
    environment: str = "dev"  # dev / production — production wymusza bezpieczne sekrety
    app_version: str = "dev"      # krótki SHA builda (wstrzykiwany w obrazie)
    build_time: str = "unknown"   # data/godzina builda obrazu (UTC)
    database_url: str = "sqlite:///./timporye.db"
    # Pula połączeń (tylko PostgreSQL). Domyślne 10+20=30 pokrywa threadpool Starlette
    # (~40 wątków dla synchronicznych handlerów), zostając poniżej max_connections PG
    # (domyślnie 100) nawet przy kilku workerach. pool_recycle odrzuca połączenia
    # starsze niż TTL (proxy/idle timeout), pool_timeout ogranicza czekanie na wolne.
    db_pool_size: int = Field(default=10, ge=1)
    db_max_overflow: int = Field(default=20, ge=0)
    db_pool_timeout: int = Field(default=30, ge=1)      # s czekania na wolne połączenie
    db_pool_recycle: int = Field(default=1800, ge=1)    # s — recykling połączenia
    # koszt bcrypt nowych hashy haseł (2^N rund); produkcja min. 12 (start odmawia niżej),
    # testy 4 — logowanie w każdym teście zjadało ~9 z 11 min CI (2026-09-29)
    bcrypt_rounds: int = Field(default=12, ge=4, le=15)
    secret_key: str = "change-me-in-production"
    # klucz szyfrowania danych w bazie (cache MSAL itp.), osobny od SECRET_KEY (SEC-017);
    # puste = jak dotąd klucz z SECRET_KEY. Stare wartości czytane dalej kluczem z SECRET_KEY
    data_encryption_key: str = ""
    # False = instancja wtórna na wspólnej bazie: bez pętli tła (alerty, digest,
    # SMS-y, kolektor AIS, sync trackingu) — inaczej wysyłki dublują się per serwer
    run_background_jobs: bool = True
    # BUILD-003: liczba workerów uvicorna — uvicorn czyta tę samą zmienną sam (CMD bez
    # --workers). >1 tylko na PostgreSQL (rate_limit.assert_worker_config); pętle tła
    # prowadzi wtedy jeden proces-lider (leader.py). Każdy worker ~260 MB RAM i własna pula.
    web_concurrency: int = Field(default=1, ge=1, le=16)
    access_token_minutes: int = Field(default=120, ge=1)  # 2 h — decyzja 2026-09-18
    # okno łaski dla ponownego użycia zrotowanego refresh tokenu (wyścig kart) — s;
    # krótkie (SEC-010): w oknie wydajemy tylko access token, bez nowego refresh
    refresh_reuse_grace_seconds: int = Field(default=10, ge=0)
    refresh_token_days: int = Field(default=14, ge=1)
    # retencja (OBS-011/GDPR-007): tokeny po wygaśnięciu, historia SMS, błędy JS z beaconu
    token_retention_days: int = Field(default=30, ge=1)
    sms_retention_days: int = Field(default=90, ge=1)
    client_error_retention_days: int = Field(default=30, ge=1)
    admin_login: str = "admin"
    admin_password: str = "admin123"
    # pusta lista = brak CORS (panel serwowany z tego samego adresu go nie potrzebuje)
    cors_origins: str = ""
    secure_cookies: bool = False  # True za HTTPS: cookies z flagą Secure + nagłówek HSTS
    # produkcja jeszcze bez HTTPS (instancja przed certyfikatem, SEC-003): zwalnia TYLKO wymóg
    # SECURE_COOKIES — reszta fail-fast (sekrety, PUBLIC_BASE_URL) i ukryte /docs działają
    allow_insecure_http: bool = False
    login_max_attempts: int = Field(default=5, ge=1)   # limit nieudanych logowań…
    login_window_minutes: int = Field(default=15, ge=1)  # …w oknie czasowym (na parę IP+login)
    # suma porażek z jednego IP (wiele loginów) — wyżej niż para, bo za NAT biura siedzi wielu ludzi
    login_max_attempts_per_ip: int = Field(default=20, ge=1)
    # SEC-012: porażki jednego konta ze WSZYSTKICH IP (rozproszony brute force) — od tylu w oknie
    # każda kolejna podwaja przerwę (base, 2×base, 4×base… maks. okno); alert do adminów
    login_account_lock_after: int = Field(default=10, ge=1)
    login_account_lock_seconds: int = Field(default=30, ge=1)
    # globalny limit żądań API na IP w oknie minutowym (0 = wyłączony)
    api_rate_limit_per_minute: int = Field(default=300, ge=0)
    password_reset_minutes: int = Field(default=30, ge=1)  # ważność linku resetu hasła
    # W14 #89: polityka haseł — minimalna długość (+ wymóg litery i cyfry w kodzie)
    password_min_length: int = Field(default=12, ge=4)
    # SEC-006: przy true admin bez 2FA czyta, ale nic nie zmieni (poza własnym kontem), dopóki
    # nie włączy 2FA — panel pokazuje ekran włączania po zalogowaniu (twofa_policy.py).
    # Domyślnie wyłączone (decyzja właściciela 2026-09-29); 2FA dobrowolne w Profilu działa zawsze.
    require_2fa_admin: bool = False
    # W14 #50: limit beaconów błędów JS z panelu (na IP, okno minutowe)
    client_error_rate_per_minute: int = Field(default=10, ge=1)
    # W14 #47: dzień tygodnia cotygodniowej weryfikacji backupu (0=pon … 6=niedziela)
    verify_backup_weekday: int = Field(default=6, ge=0, le=6)
    backup_dir: str = "/data/backups"
    # najstarsza akceptowana kopia przy weryfikacji; backup raz w tygodniu (sobota, decyzja 2026-09-28)
    backup_max_age_hours: int = Field(default=194, ge=1)
    # OBS-007: trwały plik logów z rotacją (np. /data/logs/app.log); puste = tylko stdout
    log_file: str = ""
    allowed_upload_extensions: str = ("pdf,doc,docx,xls,xlsx,csv,txt,png,jpg,jpeg,"
                                      "webp,gif,eml,msg,zip,xml,json")
    sentry_dsn: str = ""  # puste = monitoring błędów wyłączony
    sentry_release: str = ""  # SHA/tag builda; ustaw jako env w Coolify — brak = pomiń w Sentry
    # OBS-010: odsetek transakcji (wydajność) wysyłanych do Sentry; błędy idą zawsze w 100%
    sentry_traces_rate: float = Field(default=0.05, ge=0.0, le=1.0)
    public_base_url: str = ""  # adres panelu w linkach e-mail (WYMAGANY w produkcji)
    # branding stron publicznych (portal kliencki) — bez hardkodu nazwy spółki w kodzie
    portal_brand_name: str = ""   # puste = app_name
    portal_logo_url: str = ""     # opcjonalny URL logo w nagłówku portalu
    # Instancja pokazowa (portfolio): loginy tylko do odczytu (po przecinku) — każdy zapis z tych
    # kont = 403; podpowiedź „login / hasło” na ekranie logowania. Puste = zwykła instancja.
    demo_readonly_logins: str = ""
    demo_login_hint: str = ""
    # dozwolone nagłówki Host (CSV) — ochrona przed host-header injection; puste = bez filtra
    allowed_hosts: str = ""
    # liczba zaufanych proxy przed aplikacją — IP klienta bierzemy z tej pozycji X-Forwarded-For
    trusted_proxy_count: int = Field(default=1, ge=0)
    # X-Forwarded-For honorujemy TYLKO, gdy bezpośredni peer jest w tych sieciach (CSV CIDR);
    # domyślnie TYLKO sieć dockera (Traefik Coolify) i localhost — NIE 10.0.0.0/8, bo tam jest
    # sieć firmowa (SEC-002). Peer spoza listy = XFF ignorowany, bo byłby podszywalny.
    # Ta sama wartość idzie do uvicorn --forwarded-allow-ips (Dockerfile.coolify)
    trusted_proxy_cidrs: str = "172.16.0.0/12,127.0.0.1/32"
    # SMS do kierowców (łącznik kierowcy)
    sms_provider: str = "off"       # smsapi / mock / off
    smsapi_token: str = ""
    smsapi_url: str = "https://api.smsapi.pl/sms.do"
    # COST-003: globalny limit prób SMS na dobę PL (0 = bez limitu; alert adminów przy 80%)
    # i limit prób auto-przypomnienia na kontener+dostawę na dobę (pętla co 15 min)
    sms_daily_cap: int = Field(default=200, ge=0)
    sms_auto_max_attempts: int = Field(default=2, ge=1)
    # SEC-014: twardy limit dla KAŻDEGO publicznego linku (DLT, awizacja)
    # liczony od wystawienia — także gdy link nie ma własnego terminu (public_links.py)
    public_link_max_days: int = Field(default=90, ge=1)
    # interwał joba kongestii portów (AIS)
    tracking_interval_hours: float = Field(default=12.0, gt=0)
    # próg powiadomienia o zmianie ETA — drobne drgania ETA armatora to szum
    tracking_eta_alert_days: int = Field(default=2, ge=0)
    # AIS (aisstream.io) — darmowe pozycje STATKÓW jako uzupełnienie trackingu kontenerów:
    # klucz włącza kolektor websocketowy; pusty = wyłączone
    aisstream_api_key: str = ""
    aisstream_url: str = "wss://stream.aisstream.io/v0/stream"
    # co ile sekund zrywamy i odnawiamy subskrypcję (odświeżenie listy statków z kolejki)
    ais_resubscribe_seconds: float = Field(default=900.0, gt=0)
    ais_error_backoff_seconds: float = Field(default=60.0, gt=0)
    # #36: alert, gdy statek stoi przy porcie dluzej niz N godzin
    ais_anchor_alert_hours: float = Field(default=48.0, gt=0)
    # statek bez wiadomości AIS dłużej niż N godzin ma „zamrożony" near_port
    # (poza zasięgiem / poza filtrem MMSI) — nie alarmujemy o jego postoju
    ais_stale_hours: float = Field(default=24.0, gt=0)
    # Serwis paletyzacji (REST, X-API-Key) — puste = sekcja paletyzacji na karcie rozładunku
    # pokazuje "Serwis paletyzacji nie skonfigurowany" (patrz routers/containers.py: palletization)
    pallet_api_url: str = ""
    pallet_api_token: str = ""
    pallet_api_timeout: float = Field(default=5.0, gt=0)
    # Faktury (CIPL) → Excel: limit stron jednego PDF-zestawu (ochrona przed 300-stronicowym
    # skanem, który zajmie worker na minuty — ekstrakcja tekstu/tabel jest synchroniczna)
    invoice_pdf_max_pages: int = Field(default=60, ge=1)
    # W5 dokumenty: horyzont alertu braków dokumentów przed ETA (dni; nadpisywalne
    # ustawieniem admina docs_reminder_days) i tolerancja rozjazdu faktura↔zamówienie (%)
    docs_eta_days: int = Field(default=5, ge=0)
    invoice_tolerance_pct: float = Field(default=2.0, ge=0)
    # kartoteka dostawców (spec 2026-09-25): kody spółek (Company.code, CSV) pracujących na
    # materiałach Acme — widzą i używają globalnej kartoteki. Pozostałe (Borealis, Cobalt…)
    # mają tylko własnych nadawców kontenerów (Supplier.client_company_id). Env: SUPPLIER_COMPANY_CODES
    supplier_company_codes: str = "ACME,PT"
    # masowy ZIP miesiąca: twardy limit liczby plików w archiwum
    archive_zip_max_files: int = Field(default=500, ge=1)
    # OCR skanów (Tesseract): strona bez warstwy tekstowej jest renderowana (pypdfium2)
    # i czytana przez tesseract. Brak binarki = OCR pomijany (dokument dostaje błąd „skan”).
    ocr_enabled: bool = True
    ocr_lang: str = "pol+eng"
    ocr_dpi: int = Field(default=220, ge=72, le=400)
    # lokalny LLM (Ollama) — dane NIE wychodzą poza własny serwer. Pusty URL = wyłączone.
    # Ostatnia warstwa OCR (jak w compare): model obrazowy, gdy Tesseract nie dał tekstu.
    # 4 GB RAM: qwen2.5vl:3b (~3.2 GB) na granicy — mierz na realnych skanach.
    # ARCH-004: cięcie/OCR/ekstrakcja faktur w pętli tła (upload → 202, front odpytuje);
    # false albo RUN_BACKGROUND_JOBS=false = w żądaniu HTTP jak dotąd
    invoice_ocr_in_background: bool = True
    ollama_url: str = ""
    # AI-006: domyślnie tylko adres wewnętrzny (usługa Dockera, localhost, IP prywatne);
    # true = świadoma zgoda na zdalną Ollamę (dane skanów opuszczają serwer)
    ollama_allow_remote: bool = False
    ollama_timeout: float = Field(default=300.0, gt=0)   # OCR vision; CPU: strona to minuty
    # audyt AI-002: ile wywołań LLM naraz (Ollama na CPU i tak liczy po kolei); asystent
    # czeka na slot llm_wait_s, potem 503 „zajęty”; OCR czeka do ollama_timeout
    llm_max_concurrency: int = Field(default=1, ge=1)
    llm_wait_s: float = Field(default=2.0, ge=0)
    llm_timeout_s: float = Field(default=120.0, gt=0)   # timeout asystenta
    assistant_rate_limit_per_minute: int = Field(default=10, ge=0)   # per użytkownik; 0 = off
    ocr_vision_model: str = "qwen2.5vl:3b"
    assistant_model: str = "qwen2.5:1.5b"   # asystent wiedzy: ~1.2 GB RAM
    # ML (scikit-learn): sugestie REF z historii zatwierdzeń + podobieństwa do master daty
    # oraz klasyfikator typu dokumentu. Modele trzymane na dysku (joblib) w ml_model_dir;
    # puste = katalog „ml” OBOK uploads_dir (np. /data/ml), nie w nim — AI-007.
    ml_model_dir: str = ""
    ml_auto_apply_threshold: float = Field(default=0.9, ge=0.5, le=1.0)  # pewna sugestia = matched
    ml_dockind_threshold: float = Field(default=0.8, ge=0.5, le=1.0)
    ml_min_examples: int = Field(default=20, ge=2)   # mniej = klasyfikator typu nie trenuje
    ml_auto_train: bool = True                        # dotrenuj po każdym zatwierdzeniu
    ml_train_in_background: bool = True               # False = synchronicznie (testy)
    uploads_dir: str = "./uploads"
    # /proc hosta zamontowany read-only (monitor: lista procesów całego serwera); brak = sam kontener
    host_proc_dir: str = "/host/proc"
    max_upload_mb: int = Field(default=25, ge=1)
    demurrage_alert_days: int = Field(default=3, ge=0)
    # puste `demurrage_free_days` nie może wyciszać tematu — liczymy wg tej wartości
    demurrage_default_free_days: int = Field(default=5, ge=0)
    # alert, gdy odprawa (ZLECONA/REWIZJA) trwa dłużej niż tyle dni od zlecenia
    customs_alert_days: int = Field(default=3, ge=0)
    # W11 #67: auto-szkic reklamacji, gdy kontener jest >= tyle dni po ETA bez dostawy
    complaint_auto_draft_days: int = Field(default=7, ge=1)
    # W11 #69: terminy przedawnienia (dni od utworzenia reklamacji) per typ adresata
    complaint_deadline_carrier_days: int = Field(default=14, ge=1)
    complaint_deadline_insurer_days: int = Field(default=60, ge=1)
    complaint_deadline_supplier_days: int = Field(default=30, ge=1)
    # alert tyle dni przed upływem terminu przedawnienia
    complaint_deadline_alert_days: int = Field(default=3, ge=0)
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "timporye@localhost"
    # osobny kanał SMTP tylko dla zaproszeń użytkowników (np. skrzynka example.com).
    # Puste = użyj głównego SMTP (Resend). Pozwala wysyłać zaproszenia z innego adresu
    # niż powiadomienia kierowców/spedycji.
    invite_smtp_host: str = ""
    invite_smtp_port: int = Field(default=587, ge=1, le=65535)
    invite_smtp_user: str = ""
    invite_smtp_password: str = ""
    invite_smtp_from: str = ""
    # --- Awizacja dwuetapowa (maile do spedycji) ---
    # graph = Microsoft Graph sendMail (M365, client credentials) / smtp / console (log).
    # Puste = smtp, gdy ustawiony SMTP_HOST, inaczej console (workflow działa bez M365).
    mail_backend: str = ""
    ms_tenant_id: str = ""
    ms_client_id: str = ""
    ms_client_secret: str = ""
    mail_sender: str = ""      # skrzynka nadawcy w M365 (ograniczona Application Access Policy)
    # --- SharePoint → sync kolejki (Graph app-only, Sites.Selected read); docs/SHAREPOINT-SYNC.md
    # Włączone tylko, gdy wszystkie pola (poza interwałem) niepuste — domyślnie nic się nie dzieje.
    sharepoint_tenant_id: str = ""
    sharepoint_client_id: str = ""
    sharepoint_client_secret: str = ""
    sharepoint_site: str = ""          # np. acme.sharepoint.com:/sites/Transport
    sharepoint_queue_path: str = ""    # np. Shared Documents/Kolejka/kolejka.xlsx
    sharepoint_queue_company: str = ""  # kod spółki (Company.code), do której idzie kolejka
    sharepoint_queue_interval_minutes: float = Field(default=15.0, ge=1)
    # okres przejściowy Excel ↔ aplikacja (decyzja 2026-09-28): synchronizacja z SharePoint tylko
    # ręcznie (przycisk w panelu); automat co N minut włącza się jawnie SHAREPOINT_AUTO_SYNC=true
    sharepoint_auto_sync: bool = False
    avizo_stage1_days: int = Field(default=7, ge=1)    # ważność linku etapu 1 (dostawy)
    avizo_stage2_days: int = Field(default=5, ge=1)    # ważność linku etapu 2 (kierowcy)
    driver_data_retention_days: int = Field(default=90, ge=1)  # RODO: po zamknięciu zlecenia
    audit_auth_retention_days: int = Field(default=90, ge=1)  # RODO: log logowań (IP, loginy)
    # OBS-011: przeczytane powiadomienia starsze niż N dni są kasowane (nieprzeczytane zostają)
    # 90 dni = decyzja z Aktualności (2026-10-01) — ta sama wartość w kodzie i w compose Coolify
    notification_retention_days: int = Field(default=90, ge=1)
    teams_webhook_url: str = ""
    # godzina porannego digestu logistyki (czas polski, Europe/Warsaw)
    digest_hour: int = Field(default=7, ge=0, le=23)

    # --- Automatyzacje (n8n) ---
    # Statyczny token serwisowy dla n8n: nagłówek X-Automation-Token zamiast logowania
    # hasłem i odświeżania JWT. PUSTY = integracja WYŁĄCZONA (żądanie z nagłówkiem jest
    # traktowane jak nieuwierzytelnione). Wygeneruj: python -c "import secrets;
    # print(secrets.token_urlsafe(32))" — w produkcji wymagane min. 32 znaki.
    automation_api_token: str = ""
    # ACL-005 (automation_policy.py): poprzedni token akceptowany w czasie rotacji (puste =
    # tylko bieżący); opcjonalny termin ważności RRRR-MM-DD; sieci CSV, z których wolno go użyć
    automation_api_token_previous: str = ""
    automation_token_expires: str = ""
    automation_allowed_cidrs: str = ""
    # Login konta, na które podpisują się zmiany z n8n (atrybucja w audycie). Uprawnienia
    # bierze z ROLI tego konta — n8n nie ma własnej, osobnej ścieżki autoryzacji.
    automation_actor_login: str = "n8n"
    # Webhook automatyzacji dla zdarzeń wychodzących (Production URL triggera w n8n).
    # Puste = wyłączone. Nazwa celowo NIE brzmi N8N_WEBHOOK_URL — tak nazywa się zmienna
    # w samym n8n i znaczy coś innego (jego publiczna baza adresów webhooków).
    automation_webhook_url: str = ""
    # Sekret podpisu HMAC-SHA256 ciała żądania (nagłówek X-Timporye-Signature).
    # Puste = bez podpisu (wtedy webhook n8n musi być chroniony inaczej, np. header auth).
    automation_webhook_secret: str = ""
    frontend_dist: str = ""  # ścieżka do builda panelu; puste = ../frontend/dist

    # alert „stęchły import" master data: starszy niż N dni (0 nie ma sensu — min. 1)
    stale_import_days: int = Field(default=14, ge=1)

    # --- Wywołania-DLT / Power BI (SAP BW) ---
    powerbi_provider: str = "off"          # off / mock / real
    powerbi_workspace_id: str = ""
    powerbi_dataset_stock: str = ""
    powerbi_table_stock: str = ""
    powerbi_dataset_vbba: str = ""
    powerbi_table_vbba: str = ""
    powerbi_dataset_orders: str = ""
    powerbi_table_orders: str = ""
    powerbi_dataset_usage: str = ""
    powerbi_table_usage: str = ""
    powerbi_merge_key: str = "produkt"     # wspólna kolumna łączenia źródeł
    vbba_open_statuses: str = "Nie rozpoczęte,Częściowo zakończone"
    # zlecenia sprzedaży (vbbe+likp): kolumny ilości potwierdzonej i niepotwierdzonej.
    # Niepotwierdzone wchodzą w projekcję stanu (jak w arkuszu W).
    powerbi_orders_confirmed_field: str = "potw"
    powerbi_orders_unconfirmed_field: str = "niestandardowe"
    powerbi_location_field: str = "miejsce_skladowania"
    powerbi_dlt_locations: str = ""        # wartości/prefiksy lokalizacji = DLT (reszta = magazyn)
    pallet_target_days: int = Field(default=14, ge=0)      # kalibracja: docelowy zapas w dniach
    pallet_urgent_threshold: float = Field(default=2.0)    # kalibracja: próg palet „pilne”
    powerbi_tenant_id: str = ""
    powerbi_client_id: str = ""
    powerbi_client_secret: str = ""
    powerbi_access_token: str = ""         # wklejony token (dev/ad-hoc)
    powerbi_ca_bundle: str = ""            # ścieżka CA bundle (proxy re-sygnujące TLS)
    powerbi_ssl_verify: bool = True        # False tylko dla dev
    powerbi_cache_ttl_min: int = Field(default=15, ge=0)
    dlt_email: str = ""                    # adresat wywołań palet
    dlt_call_emails: str = ""              # lista adresów DLT (CSV) — fallback gdy magazyn DLT bez e-maila
    powerbi_column_map: str = ""           # JSON {nasza_nazwa: nazwa_w_kostce} — remap kolumn
    pallet_alert_interval_hours: float = Field(default=12.0, gt=0)  # cykl alertów „pilne”
    pallet_forecast_horizon_days: int = Field(default=14, ge=1)  # horyzont prognozy zapotrzebowania
    # predykcja obsady rozładunków: ile palet rozładowuje jedna osoba na zmianę
    staffing_pallets_per_person: int = Field(default=40, ge=1)

    @property
    def vbba_open_statuses_set(self) -> set[str]:
        return {s.strip() for s in self.vbba_open_statuses.split(",") if s.strip()}

    @property
    def dlt_call_emails_list(self) -> list[str]:
        return [s.strip() for s in self.dlt_call_emails.split(",") if s.strip()]

    @property
    def powerbi_dlt_locations_set(self) -> set[str]:
        return {s.strip() for s in self.powerbi_dlt_locations.split(",") if s.strip()}

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_hosts_list(self) -> list[str]:
        return [h.strip() for h in self.allowed_hosts.split(",") if h.strip()]

    @property
    def upload_extensions(self) -> set[str]:
        return {e.strip().lower() for e in self.allowed_upload_extensions.split(",") if e.strip()}


settings = Settings()
