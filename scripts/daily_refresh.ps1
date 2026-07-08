<#
  Daily automated refresh + publish for the Marketing BvA dashboard.

  Chain:  Snowflake  ->  refresh_all.py (writes data\*.json)  ->  git commit+push
          ->  GitHub  ->  Cloudflare Pages auto-rebuild (~1-2 min).

  Registered as a Windows Scheduled Task by scripts\register_daily_task.ps1.
  Reads Snowflake + GitHub credentials from the current user's Windows
  Credential Manager vault (so it must run while you are logged on).

  Every run appends a timestamped log to logs\ ; only data\ is committed, so
  throwaway scripts and local edits are never auto-published.
#>

$repo = Split-Path -Parent $PSScriptRoot          # ...\bva-marketing-dashboard
Set-Location $repo

$logDir = Join-Path $repo 'logs'
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$stamp = Get-Date -Format 'yyyy-MM-dd_HHmmss'
$log   = Join-Path $logDir "refresh_$stamp.log"

function Log($m) { "$(Get-Date -Format 'HH:mm:ss')  $m" | Tee-Object -FilePath $log -Append }

try {
    Log "=== Daily refresh start ($stamp) ==="
    Log "Repo: $repo"

    # 1) Pull fresh data from Snowflake  ->  data\*.json
    Log "Running refresh_all.py ..."
    & python (Join-Path $repo 'scripts\refresh_all.py') *>> $log
    if ($LASTEXITCODE -ne 0) { throw "refresh_all.py exited with code $LASTEXITCODE" }

    # 2) Stage ONLY the data (never the scratch scripts, logs, or local edits)
    & git add data 2>> $log
    $changes = & git status --porcelain data
    if (-not $changes) {
        Log "No data changes since last publish; nothing to push."
    }
    else {
        $msg = "Automated daily data refresh $(Get-Date -Format 'yyyy-MM-dd')"
        & git commit -m $msg *>> $log
        if ($LASTEXITCODE -ne 0) { throw "git commit exited with code $LASTEXITCODE" }
        & git push origin main *>> $log
        if ($LASTEXITCODE -ne 0) { throw "git push exited with code $LASTEXITCODE" }
        Log "Pushed: '$msg'  ->  Cloudflare will rebuild in ~1-2 min."
    }

    Log "=== Daily refresh OK ==="
    # Prune logs older than 30 days so the folder does not grow forever.
    Get-ChildItem $logDir -Filter 'refresh_*.log' |
        Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } |
        Remove-Item -Force -ErrorAction SilentlyContinue
    exit 0
}
catch {
    Log "!! FAILED: $($_.Exception.Message)"
    exit 1
}
