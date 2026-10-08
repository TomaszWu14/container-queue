<#
.SYNOPSIS
  Drafty SAD z Outlooka → folder na dysku → n8n → TIMPORYE. Opis: docs/SAD-Z-POCZTY.md.

.DESCRIPTION
  Uruchamiany co 5 minut z Harmonogramu zadań na komputerze 24/7 (Windows + Microsoft 365).
  1. Czyta Skrzynkę odbiorczą zalogowanego Outlooka (Twoje uprawnienia — bez IT, bez Graph/IMAP).
  2. Z maili od agencji (nadawca pasuje do -Senders) zapisuje załączniki SAD*.pdf / SAD*.xml
     do <Folder>\przychodzace i oznacza mail kategorią -Category (drugi raz go nie bierze).
  3. Każdy plik z przychodzace wysyła do webhooka n8n (lokalny, http://localhost:5678). Wynik:
       2xx → wyslane\RRRR-MM\          (TIMPORYE przyjęło: nowa wersja draftu albo dołączony XML)
       409 → zostaje, ponowienie za 5 min (brak paczki faktur / XML przed PDF); po -RetryDays → bledy
       401/403 → zostaje (zły sekret webhooka albo token n8n→TIMPORYE — do poprawienia w konfiguracji)
       inne 4xx → bledy\ (plik nie do przyjęcia — sprawdź ręcznie, powód w sad.log)
       5xx / brak połączenia → zostaje, ponowienie za 5 min
  Plik jest zawsze na dysku — nic nie ginie, gdy serwer albo sieć leżą.
#>
param(
  [string]$Folder = 'D:\SAD',
  [string]$Url = 'http://localhost:5678/webhook/sad-inbox',
  [string]$Secret = $env:SAD_WEBHOOK_SECRET,
  [string[]]$Senders = @('@brokers.com'),
  [string]$NamePattern = '^SAD.*\.(pdf|xml)$',
  [int]$Days = 3,
  [int]$RetryDays = 3,
  [string]$Category = 'TIMPORYE SAD',
  [switch]$OnlySave,         # tylko zapis z Outlooka, bez wysyłki (pierwszy test)
  [switch]$OnlySend          # tylko wysyłka plików z przychodzace, bez Outlooka (test łącza)
)
$ErrorActionPreference = 'Stop'
$inbox = Join-Path $Folder 'przychodzace'
$sent = Join-Path $Folder ('wyslane\' + (Get-Date -Format 'yyyy-MM'))
$failed = Join-Path $Folder 'bledy'
$log = Join-Path $Folder 'sad.log'
foreach ($d in @($inbox, $sent, $failed)) { New-Item -ItemType Directory -Force -Path $d | Out-Null }

function Log([string]$msg) {
  $line = '{0:yyyy-MM-dd HH:mm:ss}  {1}' -f (Get-Date), $msg
  Add-Content -Path $log -Value $line -Encoding UTF8
  Write-Output $line
}

# --- 1–2. Outlook → przychodzace ---------------------------------------------------------------
function Save-Attachments {
  $outlook = New-Object -ComObject Outlook.Application
  $folderInbox = $outlook.GetNamespace('MAPI').GetDefaultFolder(6)          # 6 = Skrzynka odbiorcza
  $since = (Get-Date).AddDays(-$Days).ToString('g')                          # format regionalny = format Outlooka
  $items = $folderInbox.Items.Restrict("[ReceivedTime] >= '$since'")
  $saved = 0
  foreach ($mail in @($items)) {
    if ($mail.MessageClass -notlike 'IPM.Note*') { continue }
    if (($mail.Categories -split ',\s*') -contains $Category) { continue }
    $from = [string]$mail.SenderEmailAddress
    if (-not ($Senders | Where-Object { $from.ToLower().EndsWith($_.ToLower()) })) { continue }
    $hits = 0
    foreach ($att in @($mail.Attachments)) {
      $name = [string]$att.FileName
      if ($name -notmatch $NamePattern) { continue }
      $safe = ($name -replace '[\\/:*?"<>|]', '_')
      $target = Join-Path $inbox ('{0:yyyyMMdd-HHmmss}__{1}' -f $mail.ReceivedTime, $safe)
      if (-not (Test-Path $target)) { $att.SaveAsFile($target); $saved++; $hits++ }
    }
    if ($hits -gt 0) {
      $mail.Categories = (@($mail.Categories, $Category) | Where-Object { $_ }) -join ', '
      $mail.Save()
      Log "zapisano $hits zał. z maila „$($mail.Subject)” ($from)"
    }
  }
  return $saved
}

# --- 3. przychodzace → n8n --------------------------------------------------------------------
function Send-Files {
  if (-not $Secret) { Log 'BRAK sekretu webhooka (zmienna SAD_WEBHOOK_SECRET) — pliki czekają w przychodzace'; return }
  foreach ($file in Get-ChildItem -Path $inbox -File) {
    $original = ($file.Name -split '__', 2)[-1]
    $resp = New-TemporaryFile
    # -s bez przekierowania stderr: w PowerShell 5.1 „2>&1” z $ErrorActionPreference=Stop przerywał
    # cały skrypt przy braku serwera; brak połączenia = kod 000 → ponowienie
    $code = & curl.exe -s -m 120 -o $resp.FullName -w '%{http_code}' `
      -H "X-SAD-Secret: $Secret" -F "file=@$($file.FullName);filename=$original" $Url
    $body = (Get-Content -Raw -Path $resp.FullName -ErrorAction SilentlyContinue) -replace '\s+', ' '
    Remove-Item $resp.FullName -Force
    $age = ((Get-Date) - $file.CreationTime).TotalDays
    if ($code -match '^2\d\d$') {
      Move-Item -Force $file.FullName (Join-Path $sent $file.Name)
      Log "OK $code  $original  $body"
    } elseif ($code -eq '401' -or $code -eq '403') {
      Log "SEKRET/TOKEN ($code)  $original — sprawdź SAD_WEBHOOK_SECRET i credentiale w n8n; plik czeka"
    } elseif ($code -eq '409' -and $age -lt $RetryDays) {
      Log "CZEKA 409  $original  $body"
    } elseif ($code -match '^4\d\d$') {
      Move-Item -Force $file.FullName (Join-Path $failed $file.Name)
      Log "BŁĄD $code  $original → bledy\  $body"
    } else {
      Log "PONÓW ($code)  $original — serwer/sieć niedostępne"
    }
  }
}

if (-not $OnlySend) { try {
  $n = Save-Attachments
  if ($n -gt 0) { Log "nowe pliki: $n" }
} catch {
  Log "Outlook: $($_.Exception.Message) — czy Outlook jest uruchomiony i zalogowany?"
} }
if (-not $OnlySave) { Send-Files }
