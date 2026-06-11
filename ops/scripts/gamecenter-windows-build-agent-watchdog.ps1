# Health-check GameCenter build agent every 5 minutes; restart if down.
$ErrorActionPreference = "SilentlyContinue"

$MchatDir = Join-Path $env:USERPROFILE "dev\mchat"
$ConfigPath = Join-Path $MchatDir "ops\scripts\gamecenter-windows-agent.json"
$RunScript = Join-Path $MchatDir "ops\scripts\gamecenter-windows-build-agent-run.ps1"
$LogDir = Join-Path $env:USERPROFILE "dev\gamecenter-agent"
$LogFile = Join-Path $LogDir "watchdog.log"
$Port = 19280

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Log($msg) {
    Add-Content -Path $LogFile -Value ("[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg)
}

if (-not (Test-Path $ConfigPath)) {
    Log "skip: config missing"
    exit 0
}

try {
    $raw = [System.IO.File]::ReadAllText($ConfigPath)
    $cfg = $raw | ConvertFrom-Json
    $token = [string]$cfg.token
    if ($cfg.port) { $Port = [int]$cfg.port }
} catch {
    Log "skip: bad config ($($_.Exception.Message))"
    exit 0
}

$headers = @{}
if ($token) { $headers["Authorization"] = "Bearer $token" }

try {
    $resp = Invoke-RestMethod -Uri "http://127.0.0.1:${Port}/v1/health" -Headers $headers -TimeoutSec 5
    if ($resp.ok) {
        exit 0
    }
    Log "health not ok: $($resp | ConvertTo-Json -Compress)"
} catch {
    Log "health failed: $($_.Exception.Message)"
}

if (-not (Test-Path $RunScript)) {
    Log "cannot restart: run script missing"
    exit 1
}

Log "restarting agent"
try {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $RunScript
    Log "restart invoked"
} catch {
    Log "restart failed: $($_.Exception.Message)"
    exit 1
}
