<#
.SYNOPSIS
  n8n na komputerze 24/7 (Windows): instalacja i start przy logowaniu (docs/SAD-Z-POCZTY.md).

.DESCRIPTION
  Wymaga Node.js 22 LTS (https://nodejs.org — instalator „LTS”, bez praw administratora wystarczy
  wersja .zip albo instalacja „tylko dla mnie”). n8n słucha tylko na tym komputerze
  (http://localhost:5678) — nikt z sieci się do niego nie dobije; skrypt Outlooka i Ty w
  przeglądarce łączycie się lokalnie. Dane n8n (workflow, zaszyfrowane credentiale): %USERPROFILE%\.n8n
  Uruchom raz, w zwykłym PowerShellu:
    powershell -ExecutionPolicy Bypass -File .\Zainstaluj-n8n.ps1
#>
param([string]$Version = '2.40.2')     # ta sama wersja co docker-compose.n8n.yml
$ErrorActionPreference = 'Stop'

$node = Get-Command node -ErrorAction SilentlyContinue
if (-not $node) { throw 'Brak Node.js — zainstaluj Node.js 22 LTS z https://nodejs.org i uruchom ponownie.' }
$major = [int]((& node --version).TrimStart('v').Split('.')[0])
if ($major -lt 20) { throw "Node.js $(& node --version) jest za stary — n8n wymaga 20 lub 22 LTS." }

Write-Output "Instaluję n8n@$Version (kilka minut)…"
& npm install -g "n8n@$Version"
if ($LASTEXITCODE -ne 0) { throw 'npm install nie powiódł się — sprawdź proxy firmowe (npm config get proxy).' }
$n8n = (Get-Command n8n.cmd -ErrorAction Stop).Source

# start przy logowaniu, tylko localhost, bez telemetrii
$envs = 'set N8N_LISTEN_ADDRESS=127.0.0.1&& set N8N_PORT=5678&& set N8N_HOST=localhost&& ' +
        'set N8N_DIAGNOSTICS_ENABLED=false&& set N8N_RUNNERS_ENABLED=true&& set GENERIC_TIMEZONE=Europe/Warsaw&& '
$action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument "/c $envs`"$n8n`" start"
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero) `
  -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive
Register-ScheduledTask -TaskName 'TIMPORYE n8n' -Action $action -Trigger $trigger -Settings $settings `
  -Principal $principal -Force | Out-Null
Start-ScheduledTask -TaskName 'TIMPORYE n8n'
Write-Output 'n8n uruchomiony — za ~30 s otwórz http://localhost:5678 i załóż konto właściciela.'
