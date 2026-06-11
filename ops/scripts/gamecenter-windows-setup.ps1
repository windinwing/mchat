# GameCenter Windows 编译机初始化（在 10.98.8.186 上以管理员运行 PowerShell）
# 用法: Set-ExecutionPolicy Bypass -Scope Process -Force; .\gamecenter-windows-setup.ps1
#
# 前置：已安装 Cocos Dashboard + Creator 3.8.8（及需要的 2.4.15 项目）

param(
    [string]$MchatDir = "$env:USERPROFILE\dev\mchat",
    [string]$CocosBin = "C:\Program Files\Cocos\Creator\3.8.8\CocosCreator.exe",
    [string]$ServerHost = "10.98.8.15",
    [string]$ServerUser = "xiaoxiao",
    [string]$ServerBuildPubKey = ""
)

$ErrorActionPreference = "Stop"

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }

Write-Step "1/6 安装 OpenSSH Server（若已安装则跳过）"
$cap = Get-WindowsCapability -Online | Where-Object Name -like "OpenSSH.Server*"
if ($cap.State -ne "Installed") {
    Add-WindowsCapability -Online -Name $cap.Name
} else {
    Write-Host "OpenSSH Server 已安装"
}

Start-Service sshd -ErrorAction SilentlyContinue
Set-Service -Name sshd -StartupType Automatic

$fw = Get-NetFirewallRule -Name "OpenSSH-Server-In-TCP" -ErrorAction SilentlyContinue
if (-not $fw) {
    New-NetFirewallRule -Name "OpenSSH-Server-In-TCP" -DisplayName "OpenSSH Server (sshd)" `
        -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 | Out-Null
}
Write-Host "sshd 已设为开机自启，防火墙 22 已放行"

Write-Step "2/6 将 SSH 默认 Shell 设为 Git Bash（远程 build_command 需要 bash）"
$gitBash = "C:\Program Files\Git\bin\bash.exe"
if (-not (Test-Path $gitBash)) {
    Write-Warning "未找到 Git Bash: $gitBash"
    Write-Warning "请先安装 Git for Windows: https://git-scm.com/download/win"
} else {
    if (-not (Test-Path "HKLM:\SOFTWARE\OpenSSH")) {
        New-Item -Path "HKLM:\SOFTWARE\OpenSSH" -Force | Out-Null
    }
    Set-ItemProperty -Path "HKLM:\SOFTWARE\OpenSSH" -Name DefaultShell -Value $gitBash
    Write-Host "DefaultShell = $gitBash"
}

Write-Step "3/6 检查 Git / rsync / Cocos"
$git = Get-Command git -ErrorAction SilentlyContinue
if ($git) { Write-Host "git: $($git.Source)" } else { Write-Warning "未找到 git，请安装 Git for Windows" }

$bash = Get-Command bash -ErrorAction SilentlyContinue
if ($bash) { Write-Host "bash: $($bash.Source)" } else { Write-Warning "未找到 bash" }

# rsync 常在 Git Bash 环境里，用 bash -lc 检测
$rsyncOk = $false
if ($bash) {
    bash -lc "command -v rsync" 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $rsyncOk = $true }
}
if ($rsyncOk) {
    bash -lc "rsync --version | head -1"
} else {
    Write-Warning "Git Bash 中未找到 rsync。推荐: scoop install rsync  或  choco install rsync"
}

if (Test-Path $CocosBin) {
    Write-Host "Cocos: $CocosBin"
} else {
    Write-Warning "Cocos 可执行文件不存在: $CocosBin"
    Write-Warning "请在 Cocos Dashboard 确认 3.8.8 安装路径后修改 gamecenter-local.env"
}

Write-Step "4/6 准备 mchat 目录与 gamecenter-local.env"
New-Item -ItemType Directory -Force -Path (Split-Path $MchatDir) | Out-Null
if (-not (Test-Path "$MchatDir\ops\scripts\gamecenter-local-pipeline.sh")) {
    Write-Warning "未找到 $MchatDir\ops\scripts\ — 请 git clone 或从 Mac rsync mchat 仓库到此路径"
} else {
    Write-Host "mchat: $MchatDir"
}

$envFile = "$MchatDir\ops\scripts\gamecenter-local.env"
if (-not (Test-Path $envFile)) {
    $bashCocos = "/c/Program Files/Cocos/Creator/3.8.8/CocosCreator.exe"
    $bashLocal = "/c/Users/$env:USERNAME/dev/gamecenter-server"
    @"
export GAMECENTER_COCOS_CREATOR_BIN="$bashCocos"
export LOCAL_GAMECENTER="$bashLocal"
export SSH_USER="$ServerUser"
"@ | Set-Content -Encoding UTF8 $envFile
    Write-Host "已生成 $envFile （请核对 Cocos 路径）"
} else {
    Write-Host "已存在 $envFile"
}

Write-Step "5/6 SSH 密钥：本机 -> $ServerHost（拉推源码）"
$sshDir = "$env:USERPROFILE\.ssh"
New-Item -ItemType Directory -Force -Path $sshDir | Out-Null
$key = "$sshDir\id_ed25519"
if (-not (Test-Path $key)) {
    ssh-keygen -t ed25519 -f $key -N '""' -q
    Write-Host "已生成 $key"
}
Write-Host "`n本机公钥（需追加到服务器 $ServerUser@${ServerHost}:~/.ssh/authorized_keys）："
Get-Content "$key.pub"

Write-Step "6/6 允许 $ServerHost 免密 SSH 登录本机（编译触发）"
$authKeys = "$sshDir\authorized_keys"
New-Item -ItemType Directory -Force -Path $sshDir | Out-Null
if (-not $ServerBuildPubKey) {
    $ServerBuildPubKey = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBradoTuD5p+mytbW0j+pqDTGhIKPjHUctR56Dv6pG1A xiaoxiao@xiaoyi-svr1"
}
$line = $ServerBuildPubKey.Trim()
if (Test-Path $authKeys) {
    $existing = Get-Content $authKeys -Raw
    if ($existing -notmatch [regex]::Escape($line.Substring(0, [Math]::Min(40, $line.Length)))) {
        Add-Content -Path $authKeys -Value $line
        Write-Host "已追加服务器公钥到 $authKeys"
    } else {
        Write-Host "服务器公钥已在 authorized_keys 中"
    }
} else {
    Set-Content -Path $authKeys -Value $line -Encoding UTF8
    Write-Host "已创建 $authKeys"
}

# Windows OpenSSH 权限（非管理员用户）
icacls $authKeys /inheritance:r /grant "SYSTEM:(F)" "$($env:USERNAME):(F)" | Out-Null

Write-Host "`n========================================" -ForegroundColor Green
Write-Host "下一步（在 Git Bash 中执行）：" -ForegroundColor Green
Write-Host "  cd /c/Users/$env:USERNAME/dev/mchat"
Write-Host "  ssh-copy-id $ServerUser@$ServerHost   # 或手动粘贴公钥"
Write-Host "  ssh $ServerUser@$ServerHost 'echo ok'"
Write-Host "  ./ops/scripts/gamecenter-local-pipeline.sh $ServerHost pkg0002-3-x-3-8-3ts --force"
Write-Host ""
Write-Host "告知 Mac 端配置服务器 .env：" -ForegroundColor Green
Write-Host "  GAMECENTER_BUILD_SSH_HOST=10.98.8.186"
Write-Host "  GAMECENTER_BUILD_SSH_USER=$env:USERNAME"
Write-Host "  GAMECENTER_BUILD_PIPELINE_SCRIPT=/c/Users/$env:USERNAME/dev/mchat/ops/scripts/gamecenter-local-pipeline.sh"
Write-Host "========================================" -ForegroundColor Green
