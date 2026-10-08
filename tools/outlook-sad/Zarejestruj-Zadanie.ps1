<#
.SYNOPSIS
  Rejestruje w Harmonogramie zadań uruchamianie Zbierz-SAD.ps1 co 5 minut (docs/SAD-Z-POCZTY.md).

.DESCRIPTION
  Zadanie działa na Twoim koncie i tylko gdy jesteś zalogowany — Outlook (COM) potrzebuje Twojej
  sesji. Sekret webhooka zapisuje w Twojej zmiennej środowiskowej SAD_WEBHOOK_SECRET (nie w pliku).
  Uruchom raz, w zwykłym PowerShellu (bez „jako administrator”):
    powershell -ExecutionPolicy Bypass -File .\Zarejestruj-Zadanie.ps1 -Secret '<sekret z n8n>'
  Usunięcie: Unregister-ScheduledTask -TaskName 'TIMPORYE SAD z poczty' -Confirm:$false
#>
param(
  [Parameter(Mandatory = $true)][string]$Secret,
  [string]$Folder = 'D:\SAD',
  [string]$Url = 'http://localhost:5678/webhook/sad-inbox',
  [int]$EveryMinutes = 5
)
$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot 'Zbierz-SAD.ps1'
[Environment]::SetEnvironmentVariable('SAD_WEBHOOK_SECRET', $Secret, 'User')
$env:SAD_WEBHOOK_SECRET = $Secret

$taskArgs = "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`" -Folder `"$Folder`" -Url `"$Url`""
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $taskArgs
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
  -RepetitionInterval (New-TimeSpan -Minutes $EveryMinutes)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
  -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive
Register-ScheduledTask -TaskName 'TIMPORYE SAD z poczty' -Action $action -Trigger $trigger `
  -Settings $settings -Principal $principal -Force | Out-Null
Write-Output "Zarejestrowano: co $EveryMinutes min, folder $Folder, cel $Url. Log: $Folder\sad.log"
