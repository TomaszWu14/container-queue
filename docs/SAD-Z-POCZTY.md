# Draft SAD z poczty → TIMPORYE (Outlook + n8n na komputerze 24/7)

Agencja celna (Delta Brokers) przysyła draft SAD mailem: najpierw **PDF**, później **XML** z WinSAD.
Ten obieg sam zapisuje załączniki na dysk i wgrywa je do TIMPORYE — PDF zakłada wersję draftu przy
paczce faktur kontenera i od razu porównuje ją z fakturami, XML dołącza do tej wersji i zastępuje
odczyt z PDF. **Bez IT**: poczta czytana z Twojego zalogowanego Outlooka, n8n stoi na Twoim komputerze.

```
 Outlook (Twoje konto M365)                     komputer 24/7 (Windows)
   │  co 5 min: Zbierz-SAD.ps1 (Harmonogram zadań)
   ▼
 D:\SAD\przychodzace ──► n8n  http://localhost:5678/webhook/sad-inbox   (tylko ten komputer)
   │  (kopia zawsze na dysku)     │ token X-Automation-Token
   ▼                              ▼
 D:\SAD\wyslane / bledy     TIMPORYE  http://192.0.2.10:81/api/sad-drafts/inbox  
                                  │ kontener odczytany z pliku → najnowsza paczka faktur
                                  ▼
                            Agencja → Draft SAD vN („automat”), porównanie z fakturami
```

Pliki: `tools/outlook-sad/` (skrypty PowerShell), `deploy/n8n/sad-z-poczty.json` (workflow),
endpoint `backend/app/invoices/sad_inbox.py`.

---

## 0. Sprawdzenie dostępów (na komputerze 24/7, ~10 min)

Otwórz **PowerShell** (zwykły, nie „jako administrator”) i przejdź listę. Każdy punkt ma
oczekiwany wynik — przy innym zobacz kolumnę „co zrobić”.

| # | Sprawdzenie | Polecenie | Oczekiwane | Co zrobić, gdy inaczej |
|---|---|---|---|---|
| 1 | Klasyczny Outlook (nie „Nowy Outlook”) | Outlook → prawy górny róg przełącznik **Nowy Outlook** | wyłączony | „Nowy Outlook” nie ma interfejsu COM — przełącz na klasyczny |
| 2 | Skrypty PowerShell dozwolone | `Get-ExecutionPolicy -List` | `MachinePolicy` = `Undefined` | `AllSigned`/`Restricted` z GPO blokuje skrypty — wtedy pomoże tylko IT (albo wersja w Pythonie z PyCharma — daj znać) |
| 3 | curl w systemie | `curl.exe --version` | wersja 7.x/8.x | Windows 10 1803+ ma go wbudowanego; starszy system → aktualizacja |
| 4 | Sieć do TIMPORYE | `curl.exe http://192.0.2.10:81/api/health` | `{"status":"ok"…}` | komputer poza sieci wewnętrznej / VPN — n8n nie dojdzie do aplikacji |
| 5 | Node.js ≥ 20 | `node --version` | `v22.x` (albo `v20.x`) | zainstaluj **Node.js 22 LTS** z nodejs.org; bez praw admina: wersja `.zip` rozpakowana do `%LOCALAPPDATA%\node` + dopisana do PATH użytkownika |
| 6 | npm przez proxy firmowe | `npm view n8n@2.40.2 version` | `2.40.2` | błąd sieci → `npm config set proxy http://<proxy>:<port>` (adres proxy z ustawień przeglądarki) |
| 7 | Komputer nie usypia | Ustawienia → System → Zasilanie | „Uśpij: nigdy” (podłączony) | ustaw „nigdy”; blokada ekranu (Win+L) jest OK, wylogowanie — nie |
| 8 | Outlook startuje po restarcie | `Win+R` → `shell:startup` | skrót do Outlooka | wrzuć skrót Outlooka do tego folderu |
| 9 | Adres agencji | nagłówek maila z draftem SAD | nadawca `…@brokers.com` | inna domena → podaj ją w `-Senders` (punkt 3) |

Po aktualizacjach Windows komputer bywa restartowany — **zaloguj się ponownie** (Outlook, n8n i
zadanie startują przy logowaniu; bez zalogowania Outlook jest niedostępny).

---

## 1. TIMPORYE: konto i token automatu (raz, admin)

1. Panel → Administracja → Użytkownicy: konto **`n8n`**, rola **logistics**, hasło losowe (nieużywane).
2. Token (PowerShell):
   ```powershell
   $b = New-Object byte[] 32; [Security.Cryptography.RNGCryptoServiceProvider]::new().GetBytes($b); [Convert]::ToBase64String($b)
   ```
3. Coolify → zasób panelu → **Environment**: `AUTOMATION_API_TOKEN=<token>`,
   `AUTOMATION_ACTOR_LOGIN=n8n` → **Redeploy**. Szczegóły i zabezpieczenia tokenu: `docs/N8N.md` §4.

## 2. n8n na komputerze 24/7

1. Z katalogu repo (`tools/outlook-sad`):
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\Zainstaluj-n8n.ps1
   ```
   Instaluje n8n 2.40.2 (ta sama wersja co `docker-compose.n8n.yml`) i uruchamia go przy każdym
   logowaniu, **tylko na `localhost`** — z sieci nikt się do niego nie dostanie.
2. Otwórz **http://localhost:5678**, załóż konto właściciela n8n (to nie jest konto TIMPORYE).
3. **Credentials → Add → Header Auth** (dwa):
   - `TIMPORYE token` — Name `X-Automation-Token`, Value = token z kroku 1.2,
   - `SAD webhook (X-SAD-Secret)` — Name `X-SAD-Secret`, Value = nowy losowy sekret (to samo polecenie co 1.2).
4. **Workflows → Import from File** → `deploy/n8n/sad-z-poczty.json`. W obu węzłach wybierz
   credentiale z listy (import ich nie niesie), zapisz i przełącz **Active**.

## 3. Skrypt Outlooka

1. Pierwszy test — tylko zapis, bez wysyłki (ostatnie 3 dni skrzynki):
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\Zbierz-SAD.ps1 -OnlySave
   ```
   W `D:\SAD\przychodzace` pojawią się `…__SAD7100005.pdf` itp., a maile dostaną kategorię
   **TIMPORYE SAD** (drugi raz nie będą brane). Inny dysk/folder: `-Folder 'C:\SAD'`;
   inna domena agencji: `-Senders '@brokers.com','@delta.com'`.
2. Test łącza (wysyła to, co w `przychodzace`):
   ```powershell
   $env:SAD_WEBHOOK_SECRET = '<sekret z 2.3>'; powershell -ExecutionPolicy Bypass -File .\Zbierz-SAD.ps1 -OnlySend
   ```
3. Harmonogram co 5 minut (zapamiętuje sekret w Twojej zmiennej środowiskowej, nie w pliku):
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\Zarejestruj-Zadanie.ps1 -Secret '<sekret z 2.3>'
   ```
   Z innym folderem: dodaj `-Folder 'C:\SAD'` (ten sam co w punkcie 1).

Jeśli Outlook pokaże okno „Program próbuje uzyskać dostęp do adresów e-mail” — Outlook nie widzi
aktualnego antywirusa (Plik → Opcje → Centrum zaufania → Dostęp programowy). Zgłoś to; bez tego
okno będzie wstrzymywać skrypt.

---

## 4. Na co dzień

Log: **`D:\SAD\sad.log`** — jedna linia na plik:

| Wpis | Znaczenie | Plik |
|---|---|---|
| `OK 201 …` | nowa wersja draftu albo dołączony XML; w treści numer kontenera, wersja i podsumowanie porównania | `wyslane\RRRR-MM\` |
| `OK 200 …` | ten sam plik był już wgrany (ponowienie) — bez zmian | `wyslane\` |
| `CZEKA 409 …` | brak paczki faktur dla kontenera **albo** XML przyszedł przed PDF — ponawia co 5 min, po 3 dniach → `bledy\` | zostaje |
| `BŁĄD 422 …` | to nie draft SAD / nie odczytano numeru kontenera — wgraj ręcznie przy paczce faktur | `bledy\` |
| `SEKRET/TOKEN 401/403` | zły sekret webhooka albo token n8n → TIMPORYE — popraw konfigurację | zostaje |
| `PONÓW (000/5xx)` | n8n albo serwer niedostępne — wyśle, gdy wrócą | zostaje |

W TIMPORYE wersja z automatu ma źródło **„automat”**; decyzja „akceptuję / do poprawy” zostaje po
Twojej stronie. Historia kontenera: „Draft SAD” i „Draft SAD — XML” z nazwą pliku.

## 5. Bezpieczeństwo

- n8n słucha tylko na `127.0.0.1`; webhook wymaga nagłówka `X-SAD-Secret`.
- Token TIMPORYE siedzi w n8n (zaszyfrowany kluczem z `%USERPROFILE%\.n8n`); konto `n8n` ma rolę
  logistics (admin jest odrzucany) — te same reguły dostępu co dla ludzi.
- Drafty SAD zawierają dane osobowe agenta celnego — `D:\SAD` trzymaj na tym komputerze, nie w
  folderze synchronizowanym publicznie; starsze miesiące z `wyslane\` można usuwać.
- Wyłączenie: `Unregister-ScheduledTask -TaskName 'TIMPORYE SAD z poczty'` (i `'TIMPORYE n8n'`).

> Pozostałe dokumenty z poczty (B/L, faktury, CMR…) → poczekalnia: [POCZTA-DO-POCZEKALNI.md](POCZTA-DO-POCZEKALNI.md).
