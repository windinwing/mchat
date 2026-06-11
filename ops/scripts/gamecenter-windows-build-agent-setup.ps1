# GameCenter Windows build agent setup (runs in logged-on user session, NOT Session 0 service)
#
# Usage (Administrator PowerShell):
#   Set-ExecutionPolicy Bypass -Scope Process -Force
#   .\gamecenter-windows-build-agent-setup.ps1

param(
    [string]$MchatDir = "$env:USERPROFILE\dev\mchat",
    [string]$TaskName = "GameCenterBuildAgent",
    [string]$AgentUser = $env:USERNAME,
    [int]$Port = 19280,
    [string]$DeployHost = "10.98.8.15",
    [string]$AllowFromIp = "10.98.8.15"
)

$ErrorActionPreference = "Stop"

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }

$AgentScript = Join-Path $MchatDir "ops\scripts\gamecenter-windows-build-agent.py"
$ConfigExample = Join-Path $MchatDir "ops\scripts\gamecenter-windows-agent.json.example"
$ConfigPath = Join-Path $MchatDir "ops\scripts\gamecenter-windows-agent.json"
$GitBash = "C:\Program Files\Git\bin\bash.exe"
$LogDir = Join-Path $env:USERPROFILE "dev\gamecenter-agent"
$LogFile = Join-Path $LogDir "agent.log"

Write-Step "1/6 Check files"
foreach ($path in @($AgentScript, $ConfigExample, $GitBash)) {
    if (-not (Test-Path $path)) {
        throw "Missing required file: $path"
    }
}
Write-Host "Agent script: $AgentScript"

Write-Step "2/6 Create config"
if (-not (Test-Path $ConfigPath)) {
    $token = [guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N")
    $json = Get-Content $ConfigExample -Raw -Encoding UTF8
    $json = $json.Replace("CHANGE_ME_TO_A_LONG_RANDOM_SECRET", $token)
    $json = $json.Replace("C:/Users/Administrator/dev/mchat", ($MchatDir -replace '\\', '/'))
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($ConfigPath, $json, $utf8NoBom)
    Write-Host "Created: $ConfigPath"
    Write-Host "Copy this token to 10.98.8.15 .env as GAMECENTER_BUILD_AGENT_TOKEN:" -ForegroundColor Yellow
    Write-Host $token
} else {
    Write-Host "Config already exists: $ConfigPath"
    $cfg = Get-Content $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($cfg.token) {
        Write-Host "Existing token:" -ForegroundColor Yellow
        Write-Host $cfg.token
    }
}

Write-Step "3/6 Firewall rule for TCP $Port from $AllowFromIp"
$ruleName = "GameCenter Build Agent $Port"
$existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Firewall rule already exists"
} else {
    New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow `
        -Protocol TCP -LocalPort $Port -RemoteAddress $AllowFromIp | Out-Null
    Write-Host "Allowed inbound: $AllowFromIp -> TCP $Port"
}

Write-Step "4/6 Scheduled task at user logon"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$RunScript = Join-Path $MchatDir "ops\scripts\gamecenter-windows-build-agent-run.ps1"
if (-not (Test-Path $RunScript)) {
    throw "Missing starter script: $RunScript"
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$RunScript`""

$trigger = New-ScheduledTaskTrigger -AtLogOn -User $AgentUser
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -User $AgentUser -Force | Out-Null
Write-Host "Scheduled task: $TaskName (runs when $AgentUser logs on)"

Write-Step "5/6 Watchdog task (every 5 minutes)"
$WatchdogScript = Join-Path $MchatDir "ops\scripts\gamecenter-windows-build-agent-watchdog.ps1"
if (-not (Test-Path $WatchdogScript)) {
    throw "Missing watchdog script: $WatchdogScript"
}
# Use schtasks (Register-ScheduledTask RepetitionDuration is flaky on some Windows builds).
$watchdogTask = "GameCenterBuildAgentWatchdog"
$watchdogCmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$WatchdogScript`""
$prevEap = $ErrorActionPreference
$ErrorActionPreference = "SilentlyContinue"
cmd.exe /c "schtasks /Delete /TN $watchdogTask /F" | Out-Null
$ErrorActionPreference = $prevEap
$schOut = cmd.exe /c "schtasks /Create /TN $watchdogTask /TR `"$watchdogCmd`" /SC MINUTE /MO 5 /RU $AgentUser /IT /F" 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "schtasks create failed: $schOut"
}
Write-Host "Scheduled task: $watchdogTask (every 5 min, /IT user logged on)"

Write-Step "6/6 Start agent now"
Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 3

Write-Host "`n========================================" -ForegroundColor Green
Write-Host "Done. Add to 10.98.8.15 /opt/xiaoxiao/mchat/.env:" -ForegroundColor Green
Write-Host "  GAMECENTER_BUILD_AGENT_URL=http://10.98.8.186:${Port}"
Write-Host "  GAMECENTER_BUILD_AGENT_TOKEN=<token printed above>"
Write-Host ""
Write-Host "Health check:" -ForegroundColor Green
Write-Host "  curl http://127.0.0.1:${Port}/v1/health -H `"Authorization: Bearer <token>`""
Write-Host "Log file: $LogFile"
Write-Host "========================================" -ForegroundColor Green
