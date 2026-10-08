# n8n na tej samej domenie co TIMPORYE (jedna domena, kilka aplikacji)

Założenie: na serwerze ma być **jedna publicznie widoczna aplikacja i jedna domena**,
a mimo to chcemy obok panelu prowadzić niezależnego n8n do automatyzacji — także takich,
które z TIMPORYE nie mają nic wspólnego.

Rozwiązanie: przed panelem staje **brama HTTP** (nginx), która na jednym hoście i jednym
porcie 443 rozdziela ruch po ścieżce. n8n żyje w **osobnym stacku Dockera**
(`docker-compose.n8n.yml`, własna baza, własny cykl życia — restart n8n nie rusza panelu).

```
                      ┌─────────── brama (nginx, trzyma domenę) ───────────┐
  https://domena.pl/  │  /              → app   (panel TIMPORYE, :8000)    │
                      │  /n8n/webhook/… → n8n   (osobny stack, :5678)      │
                      │  /n8n/form/…    → n8n                              │
                      └────────────────────────────────────────────────────┘
        edytor n8n: tunel SSH → http://localhost:5678  (z internetu niewidoczny)
        n8n → API panelu: http://gateway/api/…         (sieć timporye-apps)
```

Na zewnątrz widać **jeden host, jeden port i jedną aplikację**. Adresy webhooków wyglądają
jak część panelu (`https://domena.pl/n8n/webhook/...`), a edytor n8n nie ma publicznego
adresu ani otwartego portu — otwierasz go tunelem SSH ze swojego laptopa.

## Dlaczego tak, a nie „n8n pod /n8n/ w całości"

Kuszące `N8N_PATH=/n8n/` jest dziś zepsute po stronie n8n: część endpointów ignoruje
`basePath`, psuje się redirect po logowaniu, a formularze Human-in-the-Loop nie przechodzą
weryfikacji podpisu — [n8n-io/n8n#19635](https://github.com/n8n-io/n8n/issues/19635),
[#18596](https://github.com/n8n-io/n8n/issues/18596). Druga popularna droga (proxy
**wycina** prefiks, n8n stoi w roocie) przewraca się na absolutnych adresach assetów:
n8n prosi o `/assets/...`, a pod tym adresem siedzi już panel.

Dlatego nie przepisujemy ścieżek w ogóle. Zamiast tego n8n sam serwuje swoje endpointy
pod prefiksem `/n8n/` — pozwalają na to zmienne `N8N_ENDPOINT_WEBHOOK`, `N8N_ENDPOINT_FORM`
itd. (zwykłe segmenty ścieżki, ustawione w `docker-compose.n8n.yml` na `n8n/webhook`,
`n8n/form`, …). Adres widziany przez klienta i przez n8n jest **identyczny**, więc podpisy
formularzy się zgadzają, a brama jest zwykłym pass-through.

Ceną jest brak edytora pod publiczną domeną — i dobrze, bo właśnie to chcemy ukryć.

## 1. Wdrożenie

### 1a. Przygotowanie serwera (raz)

Wszystko, czego nie da się kliknąć w Coolify, robi jeden skrypt — uruchom go **na
serwerze** (zasób panelu → **Terminal** w Coolify, albo przez SSH):

```bash
./deploy/setup-n8n.sh kolejka.twojafirma.pl
```

Tworzy sieć współdzieloną `timporye-apps` (łączy niezależne stacki: brama widzi n8n,
a n8n widzi API panelu — bez niej brama wstanie, ale `/n8n/...` da 502) i wypisuje
**gotowe do wklejenia** bloki zmiennych dla obu zasobów. Uruchomienie ponownie jest
bezpieczne: sieci nie tworzy dwa razy, ale sekrety generuje nowe — nie nadpisuj nimi
działającej konfiguracji.

Resztę (punkty 1b i 1c) klikasz w Coolify, wklejając to, co wypisał skrypt.

### 1b. Stack n8n (nowy zasób w Coolify)

**+ New Resource → Docker Compose**, plik `docker-compose.n8n.yml`, **bez domeny**.
Zmienne środowiskowe:

| Zmienna | Wartość |
|---|---|
| `N8N_DB_PASSWORD` | silne hasło do bazy n8n (skrypt z 1a je generuje) |
| `N8N_ENCRYPTION_KEY` | klucz szyfrujący credentiale — przy migracji **przepisz stary 1:1** (patrz 3) |
| `N8N_PUBLIC_BASE_URL` | `https://domena.pl/` — z tego n8n buduje adresy webhooków (dokleja `n8n/webhook/...`) |
| `N8N_IMAGE` | *(opcjonalnie)* inna wersja obrazu niż przypięta w compose |
| `TZ` | *(opcjonalnie)* domyślnie `Europe/Warsaw` |

### 1c. Brama w stacku panelu

W zasobie panelu (`docker-compose.coolify.yml`) ustaw zmienne:

| Zmienna | Wartość |
|---|---|
| `COMPOSE_PROFILES` | `gateway` — bez tego brama się nie uruchamia i nic się nie zmienia |
| `TRUSTED_PROXY_COUNT` | `2` — przed aplikacją stoją teraz Traefik Coolify **i** brama; bez tego limity logowania liczyłyby IP bramy, nie klienta |
| `ALLOWED_HOSTS` | jeśli używasz — dopisz `gateway` (n8n woła API po `http://gateway/api/...`, filtr Hosta odrzuciłby to z 400) |

Potem **przenieś domenę** z serwisu `app` na `gateway` (port kontenera **80**) i wdróż.
Konfiguracja tras: `deploy/gateway/timporye.conf`.

### 1d. Sprawdzenie (3 minuty)

```bash
curl -s https://domena.pl/gateway-health          # → ok                  (brama żyje)
curl -s https://domena.pl/api/health              # → {"status":"ok"...}  (panel przez bramę)
curl -s -o /dev/null -w '%{http_code}\n' https://domena.pl/n8n/webhook/test   # → 404 od n8n
```

Ostatnie 404 jest dobrym znakiem: odpowiada n8n (nie zna workflow o tej ścieżce). Gdy
zobaczysz HTML panelu albo 502 — trasa nie dochodzi do n8n (sprawdź sieć z punktu 1a).

Zmiany w trasach warto najpierw przepuścić przez `nginx -t`:

```bash
docker run --rm -v "$PWD/deploy/gateway/timporye.conf:/etc/nginx/conf.d/default.conf:ro" \
  nginx:1.27-alpine nginx -t
```

### 1e. Edytor n8n przez tunel SSH

Port 5678 jest publikowany **tylko na loopback serwera**, więc z internetu nie istnieje:

```bash
ssh -L 5678:127.0.0.1:5678 user@serwer      # i otwórz http://localhost:5678
```

Pierwsze wejście zakłada konto właściciela n8n (n8n ma własnych użytkowników — to **nie**
są konta z panelu TIMPORYE). Włącz tam 2FA.

### 1f. Serwer bez domeny (IP:port, np. `http://192.0.2.10:81`)

Brama rozdziela ruch po **ścieżce**, nie po nazwie hosta — więc domena nie jest potrzebna.
Zamiast niej jest adres IP serwera w sieci wewnętrznej, a panel zostaje pod tym samym adresem:

```
http://192.0.2.10:81/          → panel TIMPORYE   (jak dotąd)
http://192.0.2.10:81/n8n/...   → webhooki n8n
edytor n8n                        → tunel SSH (1e)
```

Różnice względem kroków 1a–1d:

1. `./deploy/setup-n8n.sh 192.0.2.10:81` — dla adresu IP skrypt sam wypisze `http://`
   i jeden hop proxy.
2. Port hosta **81 przenieś z serwisu `app` na `gateway`** (port kontenera **80**), zamiast
   przenosić domenę. Ruch wchodzi prosto na bramę, z pominięciem Traefika — dlatego:

   | Zasób | Zmienna | Wartość |
   |---|---|---|
   | n8n | `N8N_PUBLIC_BASE_URL` | `http://192.0.2.10:81/` |
   | n8n | `N8N_PROXY_HOPS` | `1` (domyślne `2` zakłada Traefik + bramę) |
   | panel | `TRUSTED_PROXY_COUNT` | `1` |
   | panel | `ALLOWED_HOSTS` | `192.0.2.10,gateway` (port nie ma znaczenia — filtr go obcina) |
   | panel | `PUBLIC_BASE_URL` | `http://192.0.2.10:81` |
   | panel | `SECURE_COOKIES` | `false` — bez HTTPS przeglądarka nie odeśle ciasteczka `Secure` |

3. Sprawdzenie jak w 1d, tylko `http://192.0.2.10:81/...`.

Ograniczenia tego wariantu:

- **Bez HTTPS** hasła idą po sieci otwartym tekstem — wariant tylko przejściowy. Po dodaniu
  wewnętrznej nazwy DNS i certyfikatu wracasz do wariantu z domeną (`SECURE_COOKIES=true`).
- **Webhooki spoza sieci wewnętrznej nie dojdą** (usługi chmurowe nie widzą adresu `10.x`).
  Wewnątrz sieci działa wszystko, a n8n sam wychodzi do internetu — o ile przepuści go
  firewall wyjściowy.

## 2. Kolejna aplikacja pod tą samą domeną

Wzór jest w `deploy/gateway/timporye.conf` (zakomentowany blok na końcu). Jeden warunek:
aplikacja musi umieć serwować się pod tym samym prefiksem, pod jakim ją wystawiasz —
albo przez własną konfigurację ścieżek (jak `N8N_ENDPOINT_*`), albo przez ustawienie
„base path/base URL". Aplikacja, która umie tylko root, wymagałaby wycinania prefiksu,
a to wywraca jej absolutne adresy assetów — wtedy lepiej trzymać ją bez publicznego
adresu i sięgać po nią tunelem.

## 3. Migracja istniejącej instancji n8n

Klucz szyfrujący decyduje o dostępie do zapisanych credentiali. Jeśli nie ustawiałeś go
ręcznie, n8n wygenerował go sam — odczytaj w terminalu starego kontenera:

```bash
cat /home/node/.n8n/config      # pole encryptionKey
```

Ten sam klucz ustaw jako `N8N_ENCRYPTION_KEY` w nowym stacku, a potem przenieś workflow
(`n8n export:workflow --help` pokaże aktualne flagi):

```bash
# stara instancja
n8n export:workflow --all --output=/home/node/.n8n/workflows.json
n8n export:credentials --all --output=/home/node/.n8n/credentials.json
# nowa instancja (pliki skopiuj przez wolumen/scp)
n8n import:workflow --input=/home/node/.n8n/workflows.json
n8n import:credentials --input=/home/node/.n8n/credentials.json
```

**Adresy webhooków się zmienią** — z `https://stara-domena/webhook/<id>` na
`https://domena.pl/n8n/webhook/<id>`. Zaktualizuj je w systemach, które te webhooki wołają,
i dopiero potem wyłącz starą instancję (zostaw ją zatrzymaną, nie usuwaj, aż potwierdzisz).

## 4. n8n → TIMPORYE: token serwisowy

Token mapuje się na **konto użytkownika**, więc obowiązują te same role i izolacja per
zasób co dla ludzi (`deps.py`) — n8n nie ma własnej ścieżki autoryzacji.

1. W panelu (jako admin) założ konto, np. login `n8n`, rola **logistics** (`warehouse`/
   `customs` = węższy zakres). Hasło ustaw losowe i nigdzie nie używaj — n8n chodzi tokenem.
   Rola **admin jest odrzucana** (token → 403), a logowanie hasłem na to konto jest
   zablokowane, gdy `AUTOMATION_API_TOKEN` jest ustawiony (ACL-005). `view_all_companies`
   jest dozwolone (importy SAP całej grupy), ale poszerza skutki wycieku tokenu — włączaj
   tylko, gdy workflow tego potrzebuje.
2. Wygeneruj token i ustaw w zmiennych panelu:

   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

   | Zmienna | Znaczenie |
   |---|---|
   | `AUTOMATION_API_TOKEN` | token; **puste = kanał wyłączony**, w produkcji min. 32 znaki (inaczej aplikacja nie wystartuje) |
   | `AUTOMATION_ACTOR_LOGIN` | login konta serwisowego (domyślnie `n8n`) |

3. W n8n: **Credentials → Header Auth**, nagłówek `X-Automation-Token`, wartość = token.
   Podpinaj w node **HTTP Request**:

   ```
   GET  http://gateway/api/containers?status=W_DRODZE
   POST http://gateway/api/containers/123/avizo
   ```

   `http://gateway` to adres wewnętrzny w sieci `timporye-apps` — ruch nie wychodzi do
   internetu. Publiczne `https://domena.pl/api/...` też działa, tylko przechodzi przez
   proxy i liczy się do limitu żądań.

Uwagi:

- limit `API_RATE_LIMIT_PER_MINUTE` (domyślnie 300/min na IP) obejmuje też n8n; ruch
  z workflow trafia do koszyka IP bramy, więc pętla po kontenerach potrafi go dobić —
  dodaj opóźnienie w workflow,
- każda zmiana z n8n jest w audycie podpisana kontem serwisowym, więc widać, co zrobił
  człowiek, a co automat,
- wyłączenie konta serwisowego w panelu (`is_active = false`) odcina automatyzacje
  natychmiast (403) — najszybszy „kill switch" bez redeployu,
- opcjonalnie `AUTOMATION_ALLOWED_CIDRS` (np. sieć Dockera, w której stoi n8n) — token
  użyty z innej sieci dostaje 403, oraz `AUTOMATION_TOKEN_EXPIRES=RRRR-MM-DD` — po tej
  dacie token przestaje działać (401), co wymusza rotację.

**Rotacja tokenu bez przestoju (ACL-005):**

1. Wygeneruj nowy token (polecenie wyżej).
2. W zmiennych panelu: dotychczasowy token przenieś do `AUTOMATION_API_TOKEN_PREVIOUS`,
   nowy wpisz do `AUTOMATION_API_TOKEN` (i ewentualnie nowy `AUTOMATION_TOKEN_EXPIRES`);
   redeploy — od teraz działają oba.
3. W n8n podmień wartość credentiala **Header Auth** na nowy token i sprawdź workflow.
4. Wyczyść `AUTOMATION_API_TOKEN_PREVIOUS` i zrób redeploy — stary token przestaje działać.

Nowe zmienne `AUTOMATION_*` muszą być przekazane do kontenera `app` (lista `environment`
w `docker-compose.coolify.yml`), inaczej aplikacja ich nie zobaczy.

## 5. TIMPORYE → n8n: webhook zdarzeń

Każde powiadomienie (demurrage, odprawy, dokumenty, tracking, digest) leci też do n8n jako
trigger. W zmiennych panelu:

| Zmienna | Znaczenie |
|---|---|
| `AUTOMATION_WEBHOOK_URL` | adres triggera, wewnętrznie `http://gateway/n8n/webhook/<id>`; puste = kanał wyłączony |
| `AUTOMATION_WEBHOOK_SECRET` | sekret podpisu HMAC-SHA256 (zalecany; brak = tylko ostrzeżenie w logu przy starcie) |

To **nie** ta sama zmienna co `N8N_WEBHOOK_URL` w stacku n8n (tam: publiczna baza adresów,
tu: konkretny trigger) — dlatego nasza nosi przedrostek `AUTOMATION_`.

Ciało żądania:

```json
{
  "event": "demurrage",
  "title": "Kontener MSDU0806613 — zbliża się demurrage",
  "body": "...",
  "sent_at": "2026-09-18T06:00:00+00:00",
  "container_id": 123,
  "recipients": 4
}
```

Nagłówek `X-Timporye-Signature: sha256=<hex>` to HMAC-SHA256 **dokładnie tych bajtów**,
które są w ciele. Weryfikacja w n8n: w node Webhook włącz surowe ciało (*Raw Body*) i
porównaj podpis w node Code — po deserializacji i ponownym złożeniu JSON-a podpis się
nie zgodzi:

```js
const crypto = require('crypto');
const secret = 'TEN_SAM_SEKRET_CO_AUTOMATION_WEBHOOK_SECRET';
const raw = $input.first().binary.data.data;                 // surowe ciało (base64)
const body = Buffer.from(raw, 'base64');
const expected = Buffer.from('sha256=' + crypto.createHmac('sha256', secret).update(body).digest('hex'));
const got = Buffer.from($input.first().json.headers['x-timporye-signature'] || '');
// porównanie długości przed timingSafeEqual — na różnych długościach ono rzuca RangeError
if (got.length !== expected.length || !crypto.timingSafeEqual(expected, got)) {
  throw new Error('Zły podpis — żądanie nie pochodzi z TIMPORYE');
}
return [{ json: JSON.parse(body.toString('utf8')) }];
```

Nie chcesz surowego ciała? Zabezpiecz webhook credentialem *Header Auth* po stronie n8n
i traktuj podpis jako drugą warstwę.

Kanał jest **best-effort**: wysyłka idzie w tle (pula `notify`), a padnięty n8n tylko
loguje błąd — nie wywraca operacji w panelu.

## 6. Backup

`backend/scripts/backup.sh` zgrywa **tylko** bazę panelu. Baza n8n (workflow, credentiale,
historia wykonań) to osobny kontener — dodaj jej własne **Scheduled Task** w zasobie n8n:

```bash
PGPASSWORD="$N8N_DB_PASSWORD" pg_dump -h n8n-db -U n8n n8n \
  | gzip > /home/node/.n8n/backup-$(date +%F).sql.gz
```

Dane żyją na wolumenach `n8ndata`/`n8nfiles`, więc redeploy jest bezpieczny, ale utrata
wolumenu bez kopii = utrata wszystkich workflow.

## 6a. Gotowe workflow (`deploy/n8n/`)

Import: edytor n8n → **Workflows → Import from File** → plik z `deploy/n8n/`. Po imporcie
podepnij credentiale (ikona ostrzeżenia na node) i uzupełnij adresy e-mail.

### Kontrola danych — `kontrola-danych.json`

Pn–pt o 7:00 zbiera kontenery **bez PO**, **bez ETA** (tylko w transporcie / porcie /
odprawie / awizowane — wcześniej ETA bywa nieznane), **bez magazynu** i z **brakującymi
dokumentami przed ETA**, i wysyła jeden mail z linkami do kart kontenerów. Gdy braków nie
ma, maila nie ma.

Źródła: `GET /api/master-data/quality` (reguły `containers_no_po`, `containers_no_eta`,
`containers_no_warehouse` — te same widać w panelu: Master data → Jakość danych) oraz
`GET /api/customs/docs-gaps`. Konto serwisowe potrzebuje roli **logistics** (albo admin).

Do ustawienia po imporcie:

| Node | Co |
|---|---|
| Jakość danych, Braki dokumentów | credential *Header Auth* `TIMPORYE token` (sekcja 4) |
| Złóż raport | stała `PANEL` — adres panelu do linków (domyślnie `http://192.0.2.10:81`) |
| Wyślij maila | credential SMTP (ten sam serwer co `SMTP_HOST` panelu), `fromEmail`, `toEmail` |

Na liście jest do 50 pozycji na regułę (licznik w nagłówku jest pełny).

## 7. Bezpieczeństwo

- Konto serwisowe dostaje **najwęższą rolę**, która wystarcza — nie `admin`.
- Token nie wygasa: rotuj przy zmianach w zespole, trzymaj tylko w zmiennych Coolify
  i w credentialu n8n (nigdy w repo ani w treści workflow).
- Edytor n8n nie ma publicznego adresu — to najtańsza ochrona tej powierzchni. Jeśli
  kiedyś go wystawisz, włącz w n8n 2FA i rozważ ograniczenie po IP na bramie.
- Panel wysyła `X-Frame-Options: DENY` i CSP `frame-ancestors 'none'` (panelu nie wklejisz
  w iframe), a `default-src 'self'` blokuje iframe w drugą stronę. Ponieważ n8n jest teraz
  na **tym samym origin**, zakładka „Automatyzacje" z iframe byłaby technicznie możliwa
  po świadomym dopuszczeniu edytora na bramie — dziś celowo tego nie robimy.

## 8. Czego tu nie ma

- **Edytora n8n pod publiczną domeną** — blokują to błędy podścieżki w n8n (sekcja na
  początku). Gdy zostaną naprawione, wystarczy dodać trasę w bramie i `N8N_PATH`.
- **Selektywnych zdarzeń** — do n8n leci każde powiadomienie; filtrowanie po polu `event`
  robisz w workflow (node Switch/IF).
- **Wspólnego logowania** (SSO panel ↔ n8n) — n8n ma własnych użytkowników.

---

## Wariant B: własny host (sieć wewnętrzna) — `docker-compose.n8n-host.yml`

Prostszy setup, gdy IT może dać **drugą wewnętrzną nazwę DNS** (np. `n8n.acme.local`)
wskazującą na ten sam serwer. n8n dostaje własną domenę, a Traefik Coolify terminuje na
niej HTTPS — dokładnie jak panel. **Bez** bramy nginx, bez prefiksu `/n8n/`, bez tunelu SSH
i bez współdzielonej sieci `timporye-apps`.

Kiedy wybrać:
- **Wariant A** (`docker-compose.n8n.yml`) — gdy ma być **jedna publiczna domena** i n8n
  ukryty pod `/n8n/` + edytor tylko przez tunel SSH.
- **Wariant B** (ten) — sieć wewnętrzna/firmowa, druga nazwa DNS jest tania, chcesz
  najprościej: edytor i webhooki pod własnym hostem `https://n8n.../`.

### Kroki
1. IT: rekord DNS `n8n.twojafirma.pl` → IP serwera (w sieci wewnętrznej). Cert: jak dla
   panelu (wewnętrzne CA lub self-signed przez Coolify).
2. Coolify: **+ New Resource → Docker Compose**, plik `docker-compose.n8n-host.yml`.
   Na usłudze **`n8n`** ustaw domenę `https://n8n.twojafirma.pl`, **port 5678**.
3. Environment Variables (wygeneruj sekrety, np. `python -c "import secrets;
   print(secrets.token_urlsafe(24)); print(secrets.token_hex(24))"`):

   | Zmienna | Wartość |
   |---|---|
   | `N8N_DB_PASSWORD` | silne hasło do bazy n8n |
   | `N8N_ENCRYPTION_KEY` | klucz szyfrujący credentiale (min. 24 bajty; przy migracji przepisz 1:1) |
   | `N8N_HOST` | `n8n.twojafirma.pl` |
   | `N8N_PUBLIC_BASE_URL` | `https://n8n.twojafirma.pl/` (z ukośnikiem) |

4. **Deploy**. Edytor: `https://n8n.twojafirma.pl` (zaakceptuj cert, jeśli self-signed).
   Webhooki: `https://n8n.twojafirma.pl/webhook/...` (domyślne ścieżki n8n).

### Integracja z panelem TIMPORYE (opcjonalna)
n8n woła API panelu po jego domenie z tokenem serwisowym — bez współdzielonej sieci:
- w panelu (TIMPORYE) ustaw `AUTOMATION_API_TOKEN` (min. 32 znaki) i (opcjonalnie)
  `AUTOMATION_WEBHOOK_URL=https://n8n.twojafirma.pl/webhook/<id>` + `AUTOMATION_WEBHOOK_SECRET`,
- w n8n: HTTP Request → `https://kolejka.twojafirma.pl/api/...`, nagłówek z tokenem.

### Zasoby
Serwer 4 vCPU / 4 GB: app + Postgres + n8n + baza n8n to ciasno — ustaw **swap 2–4 GB**. Lokalna Ollama do AI = rozważ dobicie RAM.
