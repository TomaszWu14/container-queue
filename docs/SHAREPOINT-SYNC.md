# SharePoint → sync kolejki (automatyczny)

TIMPORYE co N minut pobiera plik kolejki z SharePointa (Microsoft Graph, tylko odczyt,
tylko ruch wychodzący) i przepuszcza go przez **ten sam** import co ręczny upload
„Synchronizacja kolejki” (`POST /api/import/queue-sync`, zapis, nie dry-run).
Plik jest importowany tylko, gdy zmienił się jego eTag — bez zmian nic się nie dzieje.

**Domyślnie wyłączone.** Bez kompletu zmiennych poniżej job nie startuje.

## 1. Prośba do IT (treść do wklejenia)

> Prosimy o App Registration w Entra ID dla aplikacji TIMPORYE (serwer wewnętrzny,
> tylko ruch wychodzący do `login.microsoftonline.com` i `graph.microsoft.com`):
>
> 1. Nowa rejestracja aplikacji, np. „TIMPORYE SharePoint read”, z client secret.
> 2. Uprawnienie Microsoft Graph typu **Application**: `Sites.Selected` + zgoda administratora
>    (admin consent). Samo `Sites.Selected` nie daje dostępu do żadnej witryny.
> 3. Nadanie tej aplikacji roli **read** na JEDNĄ witrynę: `https://acme.sharepoint.com/sites/Transport`
>    (podstawić właściwą), np. Graph Explorer / PowerShell kontem administratora:
>
>    ```
>    GET  https://graph.microsoft.com/v1.0/sites/acme.sharepoint.com:/sites/Transport   → "id"
>    POST https://graph.microsoft.com/v1.0/sites/{id}/permissions
>    {
>      "roles": ["read"],
>      "grantedToIdentities": [{ "application": { "id": "<CLIENT_ID>", "displayName": "TIMPORYE SharePoint read" } }]
>    }
>    ```
>    (PowerShell PnP: `Grant-PnPAzureADAppSitePermission -AppId <CLIENT_ID> -DisplayName "TIMPORYE SharePoint read" -Site https://acme.sharepoint.com/sites/Transport -Permissions Read`)
> 4. Przekazanie: Tenant ID, Client ID, Client secret (+ data wygaśnięcia sekretu).

## 2. Zmienne w Coolify

| Zmienna | Przykład |
|---|---|
| `SHAREPOINT_TENANT_ID` | GUID tenanta |
| `SHAREPOINT_CLIENT_ID` | GUID aplikacji |
| `SHAREPOINT_CLIENT_SECRET` | sekret (tylko w Coolify, nigdy w repo) |
| `SHAREPOINT_SITE` | `acme.sharepoint.com:/sites/Transport` |
| `SHAREPOINT_QUEUE_PATH` | `Shared Documents/Kolejka/kolejka.xlsx` (ścieżka w domyślnej bibliotece witryny) |
| `SHAREPOINT_QUEUE_COMPANY` | kod spółki, np. `BOREALIS` |
| `SHAREPOINT_QUEUE_INTERVAL_MINUTES` | `15` (domyślnie) |

Po ustawieniu: Redeploy. Job działa tylko na instancji z `RUN_BACKGROUND_JOBS=true`.
Filtr „importuj od” = ostatnia data ustawiona przy ręcznym imporcie dla tej spółki.

## 3. Jak sprawdzić

Panel admina → **Integracje** → „SharePoint (sync kolejki)”: status `on`, opis
`ok / unchanged / error`, czas ostatniego sprawdzenia i importu, liczba wierszy i zmian,
treść błędu. Typowe błędy: `Graph HTTP 403` (IT nie nadało `read` na witrynę),
`Graph HTTP 404` (zła `SHAREPOINT_SITE` / `SHAREPOINT_QUEUE_PATH`), `brak tokenu`
(zły tenant/client/secret albo wygasły sekret), `błąd sieci` (egress/proxy).

## Kolejny krok: master data

`app/sharepoint.py::fetch_file(path, etag)` pobiera dowolny plik z witryny — słowniki
(EKKO, MARM, LFA1, porty, stany DLT) można podpiąć tym samym wzorcem: nowa zmienna ze
ścieżką + job wołający istniejący parser z `importers/master_data.py`. Nie wdrożone.
