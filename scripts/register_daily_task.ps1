<#
  Registers (or updates) the Windows Scheduled Task that runs the daily
  dashboard refresh. Safe to re-run: -Force replaces any existing task.

  Examples:
    powershell -ExecutionPolicy Bypass -File scripts\register_daily_task.ps1
    powershell -ExecutionPolicy Bypass -File scripts\register_daily_task.ps1 -Time 05:00 -Cadence Daily

  Configuration chosen for a laptop:
    * Runs as YOU, only when logged on  -> Credential Manager vault is unlocked
      so Snowflake + GitHub creds are readable.
    * StartWhenAvailable                -> if the PC was off/asleep at the
      scheduled time, it runs as soon as you next log on (never skips a day).
    * Runs on battery                   -> default task settings would block
      that; we explicitly allow it.
#>
param(
    [string]$Time    = '06:30',
    [ValidateSet('Weekdays','Daily')] [string]$Cadence = 'Weekdays',
    [string]$TaskName = 'iFIT Marketing BvA - Daily Refresh'
)

$repo    = Split-Path -Parent $PSScriptRoot
$wrapper = Join-Path $repo 'scripts\daily_refresh.ps1'
if (-not (Test-Path $wrapper)) { throw "Wrapper not found: $wrapper" }

$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$wrapper`"" `
    -WorkingDirectory $repo

$at = [DateTime]::Parse($Time)
if ($Cadence -eq 'Weekdays') {
    $trigger = New-ScheduledTaskTrigger -Weekly -At $at `
        -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday
} else {
    $trigger = New-ScheduledTaskTrigger -Daily -At $at
}

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 10)
# Laptop-friendly: don't refuse / kill the run because of battery power.
$settings.DisallowStartIfOnBatteries = $false
$settings.StopIfGoingOnBatteries     = $false

$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Force `
    -Description "Refreshes the Marketing Budget-vs-Actual dashboard from Snowflake and publishes to Cloudflare. Wrapper: $wrapper" | Out-Null

Write-Output "Registered '$TaskName'  ($Cadence at $Time, run when logged on, catch-up enabled)."
