# Start GameCenter build agent (detached). Used by logon scheduled task.
$ErrorActionPreference = "Stop"

$LogDir = Join-Path $env:USERPROFILE "dev\gamecenter-agent"
$LogFile = Join-Path $LogDir "agent.log"
$PidFile = Join-Path $LogDir "agent.pid"
$StartBat = Join-Path $env:USERPROFILE "dev\mchat\ops\scripts\gamecenter-windows-build-agent-start.bat"

if (-not (Test-Path $StartBat)) {
    throw "Missing: $StartBat"
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# Already running?
if (Test-Path $PidFile) {
    $oldPid = [int](Get-Content $PidFile -ErrorAction SilentlyContinue)
    if ($oldPid -gt 0) {
        $old = Get-Process -Id $oldPid -ErrorAction SilentlyContinue
        if ($old -and $old.ProcessName -match '^(py|python|pythonw)$') {
            Add-Content $LogFile "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] agent already running pid=$oldPid"
            exit 0
        }
    }
}

# Port already in use?
$portUp = netstat -an | Select-String "LISTENING" | Select-String ":19280 "
if ($portUp) {
    Add-Content $LogFile "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] port 19280 already listening"
    exit 0
}

Add-Content $LogFile "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] launching agent via start.bat"

$proc = Start-Process -FilePath "cmd.exe" `
    -ArgumentList "/c", "`"$StartBat`"" `
    -WorkingDirectory (Split-Path $StartBat) `
    -WindowStyle Hidden `
    -PassThru

Set-Content -Path $PidFile -Value $proc.Id -Encoding ASCII
Add-Content $LogFile "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] wrapper pid=$($proc.Id)"

Start-Sleep -Seconds 2
$listen = netstat -an | Select-String "LISTENING" | Select-String ":19280 "
if (-not $listen) {
    Add-Content $LogFile "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] ERROR: port 19280 not listening after start"
    if (Test-Path (Join-Path $LogDir "agent.err.log")) {
        Get-Content (Join-Path $LogDir "agent.err.log") -Tail 10 | ForEach-Object { Add-Content $LogFile $_ }
    }
    exit 1
}

Add-Content $LogFile "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] agent OK on :19280"
